"""Market signals: fundamentals the CBOT market reacts to, turned into a
transparent up-risk / down-risk bias.  This is NOT a price forecast — each
signal says which way the *risk* leans and why, and the bias is simply the
weighted sum of those votes.

Sources (all public):
* CFTC Commitments of Traders — managed-money (fund) net position
* USDA NASS Crop Progress — % of crop rated good/excellent
* USDA WASDE — US and world ending stocks, this month vs last month
* CBOT futures curve — deferred contract vs front month
* The app's own CBOT history — trend and seasonality
"""

from __future__ import annotations

import calendar
import datetime as dt
from typing import Any

from .numbers import to_float

SIGNALS_ENGINE_VERSION = "1.0"

# CFTC contract market codes (CBOT)
CFTC_CODES = {"CORN": "002602", "SOYBEAN": "005602", "SBM": "026603", "WHEAT": "001602"}
# Yahoo symbols and listed contract months per board
YAHOO_ROOT = {"CORN": "ZC", "SOYBEAN": "ZS", "SBM": "ZM", "WHEAT": "ZW"}
CONTRACT_MONTHS = {
    "CORN": "HKNUZ", "WHEAT": "HKNUZ", "SOYBEAN": "FHKNQUX", "SBM": "FHKNQUVZ",
}
MONTH_CODE = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}


def _sig(name, direction, weight, reading, why, source, as_of=""):
    """direction: +1 = risk of higher CBOT, −1 = risk of lower, 0 = neutral."""
    return {"name": name, "direction": direction, "weight": weight, "score": direction * weight,
            "reading": reading, "why": why, "source": source, "as_of": as_of}


# ── CFTC Commitments of Traders ─────────────────────────────────────────
def parse_cot_rows(payload: Any) -> list[dict[str, Any]]:
    """Socrata JSON (publicreporting.cftc.gov, disaggregated futures-only)
    → [{date, long, short, oi}] oldest first.  Tolerant of field names."""
    rows = []
    for r in payload or []:
        if not isinstance(r, dict):
            continue
        date = str(r.get("report_date_as_yyyy_mm_dd") or r.get("report_date") or "")[:10]
        lk = next((k for k in r if "m_money" in k and "long" in k and k.endswith("_all")), None)
        sk = next((k for k in r if "m_money" in k and "short" in k and k.endswith("_all")), None)
        long_ = to_float(r.get(lk), None) if lk else None
        short = to_float(r.get(sk), None) if sk else None
        oi = to_float(r.get("open_interest_all"), None)
        if date and long_ is not None and short is not None:
            rows.append({"date": date, "long": long_, "short": short, "oi": oi})
    rows.sort(key=lambda x: x["date"])
    return rows


