"""
MCP del agente de e-commerce
----------------------------
Publica una tool de alto nivel: resolver_consulta_ecommerce.

La tool contiene la composición:
Cliente MCP -> agente LangChain -> tools del MCP de datos -> SQLite.

Modos:
  python mcp_agente.py
      inicia por STDIO: recomendado para Claude Desktop.

  MCP_AGENT_TRANSPORT=http python mcp_agente.py
      inicia HTTP en http://127.0.0.1:8001/mcp: recomendado para Streamlit.
"""
from __future__ import annotations
import os
from dotenv import load_dotenv
from fastmcp import FastMCP
from agent_core import resolver_consulta

load_dotenv()

mcp = FastMCP(
    name="Ecommerce Analyst Agent MCP",
    instructions=(
        "Este servidor expone un agente analista de e-commerce. "
        "Puede consultar datos de clientes, consumo, compras, experiencia y ventas."
    ),
)

@mcp.tool()
async def resolver_consulta_ecommerce(
    mensaje: str,
    session_id: str = "claude-desktop-demo",
    canal: str = "claude-desktop",
) -> dict:
    """
    Resuelve una consulta de e-commerce usando un agente LangChain con herramientas MCP.

    Usa session_id estable para conservar la memoria de corto plazo entre turnos.
    Ejemplo de secuencia:
    1. "Busca clientes Premium."
    2. "Analiza al de mayor consumo y dime sus categorías preferidas."
    """
    return await resolver_consulta(mensaje, session_id=session_id, canal=canal)

if __name__ == "__main__":
    transport = os.getenv("MCP_AGENT_TRANSPORT", "stdio").lower()
    if transport == "http":
        mcp.run(transport="http", host="127.0.0.1", port=8001)
    else:
        mcp.run()
