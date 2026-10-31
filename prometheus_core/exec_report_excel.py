"""Excel workbook for the Executive Import Savings Dashboard.

Seven sheets, management summary first and the arithmetic behind it after.
Every figure on the summary is a formula over the sheets that follow, and
every contract figure a formula over its daily consumption rows, so a
number can be traced from the first page down to the day it came from.
Each formula's result is also stored in the file, so it reads correctly in
viewers that do not calculate.
"""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .exec_savings import REALIZED
from .xlsx_cache import store_formula_results

EXEC_EXCEL_VERSION = "1.0"

SHEETS = ("Executive Management Summary", "Historical Savings by Commodity",
          "Historical Savings by Contract", "Open Contracts vs Local Today",
          "Daily Consumption Savings", "CBOT Fixing vs Consumption",
          "Detailed Calculations & Sources")
NAVY, GREEN, RED, GREY = "1F3A5F", "1A7A1A", "B3261E", "7A7A7A"
M0, M2, PCT = "#,##0;[Red]-#,##0", "#,##0.00;[Red]-#,##0.00", "0.0%;[Red]-0.0%"


def q(title):
    return "'" + title.replace("'", "''") + "'"


def blank(v):
    return "" if v is None else v


class Book:
    def __init__(self):
        self.wb = Workbook()
        self.cache = {}
        self.wb.active.title = SHEETS[0]
        for s in SHEETS[1:]:
            self.wb.create_sheet(s)

    def ws(self, i):
        return self.wb[SHEETS[i]]

    def put(self, ws, r, c, v, fmt=None, bold=False, color=None, fill=None, size=None,
            italic=False, wrap=False):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        if bold or color or size or italic:
            cell.font = Font(bold=bold, color=color, size=size, italic=italic)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        if wrap:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        return cell

    def f(self, ws, r, c, formula, value, fmt=None, bold=False):
        cell = self.put(ws, r, c, formula, fmt, bold)
        self.cache.setdefault(ws.title, {})[cell.coordinate] = "" if value is None else value
        return cell

    def head(self, ws, r, cols, start=1):
        for i, (label, width) in enumerate(cols):
            c = ws.cell(r, start + i, label)
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=NAVY)
            c.alignment = Alignment(wrap_text=True, horizontal="center", vertical="center")
            ws.column_dimensions[get_column_letter(start + i)].width = width
        ws.row_dimensions[r].height = 36

    def title(self, ws, text, sub):
        self.put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        self.put(ws, 2, 1, sub, italic=True, color=GREY)

    def signs(self, ws, rng):
        ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThan", formula=["0"],
                                                      font=Font(color=GREEN)))
        ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["0"],
                                                      font=Font(color=RED)))


def build_workbook(model, path):
    b = Book()
    contracts = model["contracts"]
    _daily(b, model)
    _by_contract(b, model)
    _open(b, model)
    _cbot(b, model)
    _by_commodity(b, model)
    _sources(b, model)
    _summary(b, model)
    _print_setup(b)
    b.wb.calculation.fullCalcOnLoad = True
    b.wb.save(path)
    return store_formula_results(path, b.cache)


def _print_setup(b):
    """Landscape, one page wide, headings repeated on every printed page."""
    for ws in b.wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.page_margins.left = ws.page_margins.right = 0.4
        ws.page_margins.top = ws.page_margins.bottom = 0.5
        ws.print_options.horizontalCentered = True
        top = ws.freeze_panes
        if top and ws.title != SHEETS[0]:
            row = int("".join(ch for ch in top if ch.isdigit())) - 1
            if row >= 1:
                ws.print_title_rows = f"{row}:{row}"
        ws.oddFooter.center.text = "&A · page &P of &N"


# ── 5. Daily Consumption Savings ─────────────────────────────────────────
DAILY_FIRST = 5


def _daily_rows(model):
    out = []
    for c in model["contracts"]:
        h = c.get("history") or {}
        fix = (c.get("fixing") or {})
        fixing = fix.get("value") if fix.get("usable") else None
        for d in h.get("daily") or []:
            out.append((c, d, fixing))
    return out