def cot_signal(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    nets = [r["long"] - r["short"] for r in rows]
    cur = nets[-1]
    prev = nets[-2] if len(nets) > 1 else None
    window = nets[-156:]
    rank = sum(1 for v in window if v <= cur) / len(window) * 100.0
    chg = (cur - prev) if prev is not None else None
    chg_txt = f", {chg:+,.0f} contracts on the week" if chg is not None else ""
    rk = int(round(rank))
    suffix = "th" if 10 <= rk % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(rk % 10, "th")
    reading = f"Funds net {cur:+,.0f} contracts ({rk}{suffix} percentile of {len(window)} weeks{chg_txt})"
    if rank <= 10:
        return _sig("Fund positioning (CFTC)", +1, 2.0, reading,
                    "Funds hold one of their biggest short bets — if news turns, short-covering can lift CBOT fast.",
                    "CFTC COT", rows[-1]["date"])
    if rank >= 90:
        return _sig("Fund positioning (CFTC)", -1, 2.0, reading,
                    "Funds hold one of their biggest long bets — long liquidation can push CBOT down sharply.",
                    "CFTC COT", rows[-1]["date"])
    d = 0
    why = "Fund position is not extreme."
    if chg is not None and abs(chg) >= 0.05 * max(1.0, max(abs(v) for v in window)):
        d = 1 if chg > 0 else -1
        why = f"Funds {'bought' if chg > 0 else 'sold'} heavily last week — short-term momentum {'up' if chg > 0 else 'down'}."
    return _sig("Fund positioning (CFTC)", d, 1.0, reading, why, "CFTC COT", rows[-1]["date"])


# ── USDA NASS crop condition ────────────────────────────────────────────
def parse_nass_condition(payload: Any) -> list[dict[str, Any]]:
    """Quick Stats JSON → [{week_ending, ge}] (good + excellent %), oldest first."""
    data = (payload or {}).get("data") if isinstance(payload, dict) else payload
    by_week: dict[str, dict[str, float]] = {}
    for r in data or []:
        if not isinstance(r, dict):
            continue
        wk = str(r.get("week_ending") or "")[:10]
        unit = str(r.get("unit_desc") or r.get("short_desc") or "").upper()
        val = to_float(str(r.get("Value") or r.get("value") or "").replace(",", ""), None)
        if not wk or val is None:
            continue
        slot = by_week.setdefault(wk, {})
        if "EXCELLENT" in unit:
            slot["ex"] = val
        elif "GOOD" in unit:
            slot["good"] = val
    out = [{"week_ending": w, "ge": v["ex"] + v["good"]}
           for w, v in by_week.items() if "ex" in v and "good" in v]
    out.sort(key=lambda x: x["week_ending"])
    return out


def crop_condition_signal(weeks: list[dict[str, Any]], last_year: list[dict[str, Any]] | None = None):
    if not weeks:
        return None
    cur = weeks[-1]["ge"]
    prev = weeks[-2]["ge"] if len(weeks) > 1 else None
    ly = None
    if last_year:
        # Same week of last year: the entry closest by calendar day.
        try:
            cd = dt.date.fromisoformat(weeks[-1]["week_ending"])
            ly = min(last_year, key=lambda w: abs(
                (dt.date.fromisoformat(w["week_ending"]).replace(year=cd.year) - cd).days))["ge"]
        except (ValueError, KeyError):
            ly = last_year[min(len(weeks), len(last_year)) - 1]["ge"]
    parts = [f"{cur:.0f}% good/excellent"]
    if prev is not None:
        parts.append(f"{cur - prev:+.0f} pts on the week")
    if ly is not None:
        parts.append(f"{cur - ly:+.0f} pts vs last year")
    reading = ", ".join(parts)
    score = 0
    if prev is not None and cur - prev <= -2:
        score += 1
    if prev is not None and cur - prev >= 2:
        score -= 1
    if ly is not None and cur - ly <= -5:
        score += 1
    if ly is not None and cur - ly >= 5:
        score -= 1
    d = (score > 0) - (score < 0)
    why = {1: "US crop is deteriorating — smaller harvest risk supports prices.",
           -1: "US crop looks strong — a big harvest weighs on prices.",
           0: "Crop condition is steady."}[d]
    return _sig("US crop condition (USDA)", d, 1.5, reading, why, "USDA NASS Crop Progress", weeks[-1]["week_ending"])


# ── WASDE ending stocks (entered monthly) ───────────────────────────────
def wasde_signal(us_this: Any, us_last: Any, world_this: Any = None, world_last: Any = None, month: str = ""):
    us_this, us_last = to_float(us_this, None), to_float(us_last, None)
    w_this, w_last = to_float(world_this, None), to_float(world_last, None)
    if us_this is None or not us_last:
        return None
    us_chg = (us_this / us_last - 1.0) * 100.0
    w_chg = (w_this / w_last - 1.0) * 100.0 if (w_this is not None and w_last) else None
    reading = f"US ending stocks {us_this:,.0f} ({us_chg:+.1f}% vs last month)"
    if w_chg is not None:
        reading += f", world {w_this:,.1f} ({w_chg:+.1f}%)"
    combo = us_chg + (w_chg or 0.0) * 0.5
    if combo <= -3:
        return _sig("Supply & demand (WASDE)", +1, 2.0, reading,
                    "USDA cut ending stocks — tighter supply supports higher prices.", "USDA WASDE", month)
    if combo >= 3:
        return _sig("Supply & demand (WASDE)", -1, 2.0, reading,
                    "USDA raised ending stocks — more supply weighs on prices.", "USDA WASDE", month)
    return _sig("Supply & demand (WASDE)", 0, 1.0, reading, "Ending stocks broadly unchanged.", "USDA WASDE", month)


# ── Futures curve ───────────────────────────────────────────────────────
def deferred_contract(board: str, today: dt.date, months_ahead: int = 5):
    """(yahoo_symbol, label) for the first listed contract ≥ months_ahead out."""
    board = board.upper()
    codes = CONTRACT_MONTHS.get(board)
    root = YAHOO_ROOT.get(board)
    if not codes or not root:
        return None, ""
    y, m = today.year, today.month + months_ahead
    while m > 12:
        m -= 12
        y += 1
    for _ in range(24):
        for code in codes:
            if MONTH_CODE[code] == m:
                return f"{root}{code}{str(y)[-2:]}.CBT", f"{calendar.month_abbr[m]} {y}"
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return None, ""


def curve_signal(front: Any, deferred: Any, label: str = ""):
    f, d = to_float(front, None), to_float(deferred, None)
    if not f or d is None:
        return None
    spread = (d / f - 1.0) * 100.0
    reading = f"{label or 'Deferred'} {d:,.2f} vs front {f:,.2f} ({spread:+.1f}%)"
    if spread < -1.0:
        return _sig("Futures curve", +1, 1.0, reading,
                    "Inverted curve: the market pays more for grain now than later — supply is tight today.",
                    "CBOT curve")
    if spread > 6.0:
        return _sig("Futures curve", -1, 1.0, reading,
                    "Wide carry: the market is paying to store grain — supply is ample.", "CBOT curve")
    return _sig("Futures curve", 0, 0.5, reading, "Normal carry.", "CBOT curve")


# ── Own history: trend and seasonality ──────────────────────────────────
def trend_signal(series: list[tuple[str, float]]):
    closes = [to_float(v, None) for _d, v in series or []]
    closes = [c for c in closes if c]
    if len(closes) < 60:
        return None
    last = closes[-1]
    ma50 = sum(closes[-50:]) / 50
    ma200 = sum(closes[-200:]) / min(200, len(closes))
    reading = f"Last {last:,.2f} · 50-day avg {ma50:,.2f} · 200-day avg {ma200:,.2f}"
    if last > ma50 > ma200:
        return _sig("Price trend", +1, 1.0, reading, "Price is above its 50- and 200-day averages — uptrend.", "Own CBOT history")
    if last < ma50 < ma200:
        return _sig("Price trend", -1, 1.0, reading, "Price is below its 50- and 200-day averages — downtrend.", "Own CBOT history")
    return _sig("Price trend", 0, 0.5, reading, "No clear trend.", "Own CBOT history")


def seasonality(series: list[tuple[str, float]]) -> dict[str, Any]:
    """Average month-over-month % change by calendar month from month-end closes."""
    month_end: dict[str, float] = {}
    for d, v in series or []:
        fv = to_float(v, None)
        if d and fv:
            month_end[str(d)[:7]] = fv
    keys = sorted(month_end)
    changes: dict[int, list[float]] = {m: [] for m in range(1, 13)}
    for a, b in zip(keys, keys[1:]):
        ya, ma = int(a[:4]), int(a[5:7])
        yb, mb = int(b[:4]), int(b[5:7])
        if (yb * 12 + mb) - (ya * 12 + ma) != 1:
            continue
        changes[mb].append((month_end[b] / month_end[a] - 1.0) * 100.0)
    table = []
    for m in range(1, 13):
        vals = changes[m]
        table.append({"month": m, "name": calendar.month_abbr[m], "years": len(vals),
                      "avg_pct": (sum(vals) / len(vals)) if vals else None,
                      "up_share": (sum(1 for v in vals if v > 0) / len(vals) * 100.0) if vals else None})
    years = len({k[:4] for k in keys})
    return {"table": table, "years": years, "months": len(keys)}


def seasonal_signal(season: dict[str, Any], today: dt.date):
    nxt = today.month % 12 + 1
    row = next((r for r in season.get("table", []) if r["month"] == nxt), None)
    if not row or not row["years"] or row["years"] < 2:
        return None
    reading = (f"{row['name']}: average {row['avg_pct']:+.1f}%, higher in {row['up_share']:.0f}% of "
               f"{row['years']} years")
    d = 0
    if row["avg_pct"] >= 1.5 and row["up_share"] >= 60:
        d = 1
    elif row["avg_pct"] <= -1.5 and row["up_share"] <= 40:
        d = -1
    why = {1: "Next month has usually been firmer.", -1: "Next month has usually been weaker.",
           0: "No reliable seasonal pattern for next month."}[d]
    return _sig("Seasonality (own history)", d, 0.5, reading, why, "Own CBOT history")


def combine_signals(signals: list[dict[str, Any] | None]) -> dict[str, Any]:
    sigs = [s for s in signals if s]
    score = sum(s["score"] for s in sigs)
    max_score = sum(s["weight"] for s in sigs) or 1.0
    if score >= 1.5:
        bias, advice = "UP", ("Risk leans to HIGHER CBOT: consider fixing part of the unpriced quantity, "
                              "set PROTECT ABOVE caps, and test larger up-shocks.")
    elif score <= -1.5:
        bias, advice = "DOWN", ("Risk leans to LOWER CBOT: waiting can pay — use BUY BELOW ladders rather "
                                "than fixing everything now.")
    else:
        bias, advice = "BALANCED", "No clear lean: spread pricing over time (ladder) and keep caps in place."
    return {"bias": bias, "score": score, "max_score": max_score, "signals": sigs, "advice": advice,
            "suggested_cbot_shocks": ("-5, 5, 10, 15" if bias == "UP" else "-15, -10, -5, 5" if bias == "DOWN"
                                      else "-10, -5, 5, 10"),
            "version": SIGNALS_ENGINE_VERSION}


# ── Report calendar ─────────────────────────────────────────────────────
def _weekday_on_or_after(d: dt.date) -> dt.date:
    while d.weekday() >= 5:
        d += dt.timedelta(days=1)
    return d


def _last_weekday(y: int, m: int) -> dt.date:
    d = dt.date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def _nth_weekday(y, m, weekday, n):
    d = dt.date(y, m, 1)
    while d.weekday() != weekday:
        d += dt.timedelta(days=1)
    return d + dt.timedelta(days=7 * (n - 1))


def _last_monday(y, m):
    d = dt.date(y, m, calendar.monthrange(y, m)[1])
    while d.weekday() != 0:
        d -= dt.timedelta(days=1)
    return d


def report_calendar(start: dt.date, end: dt.date) -> list[dict[str, Any]]:
    """USDA / CFTC report days between start and end.  Dates that follow a
    fixed rule are exact; WASDE is published on a schedule set each year, so
    its dates are estimates (around the 10th) — confirm on usda.gov."""
    ev = []

    def add(d, name, impact, detail, estimated=False):
        if start <= d <= end:
            ev.append({"date": d, "name": name, "impact": impact, "detail": detail,
                       "estimated": estimated, "key": f"{name}|{d.isoformat()}"})

    y, m = start.year, start.month
    while dt.date(y, m, 1) <= end:
        wasde = _weekday_on_or_after(dt.date(y, m, 10))
        add(wasde, "WASDE", "High", "USDA world supply & demand — ending stocks for corn, soybeans, meal, wheat"
            + (" + Crop Production" if m in (8, 9, 10, 11) else "")
            + (" + annual Crop Production & Grain Stocks" if m == 1 else ""), estimated=True)
        if m == 3:
            add(_last_weekday(y, 3), "Prospective Plantings + Grain Stocks", "High",
                "First US acreage intentions of the year — often a big mover")
        if m == 6:
            add(_last_weekday(y, 6), "Acreage + Grain Stocks", "High", "Actual US planted area — often a big mover")
        if m == 9:
            add(_last_weekday(y, 9), "Grain Stocks", "Medium", "Quarterly US stocks")
        m += 1
        if m > 12:
            m, y = 1, y + 1
    d = start
    memorial = {yy: _last_monday(yy, 5) for yy in range(start.year, end.year + 1)}
    labor = {yy: _nth_weekday(yy, 9, 0, 1) for yy in range(start.year, end.year + 1)}
    while d <= end:
        if d.weekday() == 0 and (4 <= d.month <= 11):
            cp = d + dt.timedelta(days=1) if d in (memorial.get(d.year), labor.get(d.year)) else d
            add(cp, "Crop Progress", "Medium", "Weekly US crop condition (good/excellent %) — Monday 4 pm ET")
        if d.weekday() == 3:
            add(d, "Export Sales", "Low", "Weekly US export sales")
        if d.weekday() == 4:
            add(d, "Commitments of Traders", "Low", "CFTC fund positions (as of Tuesday)")
        d += dt.timedelta(days=1)
    ev.sort(key=lambda e: (e["date"], {"High": 0, "Medium": 1, "Low": 2}[e["impact"]]))
    return ev
