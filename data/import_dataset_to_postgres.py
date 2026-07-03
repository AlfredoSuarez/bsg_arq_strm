"""Importa el dataset real de e-commerce a Postgres (Supabase).

Uso:
    DATABASE_URL="postgresql://postgres:<password>@<host>:5432/postgres" \
        python data/import_dataset_to_postgres.py

Lee data/ecommerce_orders_dataset.csv y carga la tabla public.orders del
proyecto Supabase. La tabla se crea si no existe (mismo esquema que la migración
create_orders_and_agent_memory) y se vacía antes de recargar, por lo que el
script es idempotente.

No genera datos ficticios: carga el archivo CSV incluido en este proyecto.
Las columnas se normalizan a minúsculas para que las tools MCP funcionen con
identificadores sin comillas tanto en SQLite como en Postgres.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pandas as pd

try:
    import psycopg
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Falta psycopg. Instala las dependencias: pip install -r requirements.txt"
    ) from exc

DATA_DIR = Path(__file__).parent
CSV_PATH = DATA_DIR / "ecommerce_orders_dataset.csv"
TABLE_NAME = "orders"

# Nombres del CSV (PascalCase) -> columnas destino en minúsculas.
COLUMN_ORDER = [
    "order_id", "customer_id", "order_date", "year", "month", "day", "day_of_week",
    "quarter", "customer_age", "customer_gender", "country", "city", "customer_segment",
    "product_id", "product_category", "product_subcategory", "brand", "unit_price",
    "quantity", "discount_percent", "discount_amount", "coupon_used", "shipping_cost",
    "tax_amount", "order_amount", "payment_method", "device_type", "traffic_source",
    "membership_status", "shipping_method", "warehouse_region", "delivery_days",
    "order_status", "returned", "review_rating", "customer_lifetime_value",
    "profit_margin_percent", "profit_amount", "season", "holiday_season", "high_value_order",
]

CREATE_TABLE_SQL = """
create table if not exists public.orders (
    order_id                bigint,
    customer_id             text,
    order_date              date,
    year                    integer,
    month                   integer,
    day                     integer,
    day_of_week             text,
    quarter                 integer,
    customer_age            integer,
    customer_gender         text,
    country                 text,
    city                    text,
    customer_segment        text,
    product_id              text,
    product_category        text,
    product_subcategory     text,
    brand                   text,
    unit_price              numeric,
    quantity                integer,
    discount_percent        numeric,
    discount_amount         numeric,
    coupon_used             text,
    shipping_cost           numeric,
    tax_amount              numeric,
    order_amount            numeric,
    payment_method          text,
    device_type             text,
    traffic_source          text,
    membership_status       text,
    shipping_method         text,
    warehouse_region        text,
    delivery_days           integer,
    order_status            text,
    returned                text,
    review_rating           numeric,
    customer_lifetime_value numeric,
    profit_margin_percent   numeric,
    profit_amount           numeric,
    season                  text,
    holiday_season          text,
    high_value_order        text
);
"""


def main() -> None:
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        raise SystemExit(
            "Falta DATABASE_URL. Ejemplo:\n"
            '  DATABASE_URL="postgresql://postgres:<password>@<host>:5432/postgres" '
            "python data/import_dataset_to_postgres.py"
        )
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"No se encontró {CSV_PATH}.")

    df = pd.read_csv(CSV_PATH)
    df.columns = [c.lower() for c in df.columns]

    missing = set(COLUMN_ORDER) - set(df.columns)
    if missing:
        raise ValueError(
            "El CSV no corresponde al esquema esperado. Columnas faltantes: "
            + ", ".join(sorted(missing))
        )

    # Normaliza la fecha a ISO para que Postgres la interprete como DATE.
    df["order_date"] = pd.to_datetime(df["order_date"], errors="raise").dt.strftime("%Y-%m-%d")
    df = df[COLUMN_ORDER]

    # Serializa a CSV en memoria para cargar con COPY (rápido y sin generar SQL gigante).
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False)
    buffer.seek(0)

    columns_sql = ", ".join(COLUMN_ORDER)
    copy_sql = (
        f"COPY public.{TABLE_NAME} ({columns_sql}) "
        f"FROM STDIN WITH (FORMAT csv)"
    )

    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLE_SQL)
            cur.execute(f"TRUNCATE public.{TABLE_NAME}")
            with cur.copy(copy_sql) as copy:
                copy.write(buffer.getvalue())
            cur.execute(f"SELECT COUNT(*) FROM public.{TABLE_NAME}")
            total = cur.fetchone()[0]
            cur.execute(f"SELECT COUNT(DISTINCT customer_id) FROM public.{TABLE_NAME}")
            customers = cur.fetchone()[0]
            cur.execute(
                f"SELECT MIN(order_date), MAX(order_date) FROM public.{TABLE_NAME}"
            )
            min_date, max_date = cur.fetchone()
        conn.commit()

    print("Datos cargados en Supabase/Postgres.")
    print(f"Órdenes cargadas: {total:,}")
    print(f"Clientes únicos: {customers:,}")
    print(f"Período: {min_date} a {max_date}")


if __name__ == "__main__":
    main()
