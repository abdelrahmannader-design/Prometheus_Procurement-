"""Inventory vs Market workbook that reads top to bottom instead of across 52 columns.

``rows`` are the app's remaining-FIFO-stock rows (one per lot: an import contract, a local
purchase or a physical adjustment) with every cost component of the lot and of importing the
same goods again today. The first sheet shows

* an overview: one line per lot — tonnes in stock, our cost, the local price today, what
  importing again today would cost, and the two differences per tonne and in total;
* under it, one card per lot: a cost ladder with our FIFO cost and today's import cost side by
  side, step by step (CIF, FX, freight, VAT, intake, clearance), then the comparison with local.

Our cost sits in the same column in the overview and in every card, and so does today's import
cost, so a figure can be followed straight down. Inputs are values (yellow); every total and
difference is a formula with its result stored. The second sheet keeps the original wide table.
"""
from __future__ import annotations

import datetime as dt

NAVY, GREEN, RED, GREY = "1F3A5F", "1A7A1A", "B3261E", "6B7280"
INPUT_FILL, HEAD_FILL, TOTAL_FILL, CARD_FILL = "FFFBEA", "DCE6F2", "E8EEF6", "F4F6FA"
F0, F2, F4 = "#,##0;-#,##0", "#,##0.00;-#,##0.00", "0.0000"
S0, S2 = "[>=0.5]+#,##0;[<=-0.5]-#,##0;0", "[>=0.005]+#,##0.00;[<=-0.005]-#,##0.00;0.00"
SHEETS = ("Inventory vs Market", "All columns")
SOURCE = {"IMPORT_CONTRACT": "Import", "LOCAL_PURCHASE": "Local purchase", "ADJUSTMENT": "Adjustment"}

WIDE_HEADS = [
    "Source", "Ref", "Supplier", "Commodity", "Origin", "Status", "Pricing", "Remaining MT",
    "FIFO CIF USD/MT", "FIFO FX EGP/USD", "FIFO CIF EGP/MT", "Freight Mode", "FIFO Freight Base EGP/MT",
    "FIFO Freight VAT %", "FIFO Freight VAT EGP/MT", "FIFO Freight incl VAT EGP/MT",
    "FIFO Intake Type", "Selected Intake / Discharge EGP/MT", "Clearance EGP/MT", "Total FIFO Expenses EGP/MT",
    "FIFO Cost Check EGP/MT", "FIFO Cost EGP/MT", "FIFO Cost Basis / Formula",
    "Live CBOT", "Premium", "Conversion Factor", "Replacement CIF USD/MT", "FX Today EGP/USD",
    "Replacement CIF EGP/MT", "Freight Base Today EGP/MT", "Freight VAT % Today", "Freight VAT Today EGP/MT",
    "Freight Today incl VAT EGP/MT", "Intake Type Today", "Direct Intake Rate Today EGP/MT",
    "Indirect Intake Rate Today EGP/MT", "Selected Intake Today EGP/MT", "Clearance Today EGP/MT",
    "Total Replacement Expenses EGP/MT", "CBOT Replacement EGP/MT", "Replacement Cost Check EGP/MT",
    "CIF Formula / Live CBOT", "Local Purchase Base EGP/MT", "Local Transport EGP/MT",
    "Current Local EGP/MT", "Edge vs Local EGP/MT", "Total Edge vs Local EGP",
    "Edge vs CBOT EGP/MT", "Total Edge vs CBOT EGP", "Decision", "Local Price Date", "Warnings"]
WIDE_GROUPS = [(1, 8, "POSITION", "1F4E78"), (9, 23, "FIFO / HISTORICAL COST BREAKDOWN", "203864"),
               (24, 42, "TODAY'S IMPORT REPLACEMENT BREAKDOWN", "5B2C6F"), (43, 44, "LOCAL PURCHASE COST", "548235"),
               (45, 52, "MARKET COMPARISON", "A64B00")]


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _sum(*xs):
    return sum(x or 0.0 for x in xs)


