"""
Portal BI E-commerce — Dashboard analítico (Streamlit + Plotly).

Lee de la MISMA capa de datos conmutable que el resto del proyecto (db.py):

    DB_BACKEND=sqlite    -> data/ecommerce_orders.db
    DB_BACKEND=supabase  -> DATABASE_URL (Postgres de Supabase)

Ejecutar:
    streamlit run dashboard.py

Reutiliza el patrón visual del dashboard de referencia (tabs, tarjetas, heatmaps
device × género) pero enfocado en ventas, margen, geografía y devoluciones sobre
el dataset real de 30.000 órdenes.
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
    """Levanta mcp_datos.py como subproceso HTTP una sola vez (para el asistente).

    Hereda el entorno (DATABASE_URL, etc.), así el MCP consulta el mismo Supabase.
    """
    if _port_open(DATA_MCP_HOST, DATA_MCP_PORT):
        return "externo"  # ya corriendo (dev local con mcp_datos.py aparte)
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

st.set_page_config(
    page_title="Portal BI E-commerce",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Estilos (adaptados del patrón de referencia, legibles en claro y oscuro).
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
# Acceso a datos: usa la capa conmutable y devuelve DataFrames cacheados.
# --------------------------------------------------------------------------- #
@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    df = pd.DataFrame(run_query(sql, params))
    # Postgres devuelve numéricos como Decimal (dtype object); Plotly exige float.
    # Convierte solo columnas cuyos valores no nulos sean todos numéricos.
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
    st.error(f"No fue posible leer los datos (backend: {backend_activo()}): {exc}")
    st.info(
        "En la nube define el secret **DATABASE_URL** (Supabase) — con eso la app usa "
        "Postgres automáticamente. En local con SQLite, ejecuta antes "
        "`python data/import_dataset_to_sqlite.py`."
    )
    st.stop()

all_years = [int(y) for y in years_df["year"].tolist()]
all_countries = countries_df["country"].tolist()

with st.sidebar:
    st.header("Filtros")
    st.caption(f"Backend activo: **{backend_activo()}**")
    sel_years = st.multiselect("Año", all_years, default=all_years)
    sel_countries = st.multiselect("País", all_countries, default=[])
    st.divider()
    st.caption("Datos de e-commerce · uso técnico/pedagógico, no es evidencia comercial real.")

where, params = build_where(sel_years, sel_countries)

st.markdown(
    """
<div class="main-header">
    <h1>📊 Portal BI E-commerce</h1>
    <p style="font-size:1.1rem;margin-top:0.5rem;">Ventas · Rentabilidad · Geografía · Segmentación · Devoluciones</p>
