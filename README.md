# Clase 3 — Agente MCP con memoria y OpenRouter sobre datos reales de e-commerce

## Propósito

Este proyecto continúa el laboratorio realizado en Colab. Conserva la misma lógica: un agente LangChain descubre tools de un servidor MCP, y cada tool encapsula una consulta SQL explícita, parametrizada y revisable. El cambio de esta versión es el proveedor del modelo: el agente usa OpenRouter y, por defecto, el modelo `nvidia/nemotron-3-ultra-550b-a55b:free`.

La meta no es enseñar un chatbot aislado. Se enseña una arquitectura de integración compuesta:

```text
CSV real → SQLite → MCP de datos → agente LangChain con memoria → MCP del agente → Streamlit / Claude Desktop
```

El proyecto permite trabajar cinco ideas en una misma experiencia:

1. Convertir un CSV real en una base SQLite reproducible.
2. Publicar capacidades analíticas personalizadas como tools MCP.
3. Crear un agente LangChain que decide qué tool usar.
4. Incorporar memoria de corto plazo mediante una ventana de contexto y `session_id`.
5. Empaquetar el agente como un MCP reutilizable, consumible desde Streamlit o Claude Desktop.

## Arquitectura

```text
                           ┌────────────────────────────┐
                           │       Claude Desktop       │
                           │    Host MCP externo        │
                           └──────────────┬─────────────┘
                                          │ stdio
                                          ▼
┌──────────────────────┐      ┌────────────────────────────┐
│  app_streamlit.py    │ HTTP │      mcp_agente.py         │
│  cliente MCP propio  │─────▶│ MCP que publica el agente  │
│ chat + memoria +     │      │ resolver_consulta_ecommerce│
│ traza visible        │      └──────────────┬─────────────┘
└──────────────────────┘                     │
                                               ▼
                                    ┌──────────────────────┐
                                    │     agent_core.py    │
                                    │ LangChain +          │
                                    │ OpenRouter + memoria │
                                    └──────────┬───────────┘
                                               │ cliente MCP HTTP
                                               ▼
                                    ┌──────────────────────┐
                                    │    mcp_datos.py      │
                                    │ tools SQL de lectura │
                                    └──────────┬───────────┘
                                               ▼
                              SQLite: ecommerce_orders.db
                                               ▲
                                               │ importación reproducible
                       ecommerce_orders_dataset.csv (dataset real)
```

Streamlit no contiene la lógica del agente. Claude Desktop tampoco. Ambos consumen la misma tool pública expuesta por `mcp_agente.py`. El agente, a su vez, utiliza el MCP de datos sin que esos clientes conozcan las queries SQL internas.

## Qué significa usar OpenRouter aquí

OpenRouter ofrece una API unificada y compatible con el formato de OpenAI. Por ello el proyecto utiliza `ChatOpenAI` de LangChain, pero lo apunta al endpoint de OpenRouter:

```python
ChatOpenAI(
    model="nvidia/nemotron-3-ultra-550b-a55b:free",
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)
```

`ChatOpenAI` es el adaptador del protocolo compatible; no implica que el modelo sea de OpenAI. El modelo efectivo se decide mediante `OPENROUTER_MODEL`.

### Sobre el acceso gratuito

Esta versión queda configurada con el slug solicitado: `nvidia/nemotron-3-ultra-550b-a55b:free`. El sufijo `:free` identifica la variante gratuita publicada por OpenRouter al momento de configurar el laboratorio. Sin embargo, los modelos gratuitos pueden tener cuotas, límites de velocidad, proveedores variables o cambios de disponibilidad. Antes de una clase, revisa el catálogo y los límites vigentes de OpenRouter.

## Crear una API key personal en OpenRouter

No se debe compartir una clave del docente ni incluir una clave en el repositorio. Cada estudiante debe usar una clave propia.

1. Crear o iniciar sesión en OpenRouter.
2. Abrir el panel de **Keys / API Keys**.
3. Elegir **Create API Key**.
4. Asignar un nombre identificable, por ejemplo `clase-mcp-ecommerce`.
5. De forma opcional, establecer un límite de créditos o permisos adecuados para un entorno de aprendizaje.
6. Copiar la clave una sola vez y pegarla únicamente en el archivo local `.env`.
7. Nunca subir `.env`, capturas de la clave ni el archivo de configuración de Claude Desktop con una clave real a GitHub.

