# Desplegar el dashboard en Streamlit Community Cloud

El dashboard (`dashboard.py`) incluye una pestaña **Asistente** con el agente MCP
embebido en el mismo proceso, por lo que un único deploy de Streamlit ofrece los
gráficos BI y el chat conversacional sobre los mismos datos de Supabase.

## 1. Requisitos previos

- El repositorio debe ser **público** en GitHub (Community Cloud solo despliega repos públicos).
- Los datos ya cargados en Supabase (`python data/import_dataset_to_postgres.py`).

## 2. Crear el app

En https://share.streamlit.io → **Create app**:

| Campo | Valor |
|---|---|
| Repository | `AlfredoSuarez/bsg_arq_strm` |
| Branch | `main` |
| **Main file path** | `dashboard.py` |

> Usa `dashboard.py`, no `app_streamlit.py`. El primero integra dashboard + asistente
> en un solo proceso; el segundo es el cliente MCP del laboratorio local (necesita los
> servidores MCP corriendo por separado).

## 3. Configurar los Secrets

En **Settings → Secrets**, pega (formato TOML):

```toml
DATABASE_URL = "postgresql://postgres.<ref>:<password>@aws-1-<region>.pooler.supabase.com:6543/postgres"
OPENROUTER_API_KEY = "sk-or-..."
# Opcional (por defecto usa el modelo gratuito del proyecto):
# OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
```

Notas importantes:

- **No necesitas `DB_BACKEND`**: si defines `DATABASE_URL`, la app usa Supabase
  automáticamente (ver `db.py`). Así se evita el conflicto típico de caer a SQLite,
  que no existe en la nube.
- Usa el **connection pooler** de Supabase (**puerto 6543**), no la conexión directa:
  Streamlit abre muchas conexiones. Copia la cadena exacta desde
  **Supabase → Project Settings → Database → Connection pooling** (modo *Transaction*).
- `OPENROUTER_API_KEY` solo es necesaria para la pestaña Asistente. Sin ella, el
  dashboard funciona igual y el asistente muestra un aviso.

## 4. Hacerlo público (si quieres acceso abierto)

Si al abrir el link te pide iniciar sesión, el app está restringido. En
**Settings → Sharing → "Who can view this app" → Public** para abrirlo a cualquiera.

## 5. Cómo funciona el asistente embebido

- La pestaña **Asistente** levanta `mcp_datos.py` como **subproceso HTTP local**
  (`127.0.0.1:8000`) una sola vez (`st.cache_resource`), heredando el entorno
  (por lo tanto consulta el mismo Supabase).
- `agent_core.resolver_consulta` corre **in-process** y descubre las 7 tools del MCP.
- No requiere `mcp_agente.py` ni puertos externos: todo vive en el proceso de Streamlit.

## Verificación rápida

Tras el deploy, en la pestaña Resumen deberías ver KPIs reales
(revenue ~ $11.3M, 30.000 órdenes). Si ves un error de datos, revisa que
`DATABASE_URL` (pooler) esté bien en Secrets.