def _daily(b, model):
    ws = b.ws(4)
    b.title(ws, "Daily Consumption Savings",
            "Every consumed tonne of every import contract, on the day it was consumed (FIFO). "
            "Saving = local price that day − the contract's landed cost. CBOT advantage = CBOT that "
            "day − the contract's fixing, × factor — a benchmark, not added to the saving.")
    b.head(ws, 4, [("Date", 11), ("ID", 8), ("Contract", 22), ("Base", 8), ("MT", 9),
                   ("Landed EGP/MT", 11), ("Local EGP/MT", 11), ("Local observed on", 11),
                   ("Local price of", 10), ("Saving EGP/MT", 11), ("Saving EGP", 13),
                   ("Tonnes", 9), ("CBOT that day", 10), ("CBOT observed on", 11),
                   ("Contract CBOT fixing", 10), ("CBOT difference", 10), ("Factor", 8),
                   ("Advantage USD/MT", 10), ("Advantage USD", 12), ("FX", 8), ("Advantage EGP", 13)])
    rows = _daily_rows(model)
    for i, (c, d, fixing) in enumerate(rows):
        r = DAILY_FIRST + i
        b.put(ws, r, 1, d["date"]); b.put(ws, r, 2, c["id"]); b.put(ws, r, 3, c["contract"])
        b.put(ws, r, 4, c["base"]); b.put(ws, r, 5, d["mt"], M0)
        b.put(ws, r, 6, blank(d.get("cost")), M2); b.put(ws, r, 7, blank(d.get("local")), M2)
        b.put(ws, r, 8, d.get("local_date") or ""); b.put(ws, r, 9, d.get("local_key") or "")
        per = (d["local"] - d["cost"]) if None not in (d.get("local"), d.get("cost")) else None
        b.f(ws, r, 10, f'=IF(OR(F{r}="",G{r}=""),"",G{r}-F{r})', per, M2)
        b.f(ws, r, 11, f'=IF(J{r}="","",J{r}*E{r})', (per * d["mt"]) if per is not None else None, M0)
        b.put(ws, r, 12, d.get("kind") or "")
        has = d.get("cbot") is not None and fixing is not None
        b.put(ws, r, 13, blank(d.get("cbot")) if has else "", M2)
        b.put(ws, r, 14, d.get("cbot_date") or "" if has else "")
        b.put(ws, r, 15, blank(fixing) if has else "", M2)
        b.f(ws, r, 16, f'=IF(OR(M{r}="",O{r}=""),"",M{r}-O{r})', d.get("cbot_diff") if has else None, M2)
        b.put(ws, r, 17, blank(c.get("factor")) if has else "", "0.0000")
        b.f(ws, r, 18, f'=IF(P{r}="","",P{r}*Q{r})', d.get("adv_usd_mt") if has else None, M2)
        b.f(ws, r, 19, f'=IF(R{r}="","",R{r}*E{r})', d.get("adv_usd") if has else None, M0)
        b.put(ws, r, 20, blank(c.get("fx")) if has else "", "0.0000")
        adv_egp = (d["adv_usd"] * c["fx"]) if (has and c.get("fx")) else None
        b.f(ws, r, 21, f'=IF(OR(S{r}="",T{r}=""),"",S{r}*T{r})', adv_egp, M0)
    last = DAILY_FIRST + len(rows) - 1
    b.signs(ws, f"J{DAILY_FIRST}:K{max(last, DAILY_FIRST)}")
    b.signs(ws, f"P{DAILY_FIRST}:U{max(last, DAILY_FIRST)}")
    ws.freeze_panes = "D5"
    ws.auto_filter.ref = f"A4:U{max(last, DAILY_FIRST)}"
    model["_daily_last"] = max(last, DAILY_FIRST)


def _D(col, model):
    return f"{q(SHEETS[4])}!${col}${DAILY_FIRST}:${col}${model['_daily_last']}"


# ── 3. Historical Savings by Contract ────────────────────────────────────
HC_FIRST = 5


def _by_contract(b, model):
    ws = b.ws(2)
    b.title(ws, "Historical Savings by Contract",
            "Consumed tonnes only, valued against the local price on each consumption day. Every "
            "figure sums the contract's rows on Daily Consumption Savings. Realized = final price; "
            "Provisional = CIF not yet final.")
    b.head(ws, 4, [("Commodity", 9), ("Contract No.", 22), ("Supplier", 15), ("ID", 7),
                   ("Contract qty MT", 10), ("Qty consumed MT", 10), ("Priced vs local MT", 10),
                   ("First consumption", 11), ("Last consumption", 11),
                   ("Imported landed cost EGP/MT", 12), ("Wtd avg local during consumption", 12),
                   ("Total historical savings EGP", 14), ("Savings %", 9), ("Savings EGP/MT", 10),
                   ("Kind", 14), ("Local cost EGP (basis for %)", 14), ("Days on a stale quote MT", 10),
                   ("Note", 60)])
    D = lambda col: _D(col, model)
    for i, c in enumerate(model["contracts"]):
        r = HC_FIRST + i
        h = c.get("history") or {}
        k = f"$D{r}"
        b.put(ws, r, 1, c["base"]); b.put(ws, r, 2, c["contract"]); b.put(ws, r, 3, c["supplier"])
        b.put(ws, r, 4, c["id"]); b.put(ws, r, 5, blank(c.get("qty_mt")), M0)
        b.f(ws, r, 6, f"=SUMIFS({D('E')},{D('B')},{k})", h.get("consumed_mt") or 0, M0)
        b.f(ws, r, 7, f'=SUMPRODUCT(({D("B")}={k})*({D("J")}<>"")*{D("E")})', h.get("local_priced_mt") or 0, M0)
        b.put(ws, r, 8, h.get("first_date") or ""); b.put(ws, r, 9, h.get("last_date") or "")
        b.put(ws, r, 10, blank(h.get("landed_egp_mt")), M2)
        b.f(ws, r, 11, f'=IF(G{r}=0,"",SUMPRODUCT(({D("B")}={k})*({D("J")}<>"")*{D("E")}*{D("G")})/G{r})',
            h.get("local_wavg"), M2)
        b.f(ws, r, 12, f'=IF(G{r}=0,"",SUMIFS({D("K")},{D("B")},{k}))', h.get("saving_egp"), M0)
        b.f(ws, r, 16, f'=IF(L{r}="","",K{r}*G{r})',
            (h["local_wavg"] * h["local_priced_mt"]) if h.get("local_wavg") is not None else None, M0)
        b.f(ws, r, 13, f'=IF(OR(L{r}="",P{r}="",P{r}=0),"",L{r}/P{r})',
            (h["saving_pct"] / 100.0) if h.get("saving_pct") is not None else None, PCT)
        b.f(ws, r, 14, f'=IF(L{r}="","",L{r}/G{r})', h.get("saving_egp_mt"), M0)
        b.put(ws, r, 15, c.get("saving_kind"))
        b.put(ws, r, 17, h.get("stale_mt") or 0, M0)
        note = []
        if not h.get("consumed_mt"):
            note.append("nothing consumed yet")
        elif h.get("unpriced_mt"):
            note.append(f"{h['unpriced_mt']:,.0f} MT had no local price on or before the day — comparison unavailable for them")
        if h.get("cost_note"):
            note.append(h["cost_note"])
        b.put(ws, r, 18, "; ".join(note))
    last = HC_FIRST + len(model["contracts"]) - 1
    tot = last + 1
    b.put(ws, tot, 1, "TOTAL", bold=True)
    s = lambda key: sum((c["history"].get(key) or 0) for c in model["contracts"])
    for col, key, fmt in ((6, "consumed_mt", M0), (7, "local_priced_mt", M0), (12, "saving_egp", M0)):
        L = get_column_letter(col)
        b.f(ws, tot, col, f"=SUM({L}{HC_FIRST}:{L}{last})", s(key), fmt, bold=True)
    local_cost = sum((c["history"].get("local_wavg") or 0) * (c["history"].get("local_priced_mt") or 0)
                     for c in model["contracts"])
    b.f(ws, tot, 16, f"=SUM(P{HC_FIRST}:P{last})", local_cost, M0, bold=True)
    b.f(ws, tot, 13, f'=IF(P{tot}=0,"",L{tot}/P{tot})', (s("saving_egp") / local_cost) if local_cost else None, PCT, bold=True)
    b.f(ws, tot, 14, f'=IF(G{tot}=0,"",L{tot}/G{tot})',
        (s("saving_egp") / s("local_priced_mt")) if s("local_priced_mt") else None, M0, bold=True)
    b.signs(ws, f"L{HC_FIRST}:N{tot}")
    ws.freeze_panes = "C5"
    ws.auto_filter.ref = f"A4:R{last}"
    model["_hc_last"] = last


