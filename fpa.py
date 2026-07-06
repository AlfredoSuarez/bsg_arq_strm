"""Capa de Planeación y Análisis Financiero (FP&A) sobre los datos de e-commerce.

Robustece el proyecto con capacidades de analista financiero, reutilizando la
MISMA capa de datos conmutable (db.py) — funciona con SQLite o Supabase.

Principio (declarado con transparencia, como en FP&A real):
    - Los ACTUALS son agregación REAL del dataset `orders`.
    - Budget, Forecast y Recurring se MODELAN sobre esos actuals con supuestos
      explícitos (abajo). No son cifras auditadas de una empresa real.

Todas las funciones devuelven DataFrames de pandas listos para graficar o para
serializar a JSON en las tools del agente.
"""
from __future__ import annotations

import pandas as pd

from db import run_query

# --- Supuestos del modelo FP&A (explícitos y ajustables) -------------------- #
GROWTH_BUDGET = 0.10        # crecimiento objetivo del budget vs año previo (+10%)
MARGIN_TARGET = 0.21        # margen bruto objetivo del budget (21%)
OPEX_PCT = 0.18             # OpEx como % de revenue (para EBITDA proxy = GP − OpEx)
FORECAST_HORIZON = 12       # meses del rolling forecast
TIER_FEES = {"Standard": 0.0, "Silver": 5.0, "Gold": 12.0, "Platinum": 25.0}

_NUM_COLS = {
    "year", "month", "revenue", "gross_profit", "gross_margin_pct", "orders",
    "aov", "return_rate_pct", "active_members", "mrr", "arr",
}


def _df(rows: list[dict]) -> pd.DataFrame:
    """Construye un DataFrame y convierte numéricos (Decimal de Postgres) a float."""
    df = pd.DataFrame(rows)
    for col in df.columns:
        if col in _NUM_COLS or df[col].dtype == object:
            conv = pd.to_numeric(df[col], errors="coerce")
            if conv.notna().any():
                # Solo reemplaza si toda columna no nula es numérica (evita romper texto).
                mask = df[col].notna()
                if mask.any() and pd.to_numeric(df[col][mask], errors="coerce").notna().all():
                    df[col] = conv
    return df


# --------------------------------------------------------------------------- #
# Actuals (reales)
# --------------------------------------------------------------------------- #
def actuals_monthly() -> pd.DataFrame:
    """Agrega los actuals mensuales reales desde `orders`."""
    sql = """
    SELECT year, month,
           ROUND(SUM(order_amount),2) AS revenue,
           ROUND(SUM(profit_amount),2) AS gross_profit,
           ROUND(100.0*SUM(profit_amount)/NULLIF(SUM(order_amount),0),2) AS gross_margin_pct,
           COUNT(*) AS orders,
           ROUND(AVG(order_amount),2) AS aov,
           ROUND(100.0*SUM(CASE WHEN returned='Yes' THEN 1 ELSE 0 END)/COUNT(*),2) AS return_rate_pct
    FROM orders
    GROUP BY year, month
    ORDER BY year, month
    """
    df = _df(run_query(sql))
    df["period"] = df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).astype(str).str.zfill(2)
    return df


def executive_pl(year: int | None = None) -> dict:
    """P&L ejecutivo agregado (opcionalmente por año) con EBITDA proxy y growth YoY."""
    a = actuals_monthly()
    scope = a if year is None else a[a["year"] == year]
    if scope.empty:
        return {"message": "Sin datos para el período"}
    revenue = float(scope["revenue"].sum())
    gp = float(scope["gross_profit"].sum())
    orders = int(scope["orders"].sum())
    opex = OPEX_PCT * revenue
    ebitda = gp - opex
    result = {
        "period": "todos" if year is None else str(year),
        "revenue": round(revenue, 2),
        "cogs": round(revenue - gp, 2),
        "gross_profit": round(gp, 2),
        "gross_margin_pct": round(100.0 * gp / revenue, 2) if revenue else 0.0,
        "opex": round(opex, 2),
        "ebitda": round(ebitda, 2),
        "ebitda_margin_pct": round(100.0 * ebitda / revenue, 2) if revenue else 0.0,
        "orders": orders,
        "aov": round(revenue / orders, 2) if orders else 0.0,
    }
    if year is not None:
        prev = a[a["year"] == year - 1]
        if not prev.empty:
            prev_rev = float(prev["revenue"].sum())
            result["revenue_growth_yoy_pct"] = round(100.0 * (revenue - prev_rev) / prev_rev, 2) if prev_rev else None
    return result


