"""Capa de acceso a datos conmutable: SQLite (local) o Supabase/Postgres (nube).

El backend se elige con la variable de entorno DB_BACKEND:

    DB_BACKEND=sqlite     -> usa data/ecommerce_orders.db            (por defecto)
    DB_BACKEND=supabase   -> usa DATABASE_URL (Postgres de Supabase)

Objetivo de diseño: las tools MCP escriben SQL UNA sola vez, con marcadores de
posición '?', y esta capa lo adapta a cada motor. Así el laboratorio local sigue
funcionando con SQLite y el portal puede desplegarse contra Supabase sin tocar
las consultas de negocio.

Requisitos de compatibilidad del SQL de las tools:
- Identificadores de columna en minúsculas y sin comillas (o entre comillas en
  minúsculas). En Postgres los identificadores sin comillas se pliegan a
  minúsculas; en SQLite el emparejamiento es insensible a mayúsculas.
- Marcadores de posición '?'. Para Postgres se traducen a '%s'.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Los backends de Postgres aceptados como sinónimos de Supabase.
_POSTGRES_BACKENDS = {"supabase", "postgres", "postgresql"}

DB_BACKEND = os.getenv("DB_BACKEND", "sqlite").strip().lower()
SQLITE_PATH = Path(__file__).parent / "data" / "ecommerce_orders.db"


def backend_activo() -> str:
    """Devuelve el backend en uso, normalizado a 'sqlite' o 'supabase'."""
    return "supabase" if DB_BACKEND in _POSTGRES_BACKENDS else "sqlite"


def _query_sqlite(sql: str, params: tuple) -> list[dict]:
    if not SQLITE_PATH.exists():
        raise FileNotFoundError(
            f"No existe {SQLITE_PATH}. Ejecuta: python data/import_dataset_to_sqlite.py"
        )
    with sqlite3.connect(SQLITE_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _query_postgres(sql: str, params: tuple) -> list[dict]:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - depende del entorno
        raise RuntimeError(
            "El backend supabase requiere 'psycopg[binary]'. Instala las dependencias "
            "con: pip install -r requirements.txt"
        ) from exc

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise RuntimeError(
            "Falta DATABASE_URL para el backend supabase. Copia la cadena de conexión "
            "de Supabase (Project Settings -> Database -> Connection string, pooler) al .env."
        )

    # Las tools usan '?'; psycopg espera '%s'. El SQL del proyecto no contiene '%'
    # literales, por lo que la sustitución directa es segura.
    pg_sql = sql.replace("?", "%s")
    with psycopg.connect(dsn) as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(pg_sql, params)
            return [dict(row) for row in cur.fetchall()]


def run_query(sql: str, params: tuple = ()) -> list[dict]:
    """Ejecuta una consulta de solo lectura en el backend configurado."""
    if backend_activo() == "supabase":
        return _query_postgres(sql, params)
    return _query_sqlite(sql, params)