def _HC(col, model):
    return f"{q(SHEETS[2])}!${col}${HC_FIRST}:${col}${model['_hc_last']}"


# ── 4. Open Contracts vs Local Today ─────────────────────────────────────
OP_FIRST = 6


def _open_rows(model):
    return [c for c in model["contracts"]
            if c.get("is_open") or (c["open"]["in_stock_mt"] + c["open"]["outstanding_mt"]) > 0]


def _open(b, model):
    ws = b.ws(3)
    b.title(ws, "Open Contracts vs Local Today",
            "Tonnes not yet consumed, against the latest Egyptian local price. Potential, not realized. "
            "Each contract's quantity is split once: consumed (historical sheet) + in stock + not yet "
            "delivered. Open contracts, plus any closed contract with stock left.")
    b.put(ws, 3, 1, "Landed cost today = CIF × FX + intake/discharge + clearance + inland freight "
                    "(the app's cost engine; customs/other costs only where recorded in those fields).",
          italic=True, color=GREY)
    b.head(ws, 5, [("Commodity", 9), ("Supplier", 15), ("Contract No.", 22), ("ID", 7),
                   ("Open contract?", 8), ("Contract qty MT", 10), ("Delivered MT", 10),
                   ("Consumed MT", 10), ("Delivered, in stock MT", 11), ("Outstanding (not delivered) MT", 12),
                   ("CIF USD/MT", 9), ("CIF basis", 22), ("FX", 8), ("FX basis", 16),
                   ("Landed cost today EGP/MT", 12), ("Local today EGP/MT", 11), ("Local observed on", 11),
                   ("Local price of", 10), ("Potential saving EGP/MT", 11), ("Potential on stock EGP", 13),
                   ("Potential on outstanding EGP", 13), ("Total potential EGP", 14),
                   ("Expected arrival", 11), ("Pricing status", 10), ("Contract value USD", 13),
                   ("Not-yet-consumed value USD", 13)])
    rows = _open_rows(model)
    for i, c in enumerate(rows):
        r = OP_FIRST + i
        o, p = c["open"], c["position"]
        vals = [c["base"], c["supplier"], c["contract"], c["id"], "Yes" if c["is_open"] else "No",
                p["qty_mt"], p["delivered_mt"], p["consumed_mt"], p["in_stock_mt"]]
        for j, v in enumerate(vals):
            b.put(ws, r, 1 + j, v, M0 if j >= 5 else None)
        b.f(ws, r, 10, f"=F{r}-G{r}", p["outstanding_mt"], M0)
        b.put(ws, r, 11, blank(c.get("cif_usd_mt")), M2); b.put(ws, r, 12, c.get("cif_basis"))
        b.put(ws, r, 13, blank(c.get("fx")), "0.0000"); b.put(ws, r, 14, c.get("fx_basis"))
        b.put(ws, r, 15, blank(o.get("landed_today")), M2); b.put(ws, r, 16, blank(o.get("local_today")), M2)
        b.put(ws, r, 17, o.get("local_date") or ""); b.put(ws, r, 18, o.get("local_key") or "")
        per = ((o["local_today"] - o["landed_today"])
               if None not in (o.get("local_today"), o.get("landed_today")) else None)
        b.f(ws, r, 19, f'=IF(OR(O{r}="",P{r}=""),"",P{r}-O{r})', per, M2)
        b.f(ws, r, 20, f'=IF(S{r}="","",S{r}*I{r})', (per * p["in_stock_mt"]) if per is not None else None, M0)
        b.f(ws, r, 21, f'=IF(S{r}="","",S{r}*J{r})', (per * p["outstanding_mt"]) if per is not None else None, M0)
        b.f(ws, r, 22, f'=IF(S{r}="","",T{r}+U{r})',
            (per * (p["in_stock_mt"] + p["outstanding_mt"])) if per is not None else None, M0)
        b.put(ws, r, 23, c.get("delivery_date")); b.put(ws, r, 24, c.get("pricing_status"))
        b.put(ws, r, 25, blank(c.get("contract_value_usd")), M0)
        b.put(ws, r, 26, blank(o.get("open_value_usd")), M0)
    last = max(OP_FIRST + len(rows) - 1, OP_FIRST)
    tot = last + 1
    b.put(ws, tot, 1, "TOTAL", bold=True)
    sm = lambda fn: sum(v for v in (fn(c) for c in rows) if isinstance(v, (int, float)))
    for col, fn, fmt in ((9, lambda c: c["position"]["in_stock_mt"], M0),
                         (10, lambda c: c["position"]["outstanding_mt"], M0),
                         (20, lambda c: c["open"]["stock_saving_egp"] if c["open"].get("saving_egp_mt") is not None else None, M0),
                         (21, lambda c: c["open"]["outstanding_saving_egp"] if c["open"].get("saving_egp_mt") is not None else None, M0),
                         (22, lambda c: (c["open"]["stock_saving_egp"] + c["open"]["outstanding_saving_egp"])
                          if c["open"].get("saving_egp_mt") is not None else None, M0)):
        L = get_column_letter(col)
        b.f(ws, tot, col, f"=SUM({L}{OP_FIRST}:{L}{last})", sm(fn), fmt, bold=True)
    b.signs(ws, f"S{OP_FIRST}:V{tot}")
    ws.freeze_panes = "E6"
    ws.auto_filter.ref = f"A5:Z{last}"
    model["_op_last"] = last
    model["_op_rows"] = rows


