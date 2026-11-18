"""Contracts position: the desk's "YC Contracts position" table, from the app's data.

One row per open contract of a commodity, split two ways at once:

* where the tonnes are — still on the way, at the port, in warehouses, or
  already sold / used (the FIFO estimate of the app);
* whether their CBOT is priced — **Long** = CBOT fixed (the contract's pricing
  lots), **Short** = CBOT still open, so a rise in the board still costs money.

Priced tonnes are matched to the oldest tonnes first: sold / used, then
warehouses, then the port, then the tonnes still on the way.  So a contract
with 1,500 of 2,000 MT priced that has all been used shows 1,500 sold Long and
500 sold Short, as the desk's own report does.

The app does not know how much stock is still at the port, so that is an
input (yellow); the rest of the stock counts as in warehouses.  Every derived
figure in the sheet is a formula over the inputs, and ``allocate`` repeats the
same arithmetic in Python for the cached results and the tests.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .numbers import to_float

SHEET = "Position detail"
SUMMARY = "Position"
MONTH_CODE = {"JAN": "F", "FEB": "G", "MAR": "H", "APR": "J", "MAY": "K", "JUN": "M", "JUL": "N",
              "AUG": "Q", "SEP": "U", "OCT": "V", "NOV": "X", "DEC": "Z"}
ORIGIN_CODE = {"BRAZIL": "BRZ", "ARGENTINA": "ARG", "UKRAINE": "UKR", "USA": "US", "ROMANIA": "ROM"}


def month_code(futures: Any) -> str:
    """'DEC-26' / 'DEC' → 'Z' (the CBOT letter for the delivery month)."""
    text = str(futures or "").strip().upper()
    return MONTH_CODE.get(text[:3], text)


def allocate(total: float, received: float, used: float, port: float, priced: float) -> dict[str, float]:
    """Split one contract into the report's buckets (see the module docstring)."""
    total = max(to_float(total, 0.0) or 0.0, 0.0)
    received = min(max(to_float(received, 0.0) or 0.0, 0.0), total)
    used = min(max(to_float(used, 0.0) or 0.0, 0.0), received)
    stock = received - used
    port = min(max(to_float(port, 0.0) or 0.0, 0.0), stock)
    wh = stock - port
    left = min(max(to_float(priced, 0.0) or 0.0, 0.0), total)
    sold_long = min(left, used); left -= sold_long
    wh_long = min(left, wh); left -= wh_long
    port_long = min(left, port); left -= port_long
    way = total - received
    way_long = min(left, way)
    out = {"open_way": way - way_long, "long_way": way_long,
           "port_long": port_long, "port_short": port - port_long,
           "wh_long": wh_long, "wh_short": wh - wh_long,
           "sold_long": sold_long, "sold_short": used - sold_long}
    out["short_delivered"] = out["sold_short"] + out["wh_short"] + out["port_short"]
    return out


def _fixed_cbot(lots, cif, factor, premium):
    """Average CBOT of the priced lots; else implied by a final CIF."""
    mt = sum(to_float(l.get("mt"), 0.0) or 0.0 for l in lots if to_float(l.get("cbot"), None) is not None)
    if mt > 0:
        return sum((to_float(l.get("mt"), 0.0) or 0.0) * to_float(l.get("cbot"), 0.0)
                   for l in lots if to_float(l.get("cbot"), None) is not None) / mt
    if cif and factor and premium is not None:
        return cif / factor - premium
    return None


def position_rows(open_rows, base="CORN", receipts=None, lots=None, final_cif=None, factor=0.3937):
    """Rows for the sheet from the management model's open contracts.

    ``receipts``: {contract_id: {vessel, shipment}} (optional); ``lots``:
    {contract_id: [{mt, cbot}]} the contract's pricing lots; ``final_cif``:
    {contract_id: CIF USD/MT} when the contract carries a final CIF.
    """
    receipts, lots, final_cif = receipts or {}, lots or {}, final_cif or {}
    rows = []
    for o in open_rows or []:
        if (o.get("base") or "").upper() != base.upper():
            continue
        cid = o.get("contract_id")
        total = to_float(o.get("qty_mt"), 0.0) or 0.0
        cl = lots.get(cid) or []
        priced = min(sum(to_float(l.get("mt"), 0.0) or 0.0 for l in cl), total)
        premium = to_float(o.get("premium"), None)
        rv = receipts.get(cid) or {}
        recv = str(o.get("storage_start") or "")[:10]
        origin = str(o.get("commodity") or "").upper().split("-")[1] if "-" in str(o.get("commodity") or "") else \
            ORIGIN_CODE.get(str(o.get("origin") or "").upper(), str(o.get("origin") or ""))
        rows.append({
            "contract_id": cid, "contract": o.get("contract") or cid, "supplier": o.get("supplier") or "",
            "origin": origin, "total": total,
            "received": to_float(o.get("delivered_mt"), 0.0) or 0.0,
            "used": to_float(o.get("consumed_mt"), 0.0) or 0.0,
            "port": 0.0, "priced": priced, "premium": premium, "futures": o.get("futures") or "",
            "fixed_cbot": _fixed_cbot(cl, final_cif.get(cid), factor, premium) if priced > 0 else None,
            "receiving_date": recv, "vessel": rv.get("vessel") or "", "shipment": rv.get("shipment") or "",
            "discharge": to_float(o.get("discharge"), None), "clearance": to_float(o.get("clearance"), None),
            "freight": to_float(o.get("freight"), None), "local": to_float(o.get("local_excl"), None),
            "local_date": str(o.get("local_date") or "")[:10],
            "fx_contract": (to_float(o.get("fx"), None)
                            if str(o.get("fx_basis") or "").lower().startswith("form 4") else None),
            "eta": None, "remarks": [], "lots": list(cl), "closed": "",
        })
    rows.sort(key=lambda r: (not r["receiving_date"], r["receiving_date"] or "9999", r["contract"]))
    flag_look_alikes(rows)
    return rows


def closed_rows(contracts, base="CORN", closed_dates=None, lots=None, as_of=None, closed_days=15, factor=0.3937):
    """Rows for contracts closed in the last ``closed_days`` days, from the management model's contracts.

    ``closed_dates``: {contract_id: ISO date the contract was closed in the app}; a closed contract without
    a recorded date is left out (its closing day is unknown). ``lots``: {contract_id: [{date, mt, cbot}]}.
    """
    as_of = as_of or dt.date.today()
    cut = as_of - dt.timedelta(days=closed_days)
    closed_dates, lots = closed_dates or {}, lots or {}
    out = []
    for c in contracts or []:
        if (c.get("base") or "").upper() != base.upper() or str(c.get("status") or "").lower() != "closed":
            continue
        cid = c.get("id") or c.get("contract_id")
        when = str(closed_dates.get(cid) or "")[:10]
        try:
            d = dt.date.fromisoformat(when)
        except ValueError:
            continue
        if d < cut or d > as_of:
            continue
        cl = lots.get(cid) or []
        prem = to_float(c.get("premium"), None)
        cif = to_float(c.get("cif_usd_mt"), None) if c.get("cif_final") or c.get("final_cif_over_lots") else None
        comm = str(c.get("commodity") or "")
        out.append({
            "contract_id": cid, "contract": c.get("contract") or cid, "supplier": c.get("supplier") or "",
            "origin": comm.upper().split("-")[1] if "-" in comm else ORIGIN_CODE.get(str(c.get("origin") or "").upper(), ""),
            "total": to_float(c.get("qty_mt"), 0.0) or 0.0,
            "received": to_float(c.get("delivered_mt"), 0.0) or 0.0,
            "used": to_float(c.get("consumed_mt"), 0.0) or 0.0,
            "premium": prem, "futures": (c.get("contract_month") or {}).get("code") if isinstance(c.get("contract_month"), dict)
            else (c.get("futures_month") or ""),
            "fx_contract": to_float(c.get("fx"), None) if str(c.get("fx_basis") or "").lower().startswith("form 4") else None,
            "fixed_cbot": _fixed_cbot(cl, cif, factor, prem),
            "receiving_date": str(c.get("storage_start") or "")[:10], "vessel": "", "shipment": "",
            "lots": cl, "closed": when})
    out.sort(key=lambda r: (r["closed"], r["contract"]), reverse=True)
    return out


def has_contract_number(name: Any) -> bool:
    """'460/20050000', 'SC33911-CH', 'TRADE#SC-33039' carry a contract number (5+ digits in a row);
    '4000MT COFCO - BRZ' is only a description."""
    return re.search(r"\d{5,}", str(name or "")) is not None


