"""
Portal BI E-commerce — Dashboard analítico (Streamlit + Plotly), bilingüe ES/EN.

Lee de la MISMA capa de datos conmutable que el resto del proyecto (db.py):

    DB_BACKEND=sqlite    -> data/ecommerce_orders.db
    DB_BACKEND=supabase  -> DATABASE_URL (Postgres de Supabase)
    (sin DB_BACKEND, si hay DATABASE_URL usa Supabase automáticamente)

Ejecutar:
    streamlit run dashboard.py

Incluye un toggle de idioma (Español / English) que traduce la interfaz y hace
que el asistente responda en el idioma elegido.
"""
from __future__ import annotations

import asyncio
import atexit
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv
from plotly.subplots import make_subplots

# --- Entorno ANTES de importar db.py (db.py resuelve el backend leyendo el entorno) ---
load_dotenv()


def _bridge_secrets() -> None:
    """Copia los secrets de Streamlit Cloud a variables de entorno.

    Necesario para que db.py (dashboard) y el subproceso del MCP de datos vean
    DATABASE_URL / OPENROUTER_API_KEY. Sin esto, en la nube caería a SQLite.
    """
    for key in ("DB_BACKEND", "DATABASE_URL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL"):
        try:
            if not os.environ.get(key) and key in st.secrets:
                os.environ[key] = str(st.secrets[key])
        except Exception:  # noqa: BLE001 - sin archivo de secrets en local
            pass


_bridge_secrets()

from db import backend_activo, run_query  # noqa: E402 - tras configurar el entorno

REPO_DIR = Path(__file__).parent
DATA_MCP_HOST, DATA_MCP_PORT = "127.0.0.1", 8000


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