def _OP(col, model):
    return f"{q(SHEETS[3])}!${col}${OP_FIRST}:${col}${model['_op_last']}"


# ── 6. CBOT Fixing vs Consumption ────────────────────────────────────────
CB_FIRST = 6


def _cbot(b, model):
    ws = b.ws(5)
    b.title(ws, "CBOT Fixing vs Consumption",
            "The contract's CBOT fixing against the CBOT on each day its tonnes were consumed. "
            "Benchmark-based price advantage — already inside the saving against local, so never added to it.")
    b.put(ws, 3, 1, "Benchmark: the app's stored CBOT history, a rolling front-month series — not the "
                    "contract's own futures month, which has often expired by the time its corn is "
                    "consumed. One-day stray prints are stepped over to the last valid day.",
          italic=True, color=GREY)
    b.head(ws, 5, [("Commodity", 9), ("Contract No.", 22), ("ID", 7), ("Fixing type", 26),
                   ("Futures month", 9), ("Pricing date", 11), ("CIF USD/MT", 9), ("Premium", 9),
                   ("Factor", 8), ("Unit", 10), ("Contract CBOT fixing", 11),
                   ("Possible fixing dates (indicative)", 26), ("Consumed MT with a CBOT", 11),
                   ("Wtd avg CBOT during consumption", 12), ("CBOT difference", 10),
                   ("Pricing advantage USD/MT", 11), ("Total CBOT advantage USD", 13),
                   ("Total CBOT advantage EGP", 14), ("Note", 60)])
    D = lambda col: _D(col, model)
    rows = [c for c in model["contracts"] if (c.get("fixing") or {}).get("value") is not None
            or "flat" not in str((c.get("fixing") or {}).get("flag", ""))]
    for i, c in enumerate(rows):
        r = CB_FIRST + i
        f, h = c.get("fixing") or {}, c.get("history") or {}
        k = f"$C{r}"
        b.put(ws, r, 1, c["base"]); b.put(ws, r, 2, c["contract"]); b.put(ws, r, 3, c["id"])
        b.put(ws, r, 4, f.get("label") or "—"); b.put(ws, r, 5, c.get("futures_month") or "")
        b.put(ws, r, 6, c.get("pricing_date") or ""); b.put(ws, r, 7, blank(c.get("cif_usd_mt")), M2)
        b.put(ws, r, 8, blank(c.get("premium")), M2); b.put(ws, r, 9, blank(c.get("factor")), "0.0000")
        b.put(ws, r, 10, f.get("unit") or "")
        if f.get("value") is not None and f.get("source") != "pricing lots":
            b.f(ws, r, 11, f'=IF(OR(G{r}="",H{r}="",I{r}=""),"",G{r}/I{r}-H{r})', f.get("value"), M2)
        else:
            b.put(ws, r, 11, blank(f.get("value")), M2)
        b.put(ws, r, 12, ", ".join(x["date"] for x in f.get("possible_dates") or []))
        usable = f.get("usable") and h.get("cbot_mt")
        b.f(ws, r, 13, f'=SUMPRODUCT(({D("B")}={k})*({D("M")}<>"")*{D("E")})', h.get("cbot_mt") or 0, M0)
        b.f(ws, r, 14, f'=IF(M{r}=0,"",SUMPRODUCT(({D("B")}={k})*({D("M")}<>"")*{D("E")}*{D("M")})/M{r})',
            h.get("cbot_wavg") if usable else None, M2)
        b.f(ws, r, 15, f'=IF(N{r}="","",N{r}-K{r})', h.get("cbot_diff") if usable else None, M2)
        b.f(ws, r, 16, f'=IF(O{r}="","",O{r}*I{r})', h.get("adv_usd_mt") if usable else None, M2)
        b.f(ws, r, 17, f'=IF(M{r}=0,"",SUMIFS({D("S")},{D("B")},{k}))', h.get("adv_usd") if usable else None, M0)
        b.f(ws, r, 18, f'=IF(M{r}=0,"",SUMIFS({D("U")},{D("B")},{k}))', h.get("adv_egp") if usable else None, M0)
        note = [f.get("flag")] if f.get("flag") else []
        if f.get("possible_dates"):
            note.append("possible dates match the implied fixing on the front-month series — leads to check, not evidence")
        if h.get("cbot_spike_days"):
            note.append(f"{h['cbot_spike_days']} consumption day(s) fell on a stray print and used the last valid day")
        if usable is False or (f.get("value") is not None and not h.get("cbot_mt")):
            note.append("no CBOT comparison")
        b.put(ws, r, 19, "; ".join(n for n in note if n))
    last = max(CB_FIRST + len(rows) - 1, CB_FIRST)
    tot = last + 1
    b.put(ws, tot, 1, "TOTAL", bold=True)
    b.f(ws, tot, 17, f"=SUM(Q{CB_FIRST}:Q{last})", model["kpis"]["cbot_adv_usd"], M0, bold=True)
    b.f(ws, tot, 18, f"=SUM(R{CB_FIRST}:R{last})", model["kpis"]["cbot_adv_egp"], M0, bold=True)
    b.signs(ws, f"O{CB_FIRST}:R{tot}")
    ws.freeze_panes = "D6"
    ws.auto_filter.ref = f"A5:S{last}"
    model["_cb_last"] = last


