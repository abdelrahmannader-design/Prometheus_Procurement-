"""CBOT fixed vs consumption — a one-screen-wide overview for one commodity.

The management workbook's consumption-day sheets repeat a contract's terms on every day and run to
forty-odd columns. This writes the same figures so that nothing needs scrolling sideways:

* **Fixed consumption** — one block per contract: its terms once (fixed CBOT, premium, factor, CIF,
  FX, discharge, clearance, landed cost), then one slim row per consumption day (CBOT that day, the
  difference to the fixed CBOT, USD and EGP, local price and the spread to our landed cost).
* **Not fixed consumption** — the same for tonnes consumed from contracts not fixed yet, against the
  latest CBOT (indicative).
* **Open contracts** — for each open contract, CBOT and market FX day by day from a few trading days
  before the contract's date to today, with the change per day and since that date, and what they do
  to our price and the saving at today's contract terms.
* **Summary** — one row per contract, read from the blocks.

Inputs are values (yellow); every derived figure is a formula with its result stored beside it.
``model`` is the management report model (``mgmt_report.build``); the open-contract trails are
prepared by the caller, which owns the date lookups.
"""
from __future__ import annotations

import datetime as dt

NAVY, GREEN, RED, GREY = "1F3A5F", "1A7A1A", "B3261E", "6B7280"
INPUT_FILL, HEAD_FILL, TOTAL_FILL, LEAD_FILL, DAY0_FILL = "FFFBEA", "DCE6F2", "E8EEF6", "E2E2E2", "FFE9A8"
F0, F2, F4 = "#,##0;-#,##0", "#,##0.00;-#,##0.00", "0.0000"
S0, S2 = "[>=0.5]+#,##0;[<=-0.5]-#,##0;0", "[>=0.005]+#,##0.00;[<=-0.005]-#,##0.00;0.00"
DF = "yyyy-mm-dd"
EPOCH = dt.date(1899, 12, 30)
SHEETS = ("Summary", "Receiving date", "Fixed consumption", "Not fixed consumption", "Open contracts")
RECV_FILL = "E3F1E5"
RECV_FMT = '"Received "yyyy-mm-dd'


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _sub(a, b):
    return a - b if None not in (a, b) else None


def _mul(*xs):
    out = 1.0
    for x in xs:
        if x is None:
            return None
        out *= x
    return out


def result_of(diff, band):
    if diff is None:
        return ""
    return "Advantage" if diff >= band else "Missed opportunity" if diff <= -band else "Neutral"


def fixed_blocks(model, base="CORN"):
    """Consumption of fixed contracts, grouped so that every block has one set of terms.

    A contract whose terms change between days (lots) gets one block per set of terms.
    """
    sav = {(r.get("contract_id"), r.get("date")): r for r in model.get("savings") or []}
    cons = {c.get("id"): c for c in model.get("contracts") or []}
    blocks, cur = [], None
    rows = sorted((r for r in model.get("cbot") or [] if r.get("base") == base and r.get("assessable", True)
                   and _n(r.get("fix")) is not None), key=lambda r: (r.get("contract_id") or "", r.get("date") or ""))
    for r in rows:
        s = sav.get((r.get("contract_id"), r.get("date"))) or {}
        terms = {"fix": _n(r.get("fix")), "fix_type": r.get("fix_type") or "", "premium": _n(r.get("premium")),
                 "factor": _n(r.get("factor")), "cif": _n(s.get("cif_used")) if s else _n(r.get("cif")),
                 "fx": _n(r.get("fx")), "discharge": _n(s.get("discharge")), "clearance": _n(s.get("clearance")),
                 "freight": _n(s.get("freight")), "futures": r.get("futures") or "", "unit": r.get("unit") or "",
                 "win_cbot": _n(r.get("win_cbot")), "win_start": r.get("win_start") or "", "win_end": r.get("win_end") or ""}
        key = (r.get("contract_id"), tuple(sorted((k, str(v)) for k, v in terms.items())))
        if cur is None or cur["key"] != key:
            c = cons.get(r.get("contract_id")) or {}
            cur = {"key": key, "contract_id": r.get("contract_id"), "contract": r.get("contract") or r.get("contract_id"),
                   "supplier": r.get("supplier") or c.get("supplier") or "", "commodity": r.get("commodity") or "",
                   "qty_mt": _n(c.get("qty_mt")), "open": bool(c.get("is_open")), "days": [], **terms}
            blocks.append(cur)
        cur["days"].append({"date": _d(r.get("date")), "mt": _n(r.get("mt")), "cbot": _n(r.get("cbot")),
                            "local_excl": _n(s.get("local_excl"))})
    blocks.sort(key=lambda b: b["days"][0]["date"] or dt.date.min, reverse=True)
    return blocks


def unfixed_blocks(model, base="CORN"):
    """Consumption of contracts not fixed yet (indicative against the latest CBOT)."""
    sav = {(r.get("contract_id"), r.get("date")): r for r in model.get("savings") or []}
    cons = {c.get("id"): c for c in model.get("contracts") or []}
    blocks, cur = [], None
    rows = sorted((r for r in model.get("cbot_unfixed") or [] if r.get("base") == base),
                  key=lambda r: (r.get("contract_id") or "", r.get("date") or ""))
    for r in rows:
        s = sav.get((r.get("contract_id"), r.get("date"))) or {}
        terms = {"premium": _n(r.get("premium")), "factor": _n(r.get("factor")), "latest": _n(r.get("latest_cbot")),
                 "latest_date": r.get("latest_cbot_date") or "", "latest_live": bool(r.get("latest_cbot_live")),
                 "fx": _n(r.get("fx")), "discharge": _n(s.get("discharge")), "clearance": _n(s.get("clearance")),
                 "freight": _n(s.get("freight")), "futures": r.get("futures") or ""}
        key = (r.get("contract_id"), tuple(sorted((k, str(v)) for k, v in terms.items())))
        if cur is None or cur["key"] != key:
            c = cons.get(r.get("contract_id")) or {}
            cur = {"key": key, "contract_id": r.get("contract_id"), "contract": r.get("contract") or r.get("contract_id"),
                   "supplier": s.get("supplier") or c.get("supplier") or "", "commodity": s.get("commodity") or c.get("commodity") or "",
                   "qty_mt": _n(c.get("qty_mt")), "open": bool(c.get("is_open")), "days": [], **terms}
            blocks.append(cur)
        cur["days"].append({"date": _d(r.get("date")), "mt": _n(r.get("mt")), "cbot": _n(r.get("cbot")),
                            "cif_used": _n(s.get("cif_used")), "local_excl": _n(s.get("local_excl"))})
    blocks.sort(key=lambda b: b["days"][0]["date"] or dt.date.min, reverse=True)
    return blocks


def merge_window(days, rv, carry=()):
    """A block's consumption days plus every day of its receipt window (receiving date → last pricing
    day before the contract was closed, or today while it is open), oldest first. A day without
    consumption has no MT. ``carry``: per-day terms taken from the nearest consumption day."""
    if not rv:
        return list(days)
    by = {d["date"]: dict(d) for d in days}
    win = rv.get("window") or [{"date": rv.get("date"), "cbot": rv.get("cbot"), "local_excl": rv.get("local_excl")}]
    for w in win:
        dd = _d(w.get("date"))
        if dd and dd not in by:
            by[dd] = {"date": dd, "mt": None, "cbot": _n(w.get("cbot")), "local_excl": _n(w.get("local_excl"))}
    out = [by[k] for k in sorted(by)]
    for k in carry:
        last = next((d.get(k) for d in out if d.get(k) is not None), None)
        for d in out:
            if d.get(k) is None:
                d[k] = last
            else:
                last = d[k]
    return out


def lots_by_day(lots):
    """{date: tonnes priced that day} from a contract's pricing lots ([{date, mt}])."""
    out = {}
    for x in lots or []:
        d, mt = _d(x.get("date")), _n(x.get("mt") if x.get("mt") is not None else x.get("qty_mt"))
        if d and mt:
            out[d] = out.get(d, 0.0) + mt
    return out


MONTHS = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6, "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11,
          "DEC": 12}


def first_notice_day(futures):
    """First notice day of a CBOT grain future such as 'DEC-26': the last business day of the month
    before the contract month (weekends only; exchange holidays are not known here). None if unreadable."""
    try:
        mon, yy = str(futures).upper().replace(" ", "").split("-")[:2]
        month, year = MONTHS[mon[:3]], 2000 + int(yy[-2:])
    except (KeyError, ValueError):
        return None
    d = dt.date(year, month, 1) - dt.timedelta(days=1)
    while d.weekday() >= 5:
        d -= dt.timedelta(days=1)
    return d


