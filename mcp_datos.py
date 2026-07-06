"""MCP de datos e-commerce basado en el dataset real del proyecto.

Cada tool expone una capacidad analítica de negocio y ejecuta SQL explícito,
parametrizado y de solo lectura. El LLM no genera SQL libre.

Backend de datos conmutable (ver db.py):
    DB_BACKEND=sqlite    -> data/ecommerce_orders.db  (laboratorio local, por defecto)
    DB_BACKEND=supabase  -> DATABASE_URL (Postgres de Supabase, portal en la nube)

Antes de ejecutar con SQLite:
    python data/import_dataset_to_sqlite.py
Antes de ejecutar con Supabase:
    DB_BACKEND=supabase DATABASE_URL=... python data/import_dataset_to_postgres.py

Inicio local:
    python mcp_datos.py

Endpoint MCP:
    http://127.0.0.1:8000/mcp
"""
from __future__ import annotations

import json
from fastmcp import FastMCP

import fpa
from db import backend_activo, run_query

mcp = FastMCP(
    name="Ecommerce Analytics Data MCP",
    instructions=(
        "Servidor MCP de analítica e-commerce de solo lectura. Usa herramientas "
        "específicas para analizar clientes, ventas, categorías, devoluciones y canales."
    ),
)


def ejecutar_sql(sql: str, parametros: tuple = ()) -> list[dict]:
    """Ejecuta SQL de solo lectura contra el backend configurado (SQLite o Supabase)."""
    return run_query(sql, parametros)


def as_json(rows: list[dict], empty_message: str = "No se encontraron resultados") -> str:
    return json.dumps(rows or [{"message": empty_message}], ensure_ascii=False, default=str)


@mcp.tool()
def buscar_clientes(texto: str, limite: int = 10) -> str:
    """Busca clientes por Customer_ID, país, ciudad, segmento o membresía.

    Úsala antes de consultar a un cliente cuando no se conoce un Customer_ID exacto.
    """
    limite = max(1, min(limite, 25))
    p = f"%{texto.strip()}%"
    sql = """
    SELECT Customer_ID,
           MAX(Country) AS Country,
           MAX(City) AS City,
           MAX(Customer_Segment) AS Customer_Segment,
           MAX(Membership_Status) AS Membership_Status,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Total_Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Total_Profit
    FROM orders
    WHERE Customer_ID LIKE ? OR Country LIKE ? OR City LIKE ?
       OR Customer_Segment LIKE ? OR Membership_Status LIKE ?
    GROUP BY Customer_ID
    ORDER BY Total_Revenue DESC
    LIMIT ?
    """
    return as_json(ejecutar_sql(sql, (p, p, p, p, p, limite)))


@mcp.tool()
def resumen_cliente(customer_id: str) -> str:
    """Resume compras, gasto, utilidad, ticket promedio, unidades y período de actividad de un cliente exacto."""
    sql = """
    SELECT Customer_ID,
           MAX(Country) AS Country,
           MAX(City) AS City,
           MAX(Customer_Segment) AS Customer_Segment,
           MAX(Membership_Status) AS Membership_Status,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Total_Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Total_Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           SUM(Quantity) AS Total_Units,
           MIN(Order_Date) AS First_Order,
           MAX(Order_Date) AS Last_Order,
           ROUND(MAX(Customer_Lifetime_Value), 2) AS Customer_Lifetime_Value
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Customer_ID
    """
    return as_json(ejecutar_sql(sql, (customer_id,)), "Cliente no encontrado")


@mcp.tool()
def perfil_compras_cliente(customer_id: str, limite: int = 8) -> str:
    """Muestra las categorías y subcategorías con mayor gasto de un cliente exacto."""
    limite = max(1, min(limite, 20))
    sql = """
    SELECT Product_Category,
           Product_Subcategory,
           COUNT(*) AS Orders,
           SUM(Quantity) AS Units,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(AVG(Discount_Percent), 2) AS Average_Discount_Percent
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Product_Category, Product_Subcategory
    ORDER BY Revenue DESC
    LIMIT ?
    """
    return as_json(ejecutar_sql(sql, (customer_id, limite)), "Cliente no encontrado")