def _CB(col, model):
    return f"{q(SHEETS[5])}!${col}${CB_FIRST}:${col}${model['_cb_last']}"


# ── 2. Historical Savings by Commodity ───────────────────────────────────
CM_FIRST = 5


def _by_commodity(b, model):
    ws = b.ws(1)
    b.title(ws, "Historical Savings by Commodity",
            "Sums of the contract rows. Historical (consumed) and potential (not yet consumed) cover "
            "different tonnes; the CBOT advantage is a benchmark shown alongside, never added.")
    b.head(ws, 4, [("Commodity", 11), ("Contracts", 9), ("Consumed MT", 11), ("Priced vs local MT", 11),
                   ("Historical savings EGP", 15), ("of which realized", 14), ("of which provisional", 14),
                   ("Savings EGP/MT", 10), ("Savings %", 9), ("Potential (not yet consumed) EGP", 15),
                   ("CBOT advantage USD (benchmark)", 14), ("CBOT advantage EGP (benchmark)", 15)])
    HC, OP, CB = (lambda col: _HC(col, model)), (lambda col: _OP(col, model)), (lambda col: _CB(col, model))
    for i, cm in enumerate(model["commodities"]):
        r = CM_FIRST + i
        k = f"$A{r}"
        b.put(ws, r, 1, cm["base"])
        b.f(ws, r, 2, f"=COUNTIF({HC('A')},{k})", cm["contracts"], "0")
        b.f(ws, r, 3, f"=SUMIFS({HC('F')},{HC('A')},{k})", cm["consumed_mt"], M0)
        b.f(ws, r, 4, f"=SUMIFS({HC('G')},{HC('A')},{k})", cm["local_priced_mt"], M0)
        b.f(ws, r, 5, f"=SUMIFS({HC('L')},{HC('A')},{k})", cm["historical_saving_egp"], M0)
        b.f(ws, r, 6, f'=SUMIFS({HC("L")},{HC("A")},{k},{HC("O")},"{REALIZED}")', cm["realized_saving_egp"], M0)
        b.f(ws, r, 7, f"=E{r}-F{r}", cm["provisional_saving_egp"], M0)
        b.f(ws, r, 8, f'=IF(D{r}=0,"",E{r}/D{r})', cm["historical_saving_egp_mt"], M0)
        local_cost = cm["local_cost_egp"]
        b.f(ws, r, 9, f'=IF(SUMIFS({HC("P")},{HC("A")},{k})=0,"",E{r}/SUMIFS({HC("P")},{HC("A")},{k}))',
            (cm["historical_saving_egp"] / local_cost) if local_cost else None, PCT)
        b.f(ws, r, 10, f"=SUMIFS({OP('V')},{OP('A')},{k})", cm["potential_saving_egp"], M0)
        b.f(ws, r, 11, f"=SUMIFS({CB('Q')},{CB('A')},{k})", cm["cbot_adv_usd"], M0)
        b.f(ws, r, 12, f"=SUMIFS({CB('R')},{CB('A')},{k})", cm["cbot_adv_egp"], M0)
    last = CM_FIRST + len(model["commodities"]) - 1
    tot = last + 1
    b.put(ws, tot, 1, "TOTAL", bold=True)
    for col, key in ((2, "contracts"), (3, "consumed_mt"), (4, "local_priced_mt"), (5, "historical_saving_egp"),
                     (6, "realized_saving_egp"), (7, "provisional_saving_egp"), (10, "potential_saving_egp"),
                     (11, "cbot_adv_usd"), (12, "cbot_adv_egp")):
        L = get_column_letter(col)
        b.f(ws, tot, col, f"=SUM({L}{CM_FIRST}:{L}{last})", sum(cm[key] for cm in model["commodities"]),
            "0" if col == 2 else M0, bold=True)
    tp = sum(cm["local_priced_mt"] for cm in model["commodities"])
    th = sum(cm["historical_saving_egp"] for cm in model["commodities"])
    b.f(ws, tot, 8, f'=IF(D{tot}=0,"",E{tot}/D{tot})', (th / tp) if tp else None, M0, bold=True)
    b.signs(ws, f"E{CM_FIRST}:L{tot}")
    ch = BarChart()
    ch.title, ch.height, ch.width = "Savings by commodity, EGP", 8, 16
    ch.add_data(Reference(ws, min_col=5, min_row=4, max_row=last), titles_from_data=True)
    ch.add_data(Reference(ws, min_col=10, min_row=4, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=CM_FIRST, max_row=last))
    ch.y_axis.number_format = '#,##0.0,,"M"'
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ws.add_chart(ch, f"A{tot + 3}")
    model["_cm_last"] = last