def vs_local_words(edge):
    if edge is None:
        return ""
    return "Our stock is cheaper than local" if edge >= 0 else "Local is cheaper than our stock"


def vs_import_words(edge):
    if edge is None:
        return ""
    return "Our stock is cheaper than importing today" if edge >= 0 else "Importing today is cheaper than our stock"


def short_words(e_loc, e_imp):
    """The overview's one-line reading of a lot."""
    a = "" if e_loc is None else ("Cheaper than local" if e_loc >= 0 else "Local is cheaper")
    b = "" if e_imp is None else ("cheaper than importing today" if e_imp >= 0 else "importing today is cheaper")
    return a + (" · " if a and b else "") + b


def ladder(r):
    """The cost steps of one lot: [(key, label, our value, today's value, note)] and which keys add up.

    ``our``/``today`` are numbers (inputs), the string "calc" (worked out from the steps above) or None.
    """
    src = r.get("source_type")
    g = lambda k: _n(r.get(k))
    steps = []
    has_today = None not in (g("live_cbot"), g("premium"), g("conversion_factor"))
    cbot_note = str(r.get("formula") or "")
    if src == "IMPORT_CONTRACT":
        has_our = None not in (g("fifo_cif_usd"), g("fifo_fx"))
        # a lot that is not priced yet is carried at today's CBOT + its premium: show those steps on our side too
        live = (r.get("fifo_cost_basis") == "live" and has_today and g("fifo_cif_usd") is not None
                and abs(g("fifo_cif_usd") - (g("live_cbot") + g("premium")) * g("conversion_factor")) < 0.005)
        steps += [("cbot", "CBOT", g("live_cbot") if live else None, g("live_cbot"), "today's live CBOT"),
                  ("prem", "+ Premium", g("premium") if live else None, g("premium"), ""),
                  ("factor", "× Factor to USD/MT", g("conversion_factor") if live else None, g("conversion_factor"), ""),
                  ("cif", "→ CIF USD/MT", "calc" if live else g("fifo_cif_usd"), "calc" if has_today else g("replacement_cif"),
                   "ours: not priced yet, so carried at live CBOT + premium" if live else "ours: the contract CIF"),
                  ("fx", "× FX EGP/USD", g("fifo_fx"), g("fx_today"), "our FX against today's market FX"),
                  ("cif_egp", "→ CIF EGP/MT", "calc" if has_our else None,
                   "calc" if g("fx_today") is not None and (has_today or g("replacement_cif") is not None) else None, ""),
                  ("frt", "+ Inland freight", g("fifo_freight_base"), g("replacement_freight_base"),
                   f"freight mode {r.get('fifo_freight_mode')}" if r.get("fifo_freight_mode") else ""),
                  ("vat", "+ VAT on freight", g("fifo_freight_vat"),
                   "calc" if None not in (g("replacement_freight_base"), g("replacement_freight_vat_pct")) else g("replacement_freight_vat"),
                   (f"{g('replacement_freight_vat_pct'):g}% of the freight" if g("replacement_freight_vat_pct") is not None else "")),
                  ("intake", "+ Intake / discharge", g("fifo_selected_intake"), g("replacement_selected_intake"),
                   " · ".join(x for x in (f"our intake: {r.get('fifo_intake_mode')}" if r.get("fifo_intake_mode") else "",
                                          f"today: {r.get('replacement_intake_mode')}" if r.get("replacement_intake_mode") else "") if x)),
                  ("clr", "+ Clearance", g("fifo_clearance"), g("replacement_clearance"), "")]
        add = ("cif_egp", "frt", "vat", "intake", "clr")
        our_ok = has_our
    elif src == "LOCAL_PURCHASE":
        steps += [("cbot", "CBOT", None, g("live_cbot"), "today's live CBOT"),
                  ("prem", "+ Premium", None, g("premium"), "portfolio premium"),
                  ("factor", "× Factor to USD/MT", None, g("conversion_factor"), ""),
                  ("cif", "→ CIF USD/MT", None, "calc" if has_today else g("replacement_cif"), ""),
                  ("fx", "× FX EGP/USD", None, g("fx_today"), "today's market FX"),
                  ("cif_egp", "→ CIF EGP/MT", None,
                   "calc" if g("fx_today") is not None and (has_today or g("replacement_cif") is not None) else None, ""),
                  ("fees", "+ Freight, intake and clearance today", None, g("replacement_total_expenses"), ""),
                  ("lbase", "Local purchase price", g("local_purchase_base"), None, "what we paid the local supplier"),
                  ("ltrans", "+ Local transport", g("local_purchase_transport"), None, "")]
        add = ("cif_egp", "fees", "lbase", "ltrans")
        our_ok = g("local_purchase_base") is not None
    else:
        add, our_ok = (), False
    return steps, add, our_ok, cbot_note


