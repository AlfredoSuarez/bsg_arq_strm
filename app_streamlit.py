"""
Cliente Streamlit del MCP del agente.

Esta aplicación NO contiene el LLM ni las consultas SQL.
Es un cliente que consume mcp_agente.py por HTTP y hace visible:
- el chat;
- la session_id;
- la memoria de corto plazo;
- las herramientas invocadas.
"""
from __future__ import annotations
import asyncio
import os
import uuid
import streamlit as st
from dotenv import load_dotenv
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()
AGENT_MCP_URL = os.getenv("AGENT_MCP_URL", "http://127.0.0.1:8001/mcp")

st.set_page_config(page_title="E-commerce Agent MCP", page_icon="🛒", layout="wide")
st.title("🛒 Agente e-commerce: Streamlit como cliente MCP")
st.caption("La UI consume el MCP del agente; el agente consume el MCP de datos.")

if "session_id" not in st.session_state:
    st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_result" not in st.session_state:
    st.session_state.last_result = None

async def llamar_agente(mensaje: str) -> dict:
    client = MultiServerMCPClient(
        {"agente": {"transport": "http", "url": AGENT_MCP_URL}}
    )
    tools = await client.get_tools()
    tool_by_name = {tool.name: tool for tool in tools}
    tool = tool_by_name["resolver_consulta_ecommerce"]
    return await tool.ainvoke({
        "mensaje": mensaje,
        "session_id": st.session_state.session_id,
        "canal": "streamlit",
    })

with st.sidebar:
    st.header("Sesión y memoria")
    st.code(st.session_state.session_id)
    st.write("La misma `session_id` mantiene la conversación dentro del proceso del agente.")
    if st.button("Nueva conversación"):
        st.session_state.session_id = f"streamlit-{uuid.uuid4().hex[:10]}"
        st.session_state.messages = []
        st.session_state.last_result = None
        st.rerun()
    st.divider()
    st.write("Servidor esperado:")
    st.code(AGENT_MCP_URL)

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ej.: Busca clientes Premium y analiza al de mayor gasto.")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("El cliente MCP consulta al agente..."):
            try:
                result = asyncio.run(llamar_agente(prompt))
                answer = result["respuesta"]
                st.markdown(answer)
                st.session_state.last_result = result
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as exc:
                st.error(f"No fue posible consultar el agente: {exc}")
                st.info(
                    "Verifica que estén activos mcp_datos.py (puerto 8000) "
                    "y mcp_agente.py en modo HTTP (puerto 8001)."
                )

if st.session_state.last_result:
    result = st.session_state.last_result
    left, right = st.columns(2)
    with left:
        st.subheader("Memoria de corto plazo")
        st.json(result["memoria"])
        st.caption(
            "Al cambiar la sesión se parte con memoria vacía. "
            "Al reiniciar mcp_agente.py, todas las memorias en RAM se eliminan."
        )
    with right:
        st.subheader("Traza de orquestación")
        st.json(result["traza"])
