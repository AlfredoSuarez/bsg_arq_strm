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
import streamlit.components.v1 as components
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
import fpa  # noqa: E402 - capa FP&A (usa la misma db conmutable)

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
    # Marketing
    "mkt_title": {"es": "Marketing: canal, promociones y retención", "en": "Marketing: channel, promotions & retention"},
    "mkt_channel_quality": {"es": "Calidad de canal: revenue vs margen (tamaño = órdenes, color = devolución %)",
                            "en": "Channel quality: revenue vs margin (size = orders, color = return %)"},
    "lbl_channel": {"es": "Canal", "en": "Channel"},
    "mkt_coupon": {"es": "Impacto de cupones", "en": "Coupon impact"},
    "mkt_with": {"es": "Con cupón", "en": "With coupon"},
    "mkt_without": {"es": "Sin cupón", "en": "Without coupon"},
    "mkt_uplift": {"es": "Uplift de ticket con cupón", "en": "AOV uplift with coupon"},
    "mkt_retention": {"es": "Retención y recompra", "en": "Retention & repeat purchase"},
    "mkt_repeat_rate": {"es": "Tasa de recompra", "en": "Repeat rate"},
    "mkt_repeat_sub": {"es": "Clientes con más de 1 orden", "en": "Customers with more than 1 order"},
    "mkt_avg_orders": {"es": "Órdenes por cliente", "en": "Orders per customer"},
    "mkt_avg_spend": {"es": "Gasto por cliente", "en": "Spend per customer"},
    "mkt_buckets": {"es": "Clientes por número de órdenes", "en": "Customers by order count"},
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
    "mem_title": {"es": "Memoria del agente (corto + largo plazo)", "en": "Agent memory (short + long term)"},
    "mem_recalled": {"es": "Recuerdos recuperados (largo plazo)", "en": "Recalled memories (long term)"},
    "footer": {"es": "Portal BI E-commerce · backend: {b} · datos de uso técnico/pedagógico.",
               "en": "E-commerce BI Portal · backend: {b} · technical/educational data."},
    # FP&A
    "tab_fpa": {"es": "💼 FP&A", "en": "💼 FP&A"},
    "fpa_year": {"es": "Año", "en": "Year"},
    "fpa_all": {"es": "Todos", "en": "All"},
    "fpa_note": {"es": "FP&A a nivel compañía (no aplica el filtro de país). Actuals reales; budget/forecast/recurring modelados.",
                 "en": "Company-wide FP&A (country filter not applied). Real actuals; budget/forecast/recurring are modeled."},
    "sub_pl": {"es": "P&L ejecutivo", "en": "Executive P&L"},
    "sub_bva": {"es": "Budget vs Actual", "en": "Budget vs Actual"},
    "sub_forecast": {"es": "Forecast", "en": "Forecast"},
    "sub_scenario": {"es": "Escenarios", "en": "Scenarios"},
    "sub_recurring": {"es": "Recurring Revenue", "en": "Recurring Revenue"},
    # Deck (presentación ejecutiva embebida desde Gamma)
    "tab_deck": {"es": "🎤 Deck", "en": "🎤 Deck"},
    "deck_head": {"es": "Presentación ejecutiva del proyecto",
                  "en": "Executive project presentation"},
    "deck_sub": {"es": "Arquitectura MCP · LangChain · Supabase · Streamlit — recorrido del portal, "
                       "las 15 tools de negocio y los resultados.",
                 "en": "MCP architecture · LangChain · Supabase · Streamlit — a walkthrough of the portal, "
                       "the 15 business tools and the results."},
    "deck_open": {"es": "🔗 Abrir el deck en Gamma (pantalla completa / exportar)",
                  "en": "🔗 Open the deck in Gamma (full screen / export)"},
    "deck_fallback": {"es": "Si la presentación no carga aquí, ábrela con el enlace de arriba.",
                      "en": "If the presentation does not load here, open it with the link above."},
    "pl_gp": {"es": "Utilidad bruta", "en": "Gross Profit"},
    "pl_margin": {"es": "Margen bruto", "en": "Gross margin"},
    "pl_ebitda": {"es": "EBITDA", "en": "EBITDA"},
    "pl_ebitda_margin": {"es": "Margen EBITDA", "en": "EBITDA margin"},
    "pl_yoy": {"es": "Crecimiento YoY", "en": "YoY growth"},
    "pl_cogs": {"es": "COGS", "en": "COGS"},
    "pl_assumptions": {"es": "Supuestos: OpEx {opex}% de revenue · budget = año previo +{g}% · margen meta {mt}% · EBITDA = Utilidad bruta − OpEx.",
                       "en": "Assumptions: OpEx {opex}% of revenue · budget = prior year +{g}% · target margin {mt}% · EBITDA = Gross Profit − OpEx."},
    "pl_monthly": {"es": "Revenue y utilidad bruta por mes", "en": "Revenue and gross profit by month"},
    "bva_title": {"es": "Actual vs Budget — revenue mensual", "en": "Actual vs Budget — monthly revenue"},
    "bva_variance": {"es": "Variación vs budget (%)", "en": "Variance vs budget (%)"},
    "bva_actual": {"es": "Actual", "en": "Actual"},
    "bva_budget": {"es": "Budget", "en": "Budget"},
    "bva_total_actual": {"es": "Actual total", "en": "Total actual"},
    "bva_total_budget": {"es": "Budget total", "en": "Total budget"},
    "bva_var": {"es": "Variación", "en": "Variance"},
    "bva_none": {"es": "No hay budget para este año (el modelo requiere el año previo).",
                 "en": "No budget for this year (the model requires the prior year)."},
    "fc_horizon": {"es": "Horizonte (meses)", "en": "Horizon (months)"},
    "fc_title": {"es": "Ingresos: histórico + rolling forecast", "en": "Revenue: history + rolling forecast"},
    "fc_hist": {"es": "Histórico (actual)", "en": "History (actual)"},
    "fc_fore": {"es": "Forecast", "en": "Forecast"},
    "sc_growth": {"es": "Crecimiento de ingresos %", "en": "Revenue growth %"},
    "sc_margin": {"es": "Margen bruto objetivo %", "en": "Target gross margin %"},
    "sc_opex": {"es": "OpEx (% de revenue)", "en": "OpEx (% of revenue)"},
    "sc_base_rev": {"es": "Revenue base", "en": "Base revenue"},
    "sc_new_rev": {"es": "Revenue escenario", "en": "Scenario revenue"},
    "sc_base_ebitda": {"es": "EBITDA base", "en": "Base EBITDA"},
    "sc_new_ebitda": {"es": "EBITDA escenario", "en": "Scenario EBITDA"},
    "sc_delta": {"es": "Δ EBITDA vs base", "en": "Δ EBITDA vs base"},
    "sc_tornado": {"es": "Sensibilidad: impacto en EBITDA (± 5 puntos por driver)",
                   "en": "Sensitivity: EBITDA impact (± 5 points per driver)"},
    "rec_mrr": {"es": "MRR", "en": "MRR"},
    "rec_arr": {"es": "ARR", "en": "ARR"},
    "rec_paying": {"es": "Miembros de pago", "en": "Paying members"},
    "rec_arpu": {"es": "ARPU", "en": "ARPU"},
    "rec_trend": {"es": "MRR mensual por tier de membresía", "en": "Monthly MRR by membership tier"},
    "rec_bytier": {"es": "MRR por tier (último mes)", "en": "MRR by tier (last month)"},
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