# --------------------------------------------------------------------------- #
# Budget vs Actual (budget modelado: año previo × growth, margen objetivo)
# --------------------------------------------------------------------------- #
def budget_vs_actual(year: int | None = None) -> pd.DataFrame:
    """Compara actuals vs budget driver-based (mes × año previo × (1+growth))."""
    a = actuals_monthly()
    prior = a[["year", "month", "revenue"]].copy()
    prior["year"] = prior["year"] + 1
    prior = prior.rename(columns={"revenue": "prev_revenue"})
    b = a.merge(prior, on=["year", "month"], how="left")
    b["budget_revenue"] = (b["prev_revenue"] * (1 + GROWTH_BUDGET)).round(2)
    b["budget_gross_profit"] = (b["budget_revenue"] * MARGIN_TARGET).round(2)
    b["var_revenue"] = (b["revenue"] - b["budget_revenue"]).round(2)
    b["var_revenue_pct"] = (100.0 * (b["revenue"] - b["budget_revenue"]) / b["budget_revenue"]).round(2)
    b = b[b["budget_revenue"].notna()]  # solo meses con año previo (budget definido)
    if year is not None:
        b = b[b["year"] == year]
    return b.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Rolling Forecast (proyección de los próximos N meses)
# --------------------------------------------------------------------------- #
def _yoy_growth(a: pd.DataFrame) -> float:
    """Crecimiento YoY de los últimos 12 meses vs los 12 previos (fallback +10%)."""
    if len(a) < 24:
        return GROWTH_BUDGET
    last12 = a.iloc[-12:]["revenue"].sum()
    prev12 = a.iloc[-24:-12]["revenue"].sum()
    return (last12 / prev12 - 1) if prev12 else GROWTH_BUDGET


def forecast(horizon: int = FORECAST_HORIZON) -> pd.DataFrame:
    """Rolling forecast: proyecta `horizon` meses tras el último actual (base YoY)."""
    a = actuals_monthly()
    growth = _yoy_growth(a)
    margin = float(a.iloc[-12:]["gross_margin_pct"].mean()) / 100.0
    by_key = {(int(r.year), int(r.month)): float(r.revenue) for r in a.itertuples()}
    last_year, last_month = int(a.iloc[-1]["year"]), int(a.iloc[-1]["month"])
    rows = []
    y, m = last_year, last_month
    for _ in range(horizon):
        m += 1
        if m > 12:
            m = 1
            y += 1
        base = by_key.get((y - 1, m))  # mismo mes del año anterior
        fc_rev = round(base * (1 + growth), 2) if base is not None else None
        rows.append({
            "year": y, "month": m,
            "period": f"{y}-{str(m).zfill(2)}",
            "forecast_revenue": fc_rev,
            "forecast_gross_profit": round(fc_rev * margin, 2) if fc_rev is not None else None,
        })
    return pd.DataFrame(rows)


# --------------------------------------------------------------------------- #
# Escenarios & Sensibilidad (pure Python sobre la base real)
# --------------------------------------------------------------------------- #
def base_totals(year: int | None = None) -> dict:
    pl = executive_pl(year)
    return {"revenue": pl["revenue"], "gross_margin_pct": pl["gross_margin_pct"], "ebitda": pl["ebitda"]}