def flag_look_alikes(rows, pool=None):
    """Same supplier, tonnage, premium and receiving date, where at least one of the two has no contract
    number of its own: probably one contract entered twice. Two different contract numbers are two
    contracts. ``pool``: all open rows to compare against (default ``rows``)."""
    seen = {}
    for r in pool if pool is not None else rows:
        if not r["receiving_date"]:
            continue
        key = (r["supplier"].strip().upper(), round(r["total"]), r["premium"], r["receiving_date"])
        seen.setdefault(key, []).append(r)
    for r in rows:
        if not r["receiving_date"]:
            continue
        key = (r["supplier"].strip().upper(), round(r["total"]), r["premium"], r["receiving_date"])
        twins = [x for x in seen.get(key, []) if x is not r and x["contract_id"] != r["contract_id"]
                 and not (has_contract_number(x["contract"]) and has_contract_number(r["contract"]))]
        if twins:
            names = ", ".join(f"{x['contract']} ({x['contract_id']})" for x in twins)
            r["remarks"].append(f"Same supplier, MT, premium and receiving date as {names}: "
                                "check it is not one contract entered twice")
    return rows


def label(r) -> str:
    """'ADM Medsofts (2 K mt) BRZ @ 180 Over Z' — the report's supplier cell."""
    k = r["total"] / 1000.0
    kt = f"{k:g}" if abs(k - round(k, 1)) < 1e-9 else f"{k:.1f}"
    prem = "" if r["premium"] is None else f" @ {r['premium']:g} Over {month_code(r['futures'])}"
    return f"{r['supplier']} ( {kt} K mt ) {r['origin']}{prem}".strip()


def delivery_text(r, as_of: dt.date | None = None) -> str:
    bits = [r["vessel"]] if r["vessel"] else []
    if r["receiving_date"]:
        bits.append("received " + r["receiving_date"])
    else:
        bits.append(r["shipment"] or "not received yet")
    return " · ".join(bits)




# ── calendar: CBOT holidays, trading days, first notice day ─────────────────

def _nth_weekday(year, month, weekday, n):
    d = dt.date(year, month, 1)
    d += dt.timedelta(days=(weekday - d.weekday()) % 7)
    return d + dt.timedelta(weeks=n - 1)


def _last_weekday(year, month, weekday):
    d = dt.date(year, month + 1, 1) - dt.timedelta(days=1) if month < 12 else dt.date(year, 12, 31)
    return d - dt.timedelta(days=(d.weekday() - weekday) % 7)


def _easter(year):
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    month = (h + l_ - 7 * m + 114) // 31
    return dt.date(year, month, (h + l_ - 7 * m + 114) % 31 + 1)


def _observed(d):
    return d - dt.timedelta(days=1) if d.weekday() == 5 else d + dt.timedelta(days=1) if d.weekday() == 6 else d


def cbot_holidays(year):
    """Full CBOT grain closures of a year (US exchange holidays)."""
    return sorted({
        _observed(dt.date(year, 1, 1)), _nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3),
        _easter(year) - dt.timedelta(days=2), _last_weekday(year, 5, 0), _observed(dt.date(year, 6, 19)),
        _observed(dt.date(year, 7, 4)), _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 11, 3, 4),
        _observed(dt.date(year, 12, 25))})


def trading_days(start, end, holidays=()):
    """Weekdays from ``start`` to ``end`` inclusive, less holidays (Excel's NETWORKDAYS)."""
    if not start or not end or end < start:
        return 0
    hol = set(holidays or ())
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5 and d not in hol:
            n += 1
        d += dt.timedelta(days=1)
    return n


def first_notice_day(futures, holidays=None):
    """CBOT grain first notice day: the last trading day of the month before the contract month."""
    months = {k: i for i, k in enumerate(("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT",
                                          "NOV", "DEC"), start=1)}
    try:
        mon, yy = str(futures).upper().replace(" ", "").split("-")[:2]
        month, year = months[mon[:3]], 2000 + int(yy[-2:])
    except (KeyError, ValueError):
        return None
    hol = set(holidays if holidays is not None else cbot_holidays(year) + cbot_holidays(year - 1))
    d = dt.date(year, month, 1) - dt.timedelta(days=1)
    while d.weekday() >= 5 or d in hol:
        d -= dt.timedelta(days=1)
    return d


# ── arrivals and cover ──────────────────────────────────────────────────────

_MONTH_WORDS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct",
                                            "nov", "dec"), start=1)}


