"""Importa el dataset real de e-commerce a SQLite.

Uso:
    python data/import_dataset_to_sqlite.py

Lee data/ecommerce_orders_dataset.csv y crea data/ecommerce_orders.db.
No genera datos ficticios: carga el archivo CSV incluido en este proyecto.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd

DATA_DIR = Path(__file__).parent
CSV_PATH = DATA_DIR / "ecommerce_orders_dataset.csv"
DB_PATH = DATA_DIR / "ecommerce_orders.db"
TABLE_NAME = "orders"

EXPECTED_COLUMNS = {
    "Order_ID", "Customer_ID", "Order_Date", "Year", "Month", "Day", "Day_Of_Week",
    "Quarter", "Customer_Age", "Customer_Gender", "Country", "City", "Customer_Segment",
    "Product_ID", "Product_Category", "Product_Subcategory", "Brand", "Unit_Price",
    "Quantity", "Discount_Percent", "Discount_Amount", "Coupon_Used", "Shipping_Cost",
    "Tax_Amount", "Order_Amount", "Payment_Method", "Device_Type", "Traffic_Source",
    "Membership_Status", "Shipping_Method", "Warehouse_Region", "Delivery_Days",
    "Order_Status", "Returned", "Review_Rating", "Customer_Lifetime_Value",
    "Profit_Margin_Percent", "Profit_Amount", "Season", "Holiday_Season", "High_Value_Order",
}


def main() -> None:
    if not CSV_PATH.exists():
        raise FileNotFoundError(
            f"No se encontró {CSV_PATH}. Copia el CSV real dentro de la carpeta data/."
        )

    df = pd.read_csv(CSV_PATH)
    missing = EXPECTED_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(
            "El CSV no corresponde al esquema esperado. Columnas faltantes: "
            + ", ".join(sorted(missing))
        )

    # Normaliza la fecha para ordenar y filtrar con SQLite sin depender del locale.
    df["Order_Date"] = pd.to_datetime(df["Order_Date"], errors="raise").dt.strftime("%Y-%m-%d")

    with sqlite3.connect(DB_PATH) as conn:
        df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
        indexes = {
            "idx_orders_customer": "Customer_ID",
            "idx_orders_date": "Order_Date",
            "idx_orders_year": "Year",
            "idx_orders_country": "Country",
            "idx_orders_segment": "Customer_Segment",
            "idx_orders_category": "Product_Category",
            "idx_orders_status": "Order_Status",
        }
        for index_name, column_name in indexes.items():
            conn.execute(f'CREATE INDEX IF NOT EXISTS {index_name} ON {TABLE_NAME} ("{column_name}")')

        total_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        customers = conn.execute("SELECT COUNT(DISTINCT Customer_ID) FROM orders").fetchone()[0]
        min_date, max_date = conn.execute(
            "SELECT MIN(Order_Date), MAX(Order_Date) FROM orders"
        ).fetchone()

    print(f"Base SQLite creada: {DB_PATH}")
    print(f"Órdenes cargadas: {total_orders:,}")
    print(f"Clientes únicos: {customers:,}")
    print(f"Período: {min_date} a {max_date}")


if __name__ == "__main__":
    main()