@mcp.tool()
def experiencia_cliente(customer_id: str) -> str:
    """Evalúa experiencia de compra: devoluciones, rating, días de entrega, estados de orden y método de envío."""
    sql = """
    SELECT Customer_ID,
           COUNT(*) AS Total_Orders,
           SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) AS Returned_Orders,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent,
           ROUND(AVG(Review_Rating), 2) AS Average_Review_Rating,
           ROUND(AVG(Delivery_Days), 2) AS Average_Delivery_Days,
           SUM(CASE WHEN Order_Status = 'Cancelled' THEN 1 ELSE 0 END) AS Cancelled_Orders,
           SUM(CASE WHEN Order_Status = 'Delivered' THEN 1 ELSE 0 END) AS Delivered_Orders,
           MAX(Shipping_Method) AS Typical_Shipping_Method
    FROM orders
    WHERE Customer_ID = ?
    GROUP BY Customer_ID
    """
    return as_json(ejecutar_sql(sql, (customer_id,)), "Cliente no encontrado")


@mcp.tool()
def ventas_por_dimension(dimension: str, year: int | None = None, limite: int = 10) -> str:
    """Entrega ranking de ventas y utilidad por país, categoría, segmento, canal de tráfico, dispositivo o método de pago.

    dimension válida: country, category, segment, traffic_source, device_type, payment_method, warehouse_region.
    year es opcional; úsalo para comparar un año específico.
    """
    # Nombres de columna en minúsculas: compatibles con SQLite (insensible a
    # mayúsculas) y con Postgres (identificadores plegados a minúsculas).
    columns = {
        "country": "country",
        "category": "product_category",
        "segment": "customer_segment",
        "traffic_source": "traffic_source",
        "device_type": "device_type",
        "payment_method": "payment_method",
        "warehouse_region": "warehouse_region",
    }
    key = dimension.strip().lower()
    if key not in columns:
        return as_json([], "Dimensión inválida. Usa: " + ", ".join(columns))
    limite = max(1, min(limite, 25))
    column = columns[key]
    if year is None:
        sql = f'''SELECT "{column}" AS Dimension,
                         COUNT(*) AS Total_Orders,
                         ROUND(SUM(Order_Amount), 2) AS Revenue,
                         ROUND(SUM(Profit_Amount), 2) AS Profit,
                         ROUND(AVG(Order_Amount), 2) AS Average_Order_Value
                  FROM orders
                  GROUP BY "{column}"
                  ORDER BY Revenue DESC
                  LIMIT ?'''
        params = (limite,)
    else:
        sql = f'''SELECT "{column}" AS Dimension,
                         COUNT(*) AS Total_Orders,
                         ROUND(SUM(Order_Amount), 2) AS Revenue,
                         ROUND(SUM(Profit_Amount), 2) AS Profit,
                         ROUND(AVG(Order_Amount), 2) AS Average_Order_Value
                  FROM orders
                  WHERE Year = ?
                  GROUP BY "{column}"
                  ORDER BY Revenue DESC
                  LIMIT ?'''
        params = (year, limite)
    return as_json(ejecutar_sql(sql, params))


@mcp.tool()
def tendencia_ventas(year: int | None = None, country: str | None = None) -> str:
    """Resume ventas mensuales, utilidad, órdenes, ticket promedio y devoluciones. Puede filtrarse por año y país."""
    filters: list[str] = []
    params: list[object] = []
    if year is not None:
        filters.append("Year = ?")
        params.append(year)
    if country:
        filters.append("Country = ?")
        params.append(country)
    where = "WHERE " + " AND ".join(filters) if filters else ""
    sql = f"""
    SELECT Year, Month,
           COUNT(*) AS Total_Orders,
           ROUND(SUM(Order_Amount), 2) AS Revenue,
           ROUND(SUM(Profit_Amount), 2) AS Profit,
           ROUND(AVG(Order_Amount), 2) AS Average_Order_Value,
           ROUND(100.0 * SUM(CASE WHEN Returned = 'Yes' THEN 1 ELSE 0 END) / COUNT(*), 2) AS Return_Rate_Percent
    FROM orders
    {where}
    GROUP BY Year, Month
    ORDER BY Year, Month
    """
    return as_json(ejecutar_sql(sql, tuple(params)))


@mcp.tool()
def detalle_orden(order_id: int) -> str:
    """Recupera el detalle de una orden real por Order_ID. Úsala cuando el usuario entrega un identificador de orden."""
    sql = """
    SELECT Order_ID, Customer_ID, Order_Date, Country, City, Customer_Segment,
           Product_ID, Product_Category, Product_Subcategory, Brand,
           Unit_Price, Quantity, Discount_Percent, Discount_Amount,
           Shipping_Cost, Tax_Amount, Order_Amount, Payment_Method,
           Device_Type, Traffic_Source, Membership_Status, Shipping_Method,
           Delivery_Days, Order_Status, Returned, Review_Rating,
           Profit_Amount, Season, Holiday_Season, High_Value_Order
    FROM orders
    WHERE Order_ID = ?
    """
    return as_json(ejecutar_sql(sql, (order_id,)), "Orden no encontrada")