def scenario(revenue_growth_pct: float, gross_margin_pct: float, opex_pct: float,
             year: int | None = None) -> dict:
    """Recalcula P&L bajo supuestos (drivers). Devuelve base, escenario y deltas."""
    base = base_totals(year)
    base_rev = base["revenue"]
    new_rev = base_rev * (1 + revenue_growth_pct / 100.0)
    new_gp = new_rev * (gross_margin_pct / 100.0)
    new_ebitda = new_gp - (opex_pct / 100.0) * new_rev
    base_ebitda = base["ebitda"]
    return {
        "drivers": {"revenue_growth_pct": revenue_growth_pct,
                     "gross_margin_pct": gross_margin_pct, "opex_pct": opex_pct},
        "base_revenue": round(base_rev, 2),
        "scenario_revenue": round(new_rev, 2),
        "base_ebitda": round(base_ebitda, 2),
        "scenario_ebitda": round(new_ebitda, 2),
        "ebitda_delta": round(new_ebitda - base_ebitda, 2),
        "ebitda_delta_pct": round(100.0 * (new_ebitda - base_ebitda) / base_ebitda, 2) if base_ebitda else None,
    }


def sensitivity(year: int | None = None, spread: float = 5.0) -> pd.DataFrame:
    """Tornado: impacto en EBITDA de mover cada driver ±spread puntos porcentuales."""
    base = base_totals(year)
    base_margin = base["gross_margin_pct"]
    drivers = [
        ("Revenue growth", "revenue_growth_pct", 0.0),
        ("Gross margin", "gross_margin_pct", base_margin),
        ("OpEx %", "opex_pct", OPEX_PCT * 100.0),
    ]
    rows = []
    for label, key, center in drivers:
        defaults = {"revenue_growth_pct": 0.0, "gross_margin_pct": base_margin, "opex_pct": OPEX_PCT * 100.0}
        low = dict(defaults); low[key] = center - spread
        high = dict(defaults); high[key] = center + spread
        e_low = scenario(**low, year=year)["scenario_ebitda"]
        e_high = scenario(**high, year=year)["scenario_ebitda"]
        rows.append({"driver": label, "ebitda_low": e_low, "ebitda_high": e_high,
                     "impact": round(abs(e_high - e_low), 2)})
    return pd.DataFrame(rows).sort_values("impact", ascending=True).reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Recurring Revenue (membresías como suscripción: MRR / ARR por tier)
# --------------------------------------------------------------------------- #
def recurring_monthly() -> pd.DataFrame:
    """MRR/ARR mensual por tier de membresía (clientes activos × cuota)."""
    sql = """
    SELECT year, month, membership_status AS tier,
           COUNT(DISTINCT customer_id) AS active_members
    FROM orders
    GROUP BY year, month, membership_status
    ORDER BY year, month
    """
    df = _df(run_query(sql))
    df["fee"] = df["tier"].map(TIER_FEES).fillna(0.0)
    df["mrr"] = (df["active_members"] * df["fee"]).round(2)
    df["arr"] = (df["mrr"] * 12).round(2)
    df["period"] = df["year"].astype(int).astype(str) + "-" + df["month"].astype(int).astype(str).str.zfill(2)
    return df


def recurring_summary(year: int | None = None) -> dict:
    """Resumen de ingreso recurrente: MRR total del último mes, ARR, ARPU por tier."""
    r = recurring_monthly()
    if year is not None:
        r = r[r["year"] == year]
    if r.empty:
        return {"message": "Sin datos"}
    last_period = r["period"].max()
    last = r[r["period"] == last_period]
    mrr = float(last["mrr"].sum())
    members = int(last["active_members"].sum())
    by_tier = [
        {"tier": row.tier, "active_members": int(row.active_members),
         "mrr": round(float(row.mrr), 2), "monthly_fee": float(row.fee)}
        for row in last.itertuples()
    ]
    return {
        "period": last_period,
        "mrr": round(mrr, 2),
        "arr": round(mrr * 12, 2),
        "paying_members": int(last[last["fee"] > 0]["active_members"].sum()),
        "arpu": round(mrr / members, 2) if members else 0.0,
        "by_tier": by_tier,
    }
