"""The Home "Open Mark-to-Market" table, as an Excel sheet laid out like the app.

Same columns as on screen for the chosen savings view (incl. / excl. / both), the commodity group bands,
the contract rows in the app's colours, the * / † marks on the local price and the TOTAL row. The figures the
app resolves (MT, CIF, FX, freight, discharge, clearance, local price and its transport) are inputs; Own
After, Local excl., Sav/MT, the totals and every group and TOTAL figure are formulas, exactly as the app
computes them (prometheus_core: Own After = CIF × FX + discharge + clearance + freight; excl. = without the
freight; Local excl. = local − its transport; Sav/MT = Local − Own After; total = Sav/MT × MT).
"""

from __future__ import annotations

from typing import Any

from .numbers import to_float

HEADINGS = {"excl": ("Freight (not counted)", "Own After excl.", "Local excl.", "Sav/MT excl."),
            "both": ("Freight", "Own After incl.", "Local incl.", "Sav/MT incl."),
            "incl": ("Freight", "Own After", "Local", "Sav/MT")}
LEAD = ["Ref", "Supplier", "Commodity", "Origin", "Status", "MT", "CIF $", "CIF Formula / Live CBOT", "FX"]
EXTRA = ["Own After excl.", "Local excl.", "Sav/MT excl.", "Total excl. EGP"]
HELP = ["Discharge EGP/MT", "Clearance EGP/MT", "Local incl. EGP/MT", "Local transport EGP/MT", "Row"]


def _n(v):
    return to_float(v, None)


def figures(row):
    """The app's arithmetic for one contract (used for the cached results and the tests)."""
    cif, fx, d, c, f = _n(row.get("cif")), _n(row.get("fx")), _n(row.get("disc")) or 0.0, _n(row.get("clr")) or 0.0, \
        _n(row.get("freight")) or 0.0
    own = cif * fx + d + c + f if cif is not None and fx else None
    own_x = own - f if own is not None else None
    loc, tr = _n(row.get("local")), _n(row.get("local_transport"))
    loc_x = loc - tr if loc is not None and tr is not None else None
    qty = _n(row.get("qty"))
    sav = loc - own if loc is not None and own is not None else None
    sav_x = loc_x - own_x if loc_x is not None and own_x is not None else None
    return {"own": own, "own_x": own_x, "local": loc, "local_x": loc_x, "sav": sav, "sav_x": sav_x,
            "tot": sav * qty if sav is not None and qty is not None else None,
            "tot_x": sav_x * qty if sav_x is not None and qty is not None else None, "qty": qty}