# ── 7. Detailed Calculations and Sources ─────────────────────────────────

def _sources(b, model):
    ws = b.ws(6)
    b.title(ws, "Detailed Calculations and Sources", "How every number is built, where it comes from, "
            "and what is missing or assumed.")
    lines = [
        ("CALCULATIONS", None),
        ("Daily local saving", "(Local market price on the consumption date − imported landed cost per MT) × "
                               "MT consumed from that contract that day. Contract total = sum of its days."),
        ("Consumption", "FIFO, oldest cargo first, at the configured daily rate from each delivery (the "
                        "Consumption Savings method). The app records no per-contract allocations."),
        ("Landed cost", "CIF × FX + intake/discharge + clearance + inland freight. History uses the "
                        "contract's recorded CIF (the Savings Tracker's cost); open contracts, or those "
                        "with no CIF, use the live estimate (today's CBOT + premium) and are labelled."),
        ("FX", "Form 4 FX once entered (every commodity except SBM), else the delivery FX, else today's FX."),
        ("Local price", "The logged price on or before the day, matched to the cargo's origin (CORN-BRZ, "
                        "CORN-ARG… else CORN), plus its transport — delivered. Its observation date is shown "
                        "on every daily row. No price on or before → comparison unavailable for those tonnes."),
        ("Savings %", "Total saving ÷ what the same tonnes would have cost locally (Σ local × MT)."),
        ("Open position", "Outstanding = contract qty − delivered. Delivered but not consumed = in stock. "
                          "Potential = (latest local − landed cost today) × tonnes not yet consumed. Never "
                          "counted as realized."),
        ("CBOT fixing", "Pricing lots: their recorded CBOT, tonne-weighted (actual). Otherwise CIF ÷ factor − "
                        "premium (implied) — corn 0.3937 ¢/bu, soybean/wheat 0.36745 ¢/bu, SBM 1.1023 $/short "
                        "ton. Flat-price contracts have none."),
        ("Unit check", "An implied fixing outside the commodity's usual range, or outside where the CBOT "
                       "traded from 150 days before to 120 days after arrival, is flagged and not used."),
        ("CBOT advantage", "(CBOT on the consumption day − fixing) × factor × MT, summed over the days; × the "
                           "contract's cost FX for EGP. A benchmark: never added to the local saving."),
        ("ASSUMPTIONS AND LIMITS", None),
        ("Benchmark", "The CBOT history is a rolling front-month series; the contract's own futures month has "
                      "often expired before consumption, so this is a replacement benchmark, labelled as such."),
        ("Possible fixing dates", "Days whose front-month CBOT was closest to the implied fixing — leads to "
                                  "check against the futures month, not evidence of the fixing date."),
        ("Customs and other costs", "Included only where recorded in the contract's fee fields."),
        ("Consumption rate", "Where the daily rate exceeds the cargo on file, the excess is 'unsourced' "
                             "(opening stock missing, or a rate above what was bought) and is not valued."),
    ]
    r = 4
    for label, text in lines:
        if text is None:
            r += 1; b.put(ws, r, 1, label, bold=True, color=NAVY)
        else:
            b.put(ws, r, 1, label, bold=True); b.put(ws, r, 2, text, wrap=True)
        r += 1
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 110
    src = model.get("sources") or {}
    r += 1; b.put(ws, r, 1, "SOURCES AND DATES", bold=True, color=NAVY); r += 1
    b.put(ws, r, 1, "Report date", bold=True); b.put(ws, r, 2, f"{model['as_of']} (generated {model['generated']})"); r += 1
    for key, d in sorted((src.get("local_latest") or {}).items()):
        b.put(ws, r, 1, f"Local price {key}", bold=True); b.put(ws, r, 2, f"latest observation {d}"); r += 1
    for base, (a, z, n) in sorted((src.get("cbot") or {}).items()):
        b.put(ws, r, 1, f"CBOT {base}", bold=True)
        b.put(ws, r, 2, f"{n} days, {a} … {z}; {src.get('spikes', {}).get(base, 0)} one-day stray prints detected"); r += 1
    fx = src.get("fx") or ["", ""]
    b.put(ws, r, 1, "FX history", bold=True); b.put(ws, r, 2, f"{fx[0]} … {fx[1]}"); r += 1
    b.put(ws, r, 1, "Daily consumption", bold=True)
    b.put(ws, r, 2, ", ".join(f"{k} {v:,.0f} MT/day" for k, v in sorted((src.get("rates") or {}).items()))); r += 1
    r += 1; b.put(ws, r, 1, "RECONCILIATION — consumption by commodity", bold=True, color=NAVY); r += 1
    heads = ["Commodity", "Method", "Daily rate", "Consumed MT", "from import contracts", "from local purchases",
             "unsourced (no cargo on file)", "stock now MT"]
    for j, h in enumerate(heads):
        b.put(ws, r, 1 + j, h, bold=True)
    for rec in model.get("reconciliation") or []:
        r += 1
        for j, key in enumerate(("base", "mode", "daily_rate", "consumed_mt", "import_mt",
                                 "local_purchase_mt", "unsourced_mt", "stock_mt")):
            v = rec.get(key)
            b.put(ws, r, 1 + j, v, M0 if isinstance(v, (int, float)) else None)
    r += 2; b.put(ws, r, 1, "RECORDS", bold=True, color=NAVY); r += 1
    if model.get("dropped"):
        for d in model["dropped"]:
            b.put(ws, r, 1, d["id"]); b.put(ws, r, 2, f"exact duplicate of {d['duplicate_of']} — left out"); r += 1
    else:
        b.put(ws, r, 2, "No exact duplicate contract records."); r += 1
    for la in model.get("look_alikes") or []:
        b.put(ws, r, 1, ", ".join(la["ids"])); b.put(ws, r, 2, f"{la['contract']}: {la['note']}", wrap=True); r += 1
    r += 1; b.put(ws, r, 1, "COST AND CBOT NOTES", bold=True, color=NAVY); r += 1
    for c in model["contracts"]:
        notes = [n for n in ((c.get("history") or {}).get("cost_note"),
                             (c.get("fixing") or {}).get("flag")) if n and "flat price" not in n]
        if notes:
            b.put(ws, r, 1, c["id"]); b.put(ws, r, 2, f"{c['contract']}: " + "; ".join(notes), wrap=True); r += 1


