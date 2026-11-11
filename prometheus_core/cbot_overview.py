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
SHEETS = ("Summary", "Fixed consumption", "Not fixed consumption", "Open contracts")


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


def lead_days(trading_days, ref, n=3):
    """The ``n`` trading days before ``ref`` (ISO dates, oldest first)."""
    before = sorted(d for d in set(trading_days or []) if d < ref)
    return before[-n:] if n > 0 else []


def write_overview(model, path, base="CORN", open_trails=None, lead=3):
    """Write the workbook. ``open_trails``: one dict per open contract with keys contract_id, contract,
    supplier, commodity, mt, pricing, entered, storage_start, day0 (ISO), premium, factor, fixed_cif,
    fixed_fx, fx_basis, discharge, clearance, other_fee and days: [{date, cbot, market_fx, local_excl,
    mode}] oldest first. Returns the counts written."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from .xlsx_cache import store_formula_results

    band = _n((model.get("options") or {}).get("neutral_cbot")) or 1.0
    fixed, unfixed = fixed_blocks(model, base), unfixed_blocks(model, base)
    opens = sorted(open_trails or [], key=lambda t: (t.get("day0") or "", t.get("contract") or ""), reverse=True)
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

    def sheet(title, text, sub, widths):
        ws = wb.active if title == SHEETS[0] else wb.create_sheet(title)
        ws.title = title
        put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        put(ws, 2, 1, sub, italic=True, color=GREY)
        for i, w in enumerate(widths, start=1):
            ws.column_dimensions[L(i)].width = w
        return ws

    isn = lambda *cells: "AND(" + ",".join(f"ISNUMBER({c})" for c in cells) + ")"
    BAND = "Summary!$C$6"
    res_f = lambda cell: (f'=IF(ISNUMBER({cell}),IF({cell}>={BAND},"Advantage",IF({cell}<=-{BAND},"Missed opportunity",'
                          f'"Neutral")),"")')
    money = lambda v: "—" if v is None else f"{v:,.0f}"

    ws0 = sheet("Summary", f"{base} — CBOT fixed vs consumption", f"As of {as_of} · open and closed {base} contracts · "
                "yellow = input, everything else is a formula", [27, 15, 20, 10, 11, 11, 11, 12, 11, 10, 12, 14, 19])

    # ── Fixed consumption ──
    W = [13, 9, 11, 11, 10, 12, 12, 12, 13, 13, 17]
    wf = sheet("Fixed consumption", f"{base} — consumption of fixed contracts, day by day",
               "A contract's terms are shown once, above its days. Difference = CBOT on the consumption day − our fixed "
               "CBOT: positive means our fixing was cheaper than the market that day. Local and landed cost exclude "
               "inland transport.", W)
    refs_fixed = []
    r = 4
    for b in fixed:
        days = b["days"]
        mt_tot = sum(d["mt"] or 0 for d in days)
        bar(wf, r, f"{b['contract']}  ·  {b['supplier']}  ·  {b['commodity']}  ·  "
                   f"{money(b['qty_mt'])} MT  ·  {b['futures']}  ·  {b['fix_type'] or 'Fixed'} CBOT fixing"
                   + ("  ·  still open" if b["open"] else ""), 11)
        heads(wf, r + 1, [f"Fixed CBOT {unit}", f"Premium {unit}", "Factor to $/MT", "CIF $/MT", "FX (contract)",
                          "CIF EGP/MT", "Discharge", "Clearance", "Landed excl. transport", "Inland freight",
                          "Landed incl. transport"])
        t = r + 2
        cif_egp = _mul(b["cif"], b["fx"])
        landed_x = (cif_egp + (b["discharge"] or 0) + (b["clearance"] or 0)) if cif_egp is not None else None
        if b["fix_type"] == "Implied" and None not in (b["cif"], b["factor"], b["premium"]):
            f(wf, t, 1, f"=D{t}/C{t}-B{t}", b["cif"] / b["factor"] - b["premium"], F2, bold=True)
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
        fix = b["cif"] / b["factor"] - b["premium"] if b["fix_type"] == "Implied" and None not in (b["cif"], b["factor"], b["premium"]) else b["fix"]
        heads(wf, r + 3, ["Consumption date", "MT", f"CBOT that day {unit}", f"CBOT − fixed {unit}", "USD/MT",
                          "Saving USD", "Saving EGP", "Local excl. transport", "Local − landed EGP/MT",
                          "Local spread EGP", "Result"])
        d0 = r + 4
        for i, d in enumerate(days):
            q = d0 + i
            diff = _sub(d["cbot"], fix)
            usd_mt = _mul(diff, b["factor"])
            usd = _mul(usd_mt, d["mt"])
            spread = _sub(d["local_excl"], landed_x)
            put(wf, q, 1, d["date"], DF, inp=True); put(wf, q, 2, d["mt"], F0, inp=True); put(wf, q, 3, d["cbot"], F2, inp=True)
            f(wf, q, 4, f'=IF({isn(f"C{q}", f"$A${t}")},C{q}-$A${t},"")', diff, S2)
            f(wf, q, 5, f'=IF(ISNUMBER(D{q}),D{q}*$C${t},"")', usd_mt, S2)
            f(wf, q, 6, f'=IF(ISNUMBER(E{q}),E{q}*B{q},"")', usd, S0)
            f(wf, q, 7, f'=IF(ISNUMBER(F{q}),F{q}*$E${t},"")', _mul(usd, b["fx"]), S0)
            put(wf, q, 8, d["local_excl"], F0, inp=True)
            f(wf, q, 9, f'=IF({isn(f"H{q}", f"$I${t}")},H{q}-$I${t},"")', spread, S0)
            f(wf, q, 10, f'=IF(ISNUMBER(I{q}),I{q}*B{q},"")', _mul(spread, d["mt"]), S0)
            f(wf, q, 11, res_f(f"D{q}"), result_of(diff, band), align="center")
        d1 = d0 + len(days) - 1
        tr = d1 + 1
        wavg = lambda k: (sum((d[k] or 0) * (d["mt"] or 0) for d in days if d[k] is not None)
                          / sum(d["mt"] or 0 for d in days if d[k] is not None)) if any(d[k] is not None and d["mt"] for d in days) else None
        c_avg, l_avg = wavg("cbot"), wavg("local_excl")
        diff_t = _sub(c_avg, fix)
        usd_t = sum(_mul(_mul(_sub(d["cbot"], fix), b["factor"]), d["mt"]) or 0 for d in days)
        spread_t = sum(_mul(_sub(d["local_excl"], landed_x), d["mt"]) or 0 for d in days)
        put(wf, tr, 1, "Total / avg", bold=True)
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
        for c in range(1, 12):
            wf.cell(tr, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        wr = tr + 1
        if b["win_cbot"] is not None:
            wd = _sub(b["win_cbot"], fix)
            put(wf, wr, 1, "② Avg CBOT, storage date → last consumption", italic=True, color=GREY)
            put(wf, wr, 3, None)
            ws_ = wf
            ws_.merge_cells(start_row=wr, start_column=1, end_row=wr, end_column=2)
            ws_.cell(wr, 1).alignment = Alignment(wrap_text=True, vertical="center")
            ws_.row_dimensions[wr].height = 30
            put(wf, wr, 3, b["win_cbot"], F2, inp=True)
            f(wf, wr, 4, f'=IF({isn(f"C{wr}", f"$A${t}")},C{wr}-$A${t},"")', wd, S2)
            f(wf, wr, 5, f'=IF(ISNUMBER(D{wr}),D{wr}*$C${t},"")', _mul(wd, b["factor"]), S2)
            f(wf, wr, 6, f'=IF(ISNUMBER(E{wr}),E{wr}*B{tr},"")', _mul(_mul(wd, b["factor"]), mt_tot), S0)
            f(wf, wr, 7, f'=IF(ISNUMBER(F{wr}),F{wr}*$E${t},"")', _mul(_mul(_mul(wd, b["factor"]), mt_tot), b["fx"]), S0)
            f(wf, wr, 11, res_f(f"D{wr}"), result_of(wd, band), align="center")
            wf.merge_cells(start_row=wr, start_column=8, end_row=wr, end_column=10)
            put(wf, wr, 8, f"{b['win_start']} → {b['win_end']}", italic=True, color=GREY, align="center")
        signs(wf, f"D{d0}:G{wr}"); signs(wf, f"I{d0}:J{tr}")
        refs_fixed.append({"b": b, "t": t, "d0": d0, "d1": d1, "tr": tr, "mt": mt_tot, "c_avg": c_avg, "diff": diff_t,
                           "usd": usd_t, "fix": fix})
        r = wr + 2
    if not fixed:
        put(wf, 4, 1, f"No fixed {base} contract has consumption yet.", italic=True, color=GREY)
    wf.freeze_panes = "A4"

    # ── Not fixed consumption ──
    wu = sheet("Not fixed consumption", f"{base} — consumption of contracts not fixed yet (indicative)",
               "Not realised: the contract has no fixed CBOT yet, so each consumption day is compared with the latest "
               "CBOT. Positive = the market was higher on the consumption day than it is now. Local and landed cost "
               "exclude inland transport.", [13, 9, 11, 11, 10, 12, 12, 11, 13, 12, 13])
    refs_unfixed = []
    r = 4
    for b in unfixed:
        days = b["days"]
        mt_tot = sum(d["mt"] or 0 for d in days)
        bar(wu, r, f"{b['contract']}  ·  {b['supplier']}  ·  {b['commodity']}  ·  {money(b['qty_mt'])} MT  ·  "
                   f"{b['futures']}  ·  not fixed yet" + ("  ·  still open" if b["open"] else ""), 11)
        heads(wu, r + 1, [f"Premium {unit}", "Factor to $/MT", f"Latest CBOT {unit}", "FX (contract)", "Discharge",
                          "Clearance", "Inland freight", "Latest CBOT date", "", "", ""])
        t = r + 2
        put(wu, t, 1, b["premium"], F2, inp=True); put(wu, t, 2, b["factor"], F4, inp=True)
        put(wu, t, 3, b["latest"], F2, inp=True, bold=True); put(wu, t, 4, b["fx"], F4, inp=True)
        put(wu, t, 5, b["discharge"], F0, inp=True); put(wu, t, 6, b["clearance"], F0, inp=True)
        put(wu, t, 7, b["freight"], F0, inp=True)
        put(wu, t, 8, (b["latest_date"] + (" · live" if b["latest_live"] else "")).strip(" ·"))
        heads(wu, r + 3, ["Consumption date", "MT", f"CBOT that day {unit}", f"CBOT − latest {unit}", "USD/MT",
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
            put(wu, q, 1, d["date"], DF, inp=True); put(wu, q, 2, d["mt"], F0, inp=True); put(wu, q, 3, d["cbot"], F2, inp=True)
            f(wu, q, 4, f'=IF({isn(f"C{q}", f"$C${t}")},C{q}-$C${t},"")', diff, S2)
            f(wu, q, 5, f'=IF(ISNUMBER(D{q}),D{q}*$B${t},"")', usd_mt, S2)
            f(wu, q, 6, f'=IF(ISNUMBER(E{q}),E{q}*B{q},"")', usd, S0)
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
        usd_t = sum(_mul(_mul(_sub(d["cbot"], b["latest"]), b["factor"]), d["mt"]) or 0 for d in days)
        put(wu, tr, 1, "Total / avg", bold=True)
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
        signs(wu, f"D{d0}:G{tr}"); signs(wu, f"K{d0}:K{tr}")
        refs_unfixed.append({"b": b, "t": t, "d0": d0, "d1": d1, "tr": tr, "mt": mt_tot, "c_avg": c_avg, "diff": diff_t,
                             "usd": usd_t})
        r = tr + 2
    if not unfixed:
        put(wu, 4, 1, f"No tonnes were consumed from a {base} contract that is not fixed yet.", italic=True, color=GREY)
    wu.freeze_panes = "A4"

    # ── Open contracts: CBOT and FX from a few trading days before the contract's date ──
    wo = sheet("Open contracts", f"{base} — open contracts: CBOT and FX since {lead} trading days before the contract date",
               f"Day 0 = the earlier of the storage start and the day the contract was entered in the system; the {lead} "
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
                   f"{tr_.get('pricing') or ''}  ·  FX: {fx_txt}  ·  entered {tr_.get('entered') or '—'}  ·  stored "
                   f"{tr_.get('storage_start') or '—'}", 12)
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

    # ── Summary: one row per contract, read from the blocks ──
    notes = [
        "Fixed = our CBOT is fixed: the difference is the CBOT on each consumption day minus our fixed CBOT. "
        "Positive (green) = our fixing was cheaper than the market on the days the corn was used: an advantage. "
        "Negative (red) = the market was cheaper: a missed opportunity.",
        "Not fixed = consumed before fixing: compared with the latest CBOT, indicative only. "
        "Open = CBOT and FX since the contract date are on the Open contracts sheet.",
    ]
    for i, tx in enumerate(notes):
        ws0.merge_cells(start_row=3 + i, start_column=1, end_row=3 + i, end_column=13)
        put(ws0, 3 + i, 1, tx, italic=True, color=GREY, wrap=True)
        ws0.row_dimensions[3 + i].height = 30
    put(ws0, 6, 1, f"Neutral band (± {unit})", bold=True)
    put(ws0, 6, 3, band, F2, inp=True)
    put(ws0, 6, 4, "a difference smaller than this either way is Neutral", italic=True, color=GREY)
    hr = 8
    heads(ws0, hr, ["Contract", "Supplier", "Status", "Consumed MT", "First day", "Last day", f"Fixed / latest CBOT {unit}",
                    f"Avg CBOT on consumption days {unit}", f"Difference {unit}", "USD/MT", "USD", "EGP", "Result"])
    row = hr + 1
    spans = {}
    for kind, refs, sh, fixcell, fxcell in (("Fixed", refs_fixed, "Fixed consumption", "A", "E"),
                                            ("Not fixed — indicative", refs_unfixed, "Not fixed consumption", "C", "D")):
        start = row
        for x in refs:
            b, q = x["b"], f"'{sh}'!"
            put(ws0, row, 1, b["contract"], bold=True); put(ws0, row, 2, b["supplier"]); put(ws0, row, 3, kind)
            ws0.cell(row, 1).hyperlink = f"#'{sh}'!A{x['t'] - 2}"
            ws0.cell(row, 1).font = Font(bold=True, color="1F5FBF", underline="single")
            f(ws0, row, 4, f"={q}B{x['tr']}", x["mt"], F0)
            f(ws0, row, 5, f"={q}A{x['d0']}", b["days"][0]["date"], DF)
            f(ws0, row, 6, f"={q}A{x['d1']}", b["days"][-1]["date"], DF)
            f(ws0, row, 7, f"={q}{fixcell}{x['t']}", x.get("fix") if kind == "Fixed" else b["latest"], F2)
            f(ws0, row, 8, f"={q}C{x['tr']}", x["c_avg"], F2)
            f(ws0, row, 9, f"={q}D{x['tr']}", x["diff"], S2)
            f(ws0, row, 10, f"={q}E{x['tr']}", x["usd"] / x["mt"] if x["mt"] else None, S2)
            f(ws0, row, 11, f"={q}F{x['tr']}", x["usd"], S0)
            f(ws0, row, 12, f"={q}G{x['tr']}", _mul(x["usd"], b["fx"]), S0)
            if kind == "Fixed":
                f(ws0, row, 13, f"={q}K{x['tr']}", result_of(x["diff"], band), align="center")
            else:
                put(ws0, row, 13, "Indicative", align="center")
            row += 1
        if refs:
            spans[kind] = (start, row - 1)
            put(ws0, row, 1, f"Total — {kind.lower()}", bold=True)
            f(ws0, row, 4, f"=SUM(D{start}:D{row - 1})", sum(x["mt"] for x in refs), F0, bold=True)
            f(ws0, row, 10, f'=IF(D{row}<>0,K{row}/D{row},"")',
              sum(x["usd"] for x in refs) / sum(x["mt"] for x in refs) if sum(x["mt"] for x in refs) else None, S2, bold=True)
            f(ws0, row, 11, f"=SUM(K{start}:K{row - 1})", sum(x["usd"] for x in refs), S0, bold=True)
            f(ws0, row, 12, f"=SUM(L{start}:L{row - 1})", sum(_mul(x["usd"], x["b"]["fx"]) or 0 for x in refs), S0, bold=True)
            for c in range(1, 14):
                ws0.cell(row, c).fill = PatternFill("solid", fgColor=TOTAL_FILL)
            row += 2
    if refs_open:
        heads(ws0, row, ["Open contract", "Supplier", "Pricing", "MT", "Day 0", "Last day", f"CBOT on day 0 {unit}",
                         f"CBOT now {unit}", f"Δ CBOT since day 0 {unit}", "Δ market FX since day 0",
                         "Our price now excl. tr.", "Local now excl. tr.", "Sav/MT now excl. tr."])
        row += 1
        o0 = row
        for x in refs_open:
            tr_, q, v = x["t"], "'Open contracts'!", x["vals"]
            put(ws0, row, 1, tr_.get("contract"), bold=True); put(ws0, row, 2, tr_.get("supplier") or "")
            put(ws0, row, 3, tr_.get("pricing") or "")
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
    for a, b_ in spans.values():
        signs(ws0, f"I{a}:L{b_ + 1}")
    ws0.freeze_panes = f"B{hr + 1}"

    for s in wb.worksheets:
        s.page_setup.orientation = "landscape"
        s.page_setup.paperSize = s.PAPERSIZE_A4
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth, s.page_setup.fitToHeight = 1, 0
        s.oddFooter.center.text = "&A · page &P of &N"
        s.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, cache)
    return {"base": base, "fixed_contracts": len(refs_fixed), "fixed_days": sum(len(x["b"]["days"]) for x in refs_fixed),
            "unfixed_contracts": len(refs_unfixed), "unfixed_days": sum(len(x["b"]["days"]) for x in refs_unfixed),
            "open_contracts": len(refs_open), "formulas": sum(len(v) for v in cache.values()),
            "fixed_usd": sum(x["usd"] for x in refs_fixed), "fixed_mt": sum(x["mt"] for x in refs_fixed)}
