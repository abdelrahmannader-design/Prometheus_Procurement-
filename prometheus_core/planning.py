"""Stock cover and buying plan.

Projects each commodity's stock day by day:

    stock(day) = stock today + arrivals up to that day − daily use × days

and answers three questions:
* when does stock fall below the safety level (and run out completely)?
* by when must a new purchase be made, given the lead time?
* how much must be bought to stay above the safety level until the
  end of the horizon?
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .numbers import to_float

PLANNING_ENGINE_VERSION = "1.0"


def _d(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def stock_cover_plan(
    stock_mt: Any,
    daily_use_mt: Any,
    arrivals: list[dict[str, Any]] | None = None,
    today: dt.date | None = None,
    horizon_days: int = 180,
    lead_time_days: int = 45,
    safety_days: int = 15,
) -> dict[str, Any]:
    """arrivals: [{"date": ISO date, "qty_mt": float, "ref": str}].

    Arrivals without a date are listed separately (not counted), because
    counting them on an arbitrary day would hide or invent a shortage.
    """
    today = today or dt.date.today()
    stock0 = to_float(stock_mt, 0.0) or 0.0
    rate = to_float(daily_use_mt, None)
    horizon = max(1, int(horizon_days or 180))
    lead = max(0, int(lead_time_days or 0))
    safety_days = max(0, int(safety_days or 0))

    dated, undated = [], []
    for a in arrivals or []:
        q = to_float(a.get("qty_mt"), 0.0) or 0.0
        if q <= 0:
            continue
        d = _d(a.get("date"))
        (dated if d is not None else undated).append({**a, "date": d, "qty_mt": q})
    # A past-dated arrival still pending is treated as arriving today.
    for a in dated:
        if a["date"] < today:
            a["date"] = today
    dated.sort(key=lambda a: a["date"])

    if not rate or rate <= 0:
        return {
            "status": "NO_RATE", "stock_mt": stock0, "daily_use_mt": None,
            "arrivals": dated, "undated_arrivals": undated, "months": [],
            "note": "No daily consumption rate — enter one in Consumption to plan.",
            "version": PLANNING_ENGINE_VERSION,
        }

    safety_mt = rate * safety_days
    end = today + dt.timedelta(days=horizon)
    by_day: dict[dt.date, float] = {}
    for a in dated:
        if a["date"] <= end:
            by_day[a["date"]] = by_day.get(a["date"], 0.0) + a["qty_mt"]

    stock = stock0
    below_safety = runout = None
    worst_gap = 0.0          # largest shortfall below the safety level
    months: dict[str, dict[str, float]] = {}
    day = today
    while day <= end:
        key = day.strftime("%Y-%m")
        m = months.setdefault(key, {"opening_mt": stock, "arrivals_mt": 0.0,
                                    "use_mt": 0.0, "closing_mt": stock})
        arr = by_day.get(day, 0.0)
        stock += arr
        m["arrivals_mt"] += arr
        if day > today:
            stock -= rate
            m["use_mt"] += rate
        m["closing_mt"] = stock
        if below_safety is None and stock < safety_mt:
            below_safety = day
        if runout is None and stock < 0:
            runout = day
        worst_gap = max(worst_gap, safety_mt - stock)
        day += dt.timedelta(days=1)

    buy_by = (below_safety - dt.timedelta(days=lead)) if below_safety else None
    days_to_buy = (buy_by - today).days if buy_by else None
    if below_safety is None:
        status = "COVERED"
    elif days_to_buy is not None and days_to_buy < 0:
        status = "LATE"          # the lead time no longer fits: buy now / local
    elif days_to_buy is not None and days_to_buy <= 14:
        status = "BUY_SOON"
    else:
        status = "PLAN"

    month_rows = []
    for key in sorted(months):
        m = months[key]
        month_rows.append({
            "month": key, "opening_mt": m["opening_mt"], "arrivals_mt": m["arrivals_mt"],
            "use_mt": m["use_mt"], "closing_mt": m["closing_mt"],
            "cover_days": (m["closing_mt"] / rate) if m["closing_mt"] > 0 else 0.0,
            "short": m["closing_mt"] < safety_mt,
        })

    return {
        "status": status,
        "stock_mt": stock0,
        "daily_use_mt": rate,
        "cover_days_now": stock0 / rate,
        "safety_mt": safety_mt,
        "below_safety_date": below_safety,
        "runout_date": runout,
        "buy_by_date": buy_by,
        "days_to_buy": days_to_buy,
        "qty_to_buy_mt": max(0.0, worst_gap),
        "horizon_end": end,
        "arrivals": dated,
        "undated_arrivals": undated,
        "months": month_rows,
        "lead_time_days": lead,
        "safety_days": safety_days,
        "version": PLANNING_ENGINE_VERSION,
    }