OpenRouter autentica con un token Bearer y recomienda mantener la clave fuera del código fuente. Si una clave se filtra, debe revocarse y reemplazarse de inmediato.

## Progresión: de Colab a Python

| En el notebook anterior | En este proyecto |
|---|---|
| CSV o datos cargados en la sesión | CSV real incluido en `data/` |
| SQLite preparado en una celda | `import_dataset_to_sqlite.py` reproducible |
| MCP con queries SQL | `mcp_datos.py` con siete tools de negocio |
| Agente LangChain ejecutado en notebook | `agent_core.py` desacoplado de la interfaz |
| Consulta aislada | Conversación con `session_id` y memoria temporal |
| Un solo consumidor | Streamlit y Claude Desktop |
| Proveedor de modelo fijo | Modelo configurable desde OpenRouter |

La regla de diseño no cambia: el LLM no escribe SQL libre. Selecciona tools específicas; cada tool usa SQL parametrizado y de solo lectura.

## Dataset real

`data/ecommerce_orders_dataset.csv` contiene 30.000 órdenes, 8.683 clientes y 41 variables sobre ventas, productos, logística, comportamiento, devoluciones y rentabilidad. Incluye campos como:

```text
Order_ID, Customer_ID, Order_Date, Country, City, Customer_Segment,
Product_Category, Product_Subcategory, Brand, Quantity, Order_Amount,
Traffic_Source, Device_Type, Membership_Status, Shipping_Method,
Delivery_Days, Order_Status, Returned, Review_Rating,
Customer_Lifetime_Value, Profit_Amount, Season
```

Los datos se usan solo como base técnica de aprendizaje; no deben interpretarse como evidencia comercial real.

### Importar el CSV a SQLite

```bash
python data/import_dataset_to_sqlite.py
```

El script valida las columnas, normaliza `Order_Date`, crea `data/ecommerce_orders.db`, importa la tabla `orders` y agrega índices para consultas frecuentes. El `.db` no se sube a Git porque puede regenerarse desde el CSV.

### Backend de datos conmutable: SQLite o Supabase

La capa de acceso a datos (`db.py`) permite elegir el motor con la variable de entorno `DB_BACKEND`, sin tocar las tools de negocio:

| `DB_BACKEND` | Motor | Uso |
|---|---|---|
| `sqlite` (por defecto) | `data/ecommerce_orders.db` | Laboratorio local, offline, cero configuración |
| `supabase` | Postgres gestionado (Supabase) | Portal en la nube, multiusuario, base para pgvector |

Las tools escriben el SQL una sola vez con marcadores `?`; `db.py` los adapta a cada motor. Para cargar el dataset completo en Supabase:

```bash
# .env con DB_BACKEND=supabase y DATABASE_URL de Supabase
python data/import_dataset_to_postgres.py   # COPY de las 30.000 órdenes
DB_BACKEND=supabase python mcp_datos.py     # el MCP de datos ahora consulta Postgres
```

La guía completa (esquema, `DATABASE_URL`, pooler, RLS y pgvector) está en [docs/BACKEND_SUPABASE.md](docs/BACKEND_SUPABASE.md).

## Tools personalizadas del MCP de datos

| Tool | Capacidad de negocio | Columnas principales |
|---|---|---|
| `buscar_clientes` | Encuentra clientes por ID, ubicación, segmento o membresía | `Customer_ID`, `Country`, `City`, `Customer_Segment` |
| `resumen_cliente` | Resume gasto, utilidad, ticket, actividad y CLV | `Order_Amount`, `Profit_Amount`, `Customer_Lifetime_Value` |
| `perfil_compras_cliente` | Muestra categorías y subcategorías preferidas | `Product_Category`, `Product_Subcategory`, `Discount_Percent` |
| `experiencia_cliente` | Evalúa devoluciones, rating, despacho y estados de orden | `Returned`, `Review_Rating`, `Delivery_Days`, `Order_Status` |
| `ventas_por_dimension` | Compara facturación y utilidad por país, categoría, segmento o canal | `Country`, `Product_Category`, `Traffic_Source`, `Profit_Amount` |
| `tendencia_ventas` | Analiza ventas mensuales, utilidad, ticket y devoluciones | `Year`, `Month`, `Order_Amount`, `Profit_Amount` |
| `detalle_orden` | Recupera el detalle de una orden específica | `Order_ID` y atributos de la transacción |