# ── 1. Executive Management Summary ──────────────────────────────────────

def _summary(b, model):
    ws = b.ws(0)
    k = model["kpis"]
    src = model.get("sources") or {}
    latest_local = max((src.get("local_latest") or {}).values(), default="")
    b.title(ws, "Executive Import Savings Dashboard",
            f"Data as of {model['as_of']} · latest local price {latest_local} · generated {model['generated']} · "
            f"{k['contracts']} contracts")
    HC, OP, CB, CM = (lambda c: _HC(c, model)), (lambda c: _OP(c, model)), (lambda c: _CB(c, model)), None
    hc_tot = model["_hc_last"] + 1
    op_tot = model["_op_last"] + 1
    cb_tot = model["_cb_last"] + 1
    hcs, ops, cbs = q(SHEETS[2]), q(SHEETS[3]), q(SHEETS[5])
    # Tonnes behind the potential: in stock + outstanding on rows that have a local and a landed price.
    pot_mt = f'SUMPRODUCT(({OP("S")}<>"")*({OP("I")}+{OP("J")}))'
    cards = [
        ("Total historical savings, EGP", f"={hcs}!L{hc_tot}", k["historical_saving_egp"], M0,
         "Consumed tonnes vs local on the day consumed"),
        ("Open contract potential savings, EGP", f"={ops}!V{op_tot}", k["potential_saving_egp"], M0,
         "Not yet consumed vs today's local — potential"),
        ("Combined historical + potential, EGP", f"=B6+E6", k["combined_benefit_egp"], M0,
         "Different tonnes, so the two add up"),
        ("Open contract outstanding quantity, MT", f'=SUMIFS({OP("J")},{OP("E")},"Yes")', k["open_outstanding_mt"], M0,
         f"not yet delivered · {k['open_in_stock_mt']:,.0f} MT delivered, in stock"),
        ("Open contract value, USD", f'=SUMIFS({OP("Y")},{OP("E")},"Yes")', k["open_full_value_usd"], M0,
         f"{k['open_contracts']} open contracts · not yet consumed ${k['open_value_usd'] or 0:,.0f}"),
        ("Weighted average savings, EGP/MT", f'=IF(({hcs}!G{hc_tot}+{pot_mt})=0,"",H6/({hcs}!G{hc_tot}+{pot_mt}))',
         k["weighted_saving_egp_mt"], M0, f"historical alone {k['historical_saving_egp_mt'] or 0:,.0f} EGP/MT"),
    ]
    for i, (label, formula, value, fmt, sub) in enumerate(cards):
        col = 2 + (i % 3) * 3
        row = 5 if i < 3 else 9
        b.put(ws, row, col, label, bold=True, color="FFFFFF", fill="1A6EBD", wrap=True)
        ws.merge_cells(start_row=row, start_column=col, end_row=row, end_column=col + 1)
        b.f(ws, row + 1, col, formula, value, fmt, bold=True)
        cell = ws.cell(row + 1, col)
        cell.font = Font(bold=True, size=18, color=GREEN if (value or 0) >= 0 else RED)
        ws.merge_cells(start_row=row + 1, start_column=col, end_row=row + 1, end_column=col + 1)
        b.put(ws, row + 2, col, sub, italic=True, color=GREY)
        ws.merge_cells(start_row=row + 2, start_column=col, end_row=row + 2, end_column=col + 2)
        ws.row_dimensions[row].height = 30
        ws.row_dimensions[row + 1].height = 28
    # The cards' formulas above reference B6/E6/H6 — keep them on those cells.
    for col in range(1, 12):
        ws.column_dimensions[get_column_letter(col)].width = 16
    ws.column_dimensions["A"].width = 3
    r = 13
    b.put(ws, r, 2, "CBOT pricing advantage (benchmark — not added to the savings above)", bold=True, color=NAVY)
    b.f(ws, r + 1, 2, f"={cbs}!Q{cb_tot}", k["cbot_adv_usd"], '"$"#,##0;[Red]-"$"#,##0', bold=True)
    b.f(ws, r + 1, 4, f"={cbs}!R{cb_tot}", k["cbot_adv_egp"], '"EGP "#,##0;[Red]-"EGP "#,##0', bold=True)
    b.put(ws, r + 2, 2, "Contract CBOT fixing vs the CBOT on each day its tonnes were consumed. Positive = "
                        "fixed below the market during consumption.", italic=True, color=GREY)
    r = 18
    b.put(ws, r, 2, "WHAT THIS SAYS", bold=True, color=NAVY)
    lines = [
        f"Realized historical savings from importing instead of buying locally: EGP {k['realized_saving_egp']:,.0f} "
        f"on final prices, plus EGP {k['provisional_saving_egp']:,.0f} provisional (CIF not final).",
        f"Tonnes not yet consumed (in stock and still to be delivered) would save a further EGP "
        f"{k['potential_saving_egp']:,.0f} against today's Egyptian local price — a potential, not realized.",
        f"Fixing CBOT against the CBOT prevailing when the material was consumed: "
        f"{'an advantage' if k['cbot_adv_usd'] >= 0 else 'a disadvantage'} of ${abs(k['cbot_adv_usd']):,.0f} "
        f"(EGP {abs(k['cbot_adv_egp']):,.0f}) — a benchmark, already inside the local saving.",
    ]
    for i, line in enumerate(lines):
        b.put(ws, r + 1 + i, 2, f"{i + 1}.  {line}")
    # Rankings
    ranked = sorted((c for c in model["contracts"] if (c.get("history") or {}).get("saving_egp") is not None),
                    key=lambda c: -c["history"]["saving_egp"])
    index = {c["id"]: i for i, c in enumerate(model["contracts"])}
    r = 23
    for title, rows, start in (("HIGHEST-SAVING CONTRACTS", ranked[:10], 2),
                               ("CONTRACTS WITH A FINANCIAL DISADVANTAGE", [c for c in ranked if c["history"]["saving_egp"] < 0][::-1][:10], 7)):
        b.put(ws, r, start, title, bold=True, color=NAVY)
        for j, h in enumerate(("Contract", "Commodity", "Historical savings EGP", "EGP/MT")):
            b.put(ws, r + 1, start + j, h, bold=True)
        for i, c in enumerate(rows):
            rr = r + 2 + i
            hr = HC_FIRST + index[c["id"]]
            b.put(ws, rr, start, c["contract"]); b.put(ws, rr, start + 1, c["base"])
            b.f(ws, rr, start + 2, f"={hcs}!L{hr}", c["history"]["saving_egp"], M0)
            b.f(ws, rr, start + 3, f"={hcs}!N{hr}", c["history"]["saving_egp_mt"], M0)
        b.signs(ws, f"{get_column_letter(start + 2)}{r + 2}:{get_column_letter(start + 3)}{r + 12}")
    ws.column_dimensions["B"].width = 26
    ws.column_dimensions["G"].width = 26
    # Commodity chart, from the commodity sheet
    cm = b.ws(1)
    last = model["_cm_last"]
    ch = BarChart()
    ch.title, ch.height, ch.width = "Savings by commodity, EGP", 7.5, 17
    ch.add_data(Reference(cm, min_col=5, min_row=4, max_row=last), titles_from_data=True)
    ch.add_data(Reference(cm, min_col=10, min_row=4, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(cm, min_col=1, min_row=CM_FIRST, max_row=last))
    ch.y_axis.number_format = '#,##0,,"M"'
    ch.x_axis.delete = False; ch.y_axis.delete = False
    ws.add_chart(ch, "B36")