def eta_from_text(text, as_of):
    """An estimated arrival date from a shipment text such as 'End December' or '2nd half October'.

    Returns (date or None, note). A period that has already passed gives no date: the cargo is late and
    only the user knows when it will land, so it is left out of the cover until a date is entered.
    """
    t = str(text or "").lower()
    found = [(m.start(), _MONTH_WORDS[m.group(1)[:3]]) for m in
             re.finditer(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*", t)]
    if not found:
        return None, "enter the expected arrival date"
    month = sorted(found)[0][1]
    year = as_of.year + (1 if month < as_of.month - 6 else 0)
    head = t[:sorted(found)[0][0]]
    day = (25 if re.search(r"\b(end|late|2nd half|second half)\b", head) else
           7 if re.search(r"\b(early|first week|1st week|beginning|first half|1st half)\b", head) else
           15)
    eta = dt.date(year, month, day)
    if eta <= as_of:
        return None, f"'{text}' has passed and it is not received: enter the expected date"
    return eta, f"estimated from '{text}': enter the real date"


def simulate_cover(stock, rate, arrivals, start, days=60):
    """Day by day from ``start``: arrivals that day, opening stock, consumption, closing stock.

    ``arrivals``: [(date, MT)]. Arrivals dated before ``start`` land on the first day. Returns the rows and
    the last fully covered day (None when the stock lasts the whole horizon).
    """
    rows, closing, covered = [], max(stock or 0.0, 0.0), None
    for k in range(days):
        d = start + dt.timedelta(days=k)
        arr = sum(mt for e, mt in arrivals if e and ((e <= d) if k == 0 else (e == d)))
        opening = closing
        short = opening + arr < rate
        use = min(rate, opening + arr)
        closing = opening + arr - use
        rows.append({"date": d, "arrivals": arr, "opening": opening, "use": use, "closing": closing, "short": short})
        if short and covered is None:
            covered = d - dt.timedelta(days=1)
    return rows, covered


# ── the sheet ───────────────────────────────────────────────────────────────

def write_position_sheet(wb, rows, *, as_of, factor=0.3937, fx=None, cbot=None, rate=None, rate_note="",
                         title="YC Contracts position", index=0, horizon=60):
    """Add the sheet to ``wb`` at ``index``; return {"cache": {cell: value}, ...} for store_formula_results.

    Top to bottom: headline boxes, 1 · pricing to-do, 2 · cover, 3 · the YC table, exposure, and the day-by-
    day cover table the cover block and the chart read from.
    """
    from openpyxl.chart import BarChart, LineChart, Reference
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    EPOCH = dt.date(1899, 12, 30)
    ws = wb.create_sheet(SHEET, index)
    cache = {}
    thin = Side(style="thin", color="7F8C9D")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    SLATE, YELLOW, BAND, TITLE, INPUT, NAVY = "44546A", "FFFF00", "DDEBF7", "FFFF99", "FFFBEA", "1F3A5F"
    RED, AMBER, GREEN = "B3261E", "B26B00", "1A7A1A"
    F0, F2, DF = "#,##0;-#,##0;\"-\"", "#,##0.00", "yyyy-mm-dd"
    S0 = "+#,##0;-#,##0;0"

    def put(r, c, v, fmt=None, bold=False, color=None, fill=None, align=None, italic=False, size=None,
            wrap=False, border=True):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        cell.font = Font(bold=bold, color=color, italic=italic, size=size or 11)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if border:
            cell.border = box
        return cell

    def fml(r, c, formula, value, fmt=F0, **kw):
        put(r, c, formula, fmt, **kw)
        if isinstance(value, dt.date):
            value = (value - EPOCH).days
        cache[f"{L(c)}{r}"] = "" if value is None else value

    def bar(r, text, c1=1, c2=16):
        ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        put(r, c1, text, bold=True, color="FFFFFF", fill=NAVY, size=12)
        ws.row_dimensions[r].height = 22

    widths = {"A": 40, "B": 20, "C": 36, "D": 11, "E": 11, "F": 11, "G": 11, "H": 10, "I": 10, "J": 10, "K": 11,
              "L": 11, "M": 11, "N": 13, "O": 12, "P": 11, "Q": 3, "R": 11, "S": 11, "T": 11, "U": 12, "V": 12,
              "W": 12, "X": 60}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False

    rate = to_float(rate, None) or 0.0
    hol = [h for y in (as_of.year, as_of.year + 1) for h in cbot_holidays(y) if h >= as_of]
    n = len(rows)
    allocs = [allocate(r["total"], r["received"], r["used"], r["port"], r["priced"]) for r in rows]
    for r_, a in zip(rows, allocs):
        r_["_a"] = a
        r_["_unpriced"] = a["open_way"] + a["short_delivered"]
        r_["_fnd"] = first_notice_day(r_["futures"]) if r_["_unpriced"] > 0 else None

    # ── layout ──
    todo = sorted([r for r in rows if r["_unpriced"] > 0.5],
                  key=lambda r: (-(r["_a"]["sold_short"] > 0.5), -(r["_a"]["wh_short"] + r["_a"]["port_short"] > 0.5),
                                 r["_fnd"] or dt.date.max, r["receiving_date"] or "9999"))
    arrive = [r for r in rows if r["_a"]["open_way"] + r["_a"]["long_way"] > 0.5]
    T_BAR, T_H, T0 = 12, 13, 14                # to-do bar, header, first row (settings box sits in R5:U10)
    T_TOT = T0 + max(len(todo), 1)
    C_BAR = T_TOT + 2
    C_SUM = C_BAR + 1                         # 5 summary lines
    C_ARR_H = C_SUM + 6
    C_ARR0 = C_ARR_H + 1
    C_END = max(C_ARR0 + max(len(arrive), 1), C_BAR + 17)
    Y_BAR = C_END + 2
    Y_H1, Y_H2 = Y_BAR + 1, Y_BAR + 2
    Y0 = Y_BAR + 3
    Y_LAST = Y0 + n - 1
    Y_TOT = Y0 + max(n, 1) if n == 0 else Y_LAST + 1
    E_BAR = Y_TOT + 2
    D_BAR = E_BAR + 10
    D_H = D_BAR + 1
    D0 = D_H + 1
    D_LAST = D0 + horizon - 1
    yrow = {id(r): Y0 + i for i, r in enumerate(rows)}

    # settings (yellow) — every formula reads these
    S_AS, S_RATE, S_CBOT, S_FX, S_CONV = "$U$6", "$U$7", "$U$8", "$U$9", "$U$10"
    ws.merge_cells("R5:U5")
    put(5, 18, "Settings (yellow = input)", bold=True, color="FFFFFF", fill=SLATE)
    for c in (19, 20, 21):
        put(5, c, None, fill=SLATE)
    for k, (text, val, fmt) in enumerate((("As of", as_of, DF), ("Consumption MT/day", rate or None, F0),
                                          ("CBOT now ¢/bu", cbot, F2), ("FX now EGP/USD", fx, "0.0000"),
                                          ("Conversion USD/MT per ¢/bu", factor, "0.0000")), start=6):
        ws.merge_cells(start_row=k, start_column=18, end_row=k, end_column=20)
        put(k, 18, text)
        put(k, 19, None); put(k, 20, None)
        put(k, 21, val, fmt, fill=INPUT, bold=True)
    ws.column_dimensions["Z"].width = 12
    put(5, 26, "CBOT holidays", bold=True, color="FFFFFF", fill=SLATE)
    for k, h in enumerate(hol or [None], start=6):
        put(k, 26, h, DF, fill=INPUT)
    HOL = f"$Z$6:$Z${5 + max(len(hol), 1)}"
    fxv, cbv, cv = fx or 0.0, cbot, factor

    # title
    ws.merge_cells("A1:P1"); ws.merge_cells("A2:P2"); ws.merge_cells("A3:P3")
    put(1, 1, title, bold=True, size=14, fill=TITLE, align="center", border=False)
    put(2, 1, f"Date : {as_of.day} {as_of:%B %Y}", bold=True, fill=TITLE, align="center", border=False)
    put(3, 1, "From the app. Long = CBOT priced (pricing lots); Short = CBOT still open. Sold / used = FIFO "
              "estimate" + (f" ({rate_note})" if rate_note else "") + ". Yellow cells are inputs: settings, port "
              "tonnes, arrival dates.", italic=True, color="555555", wrap=True, border=False, size=9)

    # ── 3 · YC table first (the other blocks read its cells) ──
    bar(Y_BAR, "3 · Contracts position — where the tonnes are and whether their CBOT is priced (as the YC report)")
    singles = {1: "Supplier", 2: "Contract", 3: "Vessel / Delivery", 4: "Total Quantity", 5: "Open & on the way",
               6: "Short & Delivered", 7: "Long & On the Way", 14: "Premium", 15: "CBOT", 16: "CIF $"}
    for c, text in singles.items():
        ws.merge_cells(start_row=Y_H1, start_column=c, end_row=Y_H2, end_column=c)
        put(Y_H1, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center", wrap=True)
        put(Y_H2, c, None, fill=SLATE)
    for c0, text in ((8, "Port"), (10, "Warehouses"), (12, "Sold / used")):
        ws.merge_cells(start_row=Y_H1, start_column=c0, end_row=Y_H1, end_column=c0 + 1)
        put(Y_H1, c0, text, bold=True, color="FFFFFF", fill=SLATE, align="center")
        put(Y_H1, c0 + 1, None, fill=SLATE)
        put(Y_H2, c0, "Long", bold=True, color="FFFFFF", fill=SLATE, align="center")
        put(Y_H2, c0 + 1, "Short", bold=True, fill=YELLOW, align="center")
    ws.merge_cells(start_row=Y_H1, start_column=18, end_row=Y_H1, end_column=22)
    put(Y_H1, 18, "From the app (yellow = input · enter port tonnes)", bold=True, fill=INPUT, align="center")
    for c in range(19, 23):
        put(Y_H1, c, None, fill=INPUT)
    for c, text in zip(range(18, 25), ("Received MT", "Sold / used MT (FIFO)", "At port MT", "Priced MT (lots)",
                                       "Fixed CBOT ¢/bu", "Check", "Remarks")):
        put(Y_H2, c, text, bold=True, fill=INPUT if c <= 22 else "F2F2F2", align="center", wrap=True)
    ws.row_dimensions[Y_H1].height, ws.row_dimensions[Y_H2].height = 22, 34
    for i, row in enumerate(rows):
        r, a = Y0 + i, row["_a"]
        band = BAND if i % 2 == 0 else None
        put(r, 1, label(row), bold=True, fill=band)
        put(r, 2, row["contract"], fill=band)
        put(r, 3, delivery_text(row), fill=band, align="center")
        put(r, 4, row["total"], F0, bold=True, fill=INPUT, align="right")
        for c, key in ((18, "received"), (19, "used"), (20, "port"), (21, "priced")):
            put(r, c, row[key], F0, fill=INPUT)
        put(r, 22, row["fixed_cbot"], F2, fill=INPUT)
        put(r, 14, row["premium"], F2, bold=True, fill=band)
        put(r, 15, month_code(row["futures"]), bold=True, fill=YELLOW, align="center")
        rec = f"MIN(MAX(R{r},0),D{r})"
        used = f"MIN(MAX(S{r},0),{rec})"
        stock = f"({rec}-{used})"
        port = f"MIN(MAX(T{r},0),{stock})"
        wh = f"({stock}-{port})"
        pr = f"MIN(MAX(U{r},0),D{r})"
        fml(r, 12, f"=MIN({pr},{used})", a["sold_long"], fill=band)
        fml(r, 13, f"={used}-L{r}", a["sold_short"], fill=YELLOW)
        fml(r, 10, f"=MIN({pr}-L{r},{wh})", a["wh_long"], fill=band)
        fml(r, 11, f"={wh}-J{r}", a["wh_short"], fill=YELLOW)
        fml(r, 8, f"=MIN({pr}-L{r}-J{r},{port})", a["port_long"], fill=band)
        fml(r, 9, f"={port}-H{r}", a["port_short"], fill=YELLOW)
        fml(r, 7, f"=MIN({pr}-L{r}-J{r}-H{r},D{r}-{rec})", a["long_way"], fill=band)
        fml(r, 5, f"=D{r}-{rec}-G{r}", a["open_way"], fill=band)
        fml(r, 6, f"=M{r}+K{r}+I{r}", a["short_delivered"], fill=band)
        cif = ((row["fixed_cbot"] + row["premium"]) * cv if row["fixed_cbot"] is not None and row["premium"] is not None
               and row["priced"] > 0 else None)
        fml(r, 16, f'=IF(AND(U{r}>0,ISNUMBER(V{r}),ISNUMBER(N{r})),(V{r}+N{r})*{S_CONV},"")', cif, "$#,##0.00",
            fill=band)
        fml(r, 23, f'=IF(ABS(D{r}-(E{r}+F{r}+G{r}+H{r}+J{r}+L{r}))<0.5,"✓","✗")', "✓", None, align="center")
        put(r, 24, "; ".join(row["remarks"]), color=RED if row["remarks"] else None, wrap=True, size=9)
        ws.row_dimensions[r].height = 30 if row["remarks"] else 22
    put(Y_TOT, 1, "Total Feed", bold=True, color="FFFFFF", fill="000000", size=12)
    for c in (2, 3, 15, 16):
        put(Y_TOT, c, None, fill="000000")
    keys = {5: "open_way", 6: "short_delivered", 7: "long_way", 8: "port_long", 9: "port_short", 10: "wh_long",
            11: "wh_short", 12: "sold_long", 13: "sold_short"}
    tot = {c: sum(r["_a"][k] for r in rows) for c, k in keys.items()}
    tot[4] = sum(r["total"] for r in rows)
    for c in range(4, 14):
        fml(Y_TOT, c, f"=SUM({L(c)}{Y0}:{L(c)}{Y_LAST})" if n else "=0", tot[c], bold=True, color="FFFFFF",
            fill="000000")
    wprem = sum(r["total"] * (r["premium"] or 0) for r in rows) / tot[4] if tot[4] else None
    fml(Y_TOT, 14, f'=IFERROR(SUMPRODUCT(D{Y0}:D{Y_LAST},N{Y0}:N{Y_LAST})/D{Y_TOT},"")', wprem, F2, bold=True,
        color="FFFFFF", fill="000000")
    ws.row_dimensions[Y_TOT].height = 24
    unpriced = tot[5] + tot[6]
    priced = tot[7] + tot[8] + tot[10] + tot[12]
    stock_now = tot[8] + tot[9] + tot[10] + tot[11]
    UNP = f"(E{Y_TOT}+F{Y_TOT})"
    STOCK = f"(H{Y_TOT}+I{Y_TOT}+J{Y_TOT}+K{Y_TOT})"

    # exposure (detail under the table)
    up_prem = (sum(r["_unpriced"] * (r["premium"] or 0) for r in rows) / unpriced) if unpriced else None
    bar(E_BAR, "CBOT exposure — what is still unpriced", 1, 3)
    ex = [("Total contracted MT", f"=D{Y_TOT}", tot[4], F0),
          ("Priced (Long) MT", f"=G{Y_TOT}+H{Y_TOT}+J{Y_TOT}+L{Y_TOT}", priced, F0),
          ("Unpriced (Short) MT", f"={UNP}", unpriced, F0),
          ("   of which already sold / used", f"=M{Y_TOT}", tot[13], F0),
          ("Avg premium of the unpriced tonnes ¢/bu",
           f'=IFERROR((SUMPRODUCT(E{Y0}:E{Y_LAST},N{Y0}:N{Y_LAST})+SUMPRODUCT(F{Y0}:F{Y_LAST},N{Y0}:N{Y_LAST}))'
           f'/{UNP},"")', up_prem, F2),
          ("Each 1 ¢/bu move in CBOT, USD", f"={UNP}*{S_CONV}", unpriced * cv, F0),
          ("Each 1 ¢/bu move in CBOT, EGP (Form 4 FX where recorded)", f"=O{T_TOT}", None, F0),
          ("Indicative CIF of the unpriced tonnes at CBOT now, $/MT",
           f'=IF(AND(ISNUMBER({S_CBOT}),ISNUMBER(C{E_BAR + 5})),({S_CBOT}+C{E_BAR + 5})*{S_CONV},"")',
           (cbv + up_prem) * cv if cbv is not None and up_prem is not None else None, "$#,##0.00")]
    for k, (text, formula, value, fmt) in enumerate(ex, start=1):
        r = E_BAR + k
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        put(r, 1, text, bold=k in (3, 7)); put(r, 2, None)
        fml(r, 3, formula, value, fmt, bold=k in (3, 7))

    # ── 2 · cover: arrivals, summary, day-by-day table, chart ──
    for r_ in arrive:
        if r_.get("eta") is None and not r_.get("_eta_note"):
            r_["eta"], r_["_eta_note"] = eta_from_text(r_.get("shipment"), as_of)
    bar(C_BAR, "2 · Cover — stock today plus arrivals against consumption")
    for c, text in zip(range(1, 6), ("Arriving", "Contract", "Arrival date note", "MT to arrive", "ETA")):
        put(C_ARR_H, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center")
    arr_rows = []
    for i, r_ in enumerate(arrive):
        r = C_ARR0 + i
        y = yrow[id(r_)]
        put(r, 1, label(r_)); put(r, 2, r_["contract"])
        put(r, 3, r_.get("_eta_note") or "", italic=True, size=9, wrap=True,
            color=RED if r_.get("eta") is None else "555555")
        mt = r_["_a"]["open_way"] + r_["_a"]["long_way"]
        fml(r, 4, f"=E{y}+G{y}", mt)
        put(r, 5, r_.get("eta"), DF, fill=INPUT, bold=True)
        arr_rows.append((r_.get("eta"), mt))
    A_MT = f"$D${C_ARR0}:$D${C_ARR0 + max(len(arrive), 1) - 1}"
    A_ETA = f"$E${C_ARR0}:$E${C_ARR0 + max(len(arrive), 1) - 1}"
    if not arrive:
        put(C_ARR0, 1, "Nothing still to arrive", italic=True)

    sim, covered = simulate_cover(stock_now, rate, arr_rows, as_of + dt.timedelta(days=1), horizon)
    bar(D_BAR, "Cover — day by day (read by section 2 and its chart)", 1, 6)
    for c, text in zip(range(1, 7), ("Date", "Arrivals MT", "Opening stock MT", "Consumption MT", "Closing stock MT",
                                     "Short?")):
        put(D_H, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center")
    for k, srow in enumerate(sim):
        r = D0 + k
        fml(r, 1, f"={S_AS}+{k + 1}", srow["date"], DF)
        crit = f'"<="&A{r}' if k == 0 else f"A{r}"
        fml(r, 2, f"=SUMIFS({A_MT},{A_ETA},{crit})" if arrive else "=0", srow["arrivals"])
        fml(r, 3, f"={STOCK}" if k == 0 else f"=E{r - 1}", srow["opening"])
        fml(r, 4, f"=MIN({S_RATE},C{r}+B{r})", srow["use"])
        fml(r, 5, f"=C{r}+B{r}-D{r}", srow["closing"])
        fml(r, 6, f"=IF(C{r}+B{r}<{S_RATE},1,0)", 1 if srow["short"] else 0, "0", align="center")
    ws.conditional_formatting.add(f"F{D0}:F{D_LAST}", CellIsRule(operator="equal", formula=["1"],
                                                                 font=Font(color=RED, bold=True)))
    COVER = (f'=IF(COUNTIF(F{D0}:F{D_LAST},1)=0,"beyond "&TEXT(A{D_LAST},"yyyy-mm-dd"),'
             f'INDEX(A{D0}:A{D_LAST},MATCH(1,F{D0}:F{D_LAST},0))-1)')
    cover_val = covered if covered is not None else f"beyond {sim[-1]['date'].isoformat()}"
    no_eta = sum(1 for e, _ in arr_rows if e is None)
    lines = [("Stock today MT (port + warehouses)", f"={STOCK}", stock_now, F0),
             ("Consumption MT/day", f"={S_RATE}", rate, F0),
             ("Days of stock without arrivals", f'=IFERROR({STOCK}/{S_RATE},"")', stock_now / rate if rate else None,
              "0.0"),
             ("Covered until (stock + arrivals with a date)", COVER, cover_val, DF),
             ("Arrivals without a date (not counted)", f'=COUNTBLANK({A_ETA})' if arrive else "=0", no_eta, "0"),
             (f"Days short of corn in the next {horizon} days", f"=SUM(F{D0}:F{D_LAST})",
              sum(1 for x in sim if x["short"]), "0")]
    for k, (text, formula, value, fmt) in enumerate(lines):
        r = C_SUM + k
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=2)
        put(r, 1, text, bold=k == 3); put(r, 2, None)
        fml(r, 3, formula, value, fmt, bold=k == 3, align="right",
            color=RED if ((k == 4 and no_eta) or (k == 5 and any(x["short"] for x in sim))) else None)
    chart = BarChart()
    chart.title = "Closing stock (line) and arrivals (bars), MT"
    chart.y_axis.title = "MT"
    chart.add_data(Reference(ws, min_col=2, min_row=D_H, max_row=D_LAST), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=1, min_row=D0, max_row=D_LAST))
    line = LineChart()
    line.add_data(Reference(ws, min_col=5, min_row=D_H, max_row=D_LAST), titles_from_data=True)
    for ser in line.series:
        ser.smooth = False
        ser.graphicalProperties.line.solidFill = "B3261E"
        ser.graphicalProperties.line.width = 28000
    chart += line
    chart.x_axis.number_format = "dd-mmm"
    chart.height, chart.width = 8.2, 22
    chart.legend.position = "b"
    ws.add_chart(chart, f"G{C_BAR + 1}")

    # ── 1 · pricing to-do ──
    bar(T_BAR, "1 · Pricing to-do — unpriced tonnes, most urgent first (used before priced is the most exposed)")
    heads = ["Supplier", "Contract", "Why now", "MT to price", "of which used", "in stock", "on the way",
             "Premium ¢/bu", "Prem. + disch. ¢/bu", "CIF now $/MT", "Own after excl. freight EGP/MT", "Local now excl. transport EGP/MT",
             "Saving now EGP/MT", "Saving on these MT, EGP", "1 ¢/bu move, EGP", "Trading days to FND"]
    for c, text in enumerate(heads, start=1):
        put(T_H, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center", wrap=True)
    for c, text in zip(range(18, 24), ("Discharge EGP/MT", "Clearance EGP/MT", "Freight EGP/MT (not included)",
                                       "Local excl. transport EGP/MT", "First notice day", "Contract FX (Form 4)")):
        put(T_H, c, text, bold=True, fill=INPUT, align="center", wrap=True)
    ws.row_dimensions[T_H].height = 44
    min_days, sav_tot, todo_vals, cent_egp = None, 0.0, [], 0.0
    for i, r_ in enumerate(todo):
        r, y, a = T0 + i, yrow[id(r_)], r_["_a"]
        band = BAND if i % 2 == 0 else None
        put(r, 1, label(r_), bold=True, fill=band); put(r, 2, r_["contract"], fill=band)
        used_u, stock_u, way_u = a["sold_short"], a["wh_short"] + a["port_short"], a["open_way"]
        mt = used_u + stock_u + way_u
        why = (f"{used_u:,.0f} MT already used" if used_u > 0.5 else "in stock" if stock_u > 0.5 else "on the way")
        fml(r, 3, f'=IF(E{r}>0.5,TEXT(E{r},"#,##0")&" MT already used",IF(F{r}>0.5,"in stock","on the way"))', why,
            None, fill=band, color=RED if used_u > 0.5 else None, bold=used_u > 0.5)
        fml(r, 4, f"=E{r}+F{r}+G{r}", mt, bold=True, fill=band)
        fml(r, 5, f"=M{y}", used_u, fill=band)
        fml(r, 6, f"=K{y}+I{y}", stock_u, fill=band)
        fml(r, 7, f"=E{y}", way_u, fill=band)
        prem = r_["premium"]
        fml(r, 8, f"=N{y}", prem, F2, fill=band)
        disc, clr, frt, loc = (r_.get(k) for k in ("discharge", "clearance", "freight", "local"))
        for c, v in ((18, disc), (19, clr), (20, frt), (21, loc)):
            put(r, c, v, F2, fill=INPUT)
        put(r, 22, r_["_fnd"], DF, fill=INPUT)
        put(r, 23, r_.get("fx_contract"), "0.0000", fill=INPUT)
        fxe = r_.get("fx_contract") or fxv                     # the contract's Form 4 rate, else FX now
        FXE = f"IF(ISNUMBER(W{r}),W{r},{S_FX})"
        pd = prem + (disc or 0) / fxe / cv if prem is not None and fxe and cv else None
        fml(r, 9, f'=IFERROR(H{r}+R{r}/{FXE}/{S_CONV},"")', pd, F2, fill=band)
        cif = (cbv + prem) * cv if cbv is not None and prem is not None else None
        fml(r, 10, f'=IFERROR(({S_CBOT}+H{r})*{S_CONV},"")', cif, "$#,##0.00", fill=band)
        landed = cif * fxe + (disc or 0) + (clr or 0) if cif is not None else None     # own after, no freight
        fml(r, 11, f'=IFERROR(J{r}*{FXE}+R{r}+S{r},"")', landed, F0, fill=band)
        fml(r, 12, f'=IF(ISNUMBER(U{r}),U{r},"")', loc, F0, fill=band)
        sav = loc - landed if loc is not None and landed is not None else None
        fml(r, 13, f'=IFERROR(L{r}-K{r},"")', sav, S0, fill=band, bold=True)
        fml(r, 14, f'=IFERROR(M{r}*D{r},"")', sav * mt if sav is not None else None, S0, fill=band)
        fml(r, 15, f"=D{r}*{S_CONV}*{FXE}", mt * cv * fxe, F0, fill=band)
        cent_egp += mt * cv * fxe
        days = trading_days(as_of, r_["_fnd"], hol) if r_["_fnd"] else None
        fml(r, 16, f'=IF(ISNUMBER(V{r}),NETWORKDAYS({S_AS},V{r},{HOL}),"")', days, "0", bold=True, fill=band,
            align="center")
        if days is not None:
            min_days = days if min_days is None else min(min_days, days)
        if sav is not None:
            sav_tot += sav * mt
        todo_vals.append(mt)
        ws.row_dimensions[r].height = 22
    if not todo:
        put(T0, 1, "Everything is priced", italic=True)
    TL = T0 + max(len(todo), 1) - 1
    put(T_TOT, 1, "Total to price", bold=True, color="FFFFFF", fill="000000")
    for c in (2, 3, 8, 9, 10, 11, 12):
        put(T_TOT, c, None, fill="000000")
    sums = {4: sum(todo_vals), 5: sum(r["_a"]["sold_short"] for r in todo),
            6: sum(r["_a"]["wh_short"] + r["_a"]["port_short"] for r in todo), 7: sum(r["_a"]["open_way"] for r in todo)}
    for c, v in sums.items():
        fml(T_TOT, c, f"=SUM({L(c)}{T0}:{L(c)}{TL})", v, bold=True, color="FFFFFF", fill="000000")
    fml(T_TOT, 13, f'=IFERROR(N{T_TOT}/D{T_TOT},"")', sav_tot / sums[4] if sums[4] else None, S0, bold=True,
        color="FFFFFF", fill="000000")
    fml(T_TOT, 14, f"=SUM(N{T0}:N{TL})", sav_tot, S0, bold=True, color="FFFFFF", fill="000000")
    fml(T_TOT, 15, f"=SUM(O{T0}:O{TL})", cent_egp, F0, bold=True, color="FFFFFF", fill="000000")
    cache[f"C{E_BAR + 7}"] = cent_egp                  # the exposure box reads this total
    fml(T_TOT, 16, f'=IF(COUNT(P{T0}:P{TL})=0,"",MIN(P{T0}:P{TL}))', min_days, "0", bold=True, color="FFFFFF",
        fill="000000", align="center")
    ws.conditional_formatting.add(f"P{T0}:P{TL}", CellIsRule(operator="lessThanOrEqual", formula=["5"],
                                                            fill=PatternFill("solid", fgColor="F8D7DA")))
    ws.conditional_formatting.add(f"P{T0}:P{TL}", CellIsRule(operator="between", formula=["6", "10"],
                                                            fill=PatternFill("solid", fgColor="FFF3CD")))
    ws.conditional_formatting.add(f"M{T0}:N{T_TOT}", CellIsRule(operator="lessThan", formula=["0"],
                                                               font=Font(color=RED, bold=True)))
    ws.conditional_formatting.add(f"M{T0}:N{TL}", CellIsRule(operator="greaterThan", formula=["0"],
                                                            font=Font(color=GREEN, bold=True)))

    # ── headline boxes (rows 5–7) ──
    fnd_min = min((r["_fnd"] for r in todo if r["_fnd"]), default=None)
    boxes = [
        ((1, 1), "Not priced yet", f"={UNP}", unpriced, '#,##0" MT"',
         f'="of "&TEXT(D{Y_TOT},"#,##0")&" MT contracted"', f"of {tot[4]:,.0f} MT contracted", RED),
        ((2, 3), "Already used, not priced", f"=M{Y_TOT}", tot[13], '#,##0" MT"',
         None, "used before its CBOT was fixed: price these first", RED),
        ((4, 7), "Days left to fix CBOT on Dec (Z)", f"=P{T_TOT}", min_days, "0",
         f'=IF(COUNT(V{T0}:V{TL})=0,"",\"first notice day \"&TEXT(MIN(V{T0}:V{TL}),"yyyy-mm-dd"))',
         f"first notice day {fnd_min.isoformat()}" if fnd_min else "", AMBER),
        ((8, 11), "Cost of each 1 ¢/bu CBOT move", f"=O{T_TOT}", cent_egp, '#,##0" EGP"',
         f'=TEXT({UNP}*{S_CONV},"#,##0")&" USD on the unpriced tonnes"', f"{unpriced * cv:,.0f} USD on the unpriced tonnes",
         NAVY),
        ((12, 16), "Stock lasts until", f"=C{C_SUM + 3}", cover_val, DF,
         (f'=TEXT({STOCK},"#,##0")&" MT in stock · next arrival "&IF(COUNT({A_ETA})=0,"none dated",'
          f'TEXT(MIN({A_ETA}),"yyyy-mm-dd"))&IF(C{C_SUM + 4}>0," · "&C{C_SUM + 4}&" without a date","")'
          if arrive else f'=TEXT({STOCK},"#,##0")&" MT in stock · nothing to arrive"'),
         (f"{stock_now:,.0f} MT in stock · next arrival "
          + (min(e for e, _ in arr_rows if e).isoformat() if any(e for e, _ in arr_rows) else "none dated")
          + (f" · {no_eta} without a date" if no_eta else "") if arrive else
          f"{stock_now:,.0f} MT in stock · nothing to arrive"), NAVY),
    ]
    for (c1, c2), head, formula, value, fmt, sub_f, sub_v, colour in boxes:
        for r in (5, 6, 7):
            if c2 > c1:
                ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        put(5, c1, head, bold=True, color="FFFFFF", fill=colour, align="center")
        fml(6, c1, formula, value, fmt, bold=True, size=18, align="center", color=colour, fill="F7F9FC")
        if sub_f:
            fml(7, c1, sub_f, sub_v, None, italic=True, size=9, align="center", color="555555", fill="F7F9FC",
                wrap=True)
        else:
            put(7, c1, sub_v, italic=True, size=9, align="center", color="555555", fill="F7F9FC", wrap=True)
        for c in range(c1 + 1, c2 + 1):
            for r in (5, 6, 7):
                ws.cell(r, c).border = box
    ws.row_dimensions[5].height, ws.row_dimensions[6].height, ws.row_dimensions[7].height = 22, 34, 28
    for r in (8, 9, 10, 11):
        ws.row_dimensions[r].height = 8

    ws.freeze_panes = "A5"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_area = f"A1:P{D_LAST}"
    for r_ in rows:
        for k in ("_a", "_unpriced", "_fnd", "_eta_note"):
            r_.pop(k, None)
    return {"cache": cache, "rows": n, "total_row": Y_TOT, "unpriced_mt": unpriced, "priced_mt": priced,
            "used_unpriced_mt": tot[13], "todo_rows": (T0, TL), "cover_until": covered, "stock_mt": stock_now,
            "min_days_to_fnd": min_days, "todo_total": T_TOT, "fx_now": fx,
            "local_date": next((r_.get("local_date") for r_ in todo if r_.get("local_date")), ""),
            "todo_fx": [r_.get("fx_contract") for r_ in todo] or [None],
            "todo_labels": [(r_["contract"], f"{r_['supplier'].split()[0]} · {r_['total']:,.0f} MT"
                             + (f" @ {r_['premium']:g}" if r_["premium"] is not None else "")) for r_ in todo]
                           or [("", "Everything is priced")],
            "layout": {"todo": T0, "cover": C_BAR, "yc": Y0, "day": D0}}


def write_summary_sheet(wb, detail, *, as_of, title="Corn position", index=0):
    """The one-screen first tab: four boxes and what to price first, every figure read from the detail sheet.

    ``detail`` is what write_position_sheet returned. Returns {cell: cached value}.
    """
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    ws = wb.create_sheet(SUMMARY, index)
    d, c_ = f"'{SHEET}'!", detail["cache"]
    cache = {}
    thin = Side(style="thin", color="7F8C9D")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    RED, AMBER, NAVY, SLATE = "B3261E", "B26B00", "1F3A5F", "44546A"
    for col, w in {"A": 44, "B": 23, "C": 12, "D": 12, "E": 14, "F": 14, "G": 15, "H": 12}.items():
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False

    def put(r, c, v, fmt=None, bold=False, color=None, fill=None, align=None, italic=False, size=11, wrap=False,
            border=True):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        cell.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if border:
            cell.border = box
        return cell

    def fml(r, c, formula, ref, fmt=None, **kw):
        put(r, c, formula, fmt, **kw)
        cache[ws.cell(r, c).coordinate] = c_.get(ref, "")

    ws.merge_cells("A1:H1")
    put(1, 1, f"{title} — {as_of.day} {as_of:%B %Y}", bold=True, size=15, color=NAVY, border=False)
    ws.merge_cells("A2:H2")
    put(2, 1, f"Details, inputs and the YC table are on the '{SHEET}' tab.", italic=True, size=9, color="666666",
        border=False)

    # four boxes: A, B, C:E, F:H
    boxes = [((1, 1), "Not priced yet", "A6", '#,##0" MT"', "A7", RED),
             ((2, 2), "Days left to fix CBOT", "D6", "0", "D7", AMBER),
             ((3, 5), "Cost of each 1 ¢/bu CBOT move", "H6", '#,##0" EGP"', None, NAVY),
             ((6, 8), "Stock lasts until", "L6", "yyyy-mm-dd", "L7", NAVY)]
    subs = {"A7": f'="of which "&TEXT({d}B6,"#,##0")&" MT already used"',
            "D7": f"={d}D7",
            "L7": f"={d}L7"}
    sub_vals = {"A7": f"of which {c_.get('B6', 0):,.0f} MT already used", "D7": c_.get("D7", ""),
                "L7": c_.get("L7", "")}
    for (c1, c2), head, ref, fmt, sub, colour in boxes:
        for r in (4, 5, 6):
            if c2 > c1:
                ws.merge_cells(start_row=r, start_column=c1, end_row=r, end_column=c2)
        put(4, c1, head, bold=True, color="FFFFFF", fill=colour, align="center", wrap=True)
        fml(5, c1, f"={d}{ref}", ref, fmt, bold=True, size=20, color=colour, fill="F7F9FC", align="center")
        if sub:
            put(6, c1, subs[sub], None, italic=True, size=9, color="555555", fill="F7F9FC", align="center", wrap=True)
            cache[ws.cell(6, c1).coordinate] = sub_vals[sub]
        else:
            put(6, c1, "a rise makes the unpriced corn dearer; a fall, cheaper", italic=True, size=9, color="555555",
                fill="F7F9FC", align="center", wrap=True)
        for c in range(c1 + 1, c2 + 1):
            for r in (4, 5, 6):
                ws.cell(r, c).border = box
    ws.row_dimensions[4].height, ws.row_dimensions[5].height, ws.row_dimensions[6].height = 30, 40, 30

    # what to price first
    ws.merge_cells("A8:H8")
    put(8, 1, "What to price first", bold=True, color="FFFFFF", fill=NAVY, size=12)
    ldate = detail.get("local_date") or ""
    for c, text in enumerate(("Contract", "Why now", "MT to price", "FX (Form 4)", "Own after excl. freight",
                              "Local now excl. transport" + (f" ({ldate[8:10]}/{ldate[5:7]})" if ldate else ""),
                              "Saving vs local now, EGP/MT", "Days left"), start=1):
        put(9, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center", wrap=True)
    ws.row_dimensions[9].height = 46
    t0, tl = detail["todo_rows"]
    n = tl - t0 + 1
    for i in range(n):
        r, t = 10 + i, t0 + i
        band = "DDEBF7" if i % 2 == 0 else None
        cno, lab = detail["todo_labels"][i]
        put(r, 1, f"{cno}  ·  {lab}" if cno else lab, None, bold=True, fill=band)
        fml(r, 2, f"={d}C{t}", f"C{t}", None, fill=band)
        fml(r, 3, f"={d}D{t}", f"D{t}", "#,##0", bold=True, fill=band)
        fxc = detail["todo_fx"][i]
        put(r, 4, f'=IF(ISNUMBER({d}W{t}),{d}W{t},"pending")', "0.00##", fill=band, align="center",
            italic=fxc is None, color="8A6D00" if fxc is None else None)
        cache[f"D{r}"] = fxc if fxc is not None else "pending"
        fml(r, 5, f"={d}K{t}", f"K{t}", "#,##0", fill=band, align="center")
        fml(r, 6, f"={d}L{t}", f"L{t}", "#,##0", fill=band, align="center")
        fml(r, 7, f"={d}M{t}", f"M{t}", "+#,##0;-#,##0;0", bold=True, fill=band, align="center")
        fml(r, 8, f"={d}P{t}", f"P{t}", "0", bold=True, fill=band, align="center")
        ws.row_dimensions[r].height = 22
    tr = 10 + n
    put(tr, 1, "Total", bold=True, color="FFFFFF", fill="000000")
    for c in (2, 4, 5, 6):
        put(tr, c, None, fill="000000")
    fml(tr, 3, f"={d}D{detail['todo_total']}", f"D{detail['todo_total']}", "#,##0", bold=True, color="FFFFFF",
        fill="000000")
    fml(tr, 7, f"={d}M{detail['todo_total']}", f"M{detail['todo_total']}", "+#,##0;-#,##0;0", bold=True,
        color="FFFFFF", fill="000000", align="center")
    fml(tr, 8, f"={d}P{detail['todo_total']}", f"P{detail['todo_total']}", "0", bold=True, color="FFFFFF",
        fill="000000", align="center")
    ws.conditional_formatting.add(f"B10:B{tr - 1}", FormulaRule(formula=['ISNUMBER(SEARCH("already used",B10))'],
                                                              font=Font(color=RED, bold=True)))
    ws.conditional_formatting.add(f"G10:G{tr - 1}", CellIsRule(operator="lessThan", formula=["0"],
                                                             font=Font(color=RED, bold=True)))
    ws.conditional_formatting.add(f"G10:G{tr - 1}", CellIsRule(operator="greaterThan", formula=["0"],
                                                             font=Font(color="1A7A1A", bold=True)))
    ws.conditional_formatting.add(f"H10:H{tr - 1}", CellIsRule(operator="lessThanOrEqual", formula=["5"],
                                                             fill=PatternFill("solid", fgColor="F8D7DA")))
    ws.conditional_formatting.add(f"H10:H{tr - 1}", CellIsRule(operator="between", formula=["6", "10"],
                                                             fill=PatternFill("solid", fgColor="FFF3CD")))
    ws.merge_cells(start_row=tr + 1, start_column=1, end_row=tr + 1, end_column=8)
    fxn = detail.get("fx_now")
    put(tr + 1, 1, "FX (Form 4) = the contract's recorded Form 4 rate; pending = no Form 4 yet, so FX now"
                   + (f" ({fxn:.4f})" if fxn else "") + " is used. Own after excl. freight = (CBOT now + premium) × 0.3937 × that FX + discharge + clearance. "
                   "Local now excl. transport = the latest local price" + (f" ({ldate})" if ldate else "")
                   + " without its transport. Saving = local − own after, both without freight. Days left = CBOT "
                   "trading days to the first notice day.", italic=True, size=9, color="666666", wrap=True, border=False)
    ws.row_dimensions[tr + 1].height = 40
    ws.page_setup.orientation = "portrait"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 1
    return cache


# ── inventory & pricing: the YC layout with remaining stock, FX, consumption and lots ──

INV_SHEET = "Inventory & pricing"


def consumed_status(total, received, used):
    """'Not arrived' / 'Not consumed yet' / 'Partly consumed' / 'Fully consumed'."""
    total, received, used = (max(to_float(x, 0.0) or 0.0, 0.0) for x in (total, received, used))
    if received <= 0.5:
        return "Not arrived"
    if used <= 0.5:
        return "Not consumed yet"
    if used >= received - 0.5 and received >= total - 0.5:
        return "Fully consumed"
    return "Partly consumed"


def pricing_status(total, priced):
    total, priced = max(to_float(total, 0.0) or 0.0, 0.0), max(to_float(priced, 0.0) or 0.0, 0.0)
    if priced <= 0.5:
        return "Unpriced"
    if priced >= total - 0.5:
        return "Fully priced"
    return f"Partly priced · {priced / total:.0%}" if total else "Partly priced"


def write_inventory_sheet(wb, rows, *, as_of, factor=0.3937, fx_now=None, title="YC Contracts position", index=0,
                          closed_days=15):
    """One row per contract (and one line per priced lot under it): where the tonnes are — on the way,
    remaining in inventory, consumed — each split Long (CBOT priced) / Short (CBOT open), with the
    contract's FX, its consumption status and its pricing status.

    ``rows``: dicts with contract, supplier, origin, total, received, used, premium, futures, fx_contract,
    fixed_cbot, receiving_date, vessel, shipment, lots [{date, mt, cbot}] and closed (ISO date, '' = open).
    Open contracts come first; contracts closed in the last ``closed_days`` days follow under their own heading,
    in grey. Returns {cell: cached value}.
    """
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    EPOCH = dt.date(1899, 12, 30)
    ws = wb.create_sheet(INV_SHEET, index)
    cache = {}
    thin = Side(style="thin", color="7F8C9D")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    SLATE, YELLOW, BAND, TITLE, INPUT = "44546A", "FFFF00", "DDEBF7", "FFFF99", "FFFBEA"
    F0 = '#,##0;-#,##0;"-"'
    widths = {"A": 40, "B": 40, "C": 11, "D": 11, "E": 17, "F": 11, "G": 11, "H": 11, "I": 11, "J": 11, "K": 11,
              "L": 11, "M": 21, "N": 10, "O": 7, "P": 11, "Q": 10, "R": 3, "S": 11, "T": 11, "U": 11, "V": 11,
              "W": 9}
    for col, w in widths.items():
        ws.column_dimensions[col].width = w
    ws.sheet_view.showGridLines = False

    def put(r, c, v, fmt=None, bold=False, color=None, fill=None, align=None, italic=False, size=11, wrap=False,
            border=True):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        cell.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)
        if border:
            cell.border = box
        return cell

    def fml(r, c, formula, value, fmt=F0, **kw):
        put(r, c, formula, fmt, **kw)
        if isinstance(value, dt.date):
            value = (value - EPOCH).days
        cache[ws.cell(r, c).coordinate] = "" if value is None else value

    ws.merge_cells("A1:Q1"); ws.merge_cells("A2:Q2"); ws.merge_cells("A3:Q3")
    put(1, 1, title, bold=True, size=14, fill=TITLE, align="center", border=False)
    put(2, 1, f"Date : {as_of.day} {as_of:%B %Y}", bold=True, fill=TITLE, align="center", border=False)
    put(3, 1, "Long = CBOT priced (the contract's pricing lots, one line each under it with its CIF $ = (lot CBOT + premium) × 0.3937; the contract's CIF $ is their MT-weighted average); Short = CBOT still open. Priced "
              "tonnes count against the oldest tonnes first: consumed, then inventory, then on the way. Consumed = "
              "FIFO estimate. FX = the contract's Form 4 rate; pending = no Form 4 yet"
              + (f" (FX now {fx_now:.4f})" if fx_now else "") + ".", italic=True, size=9, color="555555", wrap=True,
        border=False)
    ws.row_dimensions[3].height = 28

    h1, h2 = 5, 6
    singles = {1: "Supplier", 2: "Vessel / Delivery", 3: "Total Quantity", 4: "FX rate (Form 4)",
               5: "Consumed?", 12: "Priced MT", 13: "Pricing", 14: "Premium", 15: "CBOT", 16: "Fixed CBOT ¢/bu",
               17: "CIF $"}
    for c, text in singles.items():
        ws.merge_cells(start_row=h1, start_column=c, end_row=h2, end_column=c)
        put(h1, c, text, bold=True, color="FFFFFF", fill=SLATE, align="center", wrap=True)
        put(h2, c, None, fill=SLATE)
    for c0, text in ((6, "On the way"), (8, "Remaining in inventory"), (10, "Consumed")):
        ws.merge_cells(start_row=h1, start_column=c0, end_row=h1, end_column=c0 + 1)
        put(h1, c0, text, bold=True, color="FFFFFF", fill=SLATE, align="center")
        put(h1, c0 + 1, None, fill=SLATE)
        put(h2, c0, "Long", bold=True, color="FFFFFF", fill=SLATE, align="center")
        put(h2, c0 + 1, "Short", bold=True, fill=YELLOW, align="center")
    ws.merge_cells(start_row=h1, start_column=19, end_row=h1, end_column=23)
    put(h1, 19, "From the app (yellow = input)", bold=True, fill=INPUT, align="center")
    for c in range(20, 24):
        put(h1, c, None, fill=INPUT)
    for c, text in zip(range(19, 24), ("Received MT", "Consumed MT (FIFO)", "Lot date", "Lot CBOT ¢/bu", "Row")):
        put(h2, c, text, bold=True, fill=INPUT, align="center", wrap=True)
    ws.row_dimensions[h1].height, ws.row_dimensions[h2].height = 24, 30

    from openpyxl.utils import get_column_letter

    def short(d):
        x = _dt_or_none(d)
        return f"{x.day} {x:%b}" if x else str(d or "")

    def group(rows_g, r, kind, is_closed):
      tot = {k: 0.0 for k in ("total", "lw", "sw", "li", "si", "lc", "sc", "priced")}
      for i, row in enumerate(rows_g):
        band = "EDEDED" if is_closed else (BAND if i % 2 == 0 else None)
        lots = [l for l in (row.get("lots") or []) if (to_float(l.get("mt"), 0.0) or 0.0) > 0]
        total = row["total"]
        priced = sum(to_float(l.get("mt"), 0.0) or 0.0 for l in lots)     # as recorded (may round above total)
        a = allocate(total, row["received"], row["used"], 0.0, min(priced, total))
        cr = r                                          # the contract row
        lot_rows = list(range(cr + 1, cr + 1 + len(lots)))
        put(cr, 1, label(row), bold=True, fill=band)
        when = (f"received {short(row['receiving_date'])}" if row.get("receiving_date") else
                (row.get("shipment") or "not received yet"))
        put(cr, 2, f"{row['contract']}  ·  " + (f"{row['vessel']} · " if row.get("vessel") else "") + when
                   + (f"  ·  closed {short(row['closed'])}" if is_closed else ""), fill=band)
        put(cr, 3, total, F0, bold=True, fill=INPUT, align="right")
        fxc = row.get("fx_contract")
        put(cr, 4, fxc if fxc is not None else "pending", "0.00##", fill=INPUT if fxc is not None else band,
            align="center", italic=fxc is None, color="8A6D00" if fxc is None else None)
        put(cr, 19, row["received"], F0, fill=INPUT)
        put(cr, 20, row["used"], F0, fill=INPUT)
        put(cr, 23, kind, None, color="999999", size=8)
        rec = f"MIN(MAX(S{cr},0),C{cr})"
        used = f"MIN(MAX(T{cr},0),{rec})"
        inv = f"({rec}-{used})"
        pr = f"MIN(L{cr},C{cr})"
        st = consumed_status(total, row["received"], row["used"])
        fml(cr, 5, f'=IF({rec}<=0.5,"Not arrived",IF({used}<=0.5,"Not consumed yet",'
                   f'IF(AND({used}>={rec}-0.5,{rec}>=C{cr}-0.5),"Fully consumed","Partly consumed")))', st, None,
            fill=band, align="center", bold=st in ("Fully consumed", "Partly consumed"))
        fml(cr, 12, f"=SUM(L{lot_rows[0]}:L{lot_rows[-1]})" if lots else "=0", priced, bold=True, fill=band)
        fml(cr, 10, f"=MIN({pr},{used})", a["sold_long"], fill=band)
        fml(cr, 11, f"={used}-J{cr}", a["sold_short"], fill=YELLOW)
        fml(cr, 8, f"=MIN({pr}-J{cr},{inv})", a["wh_long"], fill=band)
        fml(cr, 9, f"={inv}-H{cr}", a["wh_short"], fill=YELLOW)
        fml(cr, 6, f"=MIN({pr}-J{cr}-H{cr},C{cr}-{rec})", a["long_way"], fill=band)
        fml(cr, 7, f"=C{cr}-{rec}-F{cr}", a["open_way"], fill=YELLOW)
        ps = pricing_status(total, priced)
        fml(cr, 13, f'=IF(L{cr}<=0.5,"Unpriced",IF(L{cr}>=C{cr}-0.5,"Fully priced","Partly priced · "'
                    f'&TEXT(L{cr}/C{cr},"0%")))', ps, None, fill=band, align="center",
            bold=ps != "Unpriced", color="B26B00" if ps.startswith("Partly") else None)
        put(cr, 14, row["premium"], "#,##0.00", bold=True, fill=band)
        put(cr, 15, month_code(row["futures"]), bold=True, fill=YELLOW, align="center")
        fixed = row.get("fixed_cbot") if priced > 0 else None
        put(cr, 16, fixed, "#,##0.00", fill=INPUT if fixed is not None else band)
        prem_v = row["premium"]
        lot_cbot = [to_float(l.get("cbot"), None) if to_float(l.get("cbot"), None) is not None else fixed
                    for l in lots]
        lot_cif = [(cb + prem_v) * factor if cb is not None and prem_v is not None else None for cb in lot_cbot]
        if lots:
            known = [(to_float(l.get("mt"), 0.0) or 0.0, x) for l, x in zip(lots, lot_cif) if x is not None]
            cif = (sum(m * x for m, x in known) / sum(m for m, _ in known)) if known and sum(m for m, _ in known) else None
            l0, l1 = lot_rows[0], lot_rows[-1]
            fml(cr, 17, f'=IFERROR(SUMPRODUCT(L{l0}:L{l1},Q{l0}:Q{l1})/SUMIF(Q{l0}:Q{l1},">0",L{l0}:L{l1}),"")', cif,
                "$#,##0.00", fill=band, bold=True)
        else:
            cif = (fixed + prem_v) * factor if fixed is not None and prem_v is not None else None
            fml(cr, 17, f'=IF(AND(L{cr}>0,ISNUMBER(P{cr}),ISNUMBER(N{cr})),(P{cr}+N{cr})*{factor},"")', cif,
                "$#,##0.00", fill=band)
        ws.row_dimensions[cr].height = 22
        for k, lot in enumerate(lots):
            lr = lot_rows[k]
            ld = lot.get("date")
            cb = to_float(lot.get("cbot"), None)
            put(lr, 1, "      ↳ lot priced", italic=True, color="555555", size=10)
            put(lr, 2, (f"CBOT {cb:,.2f} ¢/bu" if cb is not None else
                        "CBOT not recorded on the lot" + (f": CIF uses the implied {fixed:,.2f}" if fixed else "")),
                italic=True, color="555555", size=9, wrap=True)
            put(lr, 12, to_float(lot.get("mt"), 0.0), F0, fill=INPUT, italic=True)
            put(lr, 21, _dt_or_none(ld), "yyyy-mm-dd", fill=INPUT)
            put(lr, 22, cb, "#,##0.00", fill=INPUT)
            put(lr, 23, "lot", None, color="999999", size=8)
            fml(lr, 13, f'=IF(ISNUMBER(U{lr}),"priced "&TEXT(U{lr},"dd mmm yyyy"),"priced")',
                ("priced " + _dt_or_none(ld).strftime("%d %b %Y")) if _dt_or_none(ld) else "priced", None,
                italic=True, size=9, align="center", color="555555")
            for c in (3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15):
                put(lr, c, None)
            fml(lr, 16, f'=IF(ISNUMBER(V{lr}),V{lr},IF(ISNUMBER(P{cr}),P{cr},""))', lot_cbot[k], "#,##0.00",
                italic=True, color="555555" if cb is not None else "8A6D00")
            fml(lr, 17, f'=IF(AND(ISNUMBER(P{lr}),ISNUMBER(N{cr})),(P{lr}+N{cr})*{factor},"")', lot_cif[k],
                "$#,##0.00", italic=True, color="555555" if cb is not None else "8A6D00")
            ws.row_dimensions[lr].height = 20
        for key, v in (("total", total), ("lw", a["long_way"]), ("sw", a["open_way"]), ("li", a["wh_long"]),
                       ("si", a["wh_short"]), ("lc", a["sold_long"]), ("sc", a["sold_short"]), ("priced", priced)):
            tot[key] += v
        r = cr + 1 + len(lots)
      return r, tot

    def total_row(tr, text, first_, last_, kind, tot, fill):
        put(tr, 1, text, bold=True, color="FFFFFF", fill=fill, size=12)
        for c in (2, 4, 5, 13, 14, 15, 16, 17):
            put(tr, c, None, fill=fill)
        for c, key in ((3, "total"), (6, "lw"), (7, "sw"), (8, "li"), (9, "si"), (10, "lc"), (11, "sc"),
                       (12, "priced")):
            col = get_column_letter(c)
            fml(tr, c, f'=SUMIF($W${first_}:$W${last_},"{kind}",{col}{first_}:{col}{last_})', tot[key], bold=True,
                color="FFFFFF", fill=fill)
        ws.row_dimensions[tr].height = 24

    cut = as_of - dt.timedelta(days=closed_days)
    open_rows = [x for x in rows if not x.get("closed")]
    recent = [x for x in rows if x.get("closed") and (_dt_or_none(x["closed"]) or dt.date.min) >= cut]
    first = h2 + 1
    r, tot = group(open_rows, first, "contract", False)
    last, tr = r - 1, r
    total_row(tr, "Total Feed (open contracts)", first, last, "contract", tot, "000000")
    end = tr
    closed_tot = None
    if recent:
        hr = tr + 2
        ws.merge_cells(start_row=hr, start_column=1, end_row=hr, end_column=17)
        put(hr, 1, f"Recently closed — closed in the app in the last {closed_days} days (priced; for the record, "
                   "nothing left to price)", bold=True, color="FFFFFF", fill="7F8C9D")
        ws.row_dimensions[hr].height = 20
        r2, closed_tot = group(recent, hr + 1, "closed", True)
        total_row(r2, "Total recently closed", hr + 1, r2 - 1, "closed", closed_tot, "595959")
        end = r2

    # a short key under the table (open contracts)
    k = end + 2
    inv_tot = tot["li"] + tot["si"]
    lines = [("Remaining in inventory MT", f"=H{tr}+I{tr}", inv_tot),
             ("   of which still unpriced", f"=I{tr}", tot["si"]),
             ("Consumed but still unpriced MT", f"=K{tr}", tot["sc"]),
             ("Total unpriced MT (on the way + inventory + consumed)", f"=G{tr}+I{tr}+K{tr}",
              tot["sw"] + tot["si"] + tot["sc"])]
    for j, (text, formula, value) in enumerate(lines):
        ws.merge_cells(start_row=k + j, start_column=1, end_row=k + j, end_column=2)
        put(k + j, 1, text, bold=j in (0, 3)); put(k + j, 2, None)
        fml(k + j, 3, formula, value, bold=j in (0, 3))
    ws.conditional_formatting.add(f"E{first}:E{end}", FormulaRule(
        formula=[f'AND(E{first}="Fully consumed",L{first}<C{first}-0.5)'], font=Font(color="B3261E", bold=True)))
    ws.freeze_panes = f"C{first}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.print_area = f"A1:Q{k + len(lines)}"
    return {"cache": cache, "total_row": tr, "first": first, "last": last, "totals": tot,
            "closed_totals": closed_tot}


def _dt_or_none(v):
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v or "")[:10])
    except ValueError:
        return None