def write_open_mtm(path, groups: list[tuple[str, list[dict[str, Any]]]], *, view: str = "incl", today: str = "",
                   commodity: str = "ALL", fx_mode: str = "live") -> dict[str, Any]:
    """``groups``: [(base commodity, [row dicts])] in the app's order. A row dict carries ref, supplier,
    commodity, origin, status, qty, cif, cif_display, cif_formula, fx, freight, disc, clr, local,
    local_transport, decision, tag ('go' | 'wait' | 'missing') and marks (' *', ' †')."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from .xlsx_cache import store_formula_results

    view = view if view in HEADINGS else "incl"
    xv, both = view == "excl", view == "both"
    wb = Workbook()
    ws = wb.active
    ws.title = "Open MTM"
    cache: dict[str, Any] = {}
    thin = Side(style="thin", color="C9D3E0")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    GRP_BG, GRP_FG, TOTAL, HEAD, INPUT, NAVY = "1A2D40", "E8F0FE", "E3E8F7", "DCE6F2", "FFFBEA", "1F3A5F"
    TAG = {"go": ("1A7A1A", True), "wait": ("B3261E", False), "missing": ("8A8F98", False)}
    F0, F4, S0 = "#,##0", "0.0000", "#,##0;-#,##0;0"

    heads = LEAD + list(HEADINGS[view]) + ["Decision"] + (EXTRA if both else [])
    n_vis = len(heads)
    hcol = n_vis + 2                                        # helper columns after one blank column
    C = {name: i + 1 for i, name in enumerate(["ref", "sup", "comm", "orig", "stat", "mt", "cif", "form", "fx",
                                                "frt", "own", "loc", "sav", "dec"])}
    if both:
        C.update({"ownx": 15, "locx": 16, "savx": 17, "totx": 18})
    H = {"disc": hcol, "clr": hcol + 1, "linc": hcol + 2, "ltr": hcol + 3, "type": hcol + 4}
    col = lambda k: L(C[k])
    hc = lambda k: L(H[k])

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

    ws["A1"] = "Open Mark-to-Market"
    ws["A1"].font = Font(bold=True, size=14, color=NAVY)
    ws["A2"] = (f"{today}  ·  commodity: {commodity}  ·  FX rate: {'Locked (contract rate)' if fx_mode == 'locked' else 'Live'}"
                f"  ·  savings view: {'excl. transport' if xv else 'incl. and excl.' if both else 'incl. transport'}")
    ws["A2"].font = Font(italic=True, size=9, color="555555")
    h = 4
    for c, text in enumerate(heads, start=1):
        put(h, c, text, bold=True, fill=HEAD, align="center", wrap=True)
    for i, text in enumerate(HELP):
        put(h, hcol + i, text, bold=True, fill=INPUT, align="center", wrap=True)
    ws.row_dimensions[h].height = 32
    widths = {"ref": 26, "sup": 16, "comm": 12, "orig": 11, "stat": 9, "mt": 9, "cif": 9, "form": 30, "fx": 9,
              "frt": 11, "own": 12, "loc": 12, "sav": 11, "dec": 20, "ownx": 12, "locx": 12, "savx": 11, "totx": 14}
    for k, w in widths.items():
        if k in C:
            ws.column_dimensions[col(k)].width = w
    for k in H:
        ws.column_dimensions[hc(k)].width = 11
    ws.column_dimensions[L(hcol - 1)].width = 2

    r = h + 1
    first = r
    group_rows, contract_rows = [], []
    for comm, rows in groups:
        g = r
        group_rows.append(g)
        r += 1
        g0 = r
        for row in rows:
            fig = figures(row)
            colr, bold = TAG.get(row.get("tag"), (None, False))
            kw = {"color": colr, "bold": bold}
            put(r, C["ref"], row.get("ref"), **kw)
            put(r, C["sup"], row.get("supplier"), **kw)
            put(r, C["comm"], row.get("commodity"), **kw)
            put(r, C["orig"], row.get("origin"), **kw)
            put(r, C["stat"], row.get("status"), **kw)
            put(r, C["mt"], fig["qty"], F0, **kw)
            cif = _n(row.get("cif"))
            put(r, C["cif"], cif if cif is not None else (row.get("cif_display") or "?"), "#,##0.00", **kw)
            put(r, C["form"], row.get("cif_formula"), **kw)
            put(r, C["fx"], _n(row.get("fx")), F4, **kw)
            put(r, C["frt"], _n(row.get("freight")), F0, **kw)
            put(r, H["disc"], _n(row.get("disc")), "#,##0.00", fill=INPUT)
            put(r, H["clr"], _n(row.get("clr")), "#,##0.00", fill=INPUT)
            put(r, H["linc"], fig["local"], F0, fill=INPUT)
            put(r, H["ltr"], _n(row.get("local_transport")), F0, fill=INPUT)
            put(r, H["type"], "contract", color="999999", size=8)
            base = f"{col('cif')}{r}*{col('fx')}{r}+{hc('disc')}{r}+{hc('clr')}{r}"
            ok = f"AND(ISNUMBER({col('cif')}{r}),ISNUMBER({col('fx')}{r}),{col('fx')}{r}<>0)"
            own_incl = f'IF({ok},{base}+{col("frt")}{r},"")'
            own_excl = f'IF({ok},{base},"")'
            loc_excl = f'IF(AND(ISNUMBER({hc("linc")}{r}),ISNUMBER({hc("ltr")}{r})),{hc("linc")}{r}-{hc("ltr")}{r},"")'
            loc_incl = f'IF(ISNUMBER({hc("linc")}{r}),{hc("linc")}{r},"")'
            mark = row.get("marks") or ""
            lfmt = F0 + (f'"{mark}"' if mark else "")
            fml(r, C["own"], "=" + (own_excl if xv else own_incl), fig["own_x"] if xv else fig["own"], F0, **kw)
            fml(r, C["loc"], "=" + (loc_excl if xv else loc_incl), fig["local_x"] if xv else fig["local"], lfmt, **kw)
            fml(r, C["sav"], f'=IF(AND(ISNUMBER({col("loc")}{r}),ISNUMBER({col("own")}{r})),{col("loc")}{r}-{col("own")}{r},"")',
                fig["sav_x"] if xv else fig["sav"], S0, **kw)
            put(r, C["dec"], row.get("decision"), **kw)
            if both:
                fml(r, C["ownx"], "=" + own_excl, fig["own_x"], F0, **kw)
                fml(r, C["locx"], "=" + loc_excl, fig["local_x"], lfmt, **kw)
                fml(r, C["savx"], f'=IF(AND(ISNUMBER({col("locx")}{r}),ISNUMBER({col("ownx")}{r})),'
                                  f'{col("locx")}{r}-{col("ownx")}{r},"")', fig["sav_x"], S0, **kw)
                fml(r, C["totx"], f'=IF(AND(ISNUMBER({col("savx")}{r}),ISNUMBER({col("mt")}{r})),'
                                  f'{col("savx")}{r}*{col("mt")}{r},"")', fig["tot_x"], S0, **kw)
            row["_fig"] = fig
            contract_rows.append(r)
            r += 1
        g1 = r - 1
        # the group band, as in the app: tonne-weighted over its contracts
        figs = [x["_fig"] for x in rows]
        qty = sum(f["qty"] or 0 for f in figs)
        k_own, k_loc, k_sav = ("own_x", "local_x", "sav_x") if xv else ("own", "local", "sav")
        edge = sum((f[k_sav] or 0) * (f["qty"] or 0) for f in figs)
        gk = {"fill": GRP_BG, "color": GRP_FG, "bold": True}
        put(g, C["ref"], f"▸  {comm}  ({len(rows)} contracts)", **gk)
        for k in ("sup", "comm", "orig", "stat", "cif", "form", "fx", "frt"):
            put(g, C[k], None, fill=GRP_BG)
        rg = lambda k: f"{col(k)}{g0}:{col(k)}{g1}"
        fml(g, C["mt"], f"=SUM({rg('mt')})", qty, F0, **gk)
        wavg = lambda k, v: fml(g, C[k], f'=IF({col("mt")}{g}>0,SUMPRODUCT({rg(k)},{rg("mt")})/{col("mt")}{g},"")',
                                v, F0 if k != "sav" and k != "savx" else S0, **gk)
        wavg("own", sum((f[k_own] or 0) * (f["qty"] or 0) for f in figs) / qty if qty else None)
        wavg("loc", sum((f[k_loc] or 0) * (f["qty"] or 0) for f in figs) / qty if qty else None)
        wavg("sav", edge / qty if qty else None)
        fml(g, C["dec"], f'="EGP "&TEXT(SUMPRODUCT({rg("sav")},{rg("mt")}),"+#,##0;-#,##0;+0")&" total"',
            f"EGP {edge:+,.0f} total", None, **gk)
        if both:
            wavg("ownx", sum((f["own_x"] or 0) * (f["qty"] or 0) for f in figs) / qty if qty else None)
            wavg("locx", sum((f["local_x"] or 0) * (f["qty"] or 0) for f in figs) / qty if qty else None)
            totx = sum(f["tot_x"] or 0 for f in figs)
            fml(g, C["savx"], f'=IF({col("mt")}{g}>0,{col("totx")}{g}/{col("mt")}{g},"")', totx / qty if qty else None,
                S0, **gk)
            fml(g, C["totx"], f"=SUM({rg('totx')})", totx, S0, **gk)
        put(g, H["type"], "group", color="999999", size=8)
    last = r - 1
    t = r
    allf = [x["_fig"] for _, rows in groups for x in rows]
    qty = sum(f["qty"] or 0 for f in allf)
    k_own, k_sav = ("own_x", "sav_x") if xv else ("own", "sav")
    k_oth = "tot" if xv else "tot_x"
    edge = sum((f[k_sav] or 0) * (f["qty"] or 0) for f in allf)
    other = sum(f[k_oth] or 0 for f in allf)
    tk = {"fill": TOTAL, "bold": True}
    is_c = f'--(${hc("type")}${first}:${hc("type")}${last}="contract")'
    ra = lambda k: f"{col(k)}{first}:{col(k)}{last}"
    put(t, C["ref"], f"TOTAL  ({len(allf)} open)", **tk)
    for k in ("sup", "comm", "orig", "stat", "cif", "form", "fx", "frt", "loc"):
        put(t, C[k], None, fill=TOTAL)
    fml(t, C["mt"], f'=SUMIF(${hc("type")}${first}:${hc("type")}${last},"contract",{ra("mt")})', qty, F0, **tk)
    fml(t, C["own"], f'=IF({col("mt")}{t}>0,SUMPRODUCT({is_c},{ra("own")},{ra("mt")})/{col("mt")}{t},"")',
        sum((f[k_own] or 0) * (f["qty"] or 0) for f in allf) / qty if qty else None, F0, **tk)
    fml(t, C["dec"], f'=SUMPRODUCT({is_c},{ra("sav")},{ra("mt")})', edge, S0, **tk)
    fml(t, C["sav"], f'=IF({col("mt")}{t}>0,{col("dec")}{t}/{col("mt")}{t},"")', edge / qty if qty else None, S0, **tk)
    if both:
        put(t, C["ownx"], None, fill=TOTAL)
        put(t, C["locx"], None, fill=TOTAL)
        fml(t, C["totx"], f'=SUMIF(${hc("type")}${first}:${hc("type")}${last},"contract",{ra("totx")})', other, S0, **tk)
        fml(t, C["savx"], f'=IF({col("mt")}{t}>0,{col("totx")}{t}/{col("mt")}{t},"")', other / qty if qty else None,
            S0, **tk)
    ws.row_dimensions[t].height = 20
    note = t + 2
    ws.cell(note, 1, "*  local price carried forward >14 days        †  no delivery-date local price yet — using today's "
                     "as a stand-in").font = Font(italic=True, size=9, color="555555")
    ws.cell(note + 1, 1, "Own After = CIF × FX + discharge + clearance" + ("" if xv else " + freight")
            + (" (excl. columns: without the freight)" if both else "")
            + " · Sav/MT = Local − Own After · group and TOTAL rows are weighted by MT · yellow = figures the app "
              "resolved for each contract").font = Font(italic=True, size=9, color="555555")
    ws.freeze_panes = f"B{first}"
    ws.page_setup.orientation = "landscape"
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_view.showGridLines = False
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, {ws.title: cache})
    for _, rows in groups:
        for x in rows:
            x.pop("_fig", None)
    return {"groups": len(groups), "contracts": len(allf), "total_row": t, "edge": edge, "qty": qty,
            "formulas": len(cache), "cache": cache, "view": view}
