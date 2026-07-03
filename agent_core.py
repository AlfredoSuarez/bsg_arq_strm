"""
Núcleo reutilizable del agente.

Este módulo contiene el avance de Clase 3:
- agente LangChain con un modelo servido por OpenRouter;
- tools descubiertas desde mcp_datos.py;
- memoria de corto plazo por conversación;
- ventana de mensajes para limitar el contexto;
- trazabilidad de llamadas a tools.

No contiene Streamlit ni configuración de Claude Desktop. Eso permite reutilizar
la misma lógica desde diferentes clientes.
"""
from __future__ import annotations

import os
from collections.abc import Iterable

from dotenv import load_dotenv
from langchain.agents import AgentState, create_agent
from langchain.agents.middleware import before_model
from langchain.messages import AIMessage, RemoveMessage, ToolMessage
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES
from langgraph.runtime import Runtime

load_dotenv()

MODEL_NAME = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DATA_MCP_URL = os.getenv("DATA_MCP_URL", "http://127.0.0.1:8000/mcp")
WINDOW_MESSAGES = int(os.getenv("MEMORY_WINDOW_MESSAGES", "8"))

SYSTEM_PROMPT = """
Eres un analista de e-commerce y respondes en español claro.

REGLAS:
1. Para toda afirmación factual sobre clientes, compras, productos, experiencia o ventas,
   usa las tools MCP antes de responder.
2. Nunca inventes cifras, clientes, fechas ni resultados.
3. Si el usuario se refiere a "ese cliente", "él", "ella" o "la empresa anterior",
   revisa la conversación reciente: esa es la razón de usar memoria de corto plazo.
4. Si no tienes un Customer_ID inequívoco, usa buscar_clientes y explica cualquier ambigüedad.
5. Las tools son de solo lectura: nunca digas que modificaste la base.
6. Estructura las respuestas de análisis con Hallazgos, Evidencia y Recomendación.
7. Sé transparente: cuando los datos sean insuficientes, indícalo.
"""

# Persistencia EN MEMORIA DEL PROCESO: sirve para una clase y un prototipo local.
# Al reiniciar el proceso, las conversaciones se pierden.
CHECKPOINTER = InMemorySaver()


@before_model
def ventana_contexto(state: AgentState, runtime: Runtime):
    """Aplica una ventana pedagógica de memoria antes de cada llamada al modelo."""
    messages = state["messages"]
    if len(messages) <= WINDOW_MESSAGES:
        return None

    first_message = messages[0]
    recent_messages = messages[-WINDOW_MESSAGES:]
    # Reduce el riesgo de cortar una secuencia de tool calls justo antes de un resultado.
    if isinstance(recent_messages[0], ToolMessage) and len(messages) > WINDOW_MESSAGES + 1:
        recent_messages = messages[-(WINDOW_MESSAGES + 1):]

    return {
        "messages": [
            RemoveMessage(id=REMOVE_ALL_MESSAGES),
            first_message,
            *recent_messages,
        ]
    }


def _crear_modelo() -> ChatOpenAI:
    """Configura el adaptador OpenAI-compatible apuntando a OpenRouter."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Falta OPENROUTER_API_KEY. Crea una clave en OpenRouter y agrégala al archivo .env."
        )

    headers = {
        "HTTP-Referer": os.getenv("OPENROUTER_APP_URL", "http://localhost:8501"),
        "X-OpenRouter-Title": os.getenv("OPENROUTER_APP_NAME", "Clase 3 - Agente MCP E-commerce"),
    }

    return ChatOpenAI(
        model=MODEL_NAME,
        api_key=api_key,
        base_url=OPENROUTER_BASE_URL,
        temperature=0,
        default_headers=headers,
    )


async def construir_agente():
    """Descubre las tools remotas del MCP de datos y arma el agente LangChain."""
    client = MultiServerMCPClient(
        {"ecommerce": {"transport": "http", "url": DATA_MCP_URL}}
    )
    tools = await client.get_tools()

    agent = create_agent(
        model=_crear_modelo(),
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=CHECKPOINTER,
        middleware=[ventana_contexto],
    )
    return agent


def _texto_final(messages: list) -> str:
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            return str(message.content)
    return "El agente no generó una respuesta final."


def _traza(messages: Iterable) -> list[dict]:
    trace: list[dict] = []
    for message in messages:
        if isinstance(message, AIMessage) and message.tool_calls:
            for call in message.tool_calls:
                trace.append({
                    "tipo": "tool_call",
                    "tool": call.get("name"),
                    "argumentos": call.get("args", {}),
                })
        if isinstance(message, ToolMessage):
            content = str(message.content)
            trace.append({
                "tipo": "tool_result",
                "tool_call_id": message.tool_call_id,
                "resultado_previo": content[:500] + ("..." if len(content) > 500 else ""),
            })
    return trace


async def resolver_consulta(
    mensaje: str,
    session_id: str,
    canal: str = "web",
) -> dict:
    """Ejecuta una interacción completa y vincula turnos mediante session_id."""
    agent = await construir_agente()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": mensaje}]},
        {"configurable": {"thread_id": session_id, "canal": canal}},
    )

    messages = result["messages"]
    user_visible = [
        {
            "rol": "usuario" if getattr(m, "type", "") == "human" else "asistente",
            "contenido": str(m.content)[:600],
        }
        for m in messages
        if getattr(m, "type", "") in {"human", "ai"} and not getattr(m, "tool_calls", None)
    ]

    return {
        "respuesta": _texto_final(messages),
        "session_id": session_id,
        "canal": canal,
        "modelo": MODEL_NAME,
        "proveedor": "OpenRouter",
        "memoria": {
            "tipo": "corto_plazo_en_memoria",
            "window_messages": WINDOW_MESSAGES,
            "mensajes_estado": len(messages),
            "nota": "La conversación persiste solo mientras el proceso esté activo.",
        },
        "traza": _traza(messages),
        "historial_visible": user_visible[-WINDOW_MESSAGES:],
    }
