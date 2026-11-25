"""Pricing deadline radar: unpriced tonnes against their futures month's First Notice Day.

A contract priced "198 over DEC" has to be fixed (or rolled to the next month) before December's First
Notice Day — the last CBOT business day of November. For every open CBOT-based contract with tonnes still
unpriced, this works out the contract month (the contract's Futures month, its year inferred when missing),
First Notice Day and last trading day on the CBOT calendar (weekends and exchange holidays), the trading days
left to price, an alert level, the spread to the next listed month from stored quotes, and a plan: how many
lots of ``lot_mt`` that leaves per trading day.
"""

from __future__ import annotations

import calendar
import datetime as dt
import math
import re

from .cbot_contract import CONTRACT_MONTHS, contract as _contract, last_trading_day
from .contracts_position import cbot_holidays

MONTHS = {m.upper(): i for i, m in enumerate(calendar.month_abbr) if m}
CODES = {"F": 1, "G": 2, "H": 3, "J": 4, "K": 5, "M": 6, "N": 7, "Q": 8, "U": 9, "V": 10, "X": 11, "Z": 12}
LEVELS = (("passed", "First Notice Day reached — price or roll now"), ("red", "2 trading days or fewer"),
          ("amber", "5 trading days or fewer"), ("watch", "10 trading days or fewer"), ("ok", "more than 10 days"))
LOT_MT = {"CORN": 508.02, "SOYBEAN": 544.31, "WHEAT": 544.31, "SBM": 362.87}   # 4 CBOT contracts


def base_of(c):
    return str((c or {}).get("commodity") or "").upper().split("-")[0]


