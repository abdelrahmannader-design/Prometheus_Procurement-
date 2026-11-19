"""'Fixed till pricing': each fixed contract from its receiving date to the day its last lot was priced, only.

Built from the finished "Fixed consumption" sheet of the CBOT export (prometheus_core.cbot_overview): the same
blocks and columns, but a contract's days stop at its last priced lot, so the average, lowest and highest CBOT
and the share of days cheaper than our fixing cover only the days we could still price. A contract that is not
fully priced yet keeps every day to the window end. Inputs are links to the Fixed consumption sheet; every
derived figure is a formula with its value cached.
"""

from __future__ import annotations

import datetime as dt
import re
from copy import copy

SRC = "Fixed consumption"
SHEET = "Fixed till pricing"
EPOCH = dt.datetime(1899, 12, 30)
GREEN, RED, NAVY = "1A7A1A", "B3261E", "1F3A5F"
SUMMARY_HEADS = ["Contract", "Receiving date", "Last day counted", "Days in window", "MT priced", "Our fixed CBOT ¢/bu",
                 "Avg CBOT receiving → pricing ¢/bu", "Avg − our fixing ¢/bu", "USD (on MT priced)", "EGP",
                 "Lowest CBOT ¢/bu", "Lowest on", "Highest CBOT ¢/bu", "Highest on", "Days cheaper than our fixing",
                 "In words", "Pricing"]


def _num(v):
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _sub(a, b):
    return a - b if _num(a) is not None and _num(b) is not None else None


def _mul(a, b):
    return a * b if _num(a) is not None and _num(b) is not None else None


def _serial(v):
    if isinstance(v, dt.datetime):
        return (v - EPOCH).days + (v - EPOCH).seconds / 86400
    if isinstance(v, dt.date):
        return (dt.datetime(v.year, v.month, v.day) - EPOCH).days
    return "" if v is None else v


def _day(v):
    if isinstance(v, dt.datetime):
        return v.date()
    return v if isinstance(v, dt.date) else None


def find_blocks(fs, value):
    """The contract blocks of the Fixed consumption sheet: header row, its days, the footer row, and whether
    the contract is fully priced (lots ≥ the contract MT in the header)."""
    out = []
    for h in range(1, fs.max_row + 1):
        t = fs.cell(h, 1).value
        if not (isinstance(t, str) and "  ·  " in t and fs.cell(h + 3, 1).value == "Date"):
            continue
        r, days = h + 4, []
        while _day(fs.cell(r, 1).value):
            days.append(r)
            r += 1
        if not days:
            continue
        lots = [x for x in days if _num(value(x, 2))]
        m = re.search(r"([\d,]+(?:\.\d+)?) MT", t)
        qty = float(m.group(1).replace(",", "")) if m else None
        priced = sum(_num(value(x, 2)) or 0.0 for x in days)
        done = bool(lots) and (qty is None or priced >= qty - 1)
        last_lot = max(lots) if lots else None
        out.append({"h": h, "all_days": days, "days": [x for x in days if x <= last_lot] if done else days,
                    "foot": r, "qty": qty, "priced": priced, "done": done,
                    "last_lot": _day(fs.cell(last_lot, 1).value) if last_lot else None})
    return out


