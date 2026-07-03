# Backend de datos en Supabase (Postgres)

Esta guía explica cómo ejecutar el proyecto contra **Supabase** (Postgres gestionado)
en lugar de SQLite, conservando el laboratorio local intacto.

## Por qué Supabase

- El dataset de e-commerce es tabular y relacional: encaja de forma natural en Postgres.
- Habilita un **portal multiusuario** en la nube (a diferencia del archivo SQLite local).
- Trae **pgvector** integrado, base para la memoria semántica del agente.
- La migración es casi 1:1: las tools escriben el mismo SQL; solo cambia el backend.

## Arquitectura de la capa de datos

```
tools MCP (mcp_datos.py)
        │  SQL con marcadores '?'  (una sola vez)
        ▼
     db.py  ──►  DB_BACKEND=sqlite    ->  data/ecommerce_orders.db
             └►  DB_BACKEND=supabase  ->  DATABASE_URL (Postgres/Supabase)
```

`db.py` traduce los marcadores `?` a `%s` para Postgres. Los identificadores de columna
se manejan en **minúsculas**, lo que funciona en ambos motores (SQLite es insensible a
mayúsculas; Postgres pliega los identificadores sin comillas a minúsculas).

## Esquema

Creado mediante la migración `create_orders_and_agent_memory`:

- `public.orders` — 41 columnas (en minúsculas) + índices sobre `customer_id`,
  `order_date`, `year`, `country`, `customer_segment`, `product_category`, `order_status`.
- extensión `vector` (pgvector) habilitada.
- `public.agent_memory` — base opcional para persistir memoria del agente
  (`session_id`, `rol`, `contenido`, `embedding vector(1536)`).

## Configuración

1. Crea (o usa) un proyecto en [supabase.com](https://supabase.com).
2. Copia la cadena de conexión: **Project Settings → Database → Connection string**.
   - **Conexión directa** (`db.<ref>.supabase.co:5432`): ideal para cargas/migraciones.
   - **Pooler** (`...pooler.supabase.com:6543`): recomendado para la app con muchas conexiones.
3. En tu `.env` (nunca lo subas a Git):

   ```env
   DB_BACKEND=supabase
   DATABASE_URL=postgresql://postgres:<password>@db.<ref>.supabase.co:5432/postgres
   ```

## Cargar el dataset completo

Instala dependencias (incluye `psycopg[binary]`) y ejecuta el loader:

```bash
pip install -r requirements.txt
python data/import_dataset_to_postgres.py
```

El script crea la tabla si no existe, hace `TRUNCATE` y carga las **30.000 órdenes**
con `COPY` (rápido e idempotente). Verifica al final el total, los clientes únicos y el período.

## Ejecutar el MCP de datos contra Supabase

```bash
DB_BACKEND=supabase python mcp_datos.py
```

El resto de la arquitectura (agente, MCP del agente, Streamlit) no cambia: siguen
consumiendo el MCP de datos por HTTP.

## Seguridad

- El `.env` con `DATABASE_URL` **nunca** se versiona (ya está en `.gitignore` vía `.env`).
- Para clientes tipo dashboard usa la **anon/publishable key** + **RLS**, no la contraseña de Postgres.
- No incrustes credenciales en el código (evita el patrón de claves hardcodeadas).
- Rota la contraseña de la base si alguna vez se expone.

## Volver a SQLite

Basta con `DB_BACKEND=sqlite` (o quitar la variable). El laboratorio local sigue
funcionando sin conexión a la nube.