def _d(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def is_business_day(day):
    return day.weekday() < 5 and day not in set(cbot_holidays(day.year))


def first_notice_day(year, month):
    """The last CBOT business day of the month before the contract month."""
    d = dt.date(year, month, 1) - dt.timedelta(days=1)
    while not is_business_day(d):
        d -= dt.timedelta(days=1)
    return d


def parse_month(label):
    """'DEC' | 'DEC-26' | 'Dec 2026' | 'March' | 'Z26' → (month, year or None); None when unreadable."""
    t = str(label or "").strip().upper()
    if not t:
        return None
    m = re.fullmatch(r"([FGHJKMNQUVXZ])\s*(\d{2}|\d{4})", t)
    if m:
        y = int(m.group(2))
        return CODES[m.group(1)], (y + 2000 if y < 100 else y)
    m = re.match(r"([A-Z]{3})[A-Z]*[\s\-/'.]*(\d{2}|\d{4})?$", t)
    if not m or m.group(1) not in MONTHS:
        return None
    y = m.group(2)
    return MONTHS[m.group(1)], ((int(y) + 2000 if len(y) == 2 else int(y)) if y else None)


def resolve_month(label, base, reference):
    """(year, month) of the futures contract a label names; a label without a year takes the first year whose
    contract is still trading on ``reference`` (the delivery date, else today)."""
    p = parse_month(label)
    months = CONTRACT_MONTHS.get(base)
    if not p or not months or p[0] not in months:
        return None
    month, year = p
    if year is None:
        ref = _d(reference) or dt.date.today()
        year = next(y for y in range(ref.year - 1, ref.year + 3) if last_trading_day(y, month) >= ref)
    return year, month


def label(year, month):
    return f"{calendar.month_abbr[month].upper()}-{str(year)[-2:]}"


def month_choices(base, today=None, n=6):
    """The next ``n`` listed months of ``base`` still trading, as 'DEC-26' labels (for a dropdown)."""
    today = _d(today) or dt.date.today()
    months, out, y = CONTRACT_MONTHS.get(base) or (), [], today.year
    while months and len(out) < n:
        for m in months:
            if last_trading_day(y, m) >= today and len(out) < n:
                out.append(label(y, m))
        y += 1
    return out


def normalise_month(text, base, reference=None):
    """'DEC' → 'DEC-26' (year inferred), '' → ''. Unreadable text is returned unchanged."""
    if not str(text or "").strip():
        return ""
    r = resolve_month(text, base, reference)
    return label(*r) if r else str(text).strip()


def trading_days_left(today, fnd):
    """CBOT business days from ``today`` (included) to the day before First Notice Day."""
    n, d = 0, today
    while d < fnd:
        if is_business_day(d):
            n += 1
        d += dt.timedelta(days=1)
    return n


def next_month(base, year, month):
    months = CONTRACT_MONTHS[base]
    later = [m for m in months if m > month]
    return (year, later[0]) if later else (year + 1, months[0])


def level_of(days, passed):
    if passed:
        return "passed"
    return "red" if days <= 2 else "amber" if days <= 5 else "watch" if days <= 10 else "ok"


def priced_mt(c):
    return sum(float(l.get("qty_mt") or 0.0) for l in (c.get("pricing_lots") or []) if isinstance(l, dict))


def radar(contracts, today=None, quotes=None):
    """{rows, months, alerts}. rows: one per open contract with unpriced tonnes; months: totals per base and
    futures month; alerts: (priority, title, action) — High within 5 trading days of First Notice Day or past
    it, Medium within 10. ``quotes``: {yahoo
    symbol: price}, e.g. the stored futures curve, for the spread to the next month."""
    today = _d(today) or dt.date.today()
    quotes = quotes or {}
    rows = []
    for cid, c in (contracts or {}).items():
        if not isinstance(c, dict) or str(c.get("status") or "Open").strip().lower() == "closed":
            continue
        base = base_of(c)
        if base not in CONTRACT_MONTHS:
            continue
        qty = float(c.get("qty_mt") or 0.0)
        unpriced = max(qty - priced_mt(c), 0.0)
        if unpriced <= 0.5:
            continue
        row = {"contract_id": cid, "contract": c.get("name") or cid, "supplier": c.get("supplier") or "",
               "base": base, "qty": qty, "priced": qty - unpriced, "unpriced": unpriced,
               "month_text": str(c.get("futures_month") or "").strip()}
        ym = resolve_month(row["month_text"], base, c.get("delivery_date") or c.get("storage_start") or today)
        if not ym:
            row.update(level="no month", futures="", note="no futures month on the contract — the deadline is "
                       "unknown; set it on the contract")
            rows.append(row)
            continue
        y, m = ym
        fnd, ltd = first_notice_day(y, m), last_trading_day(y, m)
        days = trading_days_left(today, fnd)
        lot = LOT_MT.get(base, 500.0)
        lots = math.ceil(unpriced / lot - 1e-9)
        ny, nm = next_month(base, y, m)
        this_q, next_q = quotes.get(_contract(base, y, m)["symbol"]), quotes.get(_contract(base, ny, nm)["symbol"])
        row.update(futures=label(y, m), fnd=fnd, last_trading_day=ltd, days_left=days,
                   level=level_of(days, today >= fnd), lots=lots, lot_mt=lot,
                   per_day=(math.ceil(lots / days) if days else lots), next_futures=label(ny, nm),
                   spread=(next_q - this_q) if this_q is not None and next_q is not None else None)
        rows.append(row)
    order = {"passed": 0, "red": 1, "amber": 2, "watch": 3, "ok": 4, "no month": 5}
    rows.sort(key=lambda r: (order.get(r["level"], 9), r.get("days_left", 99), -r["unpriced"]))
    months = {}
    for r in rows:
        if not r.get("futures"):
            continue
        g = months.setdefault((r["base"], r["futures"]), {
            "base": r["base"], "futures": r["futures"], "fnd": r["fnd"], "days_left": r["days_left"],
            "level": r["level"], "unpriced": 0.0, "contracts": 0, "next_futures": r["next_futures"],
            "spread": r["spread"], "lot_mt": r["lot_mt"]})
        g["unpriced"] += r["unpriced"]
        g["contracts"] += 1
    for g in months.values():
        g["lots"] = math.ceil(g["unpriced"] / g["lot_mt"] - 1e-9)
        g["per_day"] = math.ceil(g["lots"] / g["days_left"]) if g["days_left"] else g["lots"]
    alerts = []
    for g in sorted(months.values(), key=lambda g: g["fnd"]):
        if g["level"] not in ("passed", "red", "amber", "watch"):
            continue
        when = f"{g['fnd']:%a %d %b}"
        spread = f" · {g['next_futures']} is {g['spread']:+.2f} vs {g['futures']}" if g["spread"] is not None else ""
        title = (f"{g['unpriced']:,.0f} MT {g['base']} unpriced on {g['futures']} ({g['contracts']} contract"
                 f"{'s' if g['contracts'] != 1 else ''}) — "
                 + (f"First Notice Day {when} has passed" if g["level"] == "passed"
                    else f"{g['days_left']} trading day{'s' if g['days_left'] != 1 else ''} to First Notice Day ({when})"))
        action = ((f"Price ≈ {g['per_day']} lot(s) of {g['lot_mt']:,.0f} MT a day ({g['lots']} lots in all), "
                   f"or roll to {g['next_futures']} with the supplier" if g["level"] != "passed"
                   else f"Price or roll to {g['next_futures']} now") + spread)
        alerts.append(("High" if g["level"] in ("passed", "red", "amber") else "Medium", title, action))
    for r in rows:
        if r["level"] == "no month":
            alerts.append(("Medium", f"{r['contract']}: {r['unpriced']:,.0f} MT unpriced with no futures month",
                           "Set the contract's Futures month so its pricing deadline is tracked"))
    return {"rows": rows, "months": sorted(months.values(), key=lambda g: g["fnd"]), "alerts": alerts}


def quote_for_contract(c, curve_rows=None, front=None, today=None):
    """The CBOT quote for the futures month on contract ``c`` (a rolled contract is valued on its own month,
    not the front month). ``curve_rows``: stored futures-curve rows ({symbol, price, as_of, source}); ``front``:
    the front quote as {symbol, price, as_of, source}. Returns {price, futures, symbol, as_of, source, matched,
    note}; matched is False when the contract's month is not quoted and the front month was used instead."""
    base = base_of(c)
    today = _d(today) or dt.date.today()
    front = front or {}
    by_symbol = {}
    for r in curve_rows or ():
        p = r.get("price") if isinstance(r, dict) else None
        if r.get("symbol") and isinstance(p, (int, float)) and not isinstance(p, bool):
            by_symbol[str(r["symbol"]).upper()] = r
    out = {"price": front.get("price"), "futures": "", "symbol": front.get("symbol") or "",
           "as_of": front.get("as_of") or "", "source": front.get("source") or "", "matched": False, "note": ""}
    ym = resolve_month((c or {}).get("futures_month"), base, (c or {}).get("delivery_date")
                       or (c or {}).get("storage_start") or today)
    if not ym:
        out["note"] = "no futures month on the contract — front month used"
        return out
    k = _contract(base, *ym)
    out["futures"] = k["futures"]
    if str(front.get("symbol") or "").upper() == k["symbol"].upper() and front.get("price") is not None:
        out.update(symbol=k["symbol"], matched=True)
        return out
    row = by_symbol.get(k["symbol"].upper())
    if row:
        out.update(price=float(row["price"]), symbol=k["symbol"], as_of=row.get("as_of") or out["as_of"],
                   source=row.get("source") or out["source"], matched=True)
        return out
    out["note"] = f"{k['futures']} not quoted — front month used; refresh the futures curve"
    return out
