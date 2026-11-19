"""The Home "Daily Open MTM Movement" table, as an Excel sheet laid out like the app.

Same columns, same order, same colours (green = the contract's total improved, red = weaker, grey = new or
left the open book) and the same TOTAL OPEN BOOK row. The values the app stores (CBOT, Sav/MT, the
attribution parts, totals, tonnes) are inputs; every Δ and the whole total row are formulas, so the sheet can
be checked and edited.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .numbers import to_float

HEADERS = ["Ref", "Commodity", "CBOT Today", "CBOT Prior", "Δ CBOT", "Sav/MT Today", "Sav/MT Prior", "Δ Sav/MT",
           "from CBOT", "from FX", "from Local", "Other", "Total Today", "Total Prior", "Δ Total"]
HELPERS = ["MT today", "MT prior", "MT in the why"]


def _num(v):
    return to_float(v, None)


def _delta(a, b, fallback):
    """The app's rule: today − prior; with only one side, a new contract counts in full and one that left the
    open book counts as a loss of its prior value (when ``fallback``)."""
    a, b = _num(a), _num(b)
    if a is not None and b is not None:
        return a - b
    if fallback and a is not None:
        return a
    if fallback and b is not None:
        return -b
    return None


def write_daily_mtm(path, rows: list[dict[str, Any]], *, today: str, prior: str, commodity: str = "ALL",
                    summary: str = "") -> dict[str, Any]:
    """``rows``: dicts with ref, commodity, tag ('improved' | 'weaker' | 'new'), cbot_today, cbot_prior,
    sav_today, sav_prior, from_cbot, from_fx, from_local, other, total_today, total_prior, qty_today,
    qty_prior, in_today / in_prior (the contract has a record on that day) and why_complete (the four parts are
    known, so the row counts in the tonne-weighted why)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from .xlsx_cache import store_formula_results

    wb = Workbook()
    ws = wb.active
    ws.title = "Daily Open MTM"
    cache: dict[str, Any] = {}
    thin = Side(style="thin", color="C9D3E0")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    NAVY, HEAD, TOTAL, INPUT = "1F3A5F", "DCE6F2", "E3E8F7", "FFFBEA"
    COLOUR = {"improved": "1A7A1A", "weaker": "B3261E", "new": "8A8F98"}
    S0, S2, F0, F2 = "+#,##0;-#,##0;0", "+#,##0.00;-#,##0.00;0.00", "#,##0", "#,##0.00"
    fallback = bool(prior)

    def put(r, c, v, fmt=None, bold=False, color=None, fill=None, align=None, italic=False, size=10, wrap=False):
        x = ws.cell(r, c, v)
        x.border = box
        if fmt:
            x.number_format = fmt
        x.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            x.fill = PatternFill("solid", fgColor=fill)
        x.alignment = Alignment(horizontal=align, vertical="center", wrap_text=wrap)

    def fml(r, c, f, v, fmt, **kw):
        put(r, c, f, fmt, **kw)
        cache[f"{L(c)}{r}"] = "" if v is None else v

    ws["A1"] = "Daily Open MTM Movement"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws["A2"] = (f"Today {today} vs the previous stored day {prior or '—'}  ·  commodity: {commodity}  ·  "
                "the parts (from CBOT, FX, Local, Other) add up to Δ Sav/MT (EGP/MT)")
    ws["A2"].font = Font(italic=True, size=9, color="555555")
    ws.merge_cells("A3:O3")
    ws["A3"] = summary
    ws["A3"].font = Font(bold=True, size=10)
    ws["A3"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[3].height = 15 * max(2, -(-len(summary) // 170))

    h = 5
    for c, text in enumerate(HEADERS + [""] + HELPERS, start=1):
        if text:
            put(h, c, text, bold=True, fill=HEAD if c <= len(HEADERS) else INPUT, align="center", wrap=True)
    ws.row_dimensions[h].height = 30
    widths = [34, 11, 11, 11, 9, 12, 12, 10, 10, 9, 10, 9, 14, 14, 13, 2, 10, 10, 11]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[L(i)].width = w

    first = h + 1
    for i, row in enumerate(rows):
        r = first + i
        col = COLOUR.get(row.get("tag"), None)
        put(r, 1, row.get("ref"), color=col, bold=row.get("tag") != "new")
        put(r, 2, row.get("commodity"), color=col)
        put(r, 3, _num(row.get("cbot_today")), F2, color=col)
        put(r, 4, _num(row.get("cbot_prior")), F2, color=col)
        fml(r, 5, f'=IF(AND(ISNUMBER(C{r}),ISNUMBER(D{r})),C{r}-D{r},"")',
            _delta(row.get("cbot_today"), row.get("cbot_prior"), False), S2, color=col)
        put(r, 6, _num(row.get("sav_today")), F0, color=col)
        put(r, 7, _num(row.get("sav_prior")), F0, color=col)
        one_side = (f'IF(ISNUMBER({{a}}{r}),{{a}}{r},IF(ISNUMBER({{b}}{r}),-{{b}}{r},""))' if fallback else '""')
        both = 'IF(AND(ISNUMBER({a}{r}),ISNUMBER({b}{r})),{a}{r}-{b}{r},' + one_side + ')'
        fml(r, 8, "=" + both.format(a="F", b="G", r=r), _delta(row.get("sav_today"), row.get("sav_prior"), fallback),
            S0, color=col)
        for c, key in ((9, "from_cbot"), (10, "from_fx"), (11, "from_local"), (12, "other")):
            put(r, c, _num(row.get(key)), S0, color=col)
        put(r, 13, _num(row.get("total_today")), F0, color=col)
        put(r, 14, _num(row.get("total_prior")), F0, color=col)
        fml(r, 15, "=" + both.format(a="M", b="N", r=r),
            _delta(row.get("total_today"), row.get("total_prior"), fallback), S0, color=col, bold=True)
        put(r, 17, _num(row.get("qty_today")), F0, fill=INPUT)
        put(r, 18, _num(row.get("qty_prior")), F0, fill=INPUT)
        why_mt = (_num(row.get("qty_today")) or 0.0) if row.get("why_complete") else 0.0
        put(r, 19, why_mt, F0, fill=INPUT)
    last = first + len(rows) - 1
    t = last + 1
    rng = lambda c: f"{L(c)}{first}:{L(c)}{last}"
    in_today = lambda x: x.get("in_today", _num(x.get("qty_today")) is not None)
    in_prior = lambda x: x.get("in_prior", _num(x.get("qty_prior")) is not None)
    n_today = sum(1 for x in rows if in_today(x))
    n_prior = sum(1 for x in rows if in_prior(x))
    put(t, 1, f"TOTAL OPEN BOOK  ({n_today} today / {n_prior} prior)", bold=True, fill=TOTAL)
    for c in (2, 3, 4, 5):
        put(t, c, None, fill=TOTAL)
    tot_today = sum(_num(x.get("total_today")) or 0 for x in rows)
    tot_prior = sum(_num(x.get("total_prior")) or 0 for x in rows)
    q_today = sum(_num(x.get("qty_today")) or 0 for x in rows if in_today(x))
    q_prior = sum(_num(x.get("qty_prior")) or 0 for x in rows if in_prior(x))
    sav_t = tot_today / q_today if q_today else None
    sav_p = tot_prior / q_prior if q_prior else None
    fml(t, 13, f"=SUM({rng(13)})", tot_today, F0, bold=True, fill=TOTAL)
    fml(t, 14, f"=SUM({rng(14)})", tot_prior, F0, bold=True, fill=TOTAL)
    fml(t, 15, f"=M{t}-N{t}", tot_today - tot_prior, S0, bold=True, fill=TOTAL)
    fml(t, 17, f"=SUM({rng(17)})", q_today, F0, bold=True, fill=TOTAL)
    fml(t, 18, f"=SUM({rng(18)})", q_prior, F0, bold=True, fill=TOTAL)
    w_mt = sum(((_num(x.get("qty_today")) or 0.0) if x.get("why_complete") else 0.0) for x in rows)
    fml(t, 19, f"=SUM({rng(19)})", w_mt, F0, bold=True, fill=TOTAL)
    fml(t, 6, f'=IF(Q{t}>0,M{t}/Q{t},"")', sav_t, F0, bold=True, fill=TOTAL)
    fml(t, 7, f'=IF(R{t}>0,N{t}/R{t},"")', sav_p, F0, bold=True, fill=TOTAL)
    fml(t, 8, f'=IF(AND(ISNUMBER(F{t}),ISNUMBER(G{t})),F{t}-G{t},"")',
        (sav_t - sav_p) if sav_t is not None and sav_p is not None else None, S0, bold=True, fill=TOTAL)
    for c, key in ((9, "from_cbot"), (10, "from_fx"), (11, "from_local"), (12, "other")):
        v = (sum((_num(x.get(key)) or 0.0) * ((_num(x.get("qty_today")) or 0.0) if x.get("why_complete") else 0.0)
                 for x in rows) / w_mt) if w_mt else None
        fml(t, c, f'=IF($S${t}>0,SUMPRODUCT({rng(c)},$S${first}:$S${last})/$S${t},"")', v, S0, bold=True, fill=TOTAL)
    ws.row_dimensions[t].height = 20
    note = t + 2
    ws.merge_cells(start_row=note, start_column=1, end_row=note, end_column=15)
    ws.cell(note, 1, "Green = the contract's total improved since the prior day · red = weaker · grey = new or left the "
                     "open book. Total row: Sav/MT = total ÷ tonnes; the parts are tonne-weighted over the contracts "
                     "whose four parts are known (column S). Yellow helper columns = the tonnes the app stored."
            ).font = Font(italic=True, size=9, color="555555")
    ws.freeze_panes = f"B{first}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, {ws.title: cache})
    return {"rows": len(rows), "total_row": t, "total_today": tot_today, "total_prior": tot_prior,
            "sav_today": sav_t, "sav_prior": sav_p, "formulas": len(cache), "cache": cache}