# Wrappers cacheados de la capa FP&A (evitan re-consultar en cada rerun).
@st.cache_data(ttl=600, show_spinner=False)
def fpa_actuals() -> pd.DataFrame:
    return fpa.actuals_monthly()


@st.cache_data(ttl=600, show_spinner=False)
def fpa_budget(year: int | None) -> pd.DataFrame:
    return fpa.budget_vs_actual(year)


@st.cache_data(ttl=600, show_spinner=False)
def fpa_forecast(horizon: int) -> pd.DataFrame:
    return fpa.forecast(horizon)


@st.cache_data(ttl=600, show_spinner=False)
def fpa_recurring() -> pd.DataFrame:
    return fpa.recurring_monthly()


@st.cache_data(ttl=600, show_spinner=False)
def fpa_pl(year: int | None) -> dict:
    return fpa.executive_pl(year)


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

tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
    [t("tab_summary"), t("tab_trend"), t("tab_segment"), t("tab_insights"), t("tab_fpa"),
     t("tab_assistant"), t("tab_deck")]
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

    # ---- Marketing: canal, promociones y retención ----
    st.divider()
    st.subheader(t("mkt_title"))
    _mw = "margen" if LANG == "es" else "margin"

    ch2 = q(
        f"""SELECT traffic_source AS canal, COUNT(*) AS orders,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
                   ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate
            FROM orders {where} GROUP BY traffic_source ORDER BY revenue DESC""",
        params,
    )
    fig = px.scatter(ch2, x="revenue", y="margin_pct", size="orders", color="return_rate",
                     hover_name="canal", color_continuous_scale="RdYlGn_r", size_max=55,
                     title=f"<b>{t('mkt_channel_quality')}</b>",
                     labels={"revenue": t("lbl_revenue"), "margin_pct": t("lbl_margin"),
                             "return_rate": t("lbl_return")})
    fig.update_layout(height=430, margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch")

    cA, cB = st.columns(2)
    with cA:
        st.markdown(f"#### {t('mkt_coupon')}")
        cp = q(
            f"""SELECT coupon_used, ROUND(AVG(order_amount),2) AS aov,
                       ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct,
                       ROUND(AVG(discount_percent),2) AS avg_discount
                FROM orders {where} GROUP BY coupon_used""",
            params,
        ).set_index("coupon_used")
        wc = cp.loc["Yes"] if "Yes" in cp.index else None
        nc = cp.loc["No"] if "No" in cp.index else None
        m1, m2 = st.columns(2)
        if wc is not None:
            m1.metric(t("mkt_with"), f"${float(wc['aov']):,.0f}", f"{float(wc['margin_pct']):.1f}% {_mw}")
        if nc is not None:
            m2.metric(t("mkt_without"), f"${float(nc['aov']):,.0f}", f"{float(nc['margin_pct']):.1f}% {_mw}")
        if wc is not None and nc is not None and float(nc["aov"]):
            uplift = 100.0 * (float(wc["aov"]) - float(nc["aov"])) / float(nc["aov"])
            st.caption(f"{t('mkt_uplift')}: {uplift:+.1f}%")
    with cB:
        st.markdown(f"#### {t('mkt_retention')}")
        ret = q(
            f"""SELECT ROUND(100.0*SUM(CASE WHEN n>1 THEN 1 ELSE 0 END)/COUNT(*),2) AS repeat_rate,
                       ROUND(AVG(n),2) AS avg_orders, ROUND(AVG(spend),2) AS avg_spend
                FROM (SELECT customer_id, COUNT(*) AS n, SUM(order_amount) AS spend
                      FROM orders {where} GROUP BY customer_id) t""",
            params,
        ).iloc[0]
        r1, r2 = st.columns(2)
        r1.metric(t("mkt_repeat_rate"), f"{float(ret['repeat_rate']):.1f}%", t("mkt_repeat_sub"))
        r2.metric(t("mkt_avg_orders"), f"{float(ret['avg_orders']):.2f}",
                  f"${float(ret['avg_spend']):,.0f} · {t('mkt_avg_spend').lower()}")

    buckets = q(
        f"""SELECT CASE WHEN n=1 THEN '1' WHEN n BETWEEN 2 AND 3 THEN '2-3'
                        WHEN n BETWEEN 4 AND 5 THEN '4-5' ELSE '6+' END AS bucket,
                   COUNT(*) AS customers
            FROM (SELECT customer_id, COUNT(*) AS n FROM orders {where} GROUP BY customer_id) t
            GROUP BY 1""",
        params,
    )
    order_b = ["1", "2-3", "4-5", "6+"]
    buckets["bucket"] = pd.Categorical(buckets["bucket"], categories=order_b, ordered=True)
    buckets = buckets.sort_values("bucket")
    figb = px.bar(buckets, x="bucket", y="customers", title=f"<b>{t('mkt_buckets')}</b>",
                  color="customers", color_continuous_scale="Teal", text="customers")
    figb.update_traces(textposition="outside")
    figb.update_layout(height=320, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(figb, width="stretch")

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
# TAB 5 — FP&A (Planeación y Análisis Financiero)
# =========================================================================== #
with tab5:
    st.caption(t("fpa_note"))
    fa = fpa_actuals()
    fpa_years = sorted(int(y) for y in fa["year"].unique())
    f_pl, f_bva, f_fc, f_sc, f_rec = st.tabs(
        [t("sub_pl"), t("sub_bva"), t("sub_forecast"), t("sub_scenario"), t("sub_recurring")]
    )

    # ---- P&L ejecutivo ----
    with f_pl:
        yopt = [t("fpa_all")] + [str(y) for y in fpa_years]
        ysel = st.selectbox(t("fpa_year"), yopt, index=len(yopt) - 1, key="pl_year")
        year = None if ysel == t("fpa_all") else int(ysel)
        pl = fpa_pl(year)
        c1, c2, c3, c4 = st.columns(4)
        kpi_card(c1, t("kpi_revenue"), f"${pl['revenue']:,.0f}", t("kpi_revenue_sub"))
        kpi_card(c2, t("pl_gp"), f"${pl['gross_profit']:,.0f}", f"{t('pl_margin')} {pl['gross_margin_pct']:.1f}%")
        kpi_card(c3, t("pl_ebitda"), f"${pl['ebitda']:,.0f}", f"{t('pl_ebitda_margin')} {pl['ebitda_margin_pct']:.1f}%")
        yoy = pl.get("revenue_growth_yoy_pct")
        kpi_card(c4, t("pl_yoy"), f"{yoy:+.1f}%" if yoy is not None else "—", t("kpi_revenue"))
        c5, c6, c7, c8 = st.columns(4)
        kpi_card(c5, t("pl_cogs"), f"${pl['cogs']:,.0f}", "Revenue − GP")
        kpi_card(c6, "OpEx", f"${pl['opex']:,.0f}", f"{int(fpa.OPEX_PCT*100)}% revenue")
        kpi_card(c7, t("kpi_orders"), f"{pl['orders']:,}", "")
        kpi_card(c8, t("kpi_aov"), f"${pl['aov']:,.2f}", "")

        m = fa if year is None else fa[fa["year"] == year]
        fig = make_subplots(specs=[[{"secondary_y": True}]])
        fig.add_trace(go.Bar(x=m["period"], y=m["revenue"], name=t("kpi_revenue"),
                             marker_color="#2E86AB", opacity=0.85), secondary_y=False)
        fig.add_trace(go.Scatter(x=m["period"], y=m["gross_profit"], name=t("pl_gp"),
                                 mode="lines+markers", line=dict(color="#06A77D", width=3)), secondary_y=True)
        fig.update_layout(title=f"<b>{t('pl_monthly')}</b>", height=420, hovermode="x unified",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          margin=dict(l=10, r=10, t=60, b=10))
        fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
        fig.update_yaxes(title_text="GP ($)", secondary_y=True)
        st.plotly_chart(fig, width="stretch")
        st.caption(t("pl_assumptions").format(opex=int(fpa.OPEX_PCT*100), g=int(fpa.GROWTH_BUDGET*100), mt=int(fpa.MARGIN_TARGET*100)))

    # ---- Budget vs Actual ----
    with f_bva:
        budget_years = [y for y in fpa_years if (y - 1) in fpa_years]
        if not budget_years:
            st.info(t("bva_none"))
        else:
            ysel = st.selectbox(t("fpa_year"), [str(y) for y in budget_years],
                                index=len(budget_years) - 1, key="bva_year")
            b = fpa_budget(int(ysel))
            if b.empty:
                st.info(t("bva_none"))
            else:
                ta, tb_ = float(b["revenue"].sum()), float(b["budget_revenue"].sum())
                c1, c2, c3 = st.columns(3)
                c1.metric(t("bva_total_actual"), f"${ta:,.0f}")
                c2.metric(t("bva_total_budget"), f"${tb_:,.0f}")
                c3.metric(t("bva_var"), f"${ta-tb_:,.0f}", f"{100*(ta-tb_)/tb_:+.1f}%")
                fig = go.Figure()
                fig.add_trace(go.Bar(x=b["period"], y=b["budget_revenue"], name=t("bva_budget"), marker_color="#A23B72", opacity=0.6))
                fig.add_trace(go.Bar(x=b["period"], y=b["revenue"], name=t("bva_actual"), marker_color="#2E86AB"))
                fig.update_layout(title=f"<b>{t('bva_title')}</b>", barmode="group", height=380,
                                  legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                                  margin=dict(l=10, r=10, t=60, b=10))
                st.plotly_chart(fig, width="stretch")
                colors = ["#06A77D" if v >= 0 else "#E63946" for v in b["var_revenue_pct"]]
                figv = go.Figure(go.Bar(x=b["period"], y=b["var_revenue_pct"], marker_color=colors,
                                        text=[f"{v:+.1f}%" for v in b["var_revenue_pct"]], textposition="outside"))
                figv.update_layout(title=f"<b>{t('bva_variance')}</b>", height=320, margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(figv, width="stretch")

    # ---- Rolling Forecast ----
    with f_fc:
        horizon = st.slider(t("fc_horizon"), 6, 24, 12, key="fc_h")
        fc = fpa_forecast(horizon)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=fa["period"], y=fa["revenue"], name=t("fc_hist"),
                                 mode="lines", line=dict(color="#2E86AB", width=2)))
        fig.add_trace(go.Scatter(x=fc["period"], y=fc["forecast_revenue"], name=t("fc_fore"),
                                 mode="lines+markers", line=dict(color="#F18F01", width=3, dash="dash")))
        fig.update_layout(title=f"<b>{t('fc_title')}</b>", height=440, hovermode="x unified",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                          margin=dict(l=10, r=10, t=60, b=10))
        st.plotly_chart(fig, width="stretch")
        c1, c2 = st.columns(2)
        c1.metric(t("fc_fore") + " Σ", f"${fc['forecast_revenue'].sum():,.0f}")
        c2.metric(t("fc_fore") + " ⌀/mes", f"${fc['forecast_revenue'].mean():,.0f}")

    # ---- Escenarios & Sensibilidad ----
    with f_sc:
        yopt = [t("fpa_all")] + [str(y) for y in fpa_years]
        ysel = st.selectbox(t("fpa_year"), yopt, index=len(yopt) - 1, key="sc_year")
        year = None if ysel == t("fpa_all") else int(ysel)
        base = fpa_pl(year)
        base_rev, base_ebitda = base["revenue"], base["ebitda"]
        c1, c2, c3 = st.columns(3)
        g = c1.slider(t("sc_growth"), -30, 50, 10, key="sc_g")
        mgn = c2.slider(t("sc_margin"), 5, 40, int(round(base["gross_margin_pct"])), key="sc_m")
        opx = c3.slider(t("sc_opex"), 5, 35, int(fpa.OPEX_PCT * 100), key="sc_o")
        new_rev = base_rev * (1 + g / 100.0)
        new_ebitda = new_rev * (mgn / 100.0) - (opx / 100.0) * new_rev
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(t("sc_base_rev"), f"${base_rev:,.0f}")
        m2.metric(t("sc_new_rev"), f"${new_rev:,.0f}", f"{g:+d}%")
        m3.metric(t("sc_new_ebitda"), f"${new_ebitda:,.0f}")
        delta = new_ebitda - base_ebitda
        m4.metric(t("sc_delta"), f"${delta:,.0f}",
                  f"{100*delta/base_ebitda:+.1f}%" if base_ebitda else "—")
        # Tornado de sensibilidad (± 5 puntos por driver)
        base_m, base_o = base["gross_margin_pct"], fpa.OPEX_PCT * 100
        def _eb(gr, mr, op):
            r = base_rev * (1 + gr / 100.0)
            return r * (mr / 100.0) - (op / 100.0) * r
        sens = [
            ("Revenue growth %", _eb(-5, base_m, base_o), _eb(5, base_m, base_o)),
            (t("pl_margin"), _eb(0, base_m - 5, base_o), _eb(0, base_m + 5, base_o)),
            ("OpEx %", _eb(0, base_m, base_o + 5), _eb(0, base_m, base_o - 5)),
        ]
        sens.sort(key=lambda s: abs(s[2] - s[1]))
        figt = go.Figure()
        for name, lo, hi in sens:
            figt.add_trace(go.Bar(y=[name], x=[hi - lo], base=lo, orientation="h",
                                  marker_color="#2E86AB", showlegend=False,
                                  text=f"${lo:,.0f} → ${hi:,.0f}", textposition="auto"))
        figt.update_layout(title=f"<b>{t('sc_tornado')}</b>", height=300, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(figt, width="stretch")

    # ---- Recurring Revenue ----
    with f_rec:
        r = fpa_recurring()
        rec = fpa.recurring_summary(None)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("rec_mrr"), f"${rec['mrr']:,.0f}", rec["period"])
        c2.metric(t("rec_arr"), f"${rec['arr']:,.0f}")
        c3.metric(t("rec_paying"), f"{rec['paying_members']:,}")
        c4.metric(t("rec_arpu"), f"${rec['arpu']:,.2f}")
        piv = r.pivot_table(index="period", columns="tier", values="mrr", aggfunc="sum").fillna(0)
        order = [c for c in ["Silver", "Gold", "Platinum", "Standard"] if c in piv.columns]
        figm = go.Figure()
        pal = {"Silver": "#A0A0A0", "Gold": "#F1C40F", "Platinum": "#9B59B6", "Standard": "#BDC3C7"}
        for tier in order:
            figm.add_trace(go.Scatter(x=piv.index, y=piv[tier], name=tier, mode="lines",
                                      stackgroup="one", line=dict(width=0.5, color=pal.get(tier))))
        figm.update_layout(title=f"<b>{t('rec_trend')}</b>", height=400, hovermode="x unified",
                           margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(figm, width="stretch")
        bt = pd.DataFrame(rec["by_tier"])
        bt = bt[bt["mrr"] > 0]
        figb = px.bar(bt, x="tier", y="mrr", title=f"<b>{t('rec_bytier')}</b>", color="tier",
                      color_discrete_map=pal, text="mrr")
        figb.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
        figb.update_layout(height=340, showlegend=False, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(figb, width="stretch")


# =========================================================================== #
# TAB 6 — Asistente conversacional (agente MCP embebido en el proceso)
# =========================================================================== #
with tab6:
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

            traza = memoria = recuerdos = None
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
                        memoria = res.get("memoria")
                        recuerdos = res.get("recuerdos")
                    except Exception as exc:  # noqa: BLE001
                        answer = f"{t('agent_error')}: {exc}"
                st.markdown(answer)

            st.session_state.chat_msgs.append({"role": "assistant", "content": answer})
            if memoria:
                with st.expander(t("mem_title")):
                    st.json(memoria)
                    if recuerdos:
                        st.caption(t("mem_recalled"))
                        st.json(recuerdos)
            if traza:
                with st.expander(t("agent_trace")):
                    st.json(traza)

        if st.session_state.chat_msgs and st.button(t("new_chat")):
            st.session_state.chat_msgs = []
            st.session_state.chat_sid = "dash-" + uuid.uuid4().hex[:8]
            st.rerun()

# =========================================================================== #
# TAB 7 — Deck ejecutivo: presentación del proyecto embebida desde Gamma.
# El deck incluye el link de esta app y del repositorio.
# =========================================================================== #
GAMMA_DOC = "https://gamma.app/docs/3o80lr80zn71soc"
GAMMA_EMBED = "https://gamma.app/embed/3o80lr80zn71soc"

with tab7:
    st.subheader(t("deck_head"))
    st.caption(t("deck_sub"))
    st.link_button(t("deck_open"), GAMMA_DOC)
    # Gamma puede restringir el iframe en algunos navegadores; el enlace de arriba
    # siempre funciona como respaldo.
    components.iframe(GAMMA_EMBED, height=640, scrolling=True)
    st.caption(t("deck_fallback"))

st.caption(t("footer").format(b=backend_activo()))