def write_workbook(rows, path, as_of=None, commodity="ALL", status="ALL"):
    """Write the workbook; returns the counts written."""
    from openpyxl import Workbook
    from openpyxl.formatting.rule import CellIsRule, FormulaRule
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter as L

    from .xlsx_cache import store_formula_results

    rows = [r for r in rows or [] if isinstance(r, dict)]
    as_of = as_of or dt.date.today().isoformat()
    wb = Workbook()
    ws = wb.active
    ws.title = SHEETS[0]
    cache = {}
    thin = Side(style="thin", color="C9D3E0")

    def put(w, r, c, v, fmt=None, bold=False, color=None, fill=None, italic=False, size=None, inp=False, wrap=False,
            align=None):
        cell = w.cell(r, c, v)
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

    def f(w, r, c, formula, value, fmt=None, **kw):
        put(w, r, c, formula, fmt, **kw)
        cache.setdefault(w.title, {})[f"{L(c)}{r}"] = "" if value is None else value

    def heads(w, r, labels, height=44, fill=HEAD_FILL):
        for i, h in enumerate(labels, start=1):
            c = put(w, r, i, h, bold=True, fill=fill, wrap=True, align="center")
            c.border = Border(bottom=thin)
        w.row_dimensions[r].height = height

    def signs(w, ref):
        w.conditional_formatting.add(ref, CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        w.conditional_formatting.add(ref, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))

    isn = lambda *cells: "AND(" + ",".join(f"ISNUMBER({c})" for c in cells) + ")"

    # columns: A label · B MT · C our cost · D local · E local − ours · F total · G import today · H today − ours · I total · J words
    for i, wdt in enumerate([40, 12, 16, 15, 14, 16, 16, 14, 16, 46], start=1):
        ws.column_dimensions[L(i)].width = wdt
    put(ws, 1, 1, "Inventory vs Market — what our stock cost, against local and importing again today", bold=True, size=15,
        color=NAVY)
    put(ws, 2, 1, f"As of {as_of} · commodity {commodity} · status {status} · EGP per tonne unless it says total · "
                  "yellow = input, everything else is a formula", italic=True, color=GREY)
    notes = [
        "Our cost (FIFO) = what the tonnes still in stock cost us, frozen when they were bought. "
        "Local today = the current local price delivered. Import again today = the same goods bought today at today's "
        "CBOT, premium and FX with today's freight and fees.",
        "A difference is always the alternative minus our cost: POSITIVE (green) = our stock is cheaper than that "
        "alternative; NEGATIVE (red) = that alternative is cheaper than what we hold. Each lot's figures are worked "
        "out step by step in its card below; our cost stays in column C and today's import cost in column G.",
    ]
    for i, tx in enumerate(notes):
        ws.merge_cells(start_row=3 + i, start_column=1, end_row=3 + i, end_column=10)
        put(ws, 3 + i, 1, tx, italic=True, color=GREY, wrap=True)
        ws.row_dimensions[3 + i].height = 30

    hr = 6
    heads(ws, hr, ["Lot (contract / purchase)", "In stock MT", "Our cost (FIFO)", "Local today", "Local − our cost",
                   "Total vs local EGP", "Import again today", "Import today − our cost", "Total vs importing EGP",
                   "In words"])
    first = hr + 1
    n = len(rows)
    total_row = first + n
    r = total_row + 3                        # the first card starts here
    refs = []
    for r_ in rows:
        src = r_.get("source_type")
        g = lambda k: _n(r_.get(k))
        steps, add, our_ok, cbot_note = ladder(r_)
        mt = g("remaining_mt")
        top = r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
        bits = [str(r_.get("ref") or ""), str(r_.get("supplier") or ""), str(r_.get("commodity") or ""),
                str(r_.get("origin") or ""), SOURCE.get(src, str(src or "")), str(r_.get("status") or ""),
                str(r_.get("pricing_status") or "")]
        c = put(ws, r, 1, "  ·  ".join(b for b in bits if b), bold=True, color="FFFFFF", fill=NAVY, size=11)
        c.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20
        heads(ws, r + 1, ["Step", "In stock MT", "Our cost (FIFO)", None, None, None, "Import again today",
                          "Today − ours", None, "Note"], height=30)
        r += 2
        put(ws, r, 1, "Tonnes still in stock", bold=True)
        put(ws, r, 2, mt, F0, inp=True, bold=True)
        mt_row = r
        r += 1
        at, vals = {}, {}
        for key, label, our, today, note in steps:
            at[key] = r
            put(ws, r, 1, label, bold=label.startswith("→"))
            fmt = F4 if key in ("fx", "factor") else F2
            for col, v, side in ((3, our, "o"), (7, today, "t")):
                cl = L(col)
                if v == "calc":
                    if key == "cif":
                        val = (vals[("cbot", side)] + vals[("prem", side)]) * vals[("factor", side)]
                        f(ws, r, col, f'=IF({isn(f"{cl}{at["cbot"]}", f"{cl}{at["prem"]}", f"{cl}{at["factor"]}")},'
                                      f'({cl}{at["cbot"]}+{cl}{at["prem"]})*{cl}{at["factor"]},"")', val, fmt, bold=True)
                    elif key == "cif_egp":
                        a, b = vals.get(("cif", side)), vals.get(("fx", side))
                        val = a * b if None not in (a, b) else None
                        f(ws, r, col, f'=IF({isn(f"{cl}{at["cif"]}", f"{cl}{at["fx"]}")},{cl}{at["cif"]}*{cl}{at["fx"]},"")',
                          val, fmt, bold=True)
                    else:                                           # VAT on today's freight
                        pct = g("replacement_freight_vat_pct")
                        val = vals[("frt", side)] * pct / 100.0
                        f(ws, r, col, f'=IF(ISNUMBER({cl}{at["frt"]}),{cl}{at["frt"]}*{pct:g}/100,"")', val, fmt)
                    vals[(key, side)] = val
                else:
                    put(ws, r, col, v, fmt, inp=True)
                    vals[(key, side)] = v
            o, t = vals.get((key, "o")), vals.get((key, "t"))
            if None not in (o, t):
                f(ws, r, 8, f'=IF({isn(f"C{r}", f"G{r}")},G{r}-C{r},"")', t - o,
                  "[>=0.00005]+0.0000;[<=-0.00005]-0.0000;0.0000" if key in ("fx", "factor") else S2, color=GREY)
            if note:
                put(ws, r, 10, note, italic=True, color=GREY, wrap=True)
            r += 1
        cost = r
        put(ws, r, 1, "→ COST EGP/MT", bold=True)
        rec_our, rec_today = g("fifo_cost"), g("replacement_cost")
        parts_o = [f"N(C{at[k]})" for k in add if k in at and vals.get((k, "o")) is not None]
        parts_t = [f"N(G{at[k]})" for k in add if k in at and vals.get((k, "t")) is not None]
        if our_ok and parts_o:
            our_cost = _sum(*[vals.get((k, "o")) for k in add])
            f(ws, r, 3, "=" + "+".join(parts_o), our_cost, F2, bold=True)
        else:                                      # the lot's breakdown is not stored: its recorded cost is the input
            our_cost = rec_our
            put(ws, r, 3, rec_our, F2, inp=True, bold=True)
        today_ok = vals.get(("cif_egp", "t")) is not None
        if today_ok and parts_t:
            today_cost = _sum(*[vals.get((k, "t")) for k in add])
            f(ws, r, 7, "=" + "+".join(parts_t), today_cost, F2, bold=True)
        else:
            today_cost = rec_today
            put(ws, r, 7, rec_today, F2, inp=rec_today is not None, bold=True)
        e_imp = today_cost - our_cost if None not in (today_cost, our_cost) else None
        f(ws, r, 8, f'=IF({isn(f"C{r}", f"G{r}")},G{r}-C{r},"")', e_imp, S2, bold=True)
        f(ws, r, 9, f'=IF({isn(f"H{r}", f"B{mt_row}")},H{r}*B{mt_row},"")',
          e_imp * mt if None not in (e_imp, mt) else None, S0, bold=True)
        f(ws, r, 10, f'=IF(ISNUMBER(H{r}),IF(H{r}>=0,"{vs_import_words(1)}","{vs_import_words(-1)}"),"")',
          vs_import_words(e_imp), bold=True)
        for cc in range(1, 11):
            ws.cell(r, cc).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        r += 1
        # the figure the app holds for this lot, to show the steps add up to it
        chk = r
        put(ws, r, 1, "Recorded in the app (check)", italic=True, color=GREY)
        put(ws, r, 3, rec_our, F2).font = Font(italic=True, color=GREY)
        put(ws, r, 7, rec_today, F2).font = Font(italic=True, color=GREY)
        gap = [None not in (x, y) and abs(x - y) > 0.01 for x, y in ((our_cost, rec_our), (today_cost, rec_today))]
        if any(gap):
            put(ws, r, 10, "The steps do not add up to the figure recorded in the app: check this lot.", color=RED, bold=True)
        r += 1
        loc_row = r
        local, ldate = g("local"), str(r_.get("local_date") or "")
        put(ws, r, 1, "Local price today, delivered" + (f" ({ldate})" if ldate else ""), bold=True)
        put(ws, r, 4, local, F2, inp=True, bold=True)
        e_loc = local - our_cost if None not in (local, our_cost) else None
        f(ws, r, 5, f'=IF({isn(f"D{r}", f"C{cost}")},D{r}-C{cost},"")', e_loc, S2, bold=True)
        f(ws, r, 6, f'=IF({isn(f"E{r}", f"B{mt_row}")},E{r}*B{mt_row},"")',
          e_loc * mt if None not in (e_loc, mt) else None, S0, bold=True)
        f(ws, r, 10, f'=IF(ISNUMBER(E{r}),IF(E{r}>=0,"{vs_local_words(1)}","{vs_local_words(-1)}"),"")',
          vs_local_words(e_loc), bold=True)
        for cc in range(1, 11):
            ws.cell(r, cc).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        r += 1
        extra = [x for x in (cbot_note and f"Today's CIF: {cbot_note}", str(r_.get("fifo_cost_formula") or "") and
                             f"Our cost: {r_.get('fifo_cost_formula')}", " | ".join(r_.get("issues") or [])) if x]
        for tx in extra:
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=10)
            put(ws, r, 1, tx, italic=True, color=GREY, wrap=True)
            ws.row_dimensions[r].height = 15 * max(1, -(-len(tx) // 190))
            r += 1
        signs(ws, f"E{loc_row}:F{loc_row}"); signs(ws, f"H{cost}:I{cost}")
        ws.conditional_formatting.add(f"J{cost}:J{loc_row}", FormulaRule(formula=[f'LEFT($J{cost},9)="Our stock"'],
                                                                           font=Font(color=GREEN, bold=True)))
        ws.conditional_formatting.add(f"J{cost}:J{loc_row}", FormulaRule(
            formula=[f'AND($J{cost}<>"",LEFT($J{cost},9)<>"Our stock",LEFT($J{cost},9)<>"The steps")'],
            font=Font(color=RED, bold=True)))
        refs.append({"r": r_, "top": top, "mt": mt_row, "cost": cost, "loc": loc_row, "our": our_cost, "today": today_cost,
                     "local": local, "e_loc": e_loc, "e_imp": e_imp, "qty": mt})
        r += 1

    # the overview reads the cards
    for i, x in enumerate(refs):
        q, r_ = first + i, x["r"]
        c = put(ws, q, 1, str(r_.get("ref") or ""), bold=True, color="1F5FBF")
        c.hyperlink = f"#'{SHEETS[0]}'!A{x['top']}"
        c.font = Font(bold=True, color="1F5FBF", underline="single")
        qty = x["qty"]
        f(ws, q, 2, f"=B{x['mt']}", qty, F0)
        f(ws, q, 3, f'=IF(ISNUMBER(C{x["cost"]}),C{x["cost"]},"")', x["our"], F2, bold=True)
        f(ws, q, 4, f'=IF(ISNUMBER(D{x["loc"]}),D{x["loc"]},"")', x["local"], F2)
        f(ws, q, 5, f'=IF(ISNUMBER(E{x["loc"]}),E{x["loc"]},"")', x["e_loc"], S2)
        f(ws, q, 6, f'=IF(ISNUMBER(F{x["loc"]}),F{x["loc"]},"")', x["e_loc"] * qty if None not in (x["e_loc"], qty) else None, S0)
        f(ws, q, 7, f'=IF(ISNUMBER(G{x["cost"]}),G{x["cost"]},"")', x["today"], F2, bold=True)
        f(ws, q, 8, f'=IF(ISNUMBER(H{x["cost"]}),H{x["cost"]},"")', x["e_imp"], S2)
        f(ws, q, 9, f'=IF(ISNUMBER(I{x["cost"]}),I{x["cost"]},"")', x["e_imp"] * qty if None not in (x["e_imp"], qty) else None, S0)
        f(ws, q, 10, f'=IF(ISNUMBER(E{q}),IF(E{q}>=0,"Cheaper than local","Local is cheaper"),"")'
                     f'&IF(AND(ISNUMBER(E{q}),ISNUMBER(H{q}))," · ","")'
                     f'&IF(ISNUMBER(H{q}),IF(H{q}>=0,"cheaper than importing today","importing today is cheaper"),"")',
          short_words(x["e_loc"], x["e_imp"]), wrap=True)
    if refs:
        last = first + n - 1
        tq = total_row
        mts = sum(x["qty"] or 0 for x in refs)
        wavg = lambda k: (sum(x[k] * (x["qty"] or 0) for x in refs if x[k] is not None)
                          / sum(x["qty"] or 0 for x in refs if x[k] is not None)) if any(x[k] is not None and x["qty"] for x in refs) else None
        tot = lambda k: sum(x[k] * (x["qty"] or 0) for x in refs if x[k] is not None and x["qty"])
        put(ws, tq, 1, "All lots — total / average per tonne", bold=True)
        f(ws, tq, 2, f"=SUM(B{first}:B{last})", mts, F0, bold=True)
        for col, k in ((3, "our"), (4, "local"), (7, "today")):
            cl = L(col)
            f(ws, tq, col, f'=IFERROR(SUMPRODUCT(B{first}:B{last},{cl}{first}:{cl}{last})/SUMPRODUCT(--ISNUMBER({cl}{first}:{cl}{last}),B{first}:B{last}),"")',
              wavg(k), F2, bold=True)
        f(ws, tq, 6, f"=SUM(F{first}:F{last})", tot("e_loc"), S0, bold=True)
        f(ws, tq, 9, f"=SUM(I{first}:I{last})", tot("e_imp"), S0, bold=True)
        f(ws, tq, 5, f'=IF(B{tq}<>0,F{tq}/B{tq},"")', tot("e_loc") / mts if mts else None, S2, bold=True)
        f(ws, tq, 8, f'=IF(B{tq}<>0,I{tq}/B{tq},"")', tot("e_imp") / mts if mts else None, S2, bold=True)
        for cc in range(1, 11):
            ws.cell(tq, cc).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        signs(ws, f"E{first}:F{tq}"); signs(ws, f"H{first}:I{tq}")
    else:
        put(ws, first, 1, "No remaining FIFO stock matches these filters.", italic=True, color=GREY)
    ws.freeze_panes = f"B{hr + 1}"
    ws.sheet_view.showGridLines = False

    # ── the original wide table, with the results of its check formulas stored ──
    w2 = wb.create_sheet(SHEETS[1])
    w2.sheet_view.showGridLines = False
    put(w2, 1, 1, "Inventory vs Market — every column (the original layout)", bold=True, size=15, color="17365D")
    for i, v in enumerate(["As of", as_of, "Commodity", commodity, "Status", status], start=1):
        put(w2, 2, i, v)
    put(w2, 3, 1, "Audit note"); put(w2, 3, 2, "Historical FIFO cost and today's replacement cost are shown separately. "
                                               "Every freight/intake expense is exposed as a numeric field.", italic=True, color="666666")
    for c1, c2, label, color in WIDE_GROUPS:
        w2.merge_cells(start_row=4, start_column=c1, end_row=4, end_column=c2)
        for cc in range(c1, c2 + 1):
            w2.cell(4, cc).fill = PatternFill("solid", fgColor=color)
        put(w2, 4, c1, label, bold=True, color="FFFFFF", fill=color, align="center")
    for i, h in enumerate(WIDE_HEADS, start=1):
        c = put(w2, 5, i, h, bold=True, color="17365D", fill="D9EAF7", wrap=True, align="center")
        c.border = Border(bottom=thin)
    w2.row_dimensions[4].height = 24; w2.row_dimensions[5].height = 48
    money = {8, 11, 13, 15, 16, 18, 19, 20, 21, 22, 29, 30, 32, 33, 35, 36, 37, 38, 39, 40, 41, 43, 44, 45, 46, 47, 48, 49}
    four = {9, 10, 26, 27, 28}
    for i, r_ in enumerate(rows):
        q = 6 + i
        g = lambda k: _n(r_.get(k))
        vals = [SOURCE.get(r_.get("source_type"), r_.get("source_type") or "").upper(), r_.get("ref"), r_.get("supplier"),
                r_.get("commodity"), r_.get("origin"), r_.get("status"), r_.get("pricing_status"), g("remaining_mt"),
                g("fifo_cif_usd"), g("fifo_fx"), None, r_.get("fifo_freight_mode"), g("fifo_freight_base"),
                g("fifo_freight_vat_pct"), g("fifo_freight_vat"), g("fifo_freight_incl_vat"), r_.get("fifo_intake_mode"),
                g("fifo_selected_intake"), g("fifo_clearance"), None, None, g("fifo_cost"), r_.get("fifo_cost_formula"),
                g("live_cbot"), g("premium"), g("conversion_factor"), g("replacement_cif"), g("fx_today"), None,
                g("replacement_freight_base"), g("replacement_freight_vat_pct"), None, None,
                r_.get("replacement_intake_mode"), g("replacement_direct_intake"), g("replacement_indirect_intake"),
                g("replacement_selected_intake"), g("replacement_clearance"), None, g("replacement_cost"), None,
                r_.get("formula"), g("local_purchase_base"), g("local_purchase_transport"), g("local"), g("edge_local_mt"),
                g("edge_local_total"), g("edge_repl_mt"), g("edge_repl_total"), r_.get("decision"), r_.get("local_date"),
                " | ".join(r_.get("issues") or [])]
        for j, v in enumerate(vals, start=1):
            if v is None:
                continue
            put(w2, q, j, v, "#,##0.00;[Red](#,##0.00);-" if j in money else "0.0000" if j in four else None)
        k_, t_, ac, af, ag, am = None, None, None, None, None, None
        if None not in (g("fifo_cif_usd"), g("fifo_fx")):
            k_ = g("fifo_cif_usd") * g("fifo_fx")
            f(w2, q, 11, f"=I{q}*J{q}", k_, "#,##0.00")
        if any(g(k) is not None for k in ("fifo_freight_incl_vat", "fifo_selected_intake", "fifo_clearance")):
            t_ = _sum(g("fifo_freight_incl_vat"), g("fifo_selected_intake"), g("fifo_clearance"))
            f(w2, q, 20, f"=P{q}+R{q}+S{q}", t_, "#,##0.00")
        if None not in (k_, t_):
            f(w2, q, 21, f"=K{q}+T{q}", k_ + t_, "#,##0.00")
        if None not in (g("replacement_cif"), g("fx_today")):
            ac = g("replacement_cif") * g("fx_today")
            f(w2, q, 29, f"=AA{q}*AB{q}", ac, "#,##0.00")
        if None not in (g("replacement_freight_base"), g("replacement_freight_vat_pct")):
            af = g("replacement_freight_base") * g("replacement_freight_vat_pct") / 100.0
            ag = g("replacement_freight_base") + af
            f(w2, q, 32, f"=AD{q}*AE{q}/100", af, "#,##0.00"); f(w2, q, 33, f"=AD{q}+AF{q}", ag, "#,##0.00")
        else:
            put(w2, q, 32, g("replacement_freight_vat"), "#,##0.00"); put(w2, q, 33, g("freight_today"), "#,##0.00")
            ag = g("freight_today")
        if any(x is not None for x in (ag, g("replacement_selected_intake"), g("replacement_clearance"))):
            am = _sum(ag, g("replacement_selected_intake"), g("replacement_clearance"))
            f(w2, q, 39, f"=AG{q}+AK{q}+AL{q}", am, "#,##0.00")
        if None not in (ac, am):
            f(w2, q, 41, f"=AC{q}+AM{q}", ac + am, "#,##0.00")
    widths = {1: 14, 2: 22, 3: 18, 4: 14, 5: 12, 6: 12, 7: 12, 8: 12, 22: 16, 23: 46, 42: 30, 50: 26, 51: 13, 52: 60}
    for i in range(1, len(WIDE_HEADS) + 1):
        w2.column_dimensions[L(i)].width = widths.get(i, 16)
    w2.freeze_panes = "C6"
    if rows:
        w2.auto_filter.ref = f"A5:{L(len(WIDE_HEADS))}{5 + len(rows)}"

    for s in wb.worksheets:
        s.page_setup.orientation = "landscape"
        s.page_setup.paperSize = s.PAPERSIZE_A4
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth, s.page_setup.fitToHeight = 1, 0
        s.oddFooter.center.text = "&A · page &P of &N"
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, cache)
    return {"lots": len(refs), "mt": sum(x["qty"] or 0 for x in refs),
            "vs_local_egp": sum(x["e_loc"] * (x["qty"] or 0) for x in refs if x["e_loc"] is not None),
            "vs_import_egp": sum(x["e_imp"] * (x["qty"] or 0) for x in refs if x["e_imp"] is not None),
            "formulas": sum(len(v) for v in cache.values())}