# =========================================================================== #
# Tools de Marketing (canales, promociones, retención)
# =========================================================================== #
@mcp.tool()
def rendimiento_canal() -> str:
    """Rendimiento de marketing por canal de tráfico: revenue, margen, ticket y devoluciones.

    Úsala para evaluar qué canales de adquisición traen clientes más rentables.
    """
    sql = """
    SELECT traffic_source AS Channel,
           COUNT(*) AS Orders,
           ROUND(SUM(order_amount),2) AS Revenue,
           ROUND(SUM(profit_amount),2) AS Profit,
           ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS Margin_Pct,
           ROUND(AVG(order_amount),2) AS AOV,
           ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS Return_Rate_Pct
    FROM orders
    GROUP BY traffic_source
    ORDER BY Revenue DESC
    """
    return as_json(ejecutar_sql(sql))


@mcp.tool()
def impacto_promociones() -> str:
    """Impacto de cupones/descuentos: compara órdenes con cupón vs sin cupón (ticket, margen, descuento)."""
    sql = """
    SELECT coupon_used AS Coupon_Used,
           COUNT(*) AS Orders,
           ROUND(SUM(order_amount),2) AS Revenue,
           ROUND(AVG(order_amount),2) AS AOV,
           ROUND(AVG(discount_percent),2) AS Avg_Discount_Pct,
           ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS Margin_Pct
    FROM orders
    GROUP BY coupon_used
    ORDER BY Revenue DESC
    """
    return as_json(ejecutar_sql(sql))


@mcp.tool()
def retencion_clientes() -> str:
    """Retención/recompra: tasa de clientes recurrentes, órdenes y gasto promedio por cliente."""
    sql = """
    SELECT ROUND(100.0*SUM(CASE WHEN n>1 THEN 1 ELSE 0 END)/COUNT(*),2) AS Repeat_Rate_Pct,
           COUNT(*) AS Customers,
           ROUND(AVG(n),2) AS Avg_Orders_Per_Customer,
           ROUND(AVG(spend),2) AS Avg_Spend_Per_Customer
    FROM (SELECT customer_id, COUNT(*) AS n, SUM(order_amount) AS spend
          FROM orders GROUP BY customer_id) t
    """
    return as_json(ejecutar_sql(sql))


# =========================================================================== #
# Tools FP&A (Planeación y Análisis Financiero)
# Actuals reales de `orders`; budget/forecast/recurring modelados (ver fpa.py).
# =========================================================================== #
def _json(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


@mcp.tool()
def kpi_ejecutivo(year: int | None = None) -> str:
    """P&L ejecutivo: revenue, COGS, margen bruto, OpEx, EBITDA y growth YoY.

    Úsala para preguntas de desempeño financiero ("¿cómo cerró 2024?", "EBITDA",
    "margen"). Sin year devuelve el consolidado de todo el período.
    """
    return _json(fpa.executive_pl(year))


@mcp.tool()
def variacion_presupuestal(year: int | None = None) -> str:
    """Variación presupuestal mensual: actual vs budget (revenue y %), favorable/desfavorable.

    El budget se modela como el año previo del mismo mes más el crecimiento objetivo.
    """
    df = fpa.budget_vs_actual(year)
    cols = ["period", "revenue", "budget_revenue", "var_revenue", "var_revenue_pct"]
    return _json(df[cols].to_dict("records") if not df.empty else [{"message": "Sin budget para el período"}])


@mcp.tool()
def forecast_ingresos(horizonte: int = 12) -> str:
    """Rolling forecast de ingresos para los próximos N meses (base crecimiento YoY)."""
    horizonte = max(1, min(horizonte, 24))
    return _json(fpa.forecast(horizonte).to_dict("records"))


@mcp.tool()
def escenario(revenue_growth_pct: float, gross_margin_pct: float,
              opex_pct: float = 18.0, year: int | None = None) -> str:
    """Modela un escenario what-if sobre el P&L y su impacto en EBITDA.

    Args:
        revenue_growth_pct: crecimiento de ingresos aplicado a la base (ej. 15 = +15%).
        gross_margin_pct: margen bruto objetivo del escenario (ej. 24).
        opex_pct: OpEx como % de revenue (por defecto 18).
        year: año base opcional; sin él usa todo el período.
    """
    return _json(fpa.scenario(revenue_growth_pct, gross_margin_pct, opex_pct, year))


@mcp.tool()
def ingreso_recurrente(year: int | None = None) -> str:
    """Ingreso recurrente por membresías: MRR, ARR, ARPU y desglose por tier."""
    return _json(fpa.recurring_summary(year))


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