def write_fixed_till_pricing(wb, cache, band=1.0, base="CORN", src=SRC, name=SHEET, index=None):
    """Add the sheet to ``wb`` (after ``src`` unless ``index``) and return {cache, blocks, summary}.

    ``cache``: the workbook's {sheet: {cell: value}} formula results so far (the source's formula values are read
    from it; the new sheet's are added to it)."""
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    fs = wb[src]
    src_cache = cache.get(src, {})

    def value(r, c):
        cell = fs.cell(r, c)
        v = cell.value
        if isinstance(v, str) and v.startswith("="):
            return src_cache.get(cell.coordinate)
        return v

    ws = wb.create_sheet(name, wb.sheetnames.index(src) + 1 if index is None else index)
    C = cache.setdefault(name, {})
    thin = Side(style="thin", color="C9D3E0")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    Q = f"'{src}'!"

    def style(dst, s):
        dst.font, dst.fill, dst.border = copy(s.font), copy(s.fill), copy(s.border)
        dst.alignment, dst.number_format = copy(s.alignment), s.number_format

    def F(r, c, formula, v, s=None, fmt=None):
        x = ws.cell(r, c, formula)
        if s is not None:
            style(x, s)
        if fmt:
            x.number_format = fmt
        if isinstance(formula, str) and formula.startswith("="):
            C[x.coordinate] = _serial(v) if v is not None else ""
        return x

    blocks = find_blocks(fs, value)
    ws["A1"] = f"{base} — fixed contracts: receiving date to the last priced lot only"
    ws["A1"].font = Font(bold=True, size=15, color=NAVY)
    ws.merge_cells("A2:Q2")
    ws["A2"] = ("Same as the Fixed consumption sheet, but each contract stops on the day its last lot was priced: days "
                "after pricing are left out. The average, lowest, highest and the days cheaper than our fixing cover only "
                "the receiving date → last pricing day. Avg − our fixing > 0 (green) = we fixed below the average of the "
                "days we could price: an advantage. A contract still being priced keeps every day up to the window end. "
                "Inputs are linked to the Fixed consumption sheet: edit them there.")
    ws["A2"].font = Font(italic=True, color="6B7280")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 45
    widths = {"A": 22, "B": 11, "C": 12, "D": 11, "E": 10, "F": 12, "G": 13, "H": 13, "I": 13, "J": 13, "K": 26,
              "L": 11, "M": 12, "N": 12, "O": 12, "P": 26, "Q": 40}
    for k, w in widths.items():
        ws.column_dimensions[k].width = w
    ws.sheet_view.showGridLines = False
    if not blocks:
        ws["A4"] = f"No fixed {base} contract."
        ws["A4"].font = Font(italic=True, color="6B7280")
        return {"cache": C, "blocks": [], "summary": []}

    head_style = fs.cell(blocks[0]["h"] + 3, 1)
    s_head, s_first = 4, 5
    ws.cell(s_head - 1, 1, "Summary — each fixed contract from its receiving date to its last priced lot").font = \
        Font(bold=True, size=11, color=NAVY)
    for i, t in enumerate(SUMMARY_HEADS, 1):
        c = ws.cell(s_head, i, t)
        style(c, head_style)
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[s_head].height = 44
    s_last = s_first + len(blocks) - 1
    s_tot = s_last + 1

    r0 = s_tot + 3
    summary = []
    for b in blocks:
        h, days, foot = b["h"], b["days"], b["foot"]
        hc = ws.cell(r0, 1, fs.cell(h, 1).value)
        style(hc, fs.cell(h, 1))
        ws.merge_cells(start_row=r0, start_column=1, end_row=r0, end_column=14)
        ws.row_dimensions[r0].height = fs.row_dimensions[h].height
        for c in range(1, 12):
            style(ws.cell(r0 + 1, c, fs.cell(h + 1, c).value), fs.cell(h + 1, c))
            F(r0 + 2, c, f"={Q}{fs.cell(h + 2, c).column_letter}{h + 2}", value(h + 2, c), fs.cell(h + 2, c))
        ws.row_dimensions[r0 + 1].height = fs.row_dimensions[h + 1].height
        for c in range(1, 15):
            style(ws.cell(r0 + 3, c, fs.cell(h + 3, c).value), fs.cell(h + 3, c))
        ws.row_dimensions[r0 + 3].height = fs.row_dimensions[h + 3].height
        t = r0 + 2
        fix, fac, cif, fx, landed = (_num(value(h + 2, c)) for c in (1, 3, 4, 5, 9))
        first = r0 + 4
        rows = []
        for i, x in enumerate(days):
            r = first + i
            d = _day(fs.cell(x, 1).value)
            mt, cb, loc, mfx = (_num(value(x, c)) for c in (2, 3, 8, 12))
            F(r, 1, f"={Q}A{x}", d, fs.cell(x, 1))
            F(r, 2, f'=IF(ISNUMBER({Q}B{x}),{Q}B{x},"")', mt, fs.cell(x, 2))
            F(r, 3, f'=IF(ISNUMBER({Q}C{x}),{Q}C{x},"")', cb, fs.cell(x, 3))
            dd = _sub(cb, fix); e = _mul(dd, fac); f_ = _mul(e, mt); g = _mul(f_, fx)
            F(r, 4, f'=IF(AND(ISNUMBER(C{r}),ISNUMBER($A${t})),C{r}-$A${t},"")', dd, fs.cell(x, 4))
            F(r, 5, f'=IF(ISNUMBER(D{r}),D{r}*$C${t},"")', e, fs.cell(x, 5))
            F(r, 6, f'=IF(AND(ISNUMBER(E{r}),ISNUMBER(B{r})),E{r}*B{r},"")', f_, fs.cell(x, 6))
            F(r, 7, f'=IF(ISNUMBER(F{r}),F{r}*$E${t},"")', g, fs.cell(x, 7))
            F(r, 8, f'=IF(ISNUMBER({Q}H{x}),{Q}H{x},"")', loc, fs.cell(x, 8))
            i_ = _sub(loc, landed); j = _mul(i_, mt)
            F(r, 9, f'=IF(AND(ISNUMBER(H{r}),ISNUMBER($I${t})),H{r}-$I${t},"")', i_, fs.cell(x, 9))
            F(r, 10, f'=IF(AND(ISNUMBER(I{r}),ISNUMBER(B{r})),I{r}*B{r},"")', j, fs.cell(x, 10))
            F(r, 12, f'=IF(ISNUMBER({Q}L{x}),{Q}L{x},"")', mfx, fs.cell(x, 12))
            m = _sub(mfx, fx)
            F(r, 13, f'=IF(AND(ISNUMBER(L{r}),ISNUMBER($E${t})),L{r}-$E${t},"")', m, fs.cell(x, 13))
            F(r, 14, f'=IF(AND(ISNUMBER(M{r}),ISNUMBER($D${t})),M{r}*$D${t},"")', _mul(m, cif), fs.cell(x, 14))
            rows.append(dict(r=r, d=d, mt=mt, cb=cb, dd=dd, f=f_, g=g, loc=loc, j=j, mfx=mfx))
        last = first + len(rows) - 1
        tot = last + 1
        rg = lambda col: f"{col}{first}:{col}{last}"
        cbs = [x["cb"] for x in rows if x["cb"] is not None]
        lo, hi = (min(cbs), max(cbs)) if cbs else (None, None)
        low_r, high_r, a, ch = tot + 2, tot + 3, tot + 1, tot + 4
        for x in rows:                                   # K: that day as a pricing point within this window
            k = ""
            if x["dd"] is not None:
                k = ("Lowest · best day to price" if x["cb"] == lo else "Highest · dearest day" if x["cb"] == hi else
                     "Cheaper than our fixing" if x["dd"] <= -band else "Dearer than our fixing" if x["dd"] >= band
                     else "About our fixing")
            r = x["r"]
            F(r, 11, f'=IF(ISNUMBER(D{r}),IF(C{r}=$C${low_r},"Lowest · best day to price",IF(C{r}=$C${high_r},'
                     f'"Highest · dearest day",IF(D{r}<=-Summary!$C$6,"Cheaper than our fixing",IF(D{r}>=Summary!$C$6,'
                     f'"Dearer than our fixing","About our fixing")))),"")', k, fs.cell(days[0], 11))
        for k in range(5):                               # footers styled and merged like the source's
            for c in range(1, 15):
                style(ws.cell(tot + k, c), fs.cell(foot + k, c))
        for mr in list(fs.merged_cells.ranges):
            if foot <= mr.min_row <= foot + 4 and mr.min_row == mr.max_row:
                ws.merge_cells(start_row=tot + (mr.min_row - foot), start_column=mr.min_col,
                               end_row=tot + (mr.min_row - foot), end_column=mr.max_col)
        mt_sum = sum(x["mt"] or 0 for x in rows)
        wavg = lambda key: (sum((x["mt"] or 0) * x[key] for x in rows if x[key] is not None and x["mt"]) / mt_sum
                            if mt_sum else None)
        ws.cell(tot, 1, "Total — lots priced")
        F(tot, 2, f"=SUM({rg('B')})", mt_sum)
        c_tot = wavg("cb")
        F(tot, 3, f'=IF(B{tot}<>0,SUMPRODUCT({rg("B")},{rg("C")})/B{tot},"")', c_tot)
        F(tot, 4, f'=IF(AND(ISNUMBER(C{tot}),ISNUMBER($A${t})),C{tot}-$A${t},"")', _sub(c_tot, fix))
        f_sum = sum(x["f"] or 0 for x in rows); g_sum = sum(x["g"] or 0 for x in rows)
        j_sum = sum(x["j"] or 0 for x in rows)
        F(tot, 5, f'=IF(B{tot}<>0,F{tot}/B{tot},"")', f_sum / mt_sum if mt_sum else None)
        F(tot, 6, f"=SUM({rg('F')})", f_sum)
        F(tot, 7, f"=SUM({rg('G')})", g_sum)
        F(tot, 8, f'=IF(B{tot}<>0,SUMPRODUCT({rg("B")},{rg("H")})/B{tot},"")', wavg("loc"))
        F(tot, 9, f'=IF(B{tot}<>0,J{tot}/B{tot},"")', j_sum / mt_sum if mt_sum else None)
        F(tot, 10, f"=SUM({rg('J')})", j_sum)
        dtot = _sub(c_tot, fix)
        F(tot, 11, f'=IF(ISNUMBER(D{tot}),IF(D{tot}<=-Summary!$C$6,"Cheaper than our fixing",IF(D{tot}>=Summary!$C$6,'
                   f'"Dearer than our fixing","About our fixing")),"")',
          "" if dtot is None else "Cheaper than our fixing" if dtot <= -band else
          "Dearer than our fixing" if dtot >= band else "About our fixing")
        avg = sum(cbs) / len(cbs) if cbs else None
        ws.cell(a, 1, "Avg CBOT, receiving date → last pricing day" if b["done"] else
                "Avg CBOT, receiving date → window end (still pricing)")
        F(a, 3, f'=IF(COUNT({rg("C")})>0,AVERAGE({rg("C")}),"")', avg)
        da = _sub(avg, fix); ea = _mul(da, fac); fa = _mul(ea, mt_sum); ga = _mul(fa, fx)
        F(a, 4, f'=IF(AND(ISNUMBER(C{a}),ISNUMBER($A${t})),C{a}-$A${t},"")', da)
        F(a, 5, f'=IF(ISNUMBER(D{a}),D{a}*$C${t},"")', ea)
        F(a, 6, f'=IF(ISNUMBER(E{a}),E{a}*B{tot},"")', fa)
        F(a, 7, f'=IF(ISNUMBER(F{a}),F{a}*$E${t},"")', ga)
        d0, d1 = rows[0]["d"], rows[-1]["d"]
        F(a, 8, f'=TEXT(A{first},"yyyy-mm-dd")&" → "&TEXT(A{last},"yyyy-mm-dd")&" ("&COUNT({rg("C")})&" days)"',
          f"{d0:%Y-%m-%d} → {d1:%Y-%m-%d} ({len(cbs)} days)")
        verdict = "" if da is None else ("We fixed below the average" if da >= band else
                                         "We fixed above the average" if da <= -band else "In line with the average")
        F(a, 11, f'=IF(ISNUMBER(D{a}),IF(D{a}>=Summary!$C$6,"We fixed below the average",IF(D{a}<=-Summary!$C$6,'
                 f'"We fixed above the average","In line with the average")),"")', verdict)
        fxs = [x["mfx"] for x in rows if x["mfx"] is not None]
        afx = sum(fxs) / len(fxs) if fxs else None
        F(a, 12, f'=IF(COUNT({rg("L")})>0,AVERAGE({rg("L")}),"")', afx)
        F(a, 13, f'=IF(AND(ISNUMBER(L{a}),ISNUMBER($E${t})),L{a}-$E${t},"")', _sub(afx, fx))
        F(a, 14, f'=IF(AND(ISNUMBER(M{a}),ISNUMBER($D${t})),M{a}*$D${t},"")', _mul(_sub(afx, fx), cif))
        ons = {}
        for rr, label, fn, word, val, fxv in (
                (low_r, "Lowest in window (CBOT · FX)", "MIN", "Best day to price", lo, min(fxs) if fxs else None),
                (high_r, "Highest in window (CBOT · FX)", "MAX", "Dearest day", hi, max(fxs) if fxs else None)):
            ws.cell(rr, 1, label)
            F(rr, 3, f'=IF(COUNT({rg("C")})>0,{fn}({rg("C")}),"")', val)
            F(rr, 4, f'=IF(AND(ISNUMBER(C{rr}),ISNUMBER($A${t})),C{rr}-$A${t},"")', _sub(val, fix))
            on = next((x["d"] for x in rows if x["cb"] == val), None)
            ons[fn] = on
            F(rr, 8, f'=IF(ISNUMBER(C{rr}),"CBOT on "&TEXT(INDEX({rg("A")},MATCH(C{rr},{rg("C")},0)),"yyyy-mm-dd"),"")',
              f"CBOT on {on:%Y-%m-%d}" if on else "")
            ws.cell(rr, 11, word)
            F(rr, 12, f'=IF(COUNT({rg("L")})>0,{fn}({rg("L")}),"")', fxv)
            F(rr, 13, f'=IF(AND(ISNUMBER(L{rr}),ISNUMBER($E${t})),L{rr}-$E${t},"")', _sub(fxv, fx))
            F(rr, 14, f'=IF(AND(ISNUMBER(M{rr}),ISNUMBER($D${t})),M{rr}*$D${t},"")', _mul(_sub(fxv, fx), cif))
        ws.cell(ch, 1, "Days cheaper than our fixing")
        share = sum(1 for v in cbs if v < fix) / len(cbs) if cbs and fix is not None else None
        F(ch, 3, f'=IF(COUNT({rg("C")})>0,COUNTIF({rg("C")},"<"&$A${t})/COUNT({rg("C")}),"")', share)
        ws.cell(ch, 8, "CBOT below our fixing · 0% = we fixed at the low")
        fshare = sum(1 for v in fxs if v < fx) / len(fxs) if fxs and fx is not None else None
        F(ch, 12, f'=IF(COUNT({rg("L")})>0,COUNTIF({rg("L")},"<"&$E${t})/COUNT({rg("L")}),"")', fshare)
        ws.cell(ch, 13, "← days market FX < ours")
        gf, rf = Font(color=GREEN, bold=True), Font(color=RED, bold=True)
        add = ws.conditional_formatting.add
        add(f"D{first}:G{a}", CellIsRule(operator="lessThan", formula=["0"], font=Font(color=GREEN)))
        add(f"D{first}:G{a}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=RED)))
        add(f"I{first}:J{a}", CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        add(f"I{first}:J{a}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))
        add(f"M{first}:N{last}", CellIsRule(operator="lessThan", formula=["0"], font=Font(color=GREEN)))
        add(f"M{first}:N{last}", CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=RED)))
        kr = f"K{first}:K{high_r}"
        add(kr, FormulaRule(formula=[f'OR(LEFT($K{first},6)="Lowest",LEFT($K{first},8)="Best day",'
                                     f'LEFT($K{first},14)="We fixed below")'], font=gf))
        add(kr, FormulaRule(formula=[f'OR(LEFT($K{first},7)="Highest",LEFT($K{first},7)="Dearest",'
                                     f'LEFT($K{first},14)="We fixed above")'], font=rf))
        add(kr, FormulaRule(formula=[f'LEFT($K{first},7)="Cheaper"'], font=Font(color=GREEN)))
        add(kr, FormulaRule(formula=[f'LEFT($K{first},6)="Dearer"'], font=Font(color=RED)))
        add(f"C{first}:C{last}", FormulaRule(formula=[f"C{first}=$C${low_r}"], font=gf))
        add(f"C{first}:C{last}", FormulaRule(formula=[f"C{first}=$C${high_r}"], font=rf))
        pricing = (f"Fully priced · last lot {b['last_lot']:%d %b}" if b["done"] else
                   (f"Partly priced: {b['priced']:,.0f} of {b['qty']:,.0f} MT · still pricing, counted to {d1:%d %b}"
                    if b["qty"] else f"Still pricing · counted to {d1:%d %b}"))
        summary.append(dict(name=fs.cell(h, 1).value.split("  ·  ")[0], r0=r0, t=t, first=first, last=last, tot=tot,
                            a=a, low=low_r, high=high_r, ch=ch, d0=d0, d1=d1, n=len(cbs), mt=mt_sum, fix=fix, avg=avg,
                            da=da, fa=fa, ga=ga, lo=lo, hi=hi, share=share, verdict=verdict, lo_on=ons.get("MIN"),
                            hi_on=ons.get("MAX"), cut=len(b["all_days"]) - len(days), pricing=pricing,
                            done=b["done"]))
        r0 = ch + 3

    S0, S2 = '[>=0.5]\\+#,##0;[<=-0.5]\\-#,##0;0', '[>=0.005]\\+#,##0.00;[<=-0.005]\\-#,##0.00;0.00'
    DF, F2, F0 = "dd mmm yyyy", "#,##0.00", "#,##0"
    for i, s in enumerate(summary):
        r = s_first + i

        def P(c, formula, v, fmt=None, bold=False, align=None):
            x = F(r, c, formula, v, fmt=fmt)
            x.border, x.font = box, Font(bold=bold)
            x.alignment = Alignment(horizontal=align, vertical="center")

        x = ws.cell(r, 1, s["name"])
        x.border, x.hyperlink = box, f"#'{name}'!A{s['r0']}"
        x.font = Font(bold=True, color="1F5FBF", underline="single")
        rng = f"{s['first']}:{{c}}{s['last']}"
        P(2, f"=A{s['first']}", s["d0"], DF, align="center")
        P(3, f"=A{s['last']}", s["d1"], DF, align="center")
        P(4, f"=COUNT(C{s['first']}:C{s['last']})", s["n"], F0, align="center")
        P(5, f"=B{s['tot']}", s["mt"], F0)
        P(6, f"=A{s['t']}", s["fix"], F2)
        P(7, f"=C{s['a']}", s["avg"], F2)
        P(8, f"=D{s['a']}", s["da"], S2, bold=True)
        P(9, f"=F{s['a']}", s["fa"], S0, bold=True)
        P(10, f"=G{s['a']}", s["ga"], S0)
        P(11, f"=C{s['low']}", s["lo"], F2)
        P(12, f"=INDEX(A{s['first']}:A{s['last']},MATCH(C{s['low']},C{s['first']}:C{s['last']},0))", s["lo_on"], DF,
          align="center")
        P(13, f"=C{s['high']}", s["hi"], F2)
        P(14, f"=INDEX(A{s['first']}:A{s['last']},MATCH(C{s['high']},C{s['first']}:C{s['last']},0))", s["hi_on"], DF,
          align="center")
        P(15, f"=C{s['ch']}", s["share"], "0%", align="center")
        P(16, f"=K{s['a']}", s["verdict"], align="center")
        x = ws.cell(r, 17, s["pricing"])
        x.border = box
        x.font = Font(italic=not s["done"], color=None if s["done"] else "B26A00")
    fill = PatternFill("solid", fgColor="E8EEF6")
    ws.cell(s_tot, 1, "Total").font = Font(bold=True)
    mt_all = sum(s["mt"] for s in summary)
    wsum = lambda key: (sum(s["mt"] * s[key] for s in summary if s[key] is not None) / mt_all) if mt_all else None
    rs = lambda col: f"{col}{s_first}:{col}{s_last}"
    totals = {5: (f"=SUM({rs('E')})", mt_all, F0),
              6: (f'=IF(E{s_tot}>0,SUMPRODUCT({rs("E")},{rs("F")})/E{s_tot},"")', wsum("fix"), F2),
              7: (f'=IF(E{s_tot}>0,SUMPRODUCT({rs("E")},{rs("G")})/E{s_tot},"")', wsum("avg"), F2),
              8: (f'=IF(E{s_tot}>0,SUMPRODUCT({rs("E")},{rs("H")})/E{s_tot},"")', wsum("da"), S2),
              9: (f"=SUM({rs('I')})", sum(s["fa"] or 0 for s in summary), S0),
              10: (f"=SUM({rs('J')})", sum(s["ga"] or 0 for s in summary), S0)}
    for c in range(1, 18):
        x = ws.cell(s_tot, c)
        if c in totals:
            fml, v, fmt = totals[c]
            F(s_tot, c, fml, v, fmt=fmt)
            x.font = Font(bold=True)
        x.fill, x.border = fill, box
    ws.conditional_formatting.add(f"H{s_first}:J{s_tot}", CellIsRule(operator="greaterThan", formula=["0"],
                                                                       font=Font(color=GREEN, bold=True)))
    ws.conditional_formatting.add(f"H{s_first}:J{s_tot}", CellIsRule(operator="lessThan", formula=["0"],
                                                                       font=Font(color=RED, bold=True)))
    ws.conditional_formatting.add(f"P{s_first}:P{s_last}", FormulaRule(
        formula=[f'LEFT($P{s_first},14)="We fixed below"'], font=Font(color=GREEN, bold=True)))
    ws.conditional_formatting.add(f"P{s_first}:P{s_last}", FormulaRule(
        formula=[f'LEFT($P{s_first},14)="We fixed above"'], font=Font(color=RED, bold=True)))
    ws.cell(s_tot + 1, 1, "USD = (avg − our fixing) × factor × MT priced: what fixing at the window's average instead "
                          "would have cost (+ = we saved). Click a contract to jump to its days.").font = \
        Font(italic=True, size=9, color="555555")
    ws.freeze_panes = "B5"
    return {"cache": C, "blocks": blocks, "summary": summary}
