"""Which CBOT contract month a price belongs to, so the app's CBOT matches CME.

CME's headline quote for a grain is its front contract: the nearest listed month until that contract's last
trading day (the business day before the 15th of the month). Yahoo's continuous symbols (ZC=F …) switch to the
next month earlier, around First Notice Day, which made the app show March while CME and the contracts
(priced on December) used December. Everything here is calendar logic only:

* ``front_contract(base, day)`` — the contract CME shows on ``day`` and its Yahoo symbol (ZCZ26.CBT);
* ``contract_windows(base, start, end)`` — the contract to read for every stretch of days, so a daily history
  is each day's close of the contract that was front that day;
* ``is_final(date, fetched_at)`` — a close fetched on its own day can be a mid-session price, not the
  settlement; it is final once fetched on a later day;
* ``merge_history(rows, new)`` — new closes replace automatic ones for the same day (never a close typed or
  imported by hand).
"""

from __future__ import annotations

import calendar
import datetime as dt

from .contracts_position import cbot_holidays

CONTRACT_MONTHS = {"CORN": (3, 5, 7, 9, 12), "WHEAT": (3, 5, 7, 9, 12),
                   "SOYBEAN": (1, 3, 5, 7, 8, 9, 11), "SBM": (1, 3, 5, 7, 8, 9, 10, 12)}
YAHOO_ROOT = {"CORN": "ZC", "WHEAT": "ZW", "SOYBEAN": "ZS", "SBM": "ZM"}
MONTH_CODE = {1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M", 7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z"}
MANUAL_SOURCES = ("excel", "manual", "typed", "import")


def _d(v):
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    return dt.date.fromisoformat(str(v)[:10])


def last_trading_day(year, month):
    """CBOT grains: the business day before the 15th calendar day of the contract month."""
    hol = set(cbot_holidays(year))
    d = dt.date(year, month, 15) - dt.timedelta(days=1)
    while d.weekday() >= 5 or d in hol:
        d -= dt.timedelta(days=1)
    return d


def contract(base, year, month):
    base = base.upper()
    code = MONTH_CODE[month]
    root = YAHOO_ROOT.get(base)
    return {"base": base, "year": year, "month": month, "code": code,
            "symbol": f"{root}{code}{str(year)[-2:]}.CBT" if root else "",
            "label": f"{calendar.month_abbr[month]}-{str(year)[-2:]}",
            "futures": f"{calendar.month_abbr[month].upper()}-{str(year)[-2:]}",
            "last_trading_day": last_trading_day(year, month)}


def front_contract(base, day=None):
    """The contract CME shows as front on ``day``: the nearest month whose last trading day is not past."""
    base = base.upper()
    months = CONTRACT_MONTHS.get(base)
    if not months:
        return None
    day = _d(day or dt.date.today())
    y = day.year
    for _ in range(3):
        for m in months:
            if (y, m) < (day.year, day.month):
                continue
            c = contract(base, y, m)
            if c["last_trading_day"] >= day:
                return c
        y += 1
    return None


def contract_windows(base, start, end):
    """[(contract, first day, last day)] covering ``start``..``end``: each day goes to the contract that was
    front that day, so a history read window by window follows CME's front month."""
    start, end = _d(start), _d(end)
    out, d = [], start
    while d <= end:
        c = front_contract(base, d)
        if c is None:
            break
        stop = min(end, c["last_trading_day"])
        out.append((c, d, stop))
        d = stop + dt.timedelta(days=1)
    return out


def is_final(date, fetched_at):
    """A daily close is final (the settlement) once it was fetched on a later day than its own."""
    try:
        return _d(fetched_at) > _d(date)
    except (TypeError, ValueError):
        return False


def _manual(row):
    src = str((row or {}).get("source") or "").lower()
    return any(k in src for k in MANUAL_SOURCES)


def merge_history(rows, new_rows):
    """Merge ``new_rows`` into ``rows`` (both [{date, commodity, price, …}]). A new close replaces the stored
    one for the same day and commodity unless the stored one was entered by hand. Returns (rows, changes) with
    changes = [(commodity, date, old price, new price)] for every value that moved or was added."""
    index = {(r.get("date"), r.get("commodity")): i for i, r in enumerate(rows)}
    changes = []
    for n in new_rows:
        key = (n.get("date"), n.get("commodity"))
        i = index.get(key)
        if i is None:
            rows.append(n)
            index[key] = len(rows) - 1
            changes.append((key[1], key[0], None, n.get("price")))
        elif not _manual(rows[i]):
            old = rows[i].get("price")
            if old != n.get("price") or rows[i].get("contract") != n.get("contract") or \
                    rows[i].get("final") != n.get("final"):
                rows[i] = n
                if old != n.get("price"):
                    changes.append((key[1], key[0], old, n.get("price")))
    return rows, changes


def needs_refresh(rows, base, today=None, days=10):
    """Dates of ``base`` in the last ``days`` days whose stored close is automatic and not final, or not
    tagged with its contract month (stored before this module): they are fetched again."""
    today = _d(today or dt.date.today())
    lo = today - dt.timedelta(days=days)
    out = []
    for r in rows:
        if r.get("commodity") != base or _manual(r):
            continue
        try:
            d = _d(r.get("date"))
        except (TypeError, ValueError):
            continue
        if lo <= d <= today and (not r.get("final") or not r.get("contract")):
            out.append(d.isoformat())
    return sorted(set(out))
