# Progresión: del notebook Colab al proyecto Python

El notebook anterior fue el primer entorno para aprender el patrón: SQLite + FastMCP + tools SQL + agente LangChain + Gemini API. Esta versión conserva el stack, pero formaliza responsabilidades y reemplaza los datos simulados por un dataset real de e-commerce.

```text
Colab: experimentación en una sesión
CSV real → SQLite → tools MCP → agente → respuesta

Proyecto Python: componentes reutilizables
CSV real → script de importación → SQLite → MCP de datos
                                      ↓
                           agente LangChain + memoria
                                      ↓
                         MCP del agente → Streamlit / Claude Desktop
```

El objetivo del cambio no es complejizar por complejizar. Es evitar que interfaz, datos, agente y protocolo queden mezclados en una sola notebook. Así se puede modificar el frontend o agregar otro cliente sin duplicar la lógica de decisión.