def lead_days(trading_days, ref, n=3):
    """The ``n`` trading days before ``ref`` (ISO dates, oldest first)."""
    before = sorted(d for d in set(trading_days or []) if d < ref)
    return before[-n:] if n > 0 else []


def write_overview(model, path, base="CORN", open_trails=None, lead=3, receipts=None, only=None):
    """Write the workbook. ``open_trails``: one dict per open contract with keys contract_id, contract,
    supplier, commodity, mt, pricing, entered, storage_start, day0 (ISO), premium, factor, fixed_cif,
    fixed_fx, fx_basis, discharge, clearance, other_fee and days: [{date, cbot, market_fx, local_excl,
    mode}] oldest first. ``receipts``: {contract_id: {date (ISO, '' = not received yet), vessel, shipment, cbot
    (close on that date), local_excl, contract, supplier, mt}}: each contract is then also compared on its
    receiving date, side by side with its consumption days. ``only``: limit to these contract ids.
    Returns the counts written."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from .xlsx_cache import store_formula_results

    band = _n((model.get("options") or {}).get("neutral_cbot")) or 1.0
    fixed, unfixed = fixed_blocks(model, base), unfixed_blocks(model, base)
    opens = sorted(open_trails or [], key=lambda t: (t.get("day0") or "", t.get("contract") or ""), reverse=True)
    rc = receipts or {}
    if only is not None:
        only = set(only)
        fixed = [b for b in fixed if b["contract_id"] in only]
        unfixed = [b for b in unfixed if b["contract_id"] in only]
        opens = [t for t in opens if t.get("contract_id") in only]
        rc = {k: v for k, v in rc.items() if k in only}
    n_blocks = {}
    for b in fixed + unfixed:
        n_blocks[b["contract_id"]] = n_blocks.get(b["contract_id"], 0) + 1
    vessel_of = lambda cid: (rc.get(cid) or {}).get("vessel") or ""
    recv_of = lambda cid: (rc.get(cid) or {}) if _d((rc.get(cid) or {}).get("date")) else None
    as_of = model.get("as_of") or dt.date.today().isoformat()
    unit = next((b["unit"] for b in fixed if b.get("unit")), "¢/bu")

    wb = Workbook()
    cache = {}
    thin = Side(style="thin", color="C9D3E0")

    def put(ws, r, c, v, fmt=None, bold=False, color=None, fill=None, italic=False, size=None, inp=False, wrap=False,
            align=None):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        if bold or color or italic or size:
            cell.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        elif inp and v is not None:
            cell.fill = PatternFill("solid", fgColor=INPUT_FILL)
        if wrap or align:
            cell.alignment = Alignment(wrap_text=wrap, vertical="center", horizontal=align)
        return cell

    def f(ws, r, c, formula, value, fmt=None, **kw):
        put(ws, r, c, formula, fmt, **kw)
        if isinstance(value, dt.date):
            value = (value - EPOCH).days
        cache.setdefault(ws.title, {})[f"{L(c)}{r}"] = "" if value is None else value

    def heads(ws, r, labels, fill=HEAD_FILL, height=44):
        for i, h in enumerate(labels, start=1):
            c = put(ws, r, i, h, bold=True, fill=fill, wrap=True, align="center")
            c.border = Border(bottom=thin)
        ws.row_dimensions[r].height = height

    def bar(ws, r, text, ncol):
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=ncol)
        c = put(ws, r, 1, text, bold=True, color="FFFFFF", fill=NAVY, size=11)
        c.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20

    def signs(ws, ref):
        ws.conditional_formatting.add(ref, CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        ws.conditional_formatting.add(ref, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))

    def sheet(title, text, sub, widths, span=None):
        ws = wb.active if title == SHEETS[0] else wb.create_sheet(title)
        ws.title = title
        put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=span or len(widths))
        put(ws, 2, 1, sub, italic=True, color=GREY, wrap=True)
        ws.row_dimensions[2].height = 15 * max(1, -(-len(sub) // int(sum(widths) * 1.15)))
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[L(i)].width = w
        return ws

    isn = lambda *cells: "AND(" + ",".join(f"ISNUMBER({c})" for c in cells) + ")"
    BAND = "Summary!$C$6"
    res_f = lambda cell: (f'=IF(ISNUMBER({cell}),IF({cell}>={BAND},"Advantage",IF({cell}<=-{BAND},"Missed opportunity",'
                          f'"Neutral")),"")')
    money = lambda v: "—" if v is None else f"{v:,.0f}"

    ws0 = sheet("Summary", f"{base} — CBOT fixed vs consumption", f"As of {as_of} · open and closed {base} contracts · "
                "consumption days and receiving date side by side · yellow = input, everything else is a formula",
                [26, 16, 19, 10, 12, 12, 10, 10, 11, 11, 16, 12, 10, 11, 11, 16, 10, 11, 12, 10, 10, 11, 10, 12, 11], span=16)
    wr_ = sheet("Receiving date", f"{base} — each contract on its receiving date",
                "Our fixed CBOT against the CBOT on the day the cargo was received (the last close before it when that day "
                "is not a trading day), on the whole contract quantity. Not fixed = against the latest CBOT, indicative. "
                "Positive = our price was cheaper than the market on the receiving date.",
                [24, 15, 20, 12, 8, 12, 10, 8, 10, 10, 11, 9, 11, 13, 11, 15])

    # ── Fixed consumption: pricing days and the market from the receiving date to the window end ──
    W = [20, 9, 11, 11, 10, 12, 12, 12, 13, 13, 17, 11, 12, 12]
    FXD = "[>=0.00005]+0.0000;[<=-0.00005]-0.0000;0.0000"
    fut = next((b["futures"] for b in fixed if b.get("futures")), "")
    fnd = first_notice_day(fut)
    wf = sheet("Fixed consumption", f"{base} — fixed contracts: pricing days and the market from receiving date to today",
               "A contract's terms are shown once, above its days. MT = the lots priced on that date. Days run from the "
               "receiving date (green) to the window end date in C3 (today while the pricing window is open; your pricing "
               "deadline once it passes), trading days only. Difference = CBOT that day − our fixed CBOT: positive means "
               "our fixing was cheaper than the market that day. Market FX = the day's market rate against our contract "
               "FX: positive = our contract FX was cheaper than the market (EGP/MT effect = difference × CIF $/MT). Local "
               "and landed cost exclude inland transport.", W)
    wf.row_dimensions[2].height = 75
    w_end = _d(as_of) or dt.date.today()
    put(wf, 3, 1, "Window end date", bold=True)
    put(wf, 3, 3, w_end, DF, inp=True)
    put(wf, 3, 4, "today while the pricing window is open" + (
        f" · set it to your {fut} pricing deadline once that passes" + (f" (first notice day {fnd.day} {fnd:%b %Y} at the latest)" if fnd else "")
        if fut else " · set it to your pricing deadline once that passes") + ", then add the new days below each contract",
        italic=True, color=GREY)
    WE = "'Fixed consumption'!$C$3"
    refs_fixed = []
    r = 4
    for b in fixed:
        rv = recv_of(b["contract_id"])
        lots = lots_by_day((rc.get(b["contract_id"]) or {}).get("lots"))
        if rv and rv.get("pricing_window"):
            days = [{"date": _d(w["date"]), "mt": None, "cbot": _n(w.get("cbot")), "local_excl": _n(w.get("local_excl")),
                     "fx": _n(w.get("market_fx")), "trading": bool(w.get("trading", True))} for w in rv["pricing_window"]]
        else:
            days = [dict(d, mt=None, fx=None, trading=True) for d in merge_window(b["days"], rv)]
        have = {d["date"] for d in days}
        for ld in sorted(lots):                      # a lot priced on a day that is not listed gets its own row
            if ld not in have:
                days.append({"date": ld, "mt": None, "cbot": None, "local_excl": None, "fx": None, "trading": True})
        days.sort(key=lambda d: d["date"])
        for d in days:
            d["mt"] = lots.get(d["date"])
        mt_tot = sum(d["mt"] or 0 for d in days)
        bar(wf, r, f"{b['contract']}  ·  {b['supplier']}  ·  {b['commodity']}  ·  "
                   f"{money(b['qty_mt'])} MT  ·  {b['futures']}  ·  {b['fix_type'] or 'Fixed'} CBOT fixing"
                   + (f"  ·  vessel {vessel_of(b['contract_id'])}" if vessel_of(b["contract_id"]) else "")
                   + (f"  ·  received {rv['date']} → " + (f"closed {rv['closed']}" if rv.get("closed") else "still open") if rv
                      else ("  ·  still open" if b["open"] else "")), 14)
        heads(wf, r + 1, [f"Fixed CBOT {unit}", f"Premium {unit}", "Factor to $/MT", "CIF $/MT", "FX (contract)",
                          "CIF EGP/MT", "Discharge", "Clearance", "Landed excl. transport", "Inland freight",
                          "Landed incl. transport"])
        t = r + 2
        cif_egp = _mul(b["cif"], b["fx"])
        landed_x = (cif_egp + (b["discharge"] or 0) + (b["clearance"] or 0)) if cif_egp is not None else None
        implied = b["fix_type"] == "Implied" and None not in (b["cif"], b["factor"], b["premium"])
        fix = b["cif"] / b["factor"] - b["premium"] if implied else b["fix"]
        if implied:
            f(wf, t, 1, f"=D{t}/C{t}-B{t}", fix, F2, bold=True)
        else:
            put(wf, t, 1, b["fix"], F2, inp=True, bold=True)
        put(wf, t, 2, b["premium"], F2, inp=True); put(wf, t, 3, b["factor"], F4, inp=True)
        put(wf, t, 4, b["cif"], F2, inp=True); put(wf, t, 5, b["fx"], F4, inp=True)
        f(wf, t, 6, f'=IF({isn(f"D{t}", f"E{t}")},D{t}*E{t},"")', cif_egp, F0)
        put(wf, t, 7, b["discharge"], F0, inp=True); put(wf, t, 8, b["clearance"], F0, inp=True)
        f(wf, t, 9, f'=IF(ISNUMBER(F{t}),F{t}+G{t}+H{t},"")', landed_x, F0, bold=True)
        put(wf, t, 10, b["freight"], F0, inp=True)
        f(wf, t, 11, f'=IF({isn(f"I{t}", f"J{t}")},I{t}+J{t},"")',
          (landed_x + b["freight"]) if None not in (landed_x, b["freight"]) else None, F0)
        heads(wf, r + 3, ["Date", "MT priced", f"CBOT that day {unit}", f"CBOT − fixed {unit}", "USD/MT",
                          "Saving USD", "Saving EGP", "Local excl. transport", "Local − landed EGP/MT",
                          "Local spread EGP", "Result", "Market FX", "Market FX − contract FX", "FX effect EGP/MT"])
        d0 = r + 4
        for i, d in enumerate(days):
            q = d0 + i
            diff = _sub(d["cbot"], fix)
            usd_mt = _mul(diff, b["factor"])
            usd = _mul(usd_mt, d["mt"])
            spread = _sub(d["local_excl"], landed_x)
            dfx = _sub(d["fx"], b["fx"])
            put(wf, q, 1, d["date"], DF, inp=True); put(wf, q, 2, d["mt"], F0); put(wf, q, 3, d["cbot"], F2, inp=True)
            f(wf, q, 4, f'=IF({isn(f"C{q}", f"$A${t}")},C{q}-$A${t},"")', diff, S2)
            f(wf, q, 5, f'=IF(ISNUMBER(D{q}),D{q}*$C${t},"")', usd_mt, S2)
            f(wf, q, 6, f'=IF({isn(f"E{q}", f"B{q}")},E{q}*B{q},"")', usd, S0)
            f(wf, q, 7, f'=IF(ISNUMBER(F{q}),F{q}*$E${t},"")', _mul(usd, b["fx"]), S0)
            put(wf, q, 8, d["local_excl"], F0, inp=True)
            f(wf, q, 9, f'=IF({isn(f"H{q}", f"$I${t}")},H{q}-$I${t},"")', spread, S0)
            f(wf, q, 10, f'=IF({isn(f"I{q}", f"B{q}")},I{q}*B{q},"")', _mul(spread, d["mt"]), S0)
            f(wf, q, 11, res_f(f"D{q}"), result_of(diff, band), align="center")
            put(wf, q, 12, d["fx"], F4, inp=True)
            f(wf, q, 13, f'=IF({isn(f"L{q}", f"$E${t}")},L{q}-$E${t},"")', dfx, FXD)
            f(wf, q, 14, f'=IF({isn(f"M{q}", f"$D${t}")},M{q}*$D${t},"")', _mul(dfx, b["cif"]), S0)
        d1 = d0 + len(days) - 1
        tr = d1 + 1
        wavg = lambda k: (sum((d[k] or 0) * (d["mt"] or 0) for d in days if d[k] is not None)
                          / sum(d["mt"] or 0 for d in days if d[k] is not None)) if any(d[k] is not None and d["mt"] for d in days) else None
        c_avg, l_avg = (wavg("cbot"), wavg("local_excl")) if mt_tot else (None, None)
        diff_t = _sub(c_avg, fix)
        usd_t = sum(_mul(_mul(_sub(d["cbot"], fix), b["factor"]), d["mt"]) or 0 for d in days)
        spread_t = sum(_mul(_sub(d["local_excl"], landed_x), d["mt"]) or 0 for d in days)
        put(wf, tr, 1, "Total / avg — lots priced", bold=True)
        f(wf, tr, 2, f"=SUM(B{d0}:B{d1})", mt_tot, F0, bold=True)
        f(wf, tr, 3, f'=IF(B{tr}<>0,SUMPRODUCT(B{d0}:B{d1},C{d0}:C{d1})/B{tr},"")', c_avg, F2, bold=True)
        f(wf, tr, 4, f'=IF({isn(f"C{tr}", f"$A${t}")},C{tr}-$A${t},"")', diff_t, S2, bold=True)
        f(wf, tr, 5, f'=IF(B{tr}<>0,F{tr}/B{tr},"")', usd_t / mt_tot if mt_tot else None, S2, bold=True)
        f(wf, tr, 6, f"=SUM(F{d0}:F{d1})", usd_t, S0, bold=True)
        f(wf, tr, 7, f"=SUM(G{d0}:G{d1})", _mul(usd_t, b["fx"]), S0, bold=True)
        f(wf, tr, 8, f'=IF(B{tr}<>0,SUMPRODUCT(B{d0}:B{d1},H{d0}:H{d1})/B{tr},"")', l_avg, F0, bold=True)
        f(wf, tr, 9, f'=IF(B{tr}<>0,J{tr}/B{tr},"")', spread_t / mt_tot if mt_tot else None, S0, bold=True)
        f(wf, tr, 10, f"=SUM(J{d0}:J{d1})", spread_t, S0, bold=True)
        f(wf, tr, 11, res_f(f"D{tr}"), result_of(diff_t, band), bold=True, align="center")
        for c in range(1, 15):
            wf.cell(tr, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
            wf.cell(tr, c).font = Font(bold=True)

        # the receiving-date row, and the window: trading days from it up to the window end date
        rr, r_diff, r_usd, r_mt, r_spread, ri = None, None, None, None, None, None
        if rv:
            ri = next((i for i, d in enumerate(days) if d["date"] == _d(rv["date"])), None)
        if ri is not None:
            rr = d0 + ri
            r_mt = mt_tot if n_blocks.get(b["contract_id"], 1) > 1 and mt_tot else (b["qty_mt"] or mt_tot)
            r_diff = _sub(days[ri]["cbot"], fix)
            r_usd = _mul(_mul(r_diff, b["factor"]), r_mt)
            r_spread = _sub(days[ri]["local_excl"], landed_x)
            wf.cell(rr, 1).number_format = RECV_FMT
            wf.cell(rr, 1).font = Font(bold=True)
            for c in range(1, 15):
                wf.cell(rr, c).fill = PatternFill("solid", fgColor=RECV_FILL)
        a_i = next((i for i, d in enumerate(days) if i >= (ri or 0) and d["trading"]), ri or 0)
        a0 = d0 + a_i
        win = [d for d in days[a_i:] if d["date"] <= w_end]
        cbs = [d["cbot"] for d in win if d["cbot"] is not None]
        fxs = [d["fx"] for d in win if d["fx"] is not None]
        RA, RC, RL = f"A{a0}:A{d1}", f"C{a0}:C{d1}", f"L{a0}:L{d1}"
        inwin = f'COUNTIFS({RA},"<="&{WE})'
        wr, lo, hi, pc = tr + 1, tr + 2, tr + 3, tr + 4
        labels = {wr: "Avg CBOT, receiving date → window end", lo: "Lowest in window (CBOT · FX)",
                  hi: "Highest in window (CBOT · FX)", pc: "Trading days cheaper than our fixing"}
        for row_, text in labels.items():
            wf.merge_cells(start_row=row_, start_column=1, end_row=row_, end_column=2)
            put(wf, row_, 1, text, italic=True, color=GREY, wrap=True)
            wf.merge_cells(start_row=row_, start_column=8, end_row=row_, end_column=10)
        wf.row_dimensions[wr].height = 30
        wf.row_dimensions[pc].height = 28.35
        w_avg = sum(cbs) / len(cbs) if cbs else None
        wd = _sub(w_avg, fix)
        f(wf, wr, 3, f'=IFERROR(AVERAGEIFS({RC},{RA},"<="&{WE}),"")', w_avg, F2)
        f(wf, wr, 4, f'=IF({isn(f"C{wr}", f"$A${t}")},C{wr}-$A${t},"")', wd, S2)
        f(wf, wr, 5, f'=IF(ISNUMBER(D{wr}),D{wr}*$C${t},"")', _mul(wd, b["factor"]), S2)
        f(wf, wr, 6, f'=IF(ISNUMBER(E{wr}),E{wr}*B{tr},"")', _mul(_mul(wd, b["factor"]), mt_tot), S0)
        f(wf, wr, 7, f'=IF(ISNUMBER(F{wr}),F{wr}*$E${t},"")', _mul(_mul(_mul(wd, b["factor"]), mt_tot), b["fx"]), S0)
        f(wf, wr, 8, f'=IF({inwin}>0,TEXT(A{a0},"yyyy-mm-dd")&" → "&TEXT(MIN({WE},MAX({RA})),"yyyy-mm-dd")&" ("&{inwin}&" trading days)","")',
          (f"{win[0]['date'].isoformat()} → {min(w_end, days[-1]['date']).isoformat()} ({len(win)} trading days)" if win else None),
          italic=True, color=GREY, align="center")
        f(wf, wr, 11, res_f(f"D{wr}"), result_of(wd, band), align="center")
        fx_avg = sum(fxs) / len(fxs) if fxs else None
        f(wf, wr, 12, f'=IFERROR(AVERAGEIFS({RL},{RA},"<="&{WE}),"")', fx_avg, F4)
        for row_, fn, vals_c, vals_f in ((lo, "MINIFS", min(cbs) if cbs else None, min(fxs) if fxs else None),
                                         (hi, "MAXIFS", max(cbs) if cbs else None, max(fxs) if fxs else None)):
            f(wf, row_, 3, f'=IF({inwin}>0,_xlfn.{fn}({RC},{RA},"<="&{WE}),"")', vals_c if win else None, F2)
            f(wf, row_, 4, f'=IF({isn(f"C{row_}", f"$A${t}")},C{row_}-$A${t},"")', _sub(vals_c, fix) if win else None, S2)
            on = next((d["date"] for d in days[a_i:] if d["cbot"] == vals_c), None) if (win and vals_c is not None) else None
            f(wf, row_, 8, f'=IF(ISNUMBER(C{row_}),"CBOT on "&TEXT(INDEX({RA},MATCH(C{row_},{RC},0)),"yyyy-mm-dd"),"")',
              f"CBOT on {on.isoformat()}" if on else None, italic=True, color=GREY, align="center")
            f(wf, row_, 12, f'=IF({inwin}>0,_xlfn.{fn}({RL},{RA},"<="&{WE}),"")', (vals_f if fxs else 0) if win else None, F4)
        for row_ in (wr, lo, hi):
            lv = {wr: fx_avg, lo: (min(fxs) if fxs else 0) if win else None, hi: (max(fxs) if fxs else 0) if win else None}[row_]
            f(wf, row_, 13, f'=IF({isn(f"L{row_}", f"$E${t}")},L{row_}-$E${t},"")', _sub(lv, b["fx"]), FXD)
            f(wf, row_, 14, f'=IF({isn(f"M{row_}", f"$D${t}")},M{row_}*$D${t},"")', _mul(_sub(lv, b["fx"]), b["cif"]), S0)
        f(wf, pc, 3, f'=IF({inwin}>0,COUNTIFS({RC},"<"&$A${t},{RA},"<="&{WE})/{inwin},"")',
          (sum(1 for d in win if d["cbot"] is not None and fix is not None and d["cbot"] < fix) / len(win)) if win else None, "0%")
        put(wf, pc, 8, "CBOT below our fixing · 0% = we fixed at the low", italic=True, color=GREY, align="center")
        f(wf, pc, 12, f'=IF({inwin}>0,COUNTIFS({RL},"<"&$E${t},{RA},"<="&{WE})/{inwin},"")',
          (sum(1 for d in win if d["fx"] is not None and b["fx"] is not None and d["fx"] < b["fx"]) / len(win)) if win else None, "0%")
        wf.merge_cells(start_row=pc, start_column=13, end_row=pc, end_column=14)
        put(wf, pc, 13, "← days market FX < ours", italic=True, color=GREY, align="center")
        signs(wf, f"D{d0}:G{pc}"); signs(wf, f"I{d0}:J{tr}"); signs(wf, f"M{d0}:N{hi}")
        refs_fixed.append({"b": b, "t": t, "d0": d0, "d1": d1, "tr": tr, "mt": mt_tot, "c_avg": c_avg, "diff": diff_t,
                           "usd": usd_t, "fix": fix, "rr": rr, "rv": rv, "r_diff": r_diff, "r_usd": r_usd, "r_mt": r_mt,
                           "r_spread": r_spread, "r_cbot": days[ri]["cbot"] if ri is not None else None,
                           "first": b["days"][0]["date"] if b["days"] else None,
                           "last": b["days"][-1]["date"] if b["days"] else None,
                           "wr": wr, "lo": lo, "hi": hi, "pc": pc,
                           "w": {"avg": w_avg, "diff": wd, "usd": _mul(_mul(wd, b["factor"]), mt_tot),
                                 "lo": min(cbs) if (cbs and win) else None, "hi": max(cbs) if (cbs and win) else None,
                                 "pct": (sum(1 for d in win if d["cbot"] is not None and fix is not None and d["cbot"] < fix) / len(win)) if win else None,
                                 "fx": fx_avg, "dfx": _sub(fx_avg, b["fx"]), "fx_egp": _mul(_sub(fx_avg, b["fx"]), b["cif"])}})
        r = pc + 2
    if not fixed:
        put(wf, 4, 1, f"No fixed {base} contract has consumption yet.", italic=True, color=GREY)

    # ── Not fixed consumption ──
    wu = sheet("Not fixed consumption", f"{base} — contracts not fixed yet (indicative)",
               "Not realised: the contract has no fixed CBOT yet, so each day is compared with the latest CBOT. "
               "MT = the lots priced on that date. Positive = the market was higher that day than it is now. Local and "
               "landed cost exclude inland transport. Days run from the receiving date (green) to the last pricing day "
               "(today while open).",
               [20, 9, 11, 11, 10, 12, 12, 11, 13, 12, 13])
    refs_unfixed = []
    r = 4
    for b in unfixed:
        rv = recv_of(b["contract_id"])
        days = merge_window(b["days"], rv, carry=("cif_used",))
        lots = lots_by_day((rc.get(b["contract_id"]) or {}).get("lots"))
        for d in days:
            d["mt"] = lots.get(d["date"])
        mt_tot = sum(d["mt"] or 0 for d in days)
        bar(wu, r, f"{b['contract']}  ·  {b['supplier']}  ·  {b['commodity']}  ·  {money(b['qty_mt'])} MT  ·  "
                   f"{b['futures']}  ·  not fixed yet"
                   + (f"  ·  vessel {vessel_of(b['contract_id'])}" if vessel_of(b["contract_id"]) else "")
                   + (f"  ·  received {rv['date']} → " + (f"closed {rv['closed']}" if rv.get("closed") else "still open") if rv
                      else ("  ·  still open" if b["open"] else "")), 11)
        heads(wu, r + 1, [f"Premium {unit}", "Factor to $/MT", f"Latest CBOT {unit}", "FX (contract)", "Discharge",
                          "Clearance", "Inland freight", "Latest CBOT date", "", "", ""])
        t = r + 2
        put(wu, t, 1, b["premium"], F2, inp=True); put(wu, t, 2, b["factor"], F4, inp=True)
        put(wu, t, 3, b["latest"], F2, inp=True, bold=True); put(wu, t, 4, b["fx"], F4, inp=True)
        put(wu, t, 5, b["discharge"], F0, inp=True); put(wu, t, 6, b["clearance"], F0, inp=True)
        put(wu, t, 7, b["freight"], F0, inp=True)
        put(wu, t, 8, (b["latest_date"] + (" · live" if b["latest_live"] else "")).strip(" ·"))
        heads(wu, r + 3, ["Date", "MT priced", f"CBOT that day {unit}", f"CBOT − latest {unit}", "USD/MT",
                          "Indicative USD", "Indicative EGP", "CIF used $/MT", "Landed excl. transport",
                          "Local excl. transport", "Local − landed EGP/MT"])
        d0 = r + 4
        landed = lambda d: (d["cif_used"] * b["fx"] + (b["discharge"] or 0) + (b["clearance"] or 0)
                            if None not in (d["cif_used"], b["fx"]) else None)
        for i, d in enumerate(days):
            q = d0 + i
            diff = _sub(d["cbot"], b["latest"])
            usd_mt = _mul(diff, b["factor"])
            usd = _mul(usd_mt, d["mt"])
            put(wu, q, 1, d["date"], DF, inp=True); put(wu, q, 2, d["mt"], F0); put(wu, q, 3, d["cbot"], F2, inp=True)
            f(wu, q, 4, f'=IF({isn(f"C{q}", f"$C${t}")},C{q}-$C${t},"")', diff, S2)
            f(wu, q, 5, f'=IF(ISNUMBER(D{q}),D{q}*$B${t},"")', usd_mt, S2)
            f(wu, q, 6, f'=IF({isn(f"E{q}", f"B{q}")},E{q}*B{q},"")', usd, S0)
            f(wu, q, 7, f'=IF(ISNUMBER(F{q}),F{q}*$D${t},"")', _mul(usd, b["fx"]), S0)
            put(wu, q, 8, d["cif_used"], F2, inp=True)
            f(wu, q, 9, f'=IF({isn(f"H{q}", f"$D${t}")},H{q}*$D${t}+$E${t}+$F${t},"")', landed(d), F0)
            put(wu, q, 10, d["local_excl"], F0, inp=True)
            f(wu, q, 11, f'=IF({isn(f"J{q}", f"I{q}")},J{q}-I{q},"")', _sub(d["local_excl"], landed(d)), S0)
        d1 = d0 + len(days) - 1
        tr = d1 + 1
        wavg = lambda vals: (sum(v * (d["mt"] or 0) for v, d in zip(vals, days) if v is not None)
                             / sum(d["mt"] or 0 for v, d in zip(vals, days) if v is not None)) \
            if any(v is not None and d["mt"] for v, d in zip(vals, days)) else None
        c_avg = wavg([d["cbot"] for d in days])
        diff_t = _sub(c_avg, b["latest"])
        b_first, b_last = b["days"][0]["date"], b["days"][-1]["date"]
        usd_t = sum(_mul(_mul(_sub(d["cbot"], b["latest"]), b["factor"]), d["mt"]) or 0 for d in days)
        put(wu, tr, 1, "Total / avg — lots priced", bold=True)
        f(wu, tr, 2, f"=SUM(B{d0}:B{d1})", mt_tot, F0, bold=True)
        f(wu, tr, 3, f'=IF(B{tr}<>0,SUMPRODUCT(B{d0}:B{d1},C{d0}:C{d1})/B{tr},"")', c_avg, F2, bold=True)
        f(wu, tr, 4, f'=IF({isn(f"C{tr}", f"$C${t}")},C{tr}-$C${t},"")', diff_t, S2, bold=True)
        f(wu, tr, 5, f'=IF(B{tr}<>0,F{tr}/B{tr},"")', usd_t / mt_tot if mt_tot else None, S2, bold=True)
        f(wu, tr, 6, f"=SUM(F{d0}:F{d1})", usd_t, S0, bold=True)
        f(wu, tr, 7, f"=SUM(G{d0}:G{d1})", _mul(usd_t, b["fx"]), S0, bold=True)
        for col, vals in ((8, [d["cif_used"] for d in days]), (9, [landed(d) for d in days]), (10, [d["local_excl"] for d in days])):
            cl = L(col)
            f(wu, tr, col, f'=IF(B{tr}<>0,SUMPRODUCT(B{d0}:B{d1},{cl}{d0}:{cl}{d1})/B{tr},"")', wavg(vals),
              F2 if col == 8 else F0, bold=True)
        f(wu, tr, 11, f'=IF({isn(f"J{tr}", f"I{tr}")},J{tr}-I{tr},"")',
          _sub(wavg([d["local_excl"] for d in days]), wavg([landed(d) for d in days])), S0, bold=True)
        for c in range(1, 12):
            wu.cell(tr, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        rr, r_diff, r_usd, r_mt, r_spread, ri = None, None, None, None, None, None
        if rv:
            ri = next((i for i, d in enumerate(days) if d["date"] == _d(rv["date"])), None)
        if ri is not None:
            rr = d0 + ri
            r_mt = mt_tot if n_blocks.get(b["contract_id"], 1) > 1 else (b["qty_mt"] or mt_tot)
            r_diff = _sub(days[ri]["cbot"], b["latest"])
            r_usd = _mul(_mul(r_diff, b["factor"]), r_mt)
            r_spread = _sub(days[ri]["local_excl"], landed(days[ri]))
            wu.cell(rr, 1).number_format = RECV_FMT
            wu.cell(rr, 1).font = Font(bold=True)
            for c in range(1, 12):
                wu.cell(rr, c).fill = PatternFill("solid", fgColor=RECV_FILL)
        wr = tr
        if ri is not None and len(days) - ri > 1:
            wr = tr + 1
            cbs = [d["cbot"] for d in days[ri:] if d["cbot"] is not None]
            w_avg = sum(cbs) / len(cbs) if cbs else None
            wd = _sub(w_avg, b["latest"])
            wu.merge_cells(start_row=wr, start_column=1, end_row=wr, end_column=2)
            put(wu, wr, 1, "Avg CBOT, receiving date → last pricing day", italic=True, color=GREY, wrap=True)
            wu.row_dimensions[wr].height = 30
            f(wu, wr, 3, f'=IF(COUNT(C{rr}:C{d1})>0,AVERAGE(C{rr}:C{d1}),"")', w_avg, F2)
            f(wu, wr, 4, f'=IF({isn(f"C{wr}", f"$C${t}")},C{wr}-$C${t},"")', wd, S2)
            f(wu, wr, 5, f'=IF(ISNUMBER(D{wr}),D{wr}*$B${t},"")', _mul(wd, b["factor"]), S2)
            f(wu, wr, 6, f'=IF(ISNUMBER(E{wr}),E{wr}*B{tr},"")', _mul(_mul(wd, b["factor"]), mt_tot), S0)
            f(wu, wr, 7, f'=IF(ISNUMBER(F{wr}),F{wr}*$D${t},"")', _mul(_mul(_mul(wd, b["factor"]), mt_tot), b["fx"]), S0)
            wu.merge_cells(start_row=wr, start_column=8, end_row=wr, end_column=10)
            put(wu, wr, 8, f"{days[ri]['date'].isoformat()} → {days[-1]['date'].isoformat()} ({len(cbs)} days)",
                italic=True, color=GREY, align="center")
        signs(wu, f"D{d0}:G{wr}"); signs(wu, f"K{d0}:K{tr}")
        refs_unfixed.append({"b": b, "t": t, "d0": d0, "d1": d1, "tr": tr, "mt": mt_tot, "c_avg": c_avg, "diff": diff_t,
                             "usd": usd_t, "rr": rr, "rv": rv, "r_diff": r_diff, "r_usd": r_usd, "r_mt": r_mt,
                             "r_spread": r_spread, "r_cbot": days[ri]["cbot"] if ri is not None else None,
                             "first": b_first, "last": b_last})
        r = wr + 2
    if not unfixed:
        put(wu, 4, 1, f"No tonnes were consumed from a {base} contract that is not fixed yet.", italic=True, color=GREY)
    wu.freeze_panes = "A4"

    # ── Open contracts: CBOT and FX from a few trading days before the contract's date ──
    wo = sheet("Open contracts", f"{base} — open contracts: CBOT and FX since {lead} trading days before the contract date",
               f"Day 0 = the receiving date (for a contract not received yet: the day it was entered in the system); the {lead} "
               "grey rows above it are the trading days before. Our price and Sav/MT use today's contract terms on each "
               "day's CBOT and FX, excluding inland transport. Positive Sav/MT = cheaper than local.",
               [12, 8, 10, 10, 11, 10, 10, 11, 10, 13, 13, 12])
    refs_open = []
    r = 4
    for tr_ in opens:
        days = tr_.get("days") or []
        if not days:
            continue
        day0 = _d(tr_.get("day0"))
        i0 = next((i for i, d in enumerate(days) if _d(d["date"]) and day0 and _d(d["date"]) >= day0), 0)
        fx_txt = tr_.get("fx_basis") or ("Form 4" if tr_.get("fixed_fx") is not None else "Market FX of the day")
        bar(wo, r, f"{tr_.get('contract')}  ·  {tr_.get('supplier') or ''}  ·  {money(_n(tr_.get('mt')))} MT  ·  "
                   f"{tr_.get('pricing') or ''}  ·  FX: {fx_txt}"
                   + (f"  ·  vessel {tr_.get('vessel')}" if tr_.get("vessel") else "")
                   + (f"  ·  received {tr_.get('received')}" if tr_.get("received")
                      else f"  ·  not received yet (entered {tr_.get('entered') or '—'})"), 12)
        heads(wo, r + 1, [f"Premium {unit}", "Factor to $/MT", "Fixed CIF $/MT", "Form 4 FX", "Discharge", "Clearance",
                          "Other fees", "MT", "Day 0", f"CBOT on day 0 {unit}", "Market FX on day 0", ""])
        t = r + 2
        d0 = r + 4
        z = d0 + i0
        prem, fac, fcif, ffx = (_n(tr_.get(k)) for k in ("premium", "factor", "fixed_cif", "fixed_fx"))
        disc, clr, oth, mt = (_n(tr_.get(k)) for k in ("discharge", "clearance", "other_fee", "mt"))
        oth = None if oth is not None and abs(oth) < 0.005 else oth
        put(wo, t, 1, prem, F2, inp=True); put(wo, t, 2, fac, F4, inp=True); put(wo, t, 3, fcif, F2, inp=True)
        put(wo, t, 4, ffx, F4, inp=True); put(wo, t, 5, disc, F0, inp=True); put(wo, t, 6, clr, F0, inp=True)
        put(wo, t, 7, oth, F0, inp=True); put(wo, t, 8, mt, F0, inp=True)
        f(wo, t, 9, f"=A{z}", _d(days[i0]["date"]), DF, bold=True)
        f(wo, t, 10, f'=IF(ISNUMBER(C{z}),C{z},"")', _n(days[i0].get("cbot")), F2, bold=True)
        f(wo, t, 11, f'=IF(ISNUMBER(F{z}),F{z},"")', _n(days[i0].get("market_fx")), F4, bold=True)
        heads(wo, r + 3, ["Date", "Days from day 0", f"CBOT {unit}", "Δ CBOT vs prior day", "Δ CBOT since day 0",
                          "Market FX", "Δ FX vs prior day", "Δ FX since day 0", "CIF $/MT", "Our price excl. transport",
                          "Local excl. transport", "Sav/MT excl. transport"])
        vals = []
        for i, d in enumerate(days):
            q, p = d0 + i, d0 + i - 1
            date, cb, mfx, loc = _d(d["date"]), _n(d.get("cbot")), _n(d.get("market_fx")), _n(d.get("local_excl"))
            pv = vals[-1] if vals else {}
            cif = fcif if fcif is not None else (((cb + prem) * fac) if None not in (cb, prem, fac) else None)
            fx = ffx if ffx is not None else mfx
            own = (cif * fx + (disc or 0) + (clr or 0) + (oth or 0)) if None not in (cif, fx) else None
            v = {"cbot": cb, "fx": mfx, "own": own, "loc": loc, "sav": _sub(loc, own)}
            vals.append(v)
            fill = LEAD_FILL if i < i0 else DAY0_FILL if i == i0 else None
            put(wo, q, 1, date, DF, inp=fill is None, fill=fill, bold=i == i0)
            f(wo, q, 2, f"=A{q}-$I${t}", (date - _d(days[i0]["date"])).days if date else None, "0", fill=fill)
            put(wo, q, 3, cb, F2, inp=True); put(wo, q, 6, mfx, F4, inp=True); put(wo, q, 11, loc, F0, inp=True)
            if i:
                f(wo, q, 4, f'=IF({isn(f"C{q}", f"C{p}")},C{q}-C{p},"")', _sub(cb, pv.get("cbot")), S2)
                f(wo, q, 7, f'=IF({isn(f"F{q}", f"F{p}")},F{q}-F{p},"")', _sub(mfx, pv.get("fx")), "[>=0.0005]+0.000;[<=-0.0005]-0.000;0.000")
            f(wo, q, 5, f'=IF({isn(f"C{q}", f"$J${t}")},C{q}-$J${t},"")', _sub(cb, _n(days[i0].get("cbot"))), S2)
            f(wo, q, 8, f'=IF({isn(f"F{q}", f"$K${t}")},F{q}-$K${t},"")', _sub(mfx, _n(days[i0].get("market_fx"))),
              "[>=0.0005]+0.000;[<=-0.0005]-0.000;0.000")
            f(wo, q, 9, f'=IF(ISNUMBER($C${t}),$C${t},IF({isn(f"C{q}", f"$A${t}", f"$B${t}")},(C{q}+$A${t})*$B${t},""))', cif, F2)
            f(wo, q, 10, f'=IF(ISNUMBER(I{q}),IF(ISNUMBER($D${t}),I{q}*$D${t}+$E${t}+$F${t}+$G${t},'
                         f'IF(ISNUMBER(F{q}),I{q}*F{q}+$E${t}+$F${t}+$G${t},"")),"")', own, F0)
            f(wo, q, 12, f'=IF({isn(f"K{q}", f"J{q}")},K{q}-J{q},"")', v["sav"], S0)
            if i < i0:
                for c in range(1, 13):
                    wo.cell(q, c).fill = PatternFill("solid", fgColor=LEAD_FILL)
        d1 = d0 + len(days) - 1
        tr = d1 + 1
        last, zero = vals[-1], vals[i0]
        put(wo, tr, 1, "Since day 0", bold=True)
        f(wo, tr, 5, f'=IF({isn(f"C{d1}", f"$J${t}")},C{d1}-$J${t},"")', _sub(last["cbot"], zero["cbot"]), S2, bold=True)
        f(wo, tr, 8, f'=IF({isn(f"F{d1}", f"$K${t}")},F{d1}-$K${t},"")', _sub(last["fx"], zero["fx"]),
          "[>=0.0005]+0.000;[<=-0.0005]-0.000;0.000", bold=True)
        for col, k in ((10, "own"), (11, "loc"), (12, "sav")):
            cl = L(col)
            f(wo, tr, col, f'=IF({isn(f"{cl}{d1}", f"{cl}{z}")},{cl}{d1}-{cl}{z},"")', _sub(last[k], zero[k]), S0, bold=True)
        for c in range(1, 13):
            wo.cell(tr, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        signs(wo, f"D{d0}:E{tr}"); signs(wo, f"G{d0}:H{tr}"); signs(wo, f"L{d0}:L{tr}")
        refs_open.append({"t": tr_, "top": t, "d0": d0, "d1": d1, "z": z, "tr": tr, "vals": vals, "i0": i0})
        r = tr + 2
    if not refs_open:
        put(wo, 4, 1, f"No open {base} contract.", italic=True, color=GREY)
    wo.freeze_panes = "A4"

    # ── Receiving date: one row per contract ──
    heads(wr_, 4, ["Contract", "Vessel", "Shipment", "Receiving date", "MT", "Pricing", f"Fixed / latest CBOT {unit}",
                   "Factor to $/MT", "FX (contract)", f"CBOT on receiving date {unit}", f"Difference {unit}", "USD/MT",
                   "USD", "EGP", "Local − landed EGP/MT", "Result"])
    lines = []
    for kind, refs, sh in (("Fixed", refs_fixed, "Fixed consumption"), ("Not fixed", refs_unfixed, "Not fixed consumption")):
        for x in refs:
            if x.get("rr"):
                lines.append((x["rv"]["date"], kind, sh, x))
    seen = {x["b"]["contract_id"] for _d0, _k, _s, x in lines}
    for x in refs_open:
        cid = x["t"].get("contract_id")
        if cid not in seen and x["t"].get("received"):
            lines.append((x["t"]["received"], "Not fixed", "Open contracts", x))
            seen.add(cid)
    lines.sort(key=lambda z: z[0], reverse=True)
    row = 5
    for date, kind, sh, x in lines:
        q = f"'{sh}'!"
        if sh == "Open contracts":
            t_, v, top, d1, z = x["t"], x["vals"], x["top"], x["d1"], x["z"]
            cid, fac = t_.get("contract_id"), _n(t_.get("factor"))
            fx = _n(t_.get("fixed_fx")) if _n(t_.get("fixed_fx")) is not None else v[-1]["fx"]
            diff = _sub(v[x["i0"]]["cbot"], v[-1]["cbot"])
            usd = _mul(_mul(diff, fac), _n(t_.get("mt")))
            put(wr_, row, 1, t_.get("contract"), bold=True)
            wr_.cell(row, 1).hyperlink = f"#'{sh}'!A{top - 2}"
            f(wr_, row, 4, f"={q}I{top}", _d(t_["days"][x["i0"]]["date"]), DF)
            f(wr_, row, 5, f"={q}H{top}", _n(t_.get("mt")), F0)
            f(wr_, row, 7, f'=IF(ISNUMBER({q}C{d1}),{q}C{d1},"")', v[-1]["cbot"], F2)
            f(wr_, row, 8, f"={q}B{top}", fac, F4)
            f(wr_, row, 9, f'=IF(ISNUMBER({q}D{top}),{q}D{top},{q}F{d1})', fx, F4)
            f(wr_, row, 10, f"={q}J{top}", v[x["i0"]]["cbot"], F2)
            f(wr_, row, 15, f'=IF(ISNUMBER({q}L{z}),{q}L{z},"")', v[x["i0"]]["sav"], S0)
        else:
            b, t, rr = x["b"], x["t"], x["rr"]
            cid, fac, fx = b["contract_id"], b["factor"], b["fx"]
            diff, usd = x["r_diff"], x["r_usd"]
            put(wr_, row, 1, b["contract"], bold=True)
            wr_.cell(row, 1).hyperlink = f"#'{sh}'!A{t - 2}"
            f(wr_, row, 4, f"={q}A{rr}", _d(x["rv"]["date"]), DF)
            put(wr_, row, 5, x["r_mt"], F0, inp=True)
            fixc, facc, fxc = ("A", "C", "E") if kind == "Fixed" else ("C", "B", "D")
            f(wr_, row, 7, f"={q}{fixc}{t}", x.get("fix") if kind == "Fixed" else b["latest"], F2)
            f(wr_, row, 8, f"={q}{facc}{t}", fac, F4)
            f(wr_, row, 9, f"={q}{fxc}{t}", fx, F4)
            f(wr_, row, 10, f"={q}C{rr}", x["r_cbot"], F2)
            f(wr_, row, 15, f"={q}{'I' if kind == 'Fixed' else 'K'}{rr}", x["r_spread"], S0)
        wr_.cell(row, 1).font = Font(bold=True, color="1F5FBF", underline="single")
        put(wr_, row, 2, vessel_of(cid)); put(wr_, row, 3, (rc.get(cid) or {}).get("shipment") or "")
        put(wr_, row, 6, kind, align="center")
        f(wr_, row, 11, f'=IF({isn(f"J{row}", f"G{row}")},J{row}-G{row},"")', diff, S2, bold=True)
        f(wr_, row, 12, f'=IF({isn(f"K{row}", f"H{row}")},K{row}*H{row},"")', _mul(diff, fac), S2)
        f(wr_, row, 13, f'=IF({isn(f"L{row}", f"E{row}")},L{row}*E{row},"")', usd, S0, bold=True)
        f(wr_, row, 14, f'=IF({isn(f"M{row}", f"I{row}")},M{row}*I{row},"")', _mul(usd, fx), S0)
        if kind == "Fixed":
            f(wr_, row, 16, res_f(f"K{row}"), result_of(diff, band), align="center")
        else:
            put(wr_, row, 16, "Indicative", align="center")
        x["_rrow"] = row
        x["_recv_usd"], x["_recv_kind"], x["_recv_mt"], x["_recv_egp"] = usd, kind, (x["r_mt"] if sh != "Open contracts" else _n(x["t"].get("mt"))), _mul(usd, fx)
        row += 1
    last = row - 1
    n_recv = len(lines)
    if lines:
        signs(wr_, f"K5:N{last}"); signs(wr_, f"O5:O{last}")
        row += 1
        for kind, label in (("Fixed", "Total — fixed"), ("Not fixed", "Total — not fixed (indicative)")):
            sel = [x for _a, k, _s, x in lines if k == kind]
            if not sel:
                continue
            put(wr_, row, 1, label, bold=True)
            f(wr_, row, 5, f'=SUMIF($F$5:$F${last},"{kind}",E5:E{last})', sum(x["_recv_mt"] or 0 for x in sel), F0, bold=True)
            f(wr_, row, 12, f'=IF(E{row}<>0,M{row}/E{row},"")',
              (sum(x["_recv_usd"] or 0 for x in sel) / sum(x["_recv_mt"] or 0 for x in sel)) if sum(x["_recv_mt"] or 0 for x in sel) else None, S2, bold=True)
            f(wr_, row, 13, f'=SUMIF($F$5:$F${last},"{kind}",M5:M{last})', sum(x["_recv_usd"] or 0 for x in sel), S0, bold=True)
            f(wr_, row, 14, f'=SUMIF($F$5:$F${last},"{kind}",N5:N{last})', sum(x["_recv_egp"] or 0 for x in sel), S0, bold=True)
            for c in range(1, 17):
                wr_.cell(row, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
            signs(wr_, f"L{row}:N{row}")
            row += 1
    pending = [(cid, v) for cid, v in rc.items() if not _d(v.get("date"))]
    if pending:
        row += 1
        put(wr_, row, 1, "Not received yet", bold=True, color=GREY)
        row += 1
        for cid, v in sorted(pending, key=lambda z: z[1].get("contract") or z[0]):
            put(wr_, row, 1, v.get("contract") or cid, bold=True); put(wr_, row, 2, v.get("vessel") or "")
            put(wr_, row, 3, v.get("shipment") or ""); put(wr_, row, 4, "Not received", italic=True, color=GREY)
            put(wr_, row, 5, _n(v.get("mt")), F0)
            row += 1
    if not lines and not pending:
        put(wr_, 5, 1, "No receiving dates were given.", italic=True, color=GREY)
    wr_.freeze_panes = "B5"

    # ── Summary: one row per contract, read from the blocks ──
    notes = [
        "Fixed = our CBOT is fixed: the difference is the CBOT on each consumption day minus our fixed CBOT. "
        "Positive (green) = our fixing was cheaper than the market on the days the corn was used: an advantage. "
        "Negative (red) = the market was cheaper: a missed opportunity.",
        "Not fixed = consumed before fixing: compared with the latest CBOT, indicative only. "
        "Open = CBOT and FX since the contract date are on the Open contracts sheet.",
    ]
    for i, tx in enumerate(notes):
        ws0.merge_cells(start_row=3 + i, start_column=1, end_row=3 + i, end_column=16)
        put(ws0, 3 + i, 1, tx, italic=True, color=GREY, wrap=True)
        ws0.row_dimensions[3 + i].height = 30
    put(ws0, 6, 1, f"Neutral band (± {unit})", bold=True)
    put(ws0, 6, 3, band, F2, inp=True)
    put(ws0, 6, 4, "a difference smaller than this either way is Neutral", italic=True, color=GREY)
    hr = 9
    for c0, c1, txt, fill in ((8, 11, "ON THE PRICING DAYS (lots priced)", HEAD_FILL), (12, 16, "ON THE RECEIVING DATE", RECV_FILL),
                              (17, 25, "PRICING WINDOW: RECEIVING DATE → WINDOW END (trading days)", HEAD_FILL)):
        ws0.merge_cells(start_row=hr - 1, start_column=c0, end_row=hr - 1, end_column=c1)
        put(ws0, hr - 1, c0, txt, bold=True, fill=fill, align="center")
    heads(ws0, hr, ["Contract", "Vessel", "Status", "MT priced", "First consumption day (estimate)",
                    "Last consumption day (estimate)", f"Fixed / latest CBOT {unit}", f"Avg CBOT {unit}",
                    f"Difference {unit}", "USD", "Result", "Receiving date", f"CBOT that day {unit}", f"Difference {unit}",
                    "USD", "Result", f"Avg CBOT {unit}", f"Difference {unit}", "USD on lots priced", f"Lowest CBOT {unit}",
                    f"Highest CBOT {unit}", "Days cheaper than our fixing", "Avg market FX", "Market FX − contract FX",
                    "FX effect EGP/MT"])
    for c in range(12, 17):
        ws0.cell(hr, c).fill = PatternFill("solid", fgColor=RECV_FILL)
    row = hr + 1
    spans = {}
    for kind, refs, sh, fixcell in (("Fixed", refs_fixed, "Fixed consumption", "A"),
                                    ("Not fixed — indicative", refs_unfixed, "Not fixed consumption", "C")):
        start = row
        for x in refs:
            b, q = x["b"], f"'{sh}'!"
            put(ws0, row, 1, b["contract"], bold=True); put(ws0, row, 2, vessel_of(b["contract_id"]) or b["supplier"])
            put(ws0, row, 3, kind)
            ws0.cell(row, 1).hyperlink = f"#'{sh}'!A{x['t'] - 2}"
            ws0.cell(row, 1).font = Font(bold=True, color="1F5FBF", underline="single")
            f(ws0, row, 4, f"={q}B{x['tr']}", x["mt"], F0)
            put(ws0, row, 5, x["first"], DF); put(ws0, row, 6, x["last"], DF)
            f(ws0, row, 7, f"={q}{fixcell}{x['t']}", x.get("fix") if kind == "Fixed" else b["latest"], F2)
            f(ws0, row, 8, f"={q}C{x['tr']}", x["c_avg"], F2)
            f(ws0, row, 9, f"={q}D{x['tr']}", x["diff"], S2)
            f(ws0, row, 10, f"={q}F{x['tr']}", x["usd"], S0)
            if kind == "Fixed":
                f(ws0, row, 11, f"={q}K{x['tr']}", result_of(x["diff"], band), align="center")
            else:
                put(ws0, row, 11, "Indicative", align="center")
            if x.get("_rrow"):
                rq, rw = "'Receiving date'!", x["_rrow"]
                f(ws0, row, 12, f"={rq}D{rw}", _d(x["rv"]["date"]), DF)
                f(ws0, row, 13, f"={rq}J{rw}", x["r_cbot"], F2)
                f(ws0, row, 14, f"={rq}K{rw}", x["r_diff"], S2)
                f(ws0, row, 15, f"={rq}M{rw}", x["r_usd"], S0)
                if kind == "Fixed":
                    f(ws0, row, 16, f"={rq}P{rw}", result_of(x["r_diff"], band), align="center")
                else:
                    put(ws0, row, 16, "Indicative", align="center")
            elif b["contract_id"] in rc:
                put(ws0, row, 12, "Not received", italic=True, color=GREY)
            if kind == "Fixed" and x.get("wr"):
                w = x["w"]
                for col, cell, val, fmt in ((17, f"C{x['wr']}", w["avg"], F2), (18, f"D{x['wr']}", w["diff"], S2),
                                            (19, f"F{x['wr']}", w["usd"], S0), (20, f"C{x['lo']}", w["lo"], F2),
                                            (21, f"C{x['hi']}", w["hi"], F2), (22, f"C{x['pc']}", w["pct"], "0%"),
                                            (23, f"L{x['wr']}", w["fx"], F4),
                                            (24, f"M{x['wr']}", w["dfx"], "[>=0.00005]+0.0000;[<=-0.00005]-0.0000;0.0000"),
                                            (25, f"N{x['wr']}", w["fx_egp"], S0)):
                    f(ws0, row, col, f"={q}{cell}", val, fmt)
            row += 1
        if refs:
            spans[kind] = (start, row - 1)
            put(ws0, row, 1, f"Total — {kind.lower()}", bold=True)
            f(ws0, row, 4, f"=SUM(D{start}:D{row - 1})", sum(x["mt"] for x in refs), F0, bold=True)
            f(ws0, row, 10, f"=SUM(J{start}:J{row - 1})", sum(x["usd"] for x in refs), S0, bold=True)
            f(ws0, row, 15, f"=SUM(O{start}:O{row - 1})", sum(x.get("r_usd") or 0 for x in refs), S0, bold=True)
            if kind == "Fixed":
                f(ws0, row, 19, f"=SUM(S{start}:S{row - 1})", sum((x.get("w") or {}).get("usd") or 0 for x in refs), S0, bold=True)
            for c in range(1, 26 if kind == "Fixed" else 17):
                ws0.cell(row, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
                ws0.cell(row, c).font = Font(bold=True)
            row += 2
    if refs_open:
        heads(ws0, row, ["Open contract", "Vessel", "Pricing", "MT", "Day 0 (receiving date)", "Last day",
                         f"CBOT on day 0 {unit}", f"CBOT now {unit}", f"Δ CBOT since day 0 {unit}",
                         "Δ market FX since day 0", "Our price now excl. tr.", "Local now excl. tr.", "Sav/MT now excl. tr."])
        row += 1
        o0 = row
        for x in refs_open:
            tr_, q, v = x["t"], "'Open contracts'!", x["vals"]
            put(ws0, row, 1, tr_.get("contract"), bold=True)
            put(ws0, row, 2, tr_.get("vessel") or tr_.get("supplier") or "")
            put(ws0, row, 3, (tr_.get("pricing") or "") + ("" if tr_.get("received") or not rc else " · not received"))
            ws0.cell(row, 1).hyperlink = f"#'Open contracts'!A{x['top'] - 2}"
            ws0.cell(row, 1).font = Font(bold=True, color="1F5FBF", underline="single")
            f(ws0, row, 4, f"={q}H{x['top']}", _n(tr_.get("mt")), F0)
            f(ws0, row, 5, f"={q}I{x['top']}", _d(tr_["days"][x["i0"]]["date"]), DF)
            f(ws0, row, 6, f"={q}A{x['d1']}", _d(tr_["days"][-1]["date"]), DF)
            f(ws0, row, 7, f"={q}J{x['top']}", v[x["i0"]]["cbot"], F2)
            f(ws0, row, 8, f'=IF(ISNUMBER({q}C{x["d1"]}),{q}C{x["d1"]},"")', v[-1]["cbot"], F2)
            f(ws0, row, 9, f"={q}E{x['tr']}", _sub(v[-1]["cbot"], v[x["i0"]]["cbot"]), S2)
            f(ws0, row, 10, f"={q}H{x['tr']}", _sub(v[-1]["fx"], v[x["i0"]]["fx"]), "[>=0.0005]+0.000;[<=-0.0005]-0.000;0.000")
            for col, src, k in ((11, "J", "own"), (12, "K", "loc")):
                f(ws0, row, col, f'=IF(ISNUMBER({q}{src}{x["d1"]}),{q}{src}{x["d1"]},"")', v[-1][k], F0)
            f(ws0, row, 13, f'=IF(ISNUMBER({q}L{x["d1"]}),{q}L{x["d1"]},"")', v[-1]["sav"], S0)
            row += 1
        signs(ws0, f"I{o0}:J{row - 1}"); signs(ws0, f"M{o0}:M{row - 1}")
    for kind_, (a, b_) in spans.items():
        signs(ws0, f"I{a}:J{b_ + 1}"); signs(ws0, f"N{a}:O{b_ + 1}")
        if kind_ == "Fixed":
            signs(ws0, f"R{a}:S{b_ + 1}"); signs(ws0, f"X{a}:Y{b_}")
    ws0.freeze_panes = f"B{hr + 1}"

    for s in wb.worksheets:
        s.page_setup.orientation = "landscape"
        s.page_setup.paperSize = s.PAPERSIZE_A4
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth, s.page_setup.fitToHeight = 1, 0
        s.oddFooter.center.text = "&A · page &P of &N"
        s.sheet_view.showGridLines = False
    ws0.sheet_state = "hidden"            # kept for the links and totals; the Receiving date sheet opens first
    wb.active = wb.index(wr_)
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, cache)
    return {"base": base, "fixed_contracts": len(refs_fixed), "fixed_days": sum(len(x["b"]["days"]) for x in refs_fixed),
            "unfixed_contracts": len(refs_unfixed), "unfixed_days": sum(len(x["b"]["days"]) for x in refs_unfixed),
            "open_contracts": len(refs_open), "received_rows": n_recv, "formulas": sum(len(v) for v in cache.values()),
            "fixed_usd": sum(x["usd"] for x in refs_fixed), "fixed_mt": sum(x["mt"] for x in refs_fixed)}