@st.cache_resource(show_spinner=False)
def ensure_data_mcp() -> str:
    """Levanta mcp_datos.py como subproceso HTTP una sola vez (para el asistente)."""
    if _port_open(DATA_MCP_HOST, DATA_MCP_PORT):
        return "externo"
    proc = subprocess.Popen(
        [sys.executable, str(REPO_DIR / "mcp_datos.py")],
        cwd=str(REPO_DIR),
        env=os.environ.copy(),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    atexit.register(proc.terminate)
    for _ in range(60):
        if _port_open(DATA_MCP_HOST, DATA_MCP_PORT):
            return "iniciado"
        time.sleep(0.5)
    raise RuntimeError("El MCP de datos no arrancó en 127.0.0.1:8000")


# --------------------------------------------------------------------------- #
# i18n: diccionario de traducciones. t(key) devuelve el texto del idioma activo.
# --------------------------------------------------------------------------- #
T: dict[str, dict[str, str]] = {
    "header_sub": {"es": "Ventas · Rentabilidad · Geografía · Segmentación · Devoluciones",
                   "en": "Sales · Profitability · Geography · Segmentation · Returns"},
    "filters": {"es": "Filtros", "en": "Filters"},
    "backend": {"es": "Backend activo", "en": "Active backend"},
    "year": {"es": "Año", "en": "Year"},
    "country": {"es": "País", "en": "Country"},
    "data_note": {"es": "Datos de e-commerce · uso técnico/pedagógico, no es evidencia comercial real.",
                  "en": "E-commerce data · technical/educational use, not real commercial evidence."},
    "orders_filter": {"es": "Órdenes (filtro)", "en": "Orders (filter)"},
    "revenue_filter": {"es": "Revenue (filtro)", "en": "Revenue (filter)"},
    "no_data": {"es": "No hay datos para el filtro seleccionado.", "en": "No data for the selected filter."},
    "read_error": {"es": "No fue posible leer los datos", "en": "Could not read the data"},
    "read_hint": {"es": "En la nube define el secret DATABASE_URL (Supabase). En local con SQLite, ejecuta antes: python data/import_dataset_to_sqlite.py",
                  "en": "In the cloud set the DATABASE_URL secret (Supabase). Locally with SQLite, first run: python data/import_dataset_to_sqlite.py"},
    # Tabs
    "tab_summary": {"es": "Resumen ejecutivo", "en": "Executive summary"},
    "tab_trend": {"es": "Tendencia temporal", "en": "Time trend"},
    "tab_segment": {"es": "Segmentación", "en": "Segmentation"},
    "tab_insights": {"es": "Insights & Acciones", "en": "Insights & Actions"},
    "tab_assistant": {"es": "🤖 Asistente", "en": "🤖 Assistant"},
    # KPIs
    "key_indicators": {"es": "Indicadores clave", "en": "Key indicators"},
    "kpi_revenue": {"es": "Revenue", "en": "Revenue"},
    "kpi_revenue_sub": {"es": "Facturación total", "en": "Total revenue"},
    "kpi_profit": {"es": "Profit", "en": "Profit"},
    "kpi_orders": {"es": "Órdenes", "en": "Orders"},
    "kpi_aov": {"es": "Ticket promedio", "en": "Avg order value"},
    "kpi_aov_sub": {"es": "Order Amount medio", "en": "Mean order amount"},
    "kpi_return": {"es": "Tasa de devolución", "en": "Return rate"},
    "kpi_return_sub": {"es": "Órdenes devueltas", "en": "Returned orders"},
    "kpi_rating": {"es": "Rating medio", "en": "Avg rating"},
    "kpi_rating_sub": {"es": "Satisfacción", "en": "Satisfaction"},
    "kpi_margin": {"es": "Margen", "en": "Margin"},
    "kpi_rev_cust": {"es": "Revenue / cliente", "en": "Revenue / customer"},
    "kpi_avg": {"es": "Promedio", "en": "Average"},
    "chart_rev_cat": {"es": "Revenue por categoría", "en": "Revenue by category"},
    "chart_top_countries": {"es": "Top 10 países por revenue", "en": "Top 10 countries by revenue"},
    "chart_rev_segment": {"es": "Revenue por segmento de cliente (color = margen %)",
                          "en": "Revenue by customer segment (color = margin %)"},
    # Trend
    "monthly_evo": {"es": "Evolución mensual", "en": "Monthly evolution"},
    "rev_profit_month": {"es": "Revenue y Profit por mes", "en": "Revenue and Profit by month"},
    "avg_rev_month": {"es": "Revenue medio/mes", "en": "Avg revenue/month"},
    "best_month": {"es": "Mejor mes", "en": "Best month"},
    "worst_month": {"es": "Peor mes", "en": "Worst month"},
    "avg_orders_month": {"es": "Órdenes medias/mes", "en": "Avg orders/month"},
    "orders_ticket": {"es": "Órdenes y ticket promedio", "en": "Orders and average ticket"},
    "orders_by_stage": {"es": "Órdenes", "en": "Orders"},
    "avg_ticket": {"es": "Ticket promedio", "en": "Avg ticket"},
    "ticket_axis": {"es": "Ticket ($)", "en": "Ticket ($)"},
    # Segmentation
    "user_dist": {"es": "Distribución de usuarios", "en": "User distribution"},
    "orders_by_gender": {"es": "Órdenes por género", "en": "Orders by gender"},
    "orders_by_device": {"es": "Órdenes por dispositivo", "en": "Orders by device"},
    "heatmaps_dg": {"es": "Heatmaps: dispositivo × género", "en": "Heatmaps: device × gender"},
    "hm_revenue": {"es": "Revenue", "en": "Revenue"},
    "hm_margin": {"es": "Margen %", "en": "Margin %"},
    "hm_aov": {"es": "Ticket promedio", "en": "Avg order value"},
    "hm_return": {"es": "Tasa de devolución %", "en": "Return rate %"},
    "channels_payments": {"es": "Canales y métodos de pago", "en": "Channels and payment methods"},
    "rev_by_channel": {"es": "Revenue por canal de tráfico", "en": "Revenue by traffic source"},
    "orders_by_payment": {"es": "Órdenes por método de pago", "en": "Orders by payment method"},
    # Insights
    "seg_by_revenue": {"es": "Segmentos device × género (por revenue)",
                       "en": "Device × gender segments (by revenue)"},
    "top_segments": {"es": "Top segmentos", "en": "Top segments"},
    "low_segments": {"es": "Segmentos de menor revenue", "en": "Lowest-revenue segments"},
    "cat_profit": {"es": "Categorías por rentabilidad", "en": "Categories by profitability"},
    "scatter_title": {"es": "Revenue vs Margen por categoría (tamaño = profit, color = devolución %)",
                      "en": "Revenue vs Margin by category (size = profit, color = return %)"},
    "lbl_revenue": {"es": "Revenue ($)", "en": "Revenue ($)"},
    "lbl_margin": {"es": "Margen %", "en": "Margin %"},
    "lbl_return": {"es": "Devolución %", "en": "Return %"},
    "quick_read": {"es": "Lectura rápida", "en": "Quick read"},
    "most_profitable": {"es": "Categoría más rentable", "en": "Most profitable category"},
    "of_profit_margin": {"es": "de profit, margen", "en": "in profit, margin"},
    "highest_return": {"es": "Mayor tasa de devolución", "en": "Highest return rate"},
    "review_quality": {"es": "revisar calidad, tallas o descripción",
                       "en": "review quality, sizing or description"},
    "overall_margin": {"es": "Margen global del filtro", "en": "Overall margin of filter"},
    "over_revenue": {"es": "sobre", "en": "over"},
    "of_revenue": {"es": "de revenue", "en": "in revenue"},
    # Assistant
    "assistant_title": {"es": "Asistente conversacional", "en": "Conversational assistant"},
    "assistant_caption": {"es": "Agente LangChain (vía OpenRouter) que consulta los mismos datos a través del MCP de datos, en el mismo proceso del dashboard.",
                          "en": "LangChain agent (via OpenRouter) querying the same data through the data MCP, in the dashboard's own process."},
    "assistant_nokey": {"es": "Configura el secret OPENROUTER_API_KEY (Settings → Secrets) para habilitar el asistente.",
                        "en": "Set the OPENROUTER_API_KEY secret (Settings → Secrets) to enable the assistant."},
    "ask_agent": {"es": "Pregunta al agente", "en": "Ask the agent"},
    "ask_placeholder": {"es": "Ej.: ¿Qué país genera más utilidad en 2024?",
                        "en": "E.g.: Which country generates the most profit in 2024?"},
    "send": {"es": "Enviar", "en": "Send"},
    "agent_spinner": {"es": "El agente consulta los datos vía MCP...",
                      "en": "The agent is querying the data via MCP..."},
    "agent_error": {"es": "No fue posible responder", "en": "Could not answer"},
    "agent_trace": {"es": "Traza de orquestación (tools MCP invocadas)",
                    "en": "Orchestration trace (MCP tools invoked)"},
    "new_chat": {"es": "Nueva conversación", "en": "New conversation"},
    "footer": {"es": "Portal BI E-commerce · backend: {b} · datos de uso técnico/pedagógico.",
               "en": "E-commerce BI Portal · backend: {b} · technical/educational data."},
}


st.set_page_config(
    page_title="Portal BI E-commerce",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Estilos (legibles en claro y oscuro).
# --------------------------------------------------------------------------- #
st.markdown(
    """
<style>
.main-header {
    text-align: center;
    background: linear-gradient(90deg, #2E86AB 0%, #06A77D 100%);
    padding: 1.8rem; border-radius: 12px; color: white; margin-bottom: 1.5rem;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
}
.metric-card {
    background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
    padding: 1.2rem; border-radius: 10px; border-left: 5px solid #2E86AB;
    margin-bottom: 1rem; box-shadow: 0 2px 4px rgba(0,0,0,0.1); color: #212529;
}
.metric-card h2, .metric-card h4, .metric-card p { color: #212529 !important; margin: 0.2rem 0; }
.metric-card h2 { color: #2E86AB !important; }
.insight-box {
    background: #fff3cd; padding: 1.2rem; border-radius: 10px;
    border-left: 5px solid #ffc107; margin: 0.8rem 0; color: #664d03;
}
.insight-box h4, .insight-box p, .insight-box li { color: #664d03 !important; }
.action-box {
    background: #d4edda; padding: 1.2rem; border-radius: 10px;
    border-left: 5px solid #28a745; margin: 0.8rem 0; color: #0f5132;
}
.action-box h3, .action-box h4, .action-box p, .action-box li { color: #0f5132 !important; }
.warning-box {
    background: #f8d7da; padding: 1.2rem; border-radius: 10px;
    border-left: 5px solid #dc3545; margin: 0.8rem 0; color: #842029;
}
.warning-box h4, .warning-box h3, .warning-box p, .warning-box li { color: #842029 !important; }
.stTabs [data-baseweb="tab-list"] { gap: 8px; width: 100%; }
.stTabs [data-baseweb="tab"] {
    height: 48px; padding: 8px 20px; background-color: #f0f2f6; color: #31333F;
    flex-grow: 1; justify-content: center; border-radius: 10px 10px 0 0; font-weight: 600;
}
.stTabs [aria-selected="true"] { background-color: #2E86AB !important; color: white !important; }
</style>
""",
    unsafe_allow_html=True,
)

PALETTE = ["#2E86AB", "#06A77D", "#F18F01", "#A23B72", "#E63946", "#264653", "#E76F51", "#2A9D8F"]


# --------------------------------------------------------------------------- #
# Idioma (toggle) — se elige antes de renderizar el resto.
# --------------------------------------------------------------------------- #
with st.sidebar:
    lang = st.radio("🌐 Idioma / Language", ["Español", "English"], horizontal=True, key="lang")
LANG = "en" if lang == "English" else "es"


def t(key: str) -> str:
    return T[key][LANG]


# --------------------------------------------------------------------------- #
# Acceso a datos: usa la capa conmutable y devuelve DataFrames cacheados.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    df = pd.DataFrame(run_query(sql, params))
    # Postgres devuelve numéricos como Decimal (dtype object); Plotly exige float.
    for col in df.columns:
        if df[col].dtype == object:
            mask = df[col].notna()
            if mask.any() and pd.to_numeric(df[col][mask], errors="coerce").notna().all():
                df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def build_where(years: list[int], countries: list[str]) -> tuple[str, tuple]:
    """Construye un WHERE parametrizado compatible con SQLite y Postgres."""
    clauses: list[str] = []
    params: list[object] = []
    if years:
        clauses.append("year IN (" + ",".join(["?"] * len(years)) + ")")
        params.extend(years)
    if countries:
        clauses.append("country IN (" + ",".join(["?"] * len(countries)) + ")")
        params.extend(countries)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, tuple(params)


def kpi_card(col, titulo: str, valor: str, subtitulo: str = "") -> None:
    col.markdown(
        f'<div class="metric-card"><h4>{titulo}</h4><h2>{valor}</h2><p>{subtitulo}</p></div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Carga base y filtros.
# --------------------------------------------------------------------------- #
try:
    years_df = q("SELECT DISTINCT year FROM orders ORDER BY year")
    countries_df = q("SELECT DISTINCT country FROM orders ORDER BY country")
except Exception as exc:  # noqa: BLE001
    st.error(f"{t('read_error')} ({backend_activo()}): {exc}")
    st.info(t("read_hint"))
    st.stop()

all_years = [int(y) for y in years_df["year"].tolist()]
all_countries = countries_df["country"].tolist()

with st.sidebar:
    st.header(t("filters"))
    st.caption(f"{t('backend')}: **{backend_activo()}**")
    sel_years = st.multiselect(t("year"), all_years, default=all_years)
    sel_countries = st.multiselect(t("country"), all_countries, default=[])
    st.divider()
    st.caption(t("data_note"))

where, params = build_where(sel_years, sel_countries)

st.markdown(
    f"""
<div class="main-header">
    <h1>📊 Portal BI E-commerce</h1>
    <p style="font-size:1.1rem;margin-top:0.5rem;">{t('header_sub')}</p>
</div>
""",
    unsafe_allow_html=True,
)

kpis = q(
    f"""
    SELECT COUNT(*) AS orders, COUNT(DISTINCT customer_id) AS customers,
           ROUND(SUM(order_amount),2) AS revenue,
           ROUND(SUM(profit_amount),2) AS profit,
           ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
           ROUND(AVG(order_amount),2) AS aov,
           ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate,
           ROUND(AVG(review_rating),2) AS rating
    FROM orders {where}
    """,
    params,
)

if kpis.empty or not kpis.loc[0, "orders"]:
    st.warning(t("no_data"))
    st.stop()

k = kpis.iloc[0]
st.sidebar.metric(t("orders_filter"), f"{int(k['orders']):,}")
st.sidebar.metric(t("revenue_filter"), f"${float(k['revenue']):,.0f}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [t("tab_summary"), t("tab_trend"), t("tab_segment"), t("tab_insights"), t("tab_assistant")]
)

# =========================================================================== #
# TAB 1 — Resumen ejecutivo
# =========================================================================== #
with tab1:
    st.subheader(t("key_indicators"))
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, t("kpi_revenue"), f"${float(k['revenue']):,.0f}", t("kpi_revenue_sub"))
    kpi_card(c2, t("kpi_profit"), f"${float(k['profit']):,.0f}", f"{t('kpi_margin')} {float(k['margin_pct']):.1f}%")
    _customers = "clientes" if LANG == "es" else "customers"
    kpi_card(c3, t("kpi_orders"), f"{int(k['orders']):,}", f"{int(k['customers']):,} {_customers}")
    kpi_card(c4, t("kpi_aov"), f"${float(k['aov']):,.2f}", t("kpi_aov_sub"))

    c5, c6, c7, c8 = st.columns(4)
    kpi_card(c5, t("kpi_return"), f"{float(k['return_rate']):.1f}%", t("kpi_return_sub"))
    kpi_card(c6, t("kpi_rating"), f"{float(k['rating']):.2f} / 5", t("kpi_rating_sub"))
    kpi_card(c7, t("kpi_margin"), f"{float(k['margin_pct']):.1f}%", "Profit / Revenue")
    kpi_card(c8, t("kpi_rev_cust"), f"${float(k['revenue'])/max(int(k['customers']),1):,.0f}", t("kpi_avg"))

    st.divider()
    left, right = st.columns(2)

    with left:
        cat = q(
            f"""SELECT product_category AS categoria,
                       ROUND(SUM(order_amount),2) AS revenue,
                       ROUND(SUM(profit_amount),2) AS profit
                FROM orders {where}
                GROUP BY product_category ORDER BY revenue DESC""",
            params,
        )
        fig = px.bar(cat, x="revenue", y="categoria", orientation="h",
                     title=f"<b>{t('chart_rev_cat')}</b>", color="revenue",
                     color_continuous_scale="Teal", text="revenue")
        fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=430,
                          coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")

    with right:
        country = q(
            f"""SELECT country AS pais, ROUND(SUM(order_amount),2) AS revenue
                FROM orders {where}
                GROUP BY country ORDER BY revenue DESC LIMIT 10""",
            params,
        )
        fig = px.bar(country, x="pais", y="revenue", title=f"<b>{t('chart_top_countries')}</b>",
                     color="revenue", color_continuous_scale="Teal", text="revenue")
        fig.update_traces(texttemplate="$%{text:,.0s}", textposition="outside")
        fig.update_layout(height=430, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")

    seg = q(
        f"""SELECT customer_segment AS segmento, COUNT(*) AS orders,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct
            FROM orders {where}
            GROUP BY customer_segment ORDER BY revenue DESC""",
        params,
    )
    fig = px.bar(seg, x="segmento", y="revenue", color="margin_pct",
                 title=f"<b>{t('chart_rev_segment')}</b>",
                 color_continuous_scale="RdYlGn", text="revenue")
    fig.update_traces(texttemplate="$%{text:,.0s}", textposition="outside")
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")

# =========================================================================== #
# TAB 2 — Tendencia temporal
# =========================================================================== #
with tab2:
    st.subheader(t("monthly_evo"))
    trend = q(
        f"""SELECT year, month,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(SUM(profit_amount),2) AS profit,
                   COUNT(*) AS orders,
                   ROUND(AVG(order_amount),2) AS aov
            FROM orders {where}
            GROUP BY year, month ORDER BY year, month""",
        params,
    )
    trend["periodo"] = (
        trend["year"].astype(int).astype(str) + "-"
        + trend["month"].astype(int).astype(str).str.zfill(2)
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=trend["periodo"], y=trend["revenue"], name=t("kpi_revenue"),
                         marker_color="#2E86AB", opacity=0.85), secondary_y=False)
    fig.add_trace(go.Scatter(x=trend["periodo"], y=trend["profit"], name=t("kpi_profit"),
                             mode="lines+markers", line=dict(color="#06A77D", width=3)), secondary_y=True)
    fig.update_layout(title=f"<b>{t('rev_profit_month')}</b>", height=460, hovermode="x unified",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                      margin=dict(l=10, r=10, t=60, b=10))
    fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
    fig.update_yaxes(title_text="Profit ($)", secondary_y=True)
    st.plotly_chart(fig, width="stretch")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(t("avg_rev_month"), f"${trend['revenue'].mean():,.0f}")
    best = trend.loc[trend["revenue"].idxmax()]
    worst = trend.loc[trend["revenue"].idxmin()]
    c2.metric(t("best_month"), best["periodo"], f"${float(best['revenue']):,.0f}")
    c3.metric(t("worst_month"), worst["periodo"], f"${float(worst['revenue']):,.0f}")
    c4.metric(t("avg_orders_month"), f"{trend['orders'].mean():,.0f}")

    st.divider()
    st.subheader(t("orders_ticket"))
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(go.Bar(x=trend["periodo"], y=trend["orders"], name=t("orders_by_stage"),
                          marker_color="#A23B72", opacity=0.7), secondary_y=False)
    fig2.add_trace(go.Scatter(x=trend["periodo"], y=trend["aov"], name=t("avg_ticket"),
                              mode="lines+markers", line=dict(color="#F18F01", width=3)), secondary_y=True)
    fig2.update_layout(height=400, hovermode="x unified",
                       legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                       margin=dict(l=10, r=10, t=30, b=10))
    fig2.update_yaxes(title_text=t("orders_by_stage"), secondary_y=False)
    fig2.update_yaxes(title_text=t("ticket_axis"), secondary_y=True)
    st.plotly_chart(fig2, width="stretch")

# =========================================================================== #
# TAB 3 — Segmentación (device × género)
# =========================================================================== #
with tab3:
    st.subheader(t("user_dist"))
    dg = q(
        f"""SELECT device_type, customer_gender, COUNT(*) AS orders,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(AVG(order_amount),2) AS aov,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
                   ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate
            FROM orders {where}
            GROUP BY device_type, customer_gender""",
        params,
    )

    c1, c2 = st.columns(2)
    with c1:
        gdist = dg.groupby("customer_gender", as_index=False)["orders"].sum()
        fig = px.pie(gdist, values="orders", names="customer_gender", hole=0.45,
                     title=f"<b>{t('orders_by_gender')}</b>", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")
    with c2:
        ddist = dg.groupby("device_type", as_index=False)["orders"].sum()
        fig = px.pie(ddist, values="orders", names="device_type", hole=0.45,
                     title=f"<b>{t('orders_by_device')}</b>", color_discrete_sequence=PALETTE[2:])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader(t("heatmaps_dg"))

    def heatmap(metric: str, title: str, scale: str, fmt: str):
        pivot = dg.pivot(index="device_type", columns="customer_gender", values=metric)
        fig = go.Figure(go.Heatmap(
            z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
            text=pivot.values, texttemplate=fmt, textfont={"size": 13},
            colorscale=scale, colorbar=dict(title="")))
        fig.update_layout(title=f"<b>{title}</b>", height=330, margin=dict(l=10, r=10, t=50, b=10))
        return fig

    h1, h2 = st.columns(2)
    h1.plotly_chart(heatmap("revenue", t("hm_revenue"), "Teal", "$%{text:,.0f}"), width="stretch")
    h2.plotly_chart(heatmap("margin_pct", t("hm_margin"), "RdYlGn", "%{text:.1f}%"), width="stretch")
    h3, h4 = st.columns(2)
    h3.plotly_chart(heatmap("aov", t("hm_aov"), "Blues", "$%{text:,.0f}"), width="stretch")
    h4.plotly_chart(heatmap("return_rate", t("hm_return"), "Reds", "%{text:.1f}%"), width="stretch")

    st.divider()
    st.subheader(t("channels_payments"))
    c1, c2 = st.columns(2)
    with c1:
        ch = q(
            f"""SELECT traffic_source AS canal, ROUND(SUM(order_amount),2) AS revenue
                FROM orders {where} GROUP BY traffic_source ORDER BY revenue DESC""",
            params,
        )
        fig = px.bar(ch, x="revenue", y="canal", orientation="h", title=f"<b>{t('rev_by_channel')}</b>",
                     color="revenue", color_continuous_scale="Teal", text="revenue")
        fig.update_traces(texttemplate="$%{text:,.0s}", textposition="outside")
        fig.update_layout(yaxis={"categoryorder": "total ascending"}, height=380,
                          coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")
    with c2:
        pm = q(
            f"""SELECT payment_method AS metodo, COUNT(*) AS orders
                FROM orders {where} GROUP BY payment_method ORDER BY orders DESC""",
            params,
        )
        fig = px.bar(pm, x="metodo", y="orders", title=f"<b>{t('orders_by_payment')}</b>",
                     color="orders", color_continuous_scale="Teal", text="orders")
        fig.update_traces(textposition="outside")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10),
                          xaxis_tickangle=-30)
        st.plotly_chart(fig, width="stretch")

# =========================================================================== #
# TAB 4 — Insights & Acciones
# =========================================================================== #
with tab4:
    st.subheader(t("seg_by_revenue"))
    ordn = "órdenes" if LANG == "es" else "orders"
    ret_lbl = "Devol." if LANG == "es" else "Ret."
    mar_lbl = "Margen" if LANG == "es" else "Margin"
    dg2 = q(
        f"""SELECT device_type || ' - ' || customer_gender AS segmento,
                   COUNT(*) AS orders,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
                   ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate
            FROM orders {where}
            GROUP BY device_type, customer_gender
            ORDER BY revenue DESC""",
        params,
    )
    top = dg2.head(3)
    bottom = dg2.tail(3).iloc[::-1]

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"#### {t('top_segments')}")
        for _, r in top.iterrows():
            st.markdown(
                f'<div class="action-box"><h4>{r["segmento"]}</h4>'
                f'<p>Revenue <b>${float(r["revenue"]):,.0f}</b> · {mar_lbl} <b>{float(r["margin_pct"]):.1f}%</b> · '
                f'{ret_lbl} {float(r["return_rate"]):.1f}% · {int(r["orders"]):,} {ordn}</p></div>',
                unsafe_allow_html=True,
            )
    with c2:
        st.markdown(f"#### {t('low_segments')}")
        for _, r in bottom.iterrows():
            st.markdown(
                f'<div class="warning-box"><h4>{r["segmento"]}</h4>'
                f'<p>Revenue <b>${float(r["revenue"]):,.0f}</b> · {mar_lbl} <b>{float(r["margin_pct"]):.1f}%</b> · '
                f'{ret_lbl} {float(r["return_rate"]):.1f}% · {int(r["orders"]):,} {ordn}</p></div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader(t("cat_profit"))
    catm = q(
        f"""SELECT product_category AS categoria,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(SUM(profit_amount),2) AS profit,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
                   ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate
            FROM orders {where}
            GROUP BY product_category ORDER BY profit DESC""",
        params,
    )
    fig = px.scatter(catm, x="revenue", y="margin_pct", size="profit", color="return_rate",
                     hover_name="categoria", color_continuous_scale="RdYlGn_r", size_max=55,
                     title=f"<b>{t('scatter_title')}</b>",
                     labels={"revenue": t("lbl_revenue"), "margin_pct": t("lbl_margin"),
                             "return_rate": t("lbl_return")})
    fig.update_layout(height=470, margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch")

    top_cat = catm.iloc[0]
    worst_ret = catm.sort_values("return_rate", ascending=False).iloc[0]
    st.markdown(
        f'<div class="insight-box"><h4>{t("quick_read")}</h4><ul>'
        f'<li>{t("most_profitable")}: <b>{top_cat["categoria"]}</b> '
        f'(${float(top_cat["profit"]):,.0f} {t("of_profit_margin")} {float(top_cat["margin_pct"]):.1f}%).</li>'
        f'<li>{t("highest_return")}: <b>{worst_ret["categoria"]}</b> '
        f'({float(worst_ret["return_rate"]):.1f}%) — {t("review_quality")}.</li>'
        f'<li>{t("overall_margin")}: <b>{float(k["margin_pct"]):.1f}%</b> '
        f'{t("over_revenue")} ${float(k["revenue"]):,.0f} {t("of_revenue")}.</li>'
        f'</ul></div>',
        unsafe_allow_html=True,
    )

# =========================================================================== #
# TAB 5 — Asistente conversacional (agente MCP embebido en el proceso)
# =========================================================================== #
with tab5:
    st.subheader(t("assistant_title"))
    st.caption(t("assistant_caption"))

    if not os.getenv("OPENROUTER_API_KEY"):
        st.warning(t("assistant_nokey"))
    else:
        if "chat_msgs" not in st.session_state:
            st.session_state.chat_msgs = []
        if "chat_sid" not in st.session_state:
            st.session_state.chat_sid = "dash-" + uuid.uuid4().hex[:8]

        for m in st.session_state.chat_msgs:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        with st.form("chat_form", clear_on_submit=True):
            pregunta = st.text_input(t("ask_agent"), placeholder=t("ask_placeholder"))
            enviar = st.form_submit_button(t("send"))

        if enviar and pregunta.strip():
            st.session_state.chat_msgs.append({"role": "user", "content": pregunta})
            with st.chat_message("user"):
                st.markdown(pregunta)

            # Ajusta el idioma de la respuesta del agente según el toggle.
            mensaje = pregunta if LANG == "es" else pregunta + "\n\n[Please answer in English.]"

            traza = None
            with st.chat_message("assistant"):
                with st.spinner(t("agent_spinner")):
                    try:
                        ensure_data_mcp()
                        from agent_core import resolver_consulta

                        res = asyncio.run(
                            resolver_consulta(mensaje, st.session_state.chat_sid, canal="dashboard")
                        )
                        answer = res["respuesta"]
                        traza = res.get("traza")
                    except Exception as exc:  # noqa: BLE001
                        answer = f"{t('agent_error')}: {exc}"
                st.markdown(answer)

            st.session_state.chat_msgs.append({"role": "assistant", "content": answer})
            if traza:
                with st.expander(t("agent_trace")):
                    st.json(traza)

        if st.session_state.chat_msgs and st.button(t("new_chat")):
            st.session_state.chat_msgs = []
            st.session_state.chat_sid = "dash-" + uuid.uuid4().hex[:8]
            st.rerun()

st.caption(t("footer").format(b=backend_activo()))
