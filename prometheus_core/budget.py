"""Budget vs actual purchase cost per commodity and budget year.

A budget is a price per MT (USD or EGP, CIF or delivered) and optionally a quantity.
Purchases are split into ACTUAL (closed import contracts and local
purchases) and COMMITTED (open import contracts, valued at today's market
for any unpriced part).  With a budget quantity the remaining tonnage is
valued at today's market price to give a full-year forecast, and the
"headroom" price says the most the remaining MT can cost and still land on
budget.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .numbers import to_float

BUDGET_ENGINE_VERSION = "1.0"


def budget_year_of(d: dt.date | None, start_month: int = 1) -> int | None:
    """Budget year a date falls in, named by the calendar year it starts in.
    start_month=7 → 2026-07-01 … 2027-06-30 is budget year 2026 (FY 2026/27)."""
    if d is None:
        return None
    sm = max(1, min(12, int(start_month or 1)))
    return d.year if d.month >= sm else d.year - 1


def budget_year_label(year: int, start_month: int = 1) -> str:
    return str(year) if int(start_month or 1) == 1 else f"FY {year}/{str(year + 1)[-2:]}"


def budget_year_range(year: int, start_month: int = 1) -> tuple[dt.date, dt.date]:
    sm = max(1, min(12, int(start_month or 1)))
    start = dt.date(year, sm, 1)
    end = dt.date(year + 1, sm, 1) - dt.timedelta(days=1)
    return start, end


def budget_vs_actual(budget: dict[str, Any] | None, lines: list[dict[str, Any]],
                     market_mt: Any = None, today: dt.date | None = None,
                     start_month: int = 1, year: int | None = None) -> dict[str, Any]:
    """budget: {price_mt, qty_mt}; lines: [{kind: ACTUAL|COMMITTED, qty_mt, cost_mt}].
    Currency-neutral: budget and costs just have to be in the same unit (e.g. USD/MT CIF).
    (price_egp_mt / cost_egp_mt are accepted as older names.)
    Returns totals, averages and "vs budget" figures = budget − actual
    (positive = UNDER budget = good, negative = over budget)."""
    b = budget or {}
    b_price = to_float(b.get("price_mt", b.get("price_egp_mt")), None)
    b_qty = to_float(b.get("qty_mt"), None)
    lines = [dict(l, cost_mt=l.get("cost_mt", l.get("cost_egp_mt"))) for l in lines]
    mkt = to_float(market_mt, None)

    def agg(kind):
        ls = [l for l in lines if l.get("kind") == kind and to_float(l.get("cost_mt"), None) is not None]
        q = sum(to_float(l.get("qty_mt"), 0.0) or 0.0 for l in ls)
        v = sum((to_float(l.get("qty_mt"), 0.0) or 0.0) * to_float(l.get("cost_mt"), 0.0) for l in ls)
        return q, v

    a_qty, a_val = agg("ACTUAL")
    c_qty, c_val = agg("COMMITTED")
    missing = sum(to_float(l.get("qty_mt"), 0.0) or 0.0 for l in lines
                  if to_float(l.get("cost_mt"), None) is None)
    t_qty, t_val = a_qty + c_qty, a_val + c_val

    def avg(v, q):
        return v / q if q else None

    out = {
        "budget_price": b_price, "budget_qty": b_qty,
        "budget_value": (b_price * b_qty) if (b_price is not None and b_qty) else None,
        "actual_qty": a_qty, "actual_value": a_val, "actual_avg": avg(a_val, a_qty),
        "committed_qty": c_qty, "committed_value": c_val, "committed_avg": avg(c_val, c_qty),
        "bought_qty": t_qty, "bought_value": t_val, "bought_avg": avg(t_val, t_qty),
        "no_cost_qty": missing, "market_price": mkt,
        "vs_budget_mt": None, "vs_budget_total": None, "vs_budget_pct": None,
        "remaining_qty": None, "remaining_value": None, "forecast_value": None, "forecast_avg": None,
        "forecast_vs_budget_total": None, "forecast_vs_budget_pct": None, "headroom_price": None,
        "pct_bought": None, "pct_year_elapsed": None, "status": "NO_BUDGET",
    }
    if b_price is None:
        return out
    if t_qty:
        out["vs_budget_mt"] = b_price - out["bought_avg"]
        out["vs_budget_total"] = out["vs_budget_mt"] * t_qty
        out["vs_budget_pct"] = out["vs_budget_mt"] / b_price * 100.0 if b_price else None
    if b_qty:
        rem = max(0.0, b_qty - t_qty)
        out["remaining_qty"] = rem
        out["pct_bought"] = t_qty / b_qty * 100.0
        if rem > 0:
            out["headroom_price"] = (b_price * b_qty - t_val) / rem
        if mkt is not None or rem == 0:
            rem_val = rem * (mkt or 0.0)
            out["remaining_value"] = rem_val
            fq = t_qty + rem
            out["forecast_value"] = t_val + rem_val
            out["forecast_avg"] = out["forecast_value"] / fq if fq else None
            out["forecast_vs_budget_total"] = b_price * fq - out["forecast_value"]
            out["forecast_vs_budget_pct"] = ((1.0 - out["forecast_avg"] / b_price) * 100.0
                                             if (b_price and out["forecast_avg"] is not None) else None)
    if year is not None and today is not None:
        s, e = budget_year_range(year, start_month)
        span = (e - s).days + 1
        out["pct_year_elapsed"] = max(0.0, min(100.0, ((today - s).days + 1) / span * 100.0))

    ref = (out["forecast_vs_budget_pct"] if out["forecast_vs_budget_pct"] is not None
           else out["vs_budget_pct"])
    if ref is None:
        out["status"] = "NOTHING_BOUGHT"
    elif ref < -2.0:
        out["status"] = "OVER"
    elif ref > 2.0:
        out["status"] = "UNDER"
    else:
        out["status"] = "ON_BUDGET"
    return out