</div>
""",
    unsafe_allow_html=True,
)

# KPIs globales (respetan el filtro).
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
    st.warning("No hay datos para el filtro seleccionado.")
    st.stop()

k = kpis.iloc[0]
st.sidebar.metric("Órdenes (filtro)", f"{int(k['orders']):,}")
st.sidebar.metric("Revenue (filtro)", f"${float(k['revenue']):,.0f}")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Resumen ejecutivo", "Tendencia temporal", "Segmentación", "Insights & Acciones", "🤖 Asistente"]
)

# =========================================================================== #
# TAB 1 — Resumen ejecutivo
# =========================================================================== #
with tab1:
    st.subheader("Indicadores clave")
    c1, c2, c3, c4 = st.columns(4)
    kpi_card(c1, "Revenue", f"${float(k['revenue']):,.0f}", "Facturación total")
    kpi_card(c2, "Profit", f"${float(k['profit']):,.0f}", f"Margen {float(k['margin_pct']):.1f}%")
    kpi_card(c3, "Órdenes", f"{int(k['orders']):,}", f"{int(k['customers']):,} clientes")
    kpi_card(c4, "Ticket promedio", f"${float(k['aov']):,.2f}", "Order Amount medio")

    c5, c6, c7, c8 = st.columns(4)
    kpi_card(c5, "Tasa de devolución", f"{float(k['return_rate']):.1f}%", "Órdenes devueltas")
    kpi_card(c6, "Rating medio", f"{float(k['rating']):.2f} / 5", "Satisfacción")
    kpi_card(c7, "Margen", f"{float(k['margin_pct']):.1f}%", "Profit / Revenue")
    kpi_card(
        c8, "Revenue / cliente",
        f"${float(k['revenue'])/max(int(k['customers']),1):,.0f}", "Promedio",
    )

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
        fig = px.bar(
            cat, x="revenue", y="categoria", orientation="h",
            title="<b>Revenue por categoría</b>", color="revenue",
            color_continuous_scale="Teal", text="revenue",
        )
        fig.update_traces(texttemplate="$%{text:,.0f}", textposition="outside")
        fig.update_layout(
            yaxis={"categoryorder": "total ascending"}, height=430,
            coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10),
        )
        st.plotly_chart(fig, width="stretch")

    with right:
        country = q(
            f"""SELECT country AS pais,
                       ROUND(SUM(order_amount),2) AS revenue
                FROM orders {where}
                GROUP BY country ORDER BY revenue DESC LIMIT 10""",
            params,
        )
        fig = px.bar(
            country, x="pais", y="revenue", title="<b>Top 10 países por revenue</b>",
            color="revenue", color_continuous_scale="Teal", text="revenue",
        )
        fig.update_traces(texttemplate="$%{text:,.0s}", textposition="outside")
        fig.update_layout(height=430, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")

    seg = q(
        f"""SELECT customer_segment AS segmento,
                   COUNT(*) AS orders,
                   ROUND(SUM(order_amount),2) AS revenue,
                   ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS margin_pct
            FROM orders {where}
            GROUP BY customer_segment ORDER BY revenue DESC""",
        params,
    )
    fig = px.bar(
        seg, x="segmento", y="revenue", color="margin_pct",
        title="<b>Revenue por segmento de cliente (color = margen %)</b>",
        color_continuous_scale="RdYlGn", text="revenue",
    )
    fig.update_traces(texttemplate="$%{text:,.0s}", textposition="outside")
    fig.update_layout(height=400, margin=dict(l=10, r=10, t=50, b=10))
    st.plotly_chart(fig, width="stretch")

# =========================================================================== #
# TAB 2 — Tendencia temporal
# =========================================================================== #
with tab2:
    st.subheader("Evolución mensual")
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
        trend["year"].astype(int).astype(str)
        + "-"
        + trend["month"].astype(int).astype(str).str.zfill(2)
    )

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Bar(x=trend["periodo"], y=trend["revenue"], name="Revenue",
               marker_color="#2E86AB", opacity=0.85),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=trend["periodo"], y=trend["profit"], name="Profit",
                   mode="lines+markers", line=dict(color="#06A77D", width=3)),
        secondary_y=True,
    )
    fig.update_layout(
        title="<b>Revenue y Profit por mes</b>", height=460, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=60, b=10),
    )
    fig.update_yaxes(title_text="Revenue ($)", secondary_y=False)
    fig.update_yaxes(title_text="Profit ($)", secondary_y=True)
    st.plotly_chart(fig, width="stretch")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenue medio/mes", f"${trend['revenue'].mean():,.0f}")
    best = trend.loc[trend["revenue"].idxmax()]
    worst = trend.loc[trend["revenue"].idxmin()]
    c2.metric("Mejor mes", best["periodo"], f"${float(best['revenue']):,.0f}")
    c3.metric("Peor mes", worst["periodo"], f"${float(worst['revenue']):,.0f}")
    c4.metric("Órdenes medias/mes", f"{trend['orders'].mean():,.0f}")

    st.divider()
    st.subheader("Órdenes y ticket promedio")
    fig2 = make_subplots(specs=[[{"secondary_y": True}]])
    fig2.add_trace(
        go.Bar(x=trend["periodo"], y=trend["orders"], name="Órdenes", marker_color="#A23B72", opacity=0.7),
        secondary_y=False,
    )
    fig2.add_trace(
        go.Scatter(x=trend["periodo"], y=trend["aov"], name="Ticket promedio",
                   mode="lines+markers", line=dict(color="#F18F01", width=3)),
        secondary_y=True,
    )
    fig2.update_layout(
        height=400, hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=30, b=10),
    )
    fig2.update_yaxes(title_text="Órdenes", secondary_y=False)
    fig2.update_yaxes(title_text="Ticket ($)", secondary_y=True)
    st.plotly_chart(fig2, width="stretch")

# =========================================================================== #
# TAB 3 — Segmentación (device × género, al estilo del dashboard de referencia)
# =========================================================================== #
with tab3:
    st.subheader("Distribución de usuarios")
    dg = q(
        f"""SELECT device_type, customer_gender,
                   COUNT(*) AS orders,
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
                     title="<b>Órdenes por género</b>", color_discrete_sequence=PALETTE)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")
    with c2:
        ddist = dg.groupby("device_type", as_index=False)["orders"].sum()
        fig = px.pie(ddist, values="orders", names="device_type", hole=0.45,
                     title="<b>Órdenes por dispositivo</b>", color_discrete_sequence=PALETTE[2:])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=360, margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig, width="stretch")

    st.divider()
    st.subheader("Heatmaps: dispositivo × género")

    def heatmap(metric: str, title: str, scale: str, fmt: str):
        pivot = dg.pivot(index="device_type", columns="customer_gender", values=metric)
        fig = go.Figure(
            go.Heatmap(
                z=pivot.values, x=list(pivot.columns), y=list(pivot.index),
                text=pivot.values, texttemplate=fmt, textfont={"size": 13},
                colorscale=scale, colorbar=dict(title=""),
            )
        )
        fig.update_layout(title=f"<b>{title}</b>", height=330, margin=dict(l=10, r=10, t=50, b=10))
        return fig

    h1, h2 = st.columns(2)
    h1.plotly_chart(heatmap("revenue", "Revenue", "Teal", "$%{text:,.0f}"), width="stretch")
    h2.plotly_chart(heatmap("margin_pct", "Margen %", "RdYlGn", "%{text:.1f}%"), width="stretch")
    h3, h4 = st.columns(2)
    h3.plotly_chart(heatmap("aov", "Ticket promedio", "Blues", "$%{text:,.0f}"), width="stretch")
    h4.plotly_chart(heatmap("return_rate", "Tasa de devolución %", "Reds", "%{text:.1f}%"), width="stretch")

    st.divider()
    st.subheader("Canales y métodos de pago")
    c1, c2 = st.columns(2)
    with c1:
        ch = q(
            f"""SELECT traffic_source AS canal, ROUND(SUM(order_amount),2) AS revenue
                FROM orders {where} GROUP BY traffic_source ORDER BY revenue DESC""",
            params,
        )
        fig = px.bar(ch, x="revenue", y="canal", orientation="h", title="<b>Revenue por canal de tráfico</b>",
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
        fig = px.bar(pm, x="metodo", y="orders", title="<b>Órdenes por método de pago</b>",
                     color="orders", color_continuous_scale="Teal", text="orders")
        fig.update_traces(textposition="outside")
        fig.update_layout(height=380, coloraxis_showscale=False, margin=dict(l=10, r=10, t=50, b=10),
                          xaxis_tickangle=-30)
        st.plotly_chart(fig, width="stretch")

# =========================================================================== #
# TAB 4 — Insights & Acciones
# =========================================================================== #
with tab4:
    st.subheader("Segmentos device × género (por revenue)")
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
        st.markdown("#### Top segmentos")
        for _, r in top.iterrows():
            st.markdown(
                f'<div class="action-box"><h4>{r["segmento"]}</h4>'
                f'<p>Revenue <b>${float(r["revenue"]):,.0f}</b> · Margen <b>{float(r["margin_pct"]):.1f}%</b> · '
                f'Devol. {float(r["return_rate"]):.1f}% · {int(r["orders"]):,} órdenes</p></div>',
                unsafe_allow_html=True,
            )
    with c2:
        st.markdown("#### Segmentos de menor revenue")
        for _, r in bottom.iterrows():
            st.markdown(
                f'<div class="warning-box"><h4>{r["segmento"]}</h4>'
                f'<p>Revenue <b>${float(r["revenue"]):,.0f}</b> · Margen <b>{float(r["margin_pct"]):.1f}%</b> · '
                f'Devol. {float(r["return_rate"]):.1f}% · {int(r["orders"]):,} órdenes</p></div>',
                unsafe_allow_html=True,
            )

    st.divider()
    st.subheader("Categorías por rentabilidad")
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
    fig = px.scatter(
        catm, x="revenue", y="margin_pct", size="profit", color="return_rate",
        hover_name="categoria", color_continuous_scale="RdYlGn_r", size_max=55,
        title="<b>Revenue vs Margen por categoría (tamaño = profit, color = devolución %)</b>",
        labels={"revenue": "Revenue ($)", "margin_pct": "Margen %", "return_rate": "Devolución %"},
    )
    fig.update_layout(height=470, margin=dict(l=10, r=10, t=60, b=10))
    st.plotly_chart(fig, width="stretch")

    top_cat = catm.iloc[0]
    worst_ret = catm.sort_values("return_rate", ascending=False).iloc[0]
    st.markdown(
        f'<div class="insight-box"><h4>Lectura rápida</h4><ul>'
        f'<li>Categoría más rentable: <b>{top_cat["categoria"]}</b> '
        f'(${float(top_cat["profit"]):,.0f} de profit, margen {float(top_cat["margin_pct"]):.1f}%).</li>'
        f'<li>Mayor tasa de devolución: <b>{worst_ret["categoria"]}</b> '
        f'({float(worst_ret["return_rate"]):.1f}%) — revisar calidad, tallas o descripción.</li>'
        f'<li>Margen global del filtro: <b>{float(k["margin_pct"]):.1f}%</b> '
        f'sobre ${float(k["revenue"]):,.0f} de revenue.</li>'
        f'</ul></div>',
        unsafe_allow_html=True,
    )

# =========================================================================== #
# TAB 5 — Asistente conversacional (agente MCP embebido en el proceso)
# =========================================================================== #
with tab5:
    st.subheader("Asistente conversacional")
    st.caption(
        "Agente LangChain (vía OpenRouter) que consulta los mismos datos a través "
        "del MCP de datos, en el mismo proceso del dashboard."
    )

    if not os.getenv("OPENROUTER_API_KEY"):
        st.warning(
            "Configura el secret **OPENROUTER_API_KEY** (Settings → Secrets) "
            "para habilitar el asistente."
        )
    else:
        if "chat_msgs" not in st.session_state:
            st.session_state.chat_msgs = []
        if "chat_sid" not in st.session_state:
            st.session_state.chat_sid = "dash-" + uuid.uuid4().hex[:8]

        for m in st.session_state.chat_msgs:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

        with st.form("chat_form", clear_on_submit=True):
            pregunta = st.text_input(
                "Pregunta al agente",
                placeholder="Ej.: ¿Qué país genera más utilidad en 2024?",
            )
            enviar = st.form_submit_button("Enviar")

        if enviar and pregunta.strip():
            st.session_state.chat_msgs.append({"role": "user", "content": pregunta})
            with st.chat_message("user"):
                st.markdown(pregunta)

            traza = None
            with st.chat_message("assistant"):
                with st.spinner("El agente consulta los datos vía MCP..."):
                    try:
                        ensure_data_mcp()
                        from agent_core import resolver_consulta

                        res = asyncio.run(
                            resolver_consulta(
                                pregunta, st.session_state.chat_sid, canal="dashboard"
                            )
                        )
                        answer = res["respuesta"]
                        traza = res.get("traza")
                    except Exception as exc:  # noqa: BLE001
                        answer = f"No fue posible responder: {exc}"
                st.markdown(answer)

            st.session_state.chat_msgs.append({"role": "assistant", "content": answer})
            if traza:
                with st.expander("Traza de orquestación (tools MCP invocadas)"):
                    st.json(traza)

        if st.session_state.chat_msgs and st.button("Nueva conversación"):
            st.session_state.chat_msgs = []
            st.session_state.chat_sid = "dash-" + uuid.uuid4().hex[:8]
            st.rerun()

st.caption(
    f"Portal BI E-commerce · backend: {backend_activo()} · "
    "datos de uso técnico/pedagógico."
)
