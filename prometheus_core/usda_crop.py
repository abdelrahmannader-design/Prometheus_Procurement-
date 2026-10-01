"""USDA NASS Quick Stats: crop progress, yield / production forecasts,
quarterly grain stocks and state-level crop condition.

Pure parsing + signals (no network).  Each parser takes the Quick Stats
JSON rows (``payload["data"]``) and is tolerant of extra rows: Quick Stats
returns irrigated / on-farm / class splits alongside the totals, and those
are filtered out here so only the headline US figure is used.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .numbers import to_float

USDA_CROP_VERSION = "1.0"

# Quick Stats commodity per app commodity (meal follows the soybean crop)
NASS_CROP = {"CORN": "CORN", "SOYBEAN": "SOYBEANS", "SBM": "SOYBEANS", "WHEAT": "WHEAT"}
# headline short_desc prefix for yield / production / stocks
NASS_PREFIX = {"CORN": "CORN, GRAIN", "SOYBEANS": "SOYBEANS", "WHEAT": "WHEAT"}
# main producing states shown in the state table
KEY_STATES = {
    "CORN": ["IA", "IL", "NE", "MN", "IN", "SD", "KS", "OH"],
    "SOYBEANS": ["IL", "IA", "MN", "IN", "NE", "OH", "MO", "ND"],
    "WHEAT": ["KS", "OK", "TX", "MT", "ND", "WA", "CO", "NE"],
}
MONTHS = {m: i for i, m in enumerate(
    ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"], start=1)}
STOCK_QUARTER = {"FIRST OF MAR": 1, "FIRST OF JUN": 2, "FIRST OF SEP": 3, "FIRST OF DEC": 4}


def pick_latest_class(payload: Any) -> list[dict[str, Any]]:
    """Wheat rows come per class; keep the class with the most recent week."""
    rows = _rows(payload)
    latest: dict[str, str] = {}
    for r in rows:
        wk = str(r.get("week_ending") or "")[:10]
        c = _class_label(r)
        if wk > latest.get(c, ""):
            latest[c] = wk
    if len(latest) <= 1:
        return rows
    best = max(latest, key=lambda c: (latest[c], c == "WINTER"))
    return [r for r in rows if _class_label(r) == best]


def _rows(payload: Any) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    return [r for r in (data or []) if isinstance(r, dict)]


def _val(r: dict[str, Any]) -> float | None:
    """Quick Stats values are strings like '1,234' or '(D)' (withheld)."""
    return to_float(str(r.get("Value", r.get("value", ""))).replace(",", "").strip(), None)


def _week_no(r: dict[str, Any]) -> int | None:
    m = re.search(r"WEEK\s*#\s*(\d+)", str(r.get("reference_period_desc", "")).upper())
    return int(m.group(1)) if m else None


def _class_label(r: dict[str, Any]) -> str:
    c = str(r.get("class_desc") or "").upper()
    if not c or c.startswith("ALL"):
        return ""
    return "WINTER" if "WINTER" in c else "SPRING" if "SPRING" in c else c.title()


# ── Crop progress (planted / emerged / … / harvested %) ─────────────────
def parse_progress(payload: Any) -> dict[str, dict[int, list[dict[str, Any]]]]:
    """→ {stage: {year: [{week, week_ending, pct}]}} ; stage like 'HARVESTED'
    or 'WINTER · PLANTED' for wheat classes."""
    out: dict[str, dict[int, list[dict[str, Any]]]] = {}
    for r in _rows(payload):
        unit = str(r.get("unit_desc") or "").upper()
        if not unit.startswith("PCT ") or str(r.get("agg_level_desc", "NATIONAL")).upper() != "NATIONAL":
            continue
        v, wk, yr = _val(r), _week_no(r), to_float(r.get("year"), None)
        if v is None or wk is None or yr is None:
            continue
        stage = unit[4:].strip()
        cls = _class_label(r)
        key = f"{cls} · {stage}" if cls else stage
        out.setdefault(key, {}).setdefault(int(yr), []).append(
            {"week": wk, "week_ending": str(r.get("week_ending") or "")[:10], "pct": v})
    for years in out.values():
        for lst in years.values():
            lst.sort(key=lambda x: x["week"])
    return out


def _pct_at(lst: list[dict[str, Any]], week: int) -> float | None:
    """Value at a reference week; before the first report = 0, after the last = 100 if it got there."""
    if not lst:
        return None
    hit = next((x["pct"] for x in lst if x["week"] == week), None)
    if hit is not None:
        return hit
    if week < lst[0]["week"]:
        return 0.0
    if week > lst[-1]["week"]:
        return lst[-1]["pct"] if lst[-1]["pct"] >= 99 else None
    before = [x for x in lst if x["week"] < week]
    return before[-1]["pct"] if before else None


def progress_summary(parsed: dict[str, dict[int, list[dict[str, Any]]]], year: int) -> list[dict[str, Any]]:
    """Latest reading per stage this year, with last year and the 5-year
    average for the same reference week (USDA's own comparison)."""
    out = []
    for stage, years in parsed.items():
        cur = years.get(year) or []
        if not cur:
            continue
        last = cur[-1]
        wk = last["week"]
        ly = _pct_at(years.get(year - 1) or [], wk)
        hist = [_pct_at(years.get(y) or [], wk) for y in range(year - 5, year)]
        hist = [h for h in hist if h is not None]
        avg5 = sum(hist) / len(hist) if hist else None
        prev = cur[-2]["pct"] if len(cur) > 1 else None
        out.append({"stage": stage, "pct": last["pct"], "week_ending": last["week_ending"], "week": wk,
                    "prev_week": prev, "last_year": ly, "avg5": avg5, "avg_years": len(hist),
                    "series": [(x["week"], x["pct"]) for x in cur]})
    out.sort(key=lambda s: s["week_ending"], reverse=True)
    return out


def progress_signal(summary: list[dict[str, Any]], today: dt.date | None = None):
    """The stage now under way (between 1 % and 99 %, reported in the last
    3 weeks) vs its 5-year average: well behind → up risk, well ahead → down."""
    today = today or dt.date.today()
    active = []
    for s in summary:
        try:
            age = (today - dt.date.fromisoformat(s["week_ending"])).days
        except ValueError:
            continue
        if 1 <= s["pct"] <= 99 and age <= 21 and s["avg5"] is not None:
            active.append(s)
    if not active:
        return None
    pri = ("HARVESTED", "PLANTED", "MATURE", "EMERGED", "SILKING", "BLOOMING", "HEADED")
    active.sort(key=lambda s: next((i for i, p in enumerate(pri) if s["stage"].endswith(p)), 9))
    s = active[0]
    diff = s["pct"] - s["avg5"]
    reading = (f"{s['stage'].title()} {s['pct']:.0f}% vs {s['avg5']:.0f}% 5-yr average"
               + (f", {s['last_year']:.0f}% last year" if s["last_year"] is not None else ""))
    from .market_signals import _sig
    if diff <= -5:
        return _sig("Crop progress (USDA)", +1, 1.0, reading,
                    "Behind the usual pace — weather delays put the crop size at risk and support prices.",
                    "USDA NASS Crop Progress", s["week_ending"])
    if diff >= 5:
        return _sig("Crop progress (USDA)", -1, 1.0, reading,
                    "Ahead of the usual pace — fast fieldwork removes a risk and lets supply arrive early.",
                    "USDA NASS Crop Progress", s["week_ending"])
    return _sig("Crop progress (USDA)", 0, 0.5, reading, "Fieldwork is on a normal pace.",
                "USDA NASS Crop Progress", s["week_ending"])


# ── Yield and production forecasts (Crop Production report) ─────────────
def _period_order(desc: str) -> int | None:
    d = str(desc or "").upper().strip()
    if d == "YEAR":
        return 13                      # final annual estimate
    m = re.match(r"YEAR\s*-\s*([A-Z]{3})\s+FORECAST", d)
    return MONTHS.get(m.group(1)) if m else None


def _period_label(desc: str) -> str:
    d = str(desc or "").upper().strip()
    if d == "YEAR":
        return "final"
    m = re.match(r"YEAR\s*-\s*([A-Z]{3})\s+FORECAST", d)
    return f"{m.group(1).title()} forecast" if m else d.title()


def parse_forecasts(payload: Any, crop: str, stat: str) -> list[dict[str, Any]]:
    """Headline US YIELD or PRODUCTION rows → [{year, order, period, value, unit}] oldest first."""
    prefix = NASS_PREFIX.get(crop, crop)
    want_unit = "BU / ACRE" if stat == "YIELD" else "BU"
    out = []
    for r in _rows(payload):
        sd = str(r.get("short_desc") or "").upper()
        if sd != f"{prefix} - {stat}, MEASURED IN {want_unit}":
            continue
        if str(r.get("agg_level_desc", "NATIONAL")).upper() != "NATIONAL":
            continue
        order = _period_order(r.get("reference_period_desc"))
        v, yr = _val(r), to_float(r.get("year"), None)
        if order is None or v is None or yr is None:
            continue
        out.append({"year": int(yr), "order": order, "period": _period_label(r.get("reference_period_desc")),
                    "value": v, "unit": want_unit})
    out.sort(key=lambda x: (x["year"], x["order"]))
    return out


def forecast_summary(rows: list[dict[str, Any]], year: int) -> dict[str, Any] | None:
    cur = [r for r in rows if r["year"] == year]
    # During the season Quick Stats also fills the annual ("YEAR") row with
    # the latest forecast. That copy is not a new estimate: drop it while it
    # equals the last monthly forecast, so the change is forecast vs forecast.
    fc = [r for r in cur if r["order"] <= 12]
    if fc:
        cur = [r for r in cur if r["order"] <= 12 or abs(r["value"] - fc[-1]["value"]) > 1e-9]
    if not cur:
        return None
    last = cur[-1]
    prev = cur[-2] if len(cur) > 1 else None
    ly = [r for r in rows if r["year"] == year - 1]
    ly_final = next((r for r in reversed(ly) if r["order"] == 13), ly[-1] if ly else None)
    return {"value": last["value"], "period": last["period"], "unit": last["unit"],
            "prev_value": prev["value"] if prev else None, "prev_period": prev["period"] if prev else "",
            "last_year": ly_final["value"] if ly_final else None,
            "series": [(r["period"], r["value"]) for r in cur]}


def yield_signal(yield_sum: dict[str, Any] | None, prod_sum: dict[str, Any] | None = None):
    """Latest yield forecast vs the previous one this season."""
    s = yield_sum
    if not s or s.get("prev_value") in (None, 0):
        return None
    chg = (s["value"] / s["prev_value"] - 1.0) * 100.0
    reading = (f"Yield {s['value']:,.1f} bu/ac ({s['period']}) vs {s['prev_value']:,.1f} "
               f"({s['prev_period']}), {chg:+.1f}%")
    if s.get("last_year"):
        reading += f"; last year {s['last_year']:,.1f}"
    if prod_sum and prod_sum.get("value"):
        reading += f" · crop {prod_sum['value'] / 1e9:,.2f} bn bu"
    from .market_signals import _sig
    if chg <= -1.0:
        return _sig("Yield forecast (USDA)", +1, 1.5, reading,
                    "USDA cut its yield estimate — a smaller crop supports prices.",
                    "USDA NASS Crop Production", s["period"])
    if chg >= 1.0:
        return _sig("Yield forecast (USDA)", -1, 1.5, reading,
                    "USDA raised its yield estimate — a bigger crop weighs on prices.",
                    "USDA NASS Crop Production", s["period"])
    return _sig("Yield forecast (USDA)", 0, 0.5, reading, "Yield estimate broadly unchanged.",
                "USDA NASS Crop Production", s["period"])


# ── Quarterly grain stocks ──────────────────────────────────────────────
def parse_stocks(payload: Any, crop: str) -> list[dict[str, Any]]:
    """Total US stocks (on + off farm) → [{year, quarter, period, value}] oldest first."""
    prefix = NASS_PREFIX.get(crop, crop)
    out = []
    for r in _rows(payload):
        sd = str(r.get("short_desc") or "").upper()
        if sd != f"{prefix} - STOCKS, MEASURED IN BU":
            continue
        if str(r.get("agg_level_desc", "NATIONAL")).upper() != "NATIONAL":
            continue
        q = STOCK_QUARTER.get(str(r.get("reference_period_desc") or "").upper().strip())
        v, yr = _val(r), to_float(r.get("year"), None)
        if q is None or v is None or yr is None:
            continue
        out.append({"year": int(yr), "quarter": q, "period": "1 " + str(r.get("reference_period_desc")).strip()[-3:].title(),
                    "value": v})
    out.sort(key=lambda x: (x["year"], x["quarter"]))
    return out


def stocks_signal(rows: list[dict[str, Any]], today: dt.date | None = None):
    """Latest quarterly stocks vs the same quarter a year earlier."""
    if not rows:
        return None
    last = rows[-1]
    ly = next((r for r in rows if r["year"] == last["year"] - 1 and r["quarter"] == last["quarter"]), None)
    if not ly or not ly["value"]:
        return None
    chg = (last["value"] / ly["value"] - 1.0) * 100.0
    reading = (f"{last['period']} {last['year']}: {last['value'] / 1e9:,.2f} bn bu vs "
               f"{ly['value'] / 1e9:,.2f} a year earlier ({chg:+.0f}%)")
    from .market_signals import _sig
    asof = f"{last['period']} {last['year']}"
    if chg <= -10:
        return _sig("Grain stocks (USDA)", +1, 1.0, reading,
                    "Much less grain in store than a year ago — tighter supply supports prices.",
                    "USDA NASS Grain Stocks", asof)
    if chg >= 10:
        return _sig("Grain stocks (USDA)", -1, 1.0, reading,
                    "Much more grain in store than a year ago — ample supply weighs on prices.",
                    "USDA NASS Grain Stocks", asof)
    return _sig("Grain stocks (USDA)", 0, 0.5, reading, "Stocks close to last year.",
                "USDA NASS Grain Stocks", asof)


# ── State-level crop condition ──────────────────────────────────────────
def parse_state_condition(payload: Any, crop: str) -> list[dict[str, Any]]:
    """Key producing states → [{state, name, ge, prev, change, poor, week_ending}] latest week."""
    want = KEY_STATES.get(crop, [])
    weeks: dict[tuple[str, str], dict[str, float]] = {}
    names: dict[str, str] = {}
    rows = _rows(payload)
    # Wheat is reported per class (winter / spring): use, per state, the
    # class with the most recent report.
    latest_cls: dict[str, tuple[str, str]] = {}
    for r in rows:
        st, wk = str(r.get("state_alpha") or "").upper(), str(r.get("week_ending") or "")[:10]
        if wk and wk > latest_cls.get(st, ("", ""))[0]:
            latest_cls[st] = (wk, _class_label(r))
    for r in rows:
        st = str(r.get("state_alpha") or "").upper()
        if want and st not in want:
            continue
        if _class_label(r) != latest_cls.get(st, ("", ""))[1]:
            continue
        wk = str(r.get("week_ending") or "")[:10]
        unit = str(r.get("unit_desc") or "").upper()
        v = _val(r)
        if not wk or v is None:
            continue
        names[st] = str(r.get("state_name") or st).title()
        slot = weeks.setdefault((st, wk), {})
        for key, tag in (("ex", "EXCELLENT"), ("vpoor", "VERY POOR"), ("poor", "POOR"), ("fair", "FAIR"),
                         ("good", "GOOD")):
            if tag in unit:
                slot[key] = v
                break
    by_state: dict[str, list[tuple[str, dict[str, float]]]] = {}
    for (st, wk), v in weeks.items():
        if "ex" in v and "good" in v:
            by_state.setdefault(st, []).append((wk, v))
    out = []
    for st, lst in by_state.items():
        lst.sort()
        wk, v = lst[-1]
        ge = v["ex"] + v["good"]
        prev = (lst[-2][1]["ex"] + lst[-2][1]["good"]) if len(lst) > 1 else None
        out.append({"state": st, "name": names.get(st, st), "ge": ge, "prev": prev,
                    "change": (ge - prev) if prev is not None else None,
                    "poor": (v.get("poor") or 0) + (v.get("vpoor") or 0), "week_ending": wk})
    order = {s: i for i, s in enumerate(want)}
    out.sort(key=lambda x: order.get(x["state"], 99))
    return out