No existe una tool genérica como `ejecutar_sql(sql)`. Esa decisión protege la base, vuelve visible la lógica de negocio y facilita que el LLM elija la herramienta correcta.

## Dashboard BI

`dashboard.py` es un dashboard analítico (Streamlit + Plotly) que lee de la misma capa `db.py`, por lo que funciona igual contra SQLite o Supabase según `DB_BACKEND`.

```bash
# Local con SQLite
streamlit run dashboard.py
# Contra Supabase
DB_BACKEND=supabase streamlit run dashboard.py
```

Reutiliza el patrón visual del caso de referencia (tabs, tarjetas, heatmaps device × género) pero enfocado en **ventas, rentabilidad y geografía**. Cinco pestañas:

| Pestaña | Contenido |
|---|---|
| Resumen ejecutivo | KPIs (revenue, profit, margen, AOV, devoluciones, rating); revenue por categoría, país y segmento |
| Tendencia temporal | Revenue y profit mensuales; órdenes y ticket promedio |
| Segmentación | Distribución y heatmaps device × género (revenue, margen, ticket, devolución); canales y pagos |
| Insights & Acciones | Top/bottom segmentos; scatter revenue-vs-margen por categoría; lectura rápida |
| 🤖 Asistente | Agente MCP conversacional **embebido en el mismo proceso** (in-process) sobre los mismos datos |

Incluye filtros por año y país, y un **toggle de idioma Español / English** en la barra lateral que traduce toda la interfaz y hace que el asistente responda en el idioma elegido. La pestaña Asistente levanta `mcp_datos.py` como subproceso local y corre el agente in-process, así que un solo deploy de Streamlit ofrece dashboard + chat. Guía de despliegue: [docs/DEPLOY_STREAMLIT.md](docs/DEPLOY_STREAMLIT.md).

> **Selección de backend (importante para desplegar):** basta definir `DATABASE_URL` (secret) para que la app use Supabase automáticamente; no hace falta `DB_BACKEND`. Esto evita el fallo de caer a SQLite en la nube (donde no existe el `.db`).

## Requisitos

- Python 3.11 o superior recomendado.
- Cuenta OpenRouter y una API key personal.
- Claude Desktop solo para la demostración de consumo externo.
- Puertos locales 8000 y 8001 disponibles.

## Instalación

### 1. Crear entorno virtual

macOS / Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Crear el archivo `.env`

macOS / Linux:

```bash
cp .env.example .env
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Edita `.env` con tu clave personal:

```env
OPENROUTER_API_KEY=tu_clave_personal
OPENROUTER_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
OPENROUTER_APP_URL=http://localhost:8501
OPENROUTER_APP_NAME=Clase 3 - Agente MCP E-commerce
DATA_MCP_URL=http://127.0.0.1:8000/mcp
AGENT_MCP_URL=http://127.0.0.1:8001/mcp
MEMORY_WINDOW_MESSAGES=8
```

### 4. Importar la base real

```bash
python data/import_dataset_to_sqlite.py
```

### 5. Verificar el entorno

```bash
python scripts/check_environment.py
```

## Ejecutar con Streamlit

Abre tres terminales en la carpeta del proyecto, todas con el entorno virtual activo.

Terminal 1, MCP de datos:

```bash
python mcp_datos.py
```

Terminal 2, MCP del agente por HTTP.

macOS / Linux:

```bash
MCP_AGENT_TRANSPORT=http python mcp_agente.py
```

Windows PowerShell:

```powershell
$env:MCP_AGENT_TRANSPORT="http"
python mcp_agente.py
```

Terminal 3, cliente Streamlit:

```bash
streamlit run app_streamlit.py
```

La interfaz muestra el chat, `session_id`, tamaño de la ventana de memoria y la traza de tools. Esto permite observar que el frontend no contiene las consultas: actúa como cliente MCP del agente.

### Preguntas sugeridas

```text
Busca clientes Premium y dime cuál tiene mayor facturación.
```

```text
Ahora analiza sus categorías preferidas y su experiencia de compra.
```

```text
Compara las ventas por categoría durante 2025.
```

```text
Analiza la tendencia mensual de ventas de Germany en 2025.
```

```text
Revisa el detalle de la orden 615717.
```

La segunda pregunta prueba la memoria: “sus” debe referirse al cliente encontrado en el turno anterior. Presiona “Nueva conversación” para comprobar que un `session_id` nuevo no hereda contexto.

## Ejecutar desde Claude Desktop

Claude Desktop actúa como host MCP e inicia `mcp_agente.py` mediante `stdio`. El MCP de datos debe seguir activo por HTTP.

1. Mantén en ejecución `python mcp_datos.py`.
2. Abre `config/claude_desktop_config.example.json`.
3. Sustituye la ruta de ejemplo por la ruta absoluta real de `mcp_agente.py`.
4. Agrega tu API key por un mecanismo seguro. Para un laboratorio local puede estar en el bloque `env`; no lo subas a Git.
5. Reinicia Claude Desktop.

Claude Desktop descubrirá una sola capacidad pública:

```text
resolver_consulta_ecommerce(mensaje, session_id, canal)
```

Claude no consulta tablas ni ejecuta SQL directamente. Consume un servicio agentivo que internamente combina OpenRouter, LangChain, memoria y herramientas del MCP de datos.

## Memoria de corto plazo

`agent_core.py` combina tres piezas:

```python
CHECKPOINTER = InMemorySaver()
```

Guarda el estado de la conversación mientras el proceso permanece encendido.

```python
{"configurable": {"thread_id": session_id}}
```

Asocia los turnos a una conversación específica. En el proyecto, `session_id` se traduce al `thread_id` de LangGraph.

```python
@before_model
def ventana_contexto(...):
```

Reduce el historial que recibe el modelo, conservando el primer mensaje y los últimos `MEMORY_WINDOW_MESSAGES`. Es el equivalente conceptual de `ConversationBufferWindowMemory(k=...)`, implementado con el enfoque actual de estado + checkpointer en LangChain/LangGraph.

La memoria no es conocimiento permanente. Se elimina al reiniciar `mcp_agente.py`. En producción se requeriría un checkpointer persistente compartido, más autenticación, autorización, límites de tasa, observabilidad y control de costos.

## Responsabilidad de cada archivo

| Archivo | Rol |
|---|---|
| `data/ecommerce_orders_dataset.csv` | Fuente real del laboratorio. |
| `data/import_dataset_to_sqlite.py` | Conversión reproducible CSV → SQLite. |
| `mcp_datos.py` | Servidor MCP de tools SQL de solo lectura. |
| `agent_core.py` | Agente LangChain + OpenRouter, memoria y trazabilidad. |
| `mcp_agente.py` | Servidor MCP que empaqueta al agente. |
| `app_streamlit.py` | Cliente MCP y visualizador del proceso. |
| `config/claude_desktop_config.example.json` | Plantilla para Claude Desktop. |
| `docs/CAMBIO_A_OPENROUTER.md` | Explica el reemplazo de Gemini por OpenRouter. |

## Diagnóstico de errores comunes

| Síntoma | Causa probable | Acción |
|---|---|---|
| `Falta OPENROUTER_API_KEY` | `.env` no existe o no tiene la clave | Copia `.env.example` a `.env` y agrega tu clave. |
| Error 401 | La clave es inválida o fue revocada | Crea una clave nueva y reemplázala en `.env`. |
| Error de cuota o disponibilidad | El modelo gratuito no está disponible o superó límites | Revisa OpenRouter; espera el restablecimiento o usa otro slug permitido. |
| Streamlit no responde | Uno de los dos MCP no está activo | Levanta primero `mcp_datos.py` y luego el agente HTTP. |
| El agente no recuerda el turno anterior | Cambiaste `session_id` o reiniciaste el agente | Mantén la misma sesión y proceso activos. |
| Claude no ve la tool | Ruta/configuración incorrecta | Revisa el JSON y reinicia Claude Desktop. |

## Límites y extensiones

Esta versión funciona en laboratorio local (SQLite) y también contra una base administrada en la nube (Supabase/Postgres) mediante `DB_BACKEND`; ver [docs/BACKEND_SUPABASE.md](docs/BACKEND_SUPABASE.md). Para un despliegue productivo completo aún conviene reemplazar `InMemorySaver` por persistencia compartida (la tabla `agent_memory` con pgvector ya queda creada como base), las URLs locales por servicios desplegados, y agregar autenticación, autorización, monitoreo, auditoría, pruebas y presupuesto de consumo.

No expongas `mcp_datos.py` a internet sin controles. Aunque las tools sean de solo lectura, los datos pueden requerir protección y permisos.

## Referencias

Las referencias oficiales se encuentran en `docs/REFERENCIAS_OFICIALES.md`.
