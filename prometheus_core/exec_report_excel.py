"""The management savings workbook — structured tables, live formulas.

Built from the model in ``mgmt_report``. Contract data, local market
observations, consumption allocations and each comparison sit in their
own Excel tables; every derived figure is a formula over the rows it comes
from (daily rows → contract summaries → management summary), and the
value of every formula is stored beside it so viewers that do not
calculate still show the numbers.
"""

from __future__ import annotations

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from .mgmt_report import MATCHED
from .xlsx_cache import store_formula_results

SHEETS = ("Management Summary", "Contract Master", "Local Market Price History",
          "Daily Consumption Allocation", "Savings vs Local", "Contract Savings Summary",
          "CBOT Fixed vs Consumption", "Contract CBOT Performance",
          "Open Contracts vs Local Today", "Excluded & Missing Data", "Validation & Sources",
          "Local Purchases", "Monthly Trend")
NAVY, GREEN, RED, GREY, AMBER = "1F3A5F", "1A7A1A", "B3261E", "6B7280", "9A6B00"
M0, M2, PCT = "#,##0;[Red]-#,##0", "#,##0.00;[Red]-#,##0.00", "0.0%"
FIRST = 5  # first data row of every table (header on row 4)


def q(title):
    return "'" + title.replace("'", "''") + "'"


def blank(v):
    return "" if v is None else v


class Book:
    def __init__(self):
        self.wb = Workbook()
        self.wb.active.title = SHEETS[0]
        for s in SHEETS[1:]:
            self.wb.create_sheet(s)
        self.cache = {s: {} for s in SHEETS}

    def ws(self, i):
        return self.wb[SHEETS[i]]

    def put(self, ws, r, c, v, fmt=None, bold=False, color=None, fill=None, size=None, wrap=False, italic=False):
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

    def f(self, ws, r, c, formula, value, fmt=None, **kw):
        self.put(ws, r, c, formula, fmt, **kw)
        self.cache[ws.title][f"{get_column_letter(c)}{r}"] = "" if value is None else value

    def title(self, ws, text, sub):
        self.put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        self.put(ws, 2, 1, sub, italic=True, color=GREY)

    def table(self, ws, name, heads, n_rows, widths=None):
        for i, h in enumerate(heads, start=1):
            ws.cell(4, i, h)
            if widths:
                ws.column_dimensions[get_column_letter(i)].width = widths[i - 1]
        last = FIRST + max(n_rows, 1) - 1
        ref = f"A4:{get_column_letter(len(heads))}{last}"
        t = Table(displayName=name, ref=ref)
        t.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
        ws.add_table(t)
        ws.freeze_panes = "C5"
        ws.row_dimensions[4].height = 32
        for i in range(1, len(heads) + 1):
            ws.cell(4, i).alignment = Alignment(wrap_text=True, vertical="center")
        return last

    def signs(self, ws, ref):
        ws.conditional_formatting.add(ref, CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        ws.conditional_formatting.add(ref, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))


def place(b, name, after):
    """Put sheet ``name`` straight after sheet ``after`` in the workbook."""
    names = b.wb.sheetnames
    b.wb.move_sheet(name, offset=(names.index(after) + 1) - names.index(name)
                    if names.index(name) > names.index(after) else 0)


def col(sheet, letter, last):
    return f"{q(SHEETS[sheet])}!${letter}${FIRST}:${letter}${last}"


def build_workbook(model, path):
    b = Book()
    last = {}
    last["cm"] = _contract_master(b, model)
    last["lp"] = _local_history(b, model)
    last["al"] = _allocations(b, model)
    last["lq"] = _local_purchases(b, model)
    _contract_master_consumed(b, model, last)
    last["sv"] = _savings(b, model)
    last["cs"] = _contract_savings(b, model, last)
    last["cb"] = _cbot(b, model)
    last["cp"] = _cbot_performance(b, model, last)
    _monthly(b, model, last)
    last["op"] = _open(b, model)
    last["ex"] = _excluded(b, model)
    _validation(b, model, last)
    _summary(b, model, last)
    for ws in b.wb.worksheets:
        ws.page_setup.orientation = "landscape"
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
        if ws.title != SHEETS[0]:
            ws.print_title_rows = "4:4"
        ws.oddFooter.center.text = "&A · page &P of &N"
    b.wb.calculation.fullCalcOnLoad = True
    b.wb.save(path)
    return store_formula_results(path, b.cache)


# ── 1. Contract Master ───────────────────────────────────────────────────

def _contract_master(b, m):
    ws = b.ws(1)
    rows = m["contracts"]
    b.title(ws, "Contract Master", "One row per contract record in the database (exact duplicates removed). "
            "CBOT Fixed: recorded pricing lots, else implied = CIF ÷ factor − premium — shown even when the "
            "pricing date is not recorded. Unpriced contracts show Not fixed and a separate indicative value.")
    heads = ["Contract ID", "Contract Number", "Supplier", "Commodity", "Origin", "Contract Status",
             "Contract Quantity MT", "Delivered Quantity MT", "Outstanding Quantity MT", "Consumed Quantity MT",
             "Available Stock MT", "Delivery Date", "Delivery Status", "CIF USD/MT", "Premium", "Premium Unit",
             "Futures Month", "Conversion Factor", "CBOT Fixed", "CBOT Fixing Type", "Indicative CBOT (not fixed)",
             "Pricing Date", "Exchange Rate", "FX Basis", "Landed Cost EGP/MT", "Pricing Status",
             "Source Record ID", "Fixing Note", "Base"]
    widths = [9, 22, 16, 11, 11, 9, 10, 10, 11, 10, 10, 11, 24, 9, 9, 10, 14, 9, 10, 26, 11, 13, 9, 11, 11,
              10, 16, 40, 8]
    last = b.table(ws, "ContractMaster", heads, len(rows), widths)
    for i, c in enumerate(rows):
        r = FIRST + i
        f, cm = c["fix"], c.get("contract_month") or {}
        vals = [c["id"], c["contract"], c.get("supplier"), c.get("commodity"), c.get("origin"), c.get("status"),
                c.get("qty_mt"), c["delivered_mt"]]
        for j, v in enumerate(vals, start=1):
            b.put(ws, r, j, blank(v), M0 if j >= 7 else None)
        b.f(ws, r, 9, f"=G{r}-H{r}", c["outstanding_mt"], M0)
        b.put(ws, r, 11, c["available_mt"], M0)
        b.put(ws, r, 12, c.get("delivery_date") or "")
        b.put(ws, r, 13, c["delivery_status"])
        b.put(ws, r, 14, blank(c.get("cif_usd_mt")), M2)
        b.put(ws, r, 15, blank(c.get("premium")), M2)
        b.put(ws, r, 16, f["unit"] if f["eligible"] else "")
        b.put(ws, r, 17, (cm.get("code", "") + (" (year inferred)" if cm.get("inferred") else ""))
              if cm else (c.get("futures_month") or ""))
        b.put(ws, r, 18, blank(f["factor"]) if f["eligible"] else "", "0.0000")
        if f["type"] == "Implied":
            b.f(ws, r, 19, f"=N{r}/R{r}-O{r}", f["value"], M2, bold=True)
        elif f["type"] == "Recorded":
            b.put(ws, r, 19, f["value"], M2, bold=True)
        elif f["type"] == "Not fixed":
            b.put(ws, r, 19, "Not fixed", color=AMBER)
        elif f["eligible"]:
            b.put(ws, r, 19, "Not assessable", color=GREY)
        b.put(ws, r, 20, f["status"])
        if f["type"] == "Not fixed" and f["indicative"] is not None:
            b.f(ws, r, 21, f"=N{r}/R{r}-O{r}", f["indicative"], M2, color=AMBER)
        b.put(ws, r, 22, f["pricing_date"] or ("Not recorded" if f["fixed"] else ""))
        b.put(ws, r, 23, blank(c.get("fx")), "0.0000")
        b.put(ws, r, 24, c.get("fx_basis") or "")
        b.put(ws, r, 25, blank(c.get("landed_egp_mt")), M2)
        b.put(ws, r, 26, c.get("pricing_status") or "")
        b.put(ws, r, 27, c.get("source_id") or "")
        b.put(ws, r, 28, f["note"])
        b.put(ws, r, 29, c["base"])
    return last


def _contract_master_consumed(b, m, last):
    ws = b.ws(1)
    for i, c in enumerate(m["contracts"]):
        r = FIRST + i
        b.f(ws, r, 10, f"=SUMIFS({col(3, 'G', last['al'])},{col(3, 'B', last['al'])},A{r})", c["consumed_mt"], M0)


# ── 2. Local Market Price History ────────────────────────────────────────

def _local_history(b, m):
    ws = b.ws(2)
    rows = sorted(m["local_obs"], key=lambda o: (o["date"], o["key"]))
    b.title(ws, "Local Market Price History", "Only the local price observations stored in the database — "
            "no rows are created. Where a quote is carried forward to a later consumption day, that is shown "
            "on Savings vs Local with the quote's own date and age.")
    heads = ["Price Observation Date", "Commodity", "Origin / Grade", "Local Market Price EGP/MT",
             "Local Freight EGP/MT", "Total Local Delivered Price EGP/MT", "Supplier / Source",
             "Source Record ID", "Data Status"]
    last = b.table(ws, "LocalPriceHistory", heads, len(rows), [12, 10, 13, 12, 11, 13, 22, 17, 24])
    for i, o in enumerate(rows):
        r = FIRST + i
        g = o.get
        b.put(ws, r, 1, g("date")); b.put(ws, r, 2, g("base") or str(g("key") or "").split("-")[0])
        b.put(ws, r, 3, g("key"))
        b.put(ws, r, 4, blank(g("price")), M2); b.put(ws, r, 5, blank(g("transport")), M2)
        b.f(ws, r, 6, f'=IF(OR(D{r}="",E{r}=""),"",D{r}+E{r})', g("delivered"), M2)
        b.put(ws, r, 7, g("source") or ""); b.put(ws, r, 8, g("source_id") or "")
        b.put(ws, r, 9, (g("status") or "Observed") + (" (freight: default rate)" if g("transport_default_used") else ""))
    return last


# ── 3. Daily Consumption Allocation ──────────────────────────────────────

def _allocations(b, m):
    ws = b.ws(3)
    rows = [a for a in m["allocations"] if a["type"] == "Import"]
    b.title(ws, "Daily Consumption Allocation", "Every consumed imported tonne attributed to a real contract. "
            "Local purchases are on their own sheet; unsourced consumption is on Excluded & Missing Data.")
    heads = ["Consumption Date", "Contract ID", "Contract Number", "Supplier", "Commodity", "Origin",
             "Quantity Consumed MT", "Allocation Method", "Contract Remaining Balance MT", "Contract Source ID",
             "Consumption Source / Assumption", "Record Type", "Base"]
    last = b.table(ws, "Allocations", heads, len(rows), [12, 12, 22, 16, 11, 11, 10, 13, 12, 18, 40, 13, 8])
    for i, a in enumerate(rows):
        r = FIRST + i
        for j, v in enumerate([a["date"], a["contract_id"], a["contract"], a["supplier"], a["commodity"],
                               a["origin"], a["mt"], a["method"], a.get("remaining_mt"), a["source_id"],
                               a["assumption"], a["type"], a["base"]], start=1):
            b.put(ws, r, j, blank(v), M0 if j in (7, 9) else None)
    return last


def _local_purchases(b, m):
    ws = b.ws(11)
    place(b, ws.title, SHEETS[3])
    rows = [a for a in m["allocations"] if a["type"] != "Import"]
    b.title(ws, "Local Purchases", "Tonnes supplied by local purchases, kept apart: never part of the import "
            "savings. Each is set against the local market price + freight observed for its day "
            "(positive = bought below that day's market).")
    heads = ["Consumption Date", "Purchase ID", "Purchase", "Supplier", "Commodity", "Quantity Consumed MT",
             "Purchase Cost EGP/MT", "Local Market + Freight EGP/MT", "Market Price Date", "vs Market EGP/MT",
             "vs Market EGP", "Base", "Allocation Method", "Source Record ID"]
    last = b.table(ws, "LocalPurchases", heads, len(rows), [12, 16, 30, 22, 10, 10, 12, 13, 12, 11, 13, 8, 13, 22])
    for i, a in enumerate(rows):
        r = FIRST + i
        loc = a.get("local") or {}
        price = loc.get("price")
        for j, v in enumerate([a["date"], a["contract_id"], a["contract"], a["supplier"], a["commodity"], a["mt"],
                               a.get("cost"), price, loc.get("date") or ""], start=1):
            b.put(ws, r, j, blank(v), M0 if j == 6 else (M2 if j in (7, 8) else None))
        per = (price - a["cost"]) if None not in (price, a.get("cost")) else None
        b.f(ws, r, 10, f'=IF(OR(G{r}="",H{r}=""),"",H{r}-G{r})', per, M2)
        b.f(ws, r, 11, f'=IF(J{r}="","",J{r}*F{r})', per * a["mt"] if per is not None else None, M0)
        b.put(ws, r, 12, a["base"]); b.put(ws, r, 13, a["method"]); b.put(ws, r, 14, a["source_id"])
    b.signs(ws, f"J{FIRST}:K{last}")
    return last


# ── 4. Savings vs Local ──────────────────────────────────────────────────

def _savings(b, m):
    ws = b.ws(4)
    rows = m["savings"]
    b.title(ws, "Savings vs Local", "Daily Savings = (Local Delivered Price − Imported Landed Cost) × "
            "Consumed MT. Only rows with a real contract, a landed cost and a local observation at most "
            f"{m['options']['max_carry_days']} days old; the rest are on Excluded & Missing Data, not counted as zero.")
    heads = ["Contract Number", "Contract ID", "Supplier", "Commodity", "Consumption Date", "Consumed MT",
             "Imported Landed Cost EGP/MT", "Local Delivered Price EGP/MT", "Local Price Observation Date",
             "Quote Age (days)", "Local Price Record ID", "Savings EGP/MT", "Total Savings EGP", "CIF Basis",
             "Allocation Method", "Data Quality Status", "Local Price Of", "Local x MT", "Base", "Month"]
    last = b.table(ws, "SavingsVsLocal", heads, len(rows),
                   [22, 9, 16, 11, 12, 9, 12, 12, 12, 8, 16, 11, 13, 13, 13, 40, 11, 14, 8, 9])
    for i, s in enumerate(rows):
        r = FIRST + i
        for j, v in enumerate([s["contract"], s["contract_id"], s["supplier"], s["commodity"], s["date"],
                               s["mt"], s["cost"], s["local"], s["local_date"], s["local_age"],
                               s["local_source"]], start=1):
            b.put(ws, r, j, blank(v), M0 if j == 6 else (M2 if j in (7, 8) else None))
        b.f(ws, r, 12, f"=H{r}-G{r}", s["saving_mt"], M2)
        b.f(ws, r, 13, f"=L{r}*F{r}", s["saving"], M0)
        b.put(ws, r, 14, s["cif_basis"]); b.put(ws, r, 15, s["method"]); b.put(ws, r, 16, s["quality"])
        b.put(ws, r, 17, s["local_key"])
        b.f(ws, r, 18, f"=H{r}*F{r}", s["local"] * s["mt"], M0)
        b.put(ws, r, 19, s["base"])
        b.put(ws, r, 20, s["date"][:7])
    b.signs(ws, f"L{FIRST}:M{last}")
    return last


# ── 4b. Contract Savings Summary ─────────────────────────────────────────

def _contract_savings(b, m, last):
    ws = b.ws(5)
    rows = [c for c in m["contracts"] if c["consumed_mt"] > 0]
    rows.sort(key=lambda c: -(c["hist"]["saving"] or -1e18))
    b.title(ws, "Contract Savings Summary", "Active consumption performance: one row per contract with "
            "consumption (zero-consumption contracts stay in the Contract Master only). Every figure is a "
            "formula over Daily Consumption Allocation and Savings vs Local.")
    heads = ["Contract ID", "Contract Number", "Supplier", "Commodity", "Consumed MT", "Compared MT",
             "Not Compared MT", "Landed Cost EGP/MT", "Wtd Avg Local EGP/MT", "Total Savings EGP",
             "Savings EGP/MT", "Savings %", "First Consumption", "Last Consumption", "CIF Basis", "Result",
             "Final Assessment", "Base"]
    end = b.table(ws, "ContractSavings", heads, len(rows),
                  [9, 22, 16, 11, 10, 10, 10, 11, 11, 13, 10, 8, 12, 12, 13, 9, 90, 8])
    for i, c in enumerate(rows):
        r = FIRST + i
        h = c["hist"]
        b.put(ws, r, 1, c["id"]); b.put(ws, r, 2, c["contract"]); b.put(ws, r, 3, c.get("supplier"))
        b.put(ws, r, 4, c.get("commodity"))
        b.f(ws, r, 5, f"=SUMIFS({col(3, 'G', last['al'])},{col(3, 'B', last['al'])},A{r})", c["consumed_mt"], M0)
        b.f(ws, r, 6, f"=SUMIFS({col(4, 'F', last['sv'])},{col(4, 'B', last['sv'])},A{r})", h["priced_mt"], M0)
        b.f(ws, r, 7, f"=E{r}-F{r}", c["consumed_mt"] - h["priced_mt"], M0)
        b.put(ws, r, 8, blank(c.get("landed_egp_mt")), M2)
        b.f(ws, r, 9, f'=IF(F{r}=0,"",SUMIFS({col(4, "R", last["sv"])},{col(4, "B", last["sv"])},A{r})/F{r})',
            h["local_wavg"], M2)
        b.f(ws, r, 10, f'=IF(F{r}=0,"",SUMIFS({col(4, "M", last["sv"])},{col(4, "B", last["sv"])},A{r}))',
            h["saving"], M0, bold=True)
        b.f(ws, r, 11, f'=IF(F{r}=0,"",J{r}/F{r})', h["saving_mt"], M2)
        b.f(ws, r, 12, f'=IF(F{r}=0,"",J{r}/(I{r}*F{r}))',
            (h["saving_pct"] / 100) if h["saving_pct"] is not None else None, PCT)
        b.put(ws, r, 13, c["first_date"]); b.put(ws, r, 14, c["last_date"])
        b.put(ws, r, 15, "Final CIF" if c.get("cif_final") else "Provisional CIF")
        res = ("Not compared" if h["saving"] is None else "Saving" if h["saving"] >= 0 else "Loss")
        b.f(ws, r, 16, f'=IF(J{r}="","Not compared",IF(J{r}>=0,"Saving","Loss"))', res)
        b.put(ws, r, 17, c["assessment"], wrap=False)
        b.put(ws, r, 18, c["base"])
    b.signs(ws, f"J{FIRST}:L{end}")
    m["_cs_rows"] = rows
    return end


# ── 5. CBOT Fixed vs Consumption ─────────────────────────────────────────

def _cbot(b, m):
    ws = b.ws(6)
    rows = m["cbot"]
    n = m["options"]["neutral_cbot"]
    b.title(ws, "CBOT Fixed vs Consumption", "CBOT Difference = consumption-day CBOT − contract CBOT fixed; "
            "USD/MT = difference × conversion factor; USD = USD/MT × consumed MT. Compared only on days the "
            "CBOT stored in the app for the consumption day itself (the futures month is only the month the "
            "premium is quoted over; the series' month that day is in the last column). A historical benchmark "
            "comparison, not a proven "
            "avoidable loss.")
    heads = ["Contract Number", "Contract ID", "Supplier", "Commodity", "Consumption Date", "Consumed MT",
             "CIF USD/MT", "Contract Premium", "Price Unit", "Conversion Factor", "CBOT Fixed", "Fixing Type",
             "Futures Month", "CBOT on Consumption Date", "Market Price Date", "Benchmark Status",
             "CBOT Difference", "Difference USD/MT", "Total Advantage / Missed USD", "FX",
             "Total Advantage / Missed EGP", "Result", "CBOT x MT", "Base", "Series Month That Day", "Month"]
    last = b.table(ws, "CbotVsConsumption", heads, len(rows),
                   [22, 9, 16, 11, 12, 9, 9, 9, 10, 9, 10, 11, 9, 11, 12, 22, 10, 10, 13, 8, 14, 16, 12, 8, 20, 9])
    for i, x in enumerate(rows):
        r = FIRST + i
        for j, v in enumerate([x["contract"], x["contract_id"], x["supplier"], x["commodity"], x["date"],
                               x["mt"], x["cif"], x["premium"], x["unit"], x["factor"], x["fix"],
                               x["fix_type"], x["futures"], x["cbot"], x["cbot_date"], x["benchmark"]], start=1):
            b.put(ws, r, j, blank(v), M0 if j == 6 else (M2 if j in (7, 8, 11, 14) else
                                                          ("0.0000" if j == 10 else None)))
        b.f(ws, r, 17, f'=IF(P{r}="{MATCHED}",N{r}-K{r},"")', x["diff"], M2)
        b.f(ws, r, 18, f'=IF(Q{r}="","",Q{r}*J{r})', x["usd_mt"], M2)
        b.f(ws, r, 19, f'=IF(R{r}="","",R{r}*F{r})', x["usd"], M0)
        b.put(ws, r, 20, blank(x["fx"]), "0.0000")
        b.f(ws, r, 21, f'=IF(OR(S{r}="",T{r}=""),"",S{r}*T{r})', x["egp"], M0)
        b.f(ws, r, 22, f'=IF(Q{r}="","Not assessable",IF(Q{r}>={n},"Advantage",IF(Q{r}<=-{n},"Missed opportunity","Neutral")))',
            x["result"])
        b.f(ws, r, 23, f'=IF(Q{r}="","",N{r}*F{r})', (x["cbot"] * x["mt"]) if x["assessable"] else None, M0)
        b.put(ws, r, 24, x["base"])
        b.put(ws, r, 25, x.get("series_month") or "")
        b.put(ws, r, 26, x["date"][:7])
    b.signs(ws, f"Q{FIRST}:U{last}")
    return last


# ── 6. Contract CBOT Performance ─────────────────────────────────────────

def _cbot_performance(b, m, last):
    ws = b.ws(7)
    n = m["options"]["neutral_cbot"]
    rows = [c for c in m["contracts"] if c["fix"]["fixed"] and c["cbot"]["consumed_mt"] > 0]
    rows.sort(key=lambda c: (c["cbot"]["usd"] is None, c["cbot"]["usd"] or 0))
    b.title(ws, "Contract CBOT Performance", "One row per fixed contract with consumption. Average CBOT is "
            "weighted by the tonnes consumed each day, against the CBOT stored for that day; the result is the "
            "sum of those days' differences — never the whole contract quantity. Not assessable where no CBOT is stored.")
    heads = ["Contract ID", "Contract", "Supplier", "Commodity", "MT Consumed", "MT Assessed", "Coverage %",
             "CIF $/MT", "Premium", "Price Unit", "CBOT Fixed", "Fixing Type", "Avg CBOT During Consumption",
             "Difference", "Advantage USD", "Missed Opportunity USD", "Net Result USD", "Net Result EGP",
             "Assessment", "Base"]
    end = b.table(ws, "ContractCbot", heads, len(rows),
                  [9, 22, 16, 11, 10, 10, 9, 9, 9, 10, 10, 11, 12, 10, 12, 13, 12, 13, 18, 8])
    C = lambda letter: col(6, letter, last["cb"])
    for i, c in enumerate(rows):
        r = FIRST + i
        cb, f = c["cbot"], c["fix"]
        b.put(ws, r, 1, c["id"]); b.put(ws, r, 2, c["contract"]); b.put(ws, r, 3, c.get("supplier"))
        b.put(ws, r, 4, c.get("commodity"))
        b.f(ws, r, 5, f"=SUMIFS({C('F')},{C('B')},A{r})", cb["consumed_mt"], M0)
        b.f(ws, r, 6, f'=SUMIFS({C("F")},{C("B")},A{r},{C("P")},"{MATCHED}")', cb["assessed_mt"], M0)
        b.f(ws, r, 7, f'=IF(E{r}=0,"",F{r}/E{r})', cb["coverage"], PCT)
        b.put(ws, r, 8, blank(c.get("cif_usd_mt")), M2); b.put(ws, r, 9, blank(c.get("premium")), M2)
        b.put(ws, r, 10, f["unit"]); b.put(ws, r, 11, f["value"], M2, bold=True); b.put(ws, r, 12, f["type"])
        b.f(ws, r, 13, f'=IF(F{r}=0,"",SUMIFS({C("W")},{C("B")},A{r})/F{r})', cb["avg_cbot"], M2)
        b.f(ws, r, 14, f'=IF(M{r}="","",M{r}-K{r})', cb["diff"], M2)
        b.f(ws, r, 15, f'=SUMIFS({C("S")},{C("B")},A{r},{C("S")},">0")', cb["advantage_usd"], M0)
        b.f(ws, r, 16, f'=SUMIFS({C("S")},{C("B")},A{r},{C("S")},"<0")', cb["missed_usd"], M0)
        b.f(ws, r, 17, f'=IF(F{r}=0,"",O{r}+P{r})', cb["usd"], M0, bold=True)
        b.f(ws, r, 18, f'=IF(F{r}=0,"",SUMIFS({C("U")},{C("B")},A{r}))', cb["egp"], M0)
        b.f(ws, r, 19, f'=IF(F{r}=0,"Not assessable",IF(N{r}>={n},"Advantage",IF(N{r}<=-{n},"Missed opportunity","Neutral")))',
            cb["assessment"])
        b.put(ws, r, 20, c["base"])
    b.signs(ws, f"N{FIRST}:R{end}")
    m["_cp_rows"] = rows
    return end


# ── 6b. Monthly Trend ────────────────────────────────────────────────

def _monthly(b, m, last):
    ws = b.ws(12)
    place(b, ws.title, SHEETS[7])
    b.title(ws, "Monthly Trend", "Savings vs local and the CBOT benchmark by consumption month — SUMIFS over "
            "Savings vs Local and CBOT Fixed vs Consumption (Month columns). The two are separate measures.")
    months = sorted({s["date"][:7] for s in m["savings"]} | {x["date"][:7] for x in m["cbot"] if x["assessable"]})
    heads = ["Month", "Savings vs Local EGP", "Compared MT", "Savings EGP/MT", "CBOT Net USD", "CBOT Advantage USD",
             "CBOT Missed USD", "CBOT MT"]
    end = b.table(ws, "MonthlyTrend", heads, len(months), [10, 16, 12, 12, 14, 15, 15, 11])
    SV = lambda c_: col(4, c_, last["sv"])
    CB = lambda c_: col(6, c_, last["cb"])
    for i, mo in enumerate(months):
        r = FIRST + i
        sv = [s for s in m["savings"] if s["date"][:7] == mo]
        cb = [x for x in m["cbot"] if x["assessable"] and x["date"][:7] == mo]
        sav, mt = sum(s["saving"] for s in sv), sum(s["mt"] for s in sv)
        b.put(ws, r, 1, mo)
        b.f(ws, r, 2, f"=SUMIFS({SV('M')},{SV('T')},A{r})", sav, M0)
        b.f(ws, r, 3, f"=SUMIFS({SV('F')},{SV('T')},A{r})", mt, M0)
        b.f(ws, r, 4, f'=IF(C{r}=0,"",B{r}/C{r})', (sav / mt) if mt else None, M2)
        b.f(ws, r, 5, f"=SUMIFS({CB('S')},{CB('Z')},A{r})", sum(x["usd"] for x in cb), M0)
        b.f(ws, r, 6, f'=SUMIFS({CB("S")},{CB("Z")},A{r},{CB("S")},">0")', sum(x["usd"] for x in cb if x["usd"] > 0), M0)
        b.f(ws, r, 7, f'=SUMIFS({CB("S")},{CB("Z")},A{r},{CB("S")},"<0")', sum(x["usd"] for x in cb if x["usd"] < 0), M0)
        b.f(ws, r, 8, f"=SUMIFS({CB('F')},{CB('Z')},A{r})", sum(x["mt"] for x in cb), M0)
    b.signs(ws, f"B{FIRST}:G{end}")
    for title, col_i, anchor in (("Savings vs local by month, EGP", 2, "J4"), ("CBOT net result by month, USD", 5, "J22")):
        ch = BarChart()
        ch.title, ch.legend = title, None
        ch.y_axis.number_format = '#,##0.0,,"M"' if col_i == 2 else '#,##0,"k"'
        ch.x_axis.delete = False
        ch.y_axis.delete = False
        ch.add_data(Reference(ws, min_col=col_i, min_row=4, max_row=end), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=FIRST, max_row=end))
        ch.height, ch.width = 7.5, 16
        ws.add_chart(ch, anchor)


# ── 7. Open Contracts vs Local Today ─────────────────────────────────────

def _open(b, m):
    ws = b.ws(8)
    rows = m["open"]
    b.title(ws, "Open Contracts vs Local Today", "Not-yet-consumed tonnes (available stock + outstanding) at the "
            "latest local delivered price. Fixed-price contracts are the confirmed potential; unpriced contracts "
            "are an indicative scenario and are totalled separately. Potential, not realized.")
    heads = ["Contract Number", "Contract ID", "Supplier", "Commodity", "Contract Status", "Total Quantity MT",
             "Delivered MT", "Consumed MT", "Available Stock MT", "Outstanding MT", "Pricing Status",
             "Fixed or Indicative CIF USD/MT", "CIF Basis", "Applicable FX", "FX Basis",
             "Estimated Full Landed Cost EGP/MT", "Latest Local Delivered Price EGP/MT", "Local Price Date",
             "Local Price Of", "Savings EGP/MT", "Potential Savings EGP", "Classification", "Delivery Status",
             "Open Contract", "Delivery Confirmed", "Base"]
    last = b.table(ws, "OpenVsLocal", heads, len(rows),
                   [20, 9, 16, 11, 9, 10, 10, 10, 10, 10, 10, 11, 24, 9, 14, 12, 12, 11, 10, 10, 13, 18, 26, 8, 9, 8])
    for i, o in enumerate(rows):
        r = FIRST + i
        for j, v in enumerate([o["contract"], o["contract_id"], o["supplier"], o["commodity"], o["status"],
                               o["qty_mt"], o["delivered_mt"], o["consumed_mt"], o["available_mt"]], start=1):
            b.put(ws, r, j, blank(v), M0 if j >= 6 else None)
        b.f(ws, r, 10, f"=F{r}-G{r}", o["outstanding_mt"], M0)
        for j, v, fmt in ((11, o["pricing_status"], None), (12, o["cif"], M2), (13, o["cif_basis"], None),
                          (14, o["fx"], "0.0000"), (15, o["fx_basis"], None), (16, o["landed"], M2),
                          (17, o["local"], M2), (18, o["local_date"], None), (19, o["local_key"], None)):
            b.put(ws, r, j, blank(v), fmt)
        b.f(ws, r, 20, f'=IF(OR(P{r}="",Q{r}=""),"",Q{r}-P{r})', o["saving_mt"], M2)
        b.f(ws, r, 21, f'=IF(T{r}="","",T{r}*(I{r}+J{r}))', o["potential"], M0, bold=True)
        b.put(ws, r, 22, o["class"]); b.put(ws, r, 23, o["delivery_status"])
        b.put(ws, r, 24, "Yes" if o["is_open"] else "No")
        b.put(ws, r, 25, "No" if "not verified" in o["delivery_status"] or "reconcile" in o["delivery_status"] else "Yes")
        b.put(ws, r, 26, o["base"])
    b.signs(ws, f"T{FIRST}:U{last}")
    return last


# ── 8. Excluded & Missing Data ───────────────────────────────────────────

def _excluded(b, m):
    ws = b.ws(9)
    order = ["Unsourced consumption", "Cleared by stock count", "Logged entry not used", "No landed cost",
             "No usable local price", "Contract not fixed", "CBOT comparison not assessable",
             "Delivery not verified", "Duplicate record dropped", "Stock count vs FIFO model"]
    rows = sorted(m["excluded"], key=lambda e: (order.index(e["category"]) if e["category"] in order else 99,
                                                 e.get("date") or "", e.get("contract_id") or ""))
    b.title(ws, "Excluded & Missing Data", "Every record kept out of the financial results, and why. Nothing "
            "here is counted as zero savings or filled with an assumed value.")
    heads = ["Category", "Date", "Contract", "Contract ID", "Commodity", "Quantity MT", "Reason", "Source"]
    last = b.table(ws, "Excluded", heads, len(rows), [28, 12, 22, 10, 10, 10, 90, 22])
    for i, e in enumerate(rows):
        r = FIRST + i
        for j, v in enumerate([e["category"], e.get("date"), e.get("contract"), e.get("contract_id"),
                               e.get("commodity"), e.get("mt"), e["reason"], e.get("source")], start=1):
            b.put(ws, r, j, blank(v), M0 if j == 6 else None)
    return last


# ── 9. Validation & Sources ──────────────────────────────────────────────

def _validation(b, m, last):
    ws = b.ws(10)
    b.title(ws, "Validation & Sources", f"Checks run before export · model checksum {m['checksum']} (the HTML "
            "dashboard prints the same checksum when it renders the same figures).")
    ready = m["management_ready"]
    b.put(ws, 3, 1, "MANAGEMENT-READY — all checks passed" if ready else
          "NOT MANAGEMENT-READY — see the failed checks below", bold=True, color="FFFFFF",
          fill=GREEN if ready else RED)
    for j, h in enumerate(("Check", "Result", "Detail"), start=1):
        b.put(ws, 4, j, h, bold=True, color="FFFFFF", fill=NAVY)
    r = FIRST
    for v in m["validation"]:
        b.put(ws, r, 1, v["check"]); b.put(ws, r, 2, "PASS" if v["passed"] else "FAIL", bold=True,
                                           color=GREEN if v["passed"] else RED)
        b.put(ws, r, 3, v["detail"])
        r += 1
    r += 1
    b.put(ws, r, 1, "AUDIT — Total Consumed MT = Sourced Allocated MT + Excluded / Unallocated MT", bold=True, color=NAVY)
    r += 1
    for j, h in enumerate(("Commodity", "Total Consumed MT", "Sourced Allocated MT", "Excluded / Unallocated MT",
                           "Difference MT"), start=1):
        b.put(ws, r, j, h, bold=True, color="FFFFFF", fill=NAVY)
    r += 1
    for a in m["audit"]:
        b.put(ws, r, 1, a["base"]); b.put(ws, r, 2, a["consumed_mt"], M0)
        b.f(ws, r, 3, f'=SUMIFS({col(3, "G", last["al"])},{col(3, "M", last["al"])},A{r})'
                      f'+SUMIFS({col(11, "F", last["lq"])},{col(11, "L", last["lq"])},A{r})', a["allocated_mt"], M0)
        b.f(ws, r, 4, f'=SUMIFS({col(9, "F", last["ex"])},{col(9, "E", last["ex"])},A{r},{col(9, "A", last["ex"])},"Unsourced consumption")'
                      f'+SUMIFS({col(9, "F", last["ex"])},{col(9, "E", last["ex"])},A{r},{col(9, "A", last["ex"])},"Cleared by stock count")',
            a["excluded_mt"], M0)
        b.f(ws, r, 5, f"=B{r}-C{r}-D{r}", a["difference_mt"], M0)
        r += 1
    r += 1
    b.put(ws, r, 1, "SOURCES", bold=True, color=NAVY)
    r += 1
    src = m.get("sources") or {}
    lines = [("Data as of", m["as_of"]), ("Generated", m["generated"]), ("Consumption method", m["walk_mode"]),
             ("Daily rates (MT/day)", ", ".join(f"{k} {v:g}" for k, v in (m.get("rates") or {}).items())),
             ("CBOT history", src.get("cbot_source", "cbot_history"))]
    lines += [(f"CBOT {k}", f"{v[0]} → {v[1]} ({v[2]} days)") for k, v in (src.get("cbot") or {}).items()]
    lines += [(f"Latest local price {k}", v) for k, v in sorted((src.get("local_latest") or {}).items())]
    lines += [("FX history", " → ".join(src.get("fx") or [])),
              ("One-day CBOT spikes stepped over", ", ".join(f"{k} {v}" for k, v in (src.get("spikes") or {}).items()))]
    for k, v in lines:
        b.put(ws, r, 1, k); b.put(ws, r, 2, str(v)); r += 1
    r += 1
    b.put(ws, r, 1, "METHOD", bold=True, color=NAVY)
    r += 1
    o = m["options"]
    for t in [
        "Consumption: FIFO allocation of the configured daily rate from each delivery, oldest cargo first "
        "(FIFO Estimated). Logged withdrawals are used as Actual only when they are credible; see Excluded.",
        "Unsourced consumption (days with no cargo or local purchase in stock) is excluded, never allocated.",
        f"Local price: the origin-matched delivered price (price + freight) observed on or before the day; "
        f"up to {o['carry_days']} days old = carried forward, up to {o['max_carry_days']} = stale but used and "
        "flagged, older = excluded.",
        "Landed cost: CIF × FX (Form 4 once entered, except SBM; else delivery FX) + discharge + clearance + "
        "inland freight. Final CIF for priced contracts, provisional otherwise.",
        "CBOT fixed: recorded pricing lots (tonne-weighted), else implied = CIF ÷ factor − premium "
        "(CORN 0.3937; SOYBEAN, WHEAT 0.36745; SBM 1.1023, premium in $/short ton). Not shown as fixed for "
        "unpriced contracts. No price-adjustment fields are recorded in the database.",
        "Consumption-day CBOT: the CBOT stored in the app for each consumption day (the nearest futures "
        "month that day, recorded per row). The contract's futures month is the month its premium is quoted "
        "over and does not restrict the comparison. "
        f"Prints more than {o['cbot_max_age_days']} days old and one-day spikes are not used.",
        f"Result: Advantage when CBOT − fixed ≥ {o['neutral_cbot']:g} price unit, Missed opportunity when ≤ "
        f"−{o['neutral_cbot']:g}, else Neutral. A historical benchmark, not an executable alternative.",
        "Savings vs local and the CBOT result are separate measures and are never added together.",
    ]:
        b.put(ws, r, 1, t); r += 1
    ws.column_dimensions["A"].width = 46
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 22
    ws.column_dimensions["E"].width = 14


# ── 0. Management Summary ────────────────────────────────────────────────

def _summary(b, m, last):
    ws = b.ws(0)
    k, qd = m["kpis"], m["quality"]
    ready = m["management_ready"]
    b.title(ws, "Procurement Savings — Management Summary",
            f"Data as of {m['as_of']} · generated {m['generated']} · checksum {m['checksum']} · {k['contracts']} contracts")
    failed = [v["check"] for v in m["validation"] if not v["passed"]]
    b.put(ws, 3, 2, ("Management-ready: all validation checks passed" if ready else
                     "NOT management-ready — failed: " + "; ".join(failed)),
          bold=True, color="FFFFFF", fill=GREEN if ready else RED)
    ws.merge_cells("B3:I3")
    SV = lambda c: col(4, c, last["sv"])
    CB = lambda c: col(6, c, last["cb"])
    OP = lambda c: col(8, c, last["op"])
    cards = [
        ("Historical savings vs local, EGP", f"=SUM({SV('M')})", k["historical_saving_egp"],
         f"Actual consumption, FIFO estimated · {k['historical_mt']:,.0f} MT · final CIF "
         f"{k['historical_final_egp']:,.0f} · provisional {k['historical_provisional_egp']:,.0f}"),
        ("Open contracts potential vs local (fixed price), EGP", f'=SUMIFS({OP("U")},{OP("V")},"Fixed price")',
         k["open_fixed_potential_egp"],
         f"Potential · {k['open_fixed_mt']:,.0f} MT · unpriced scenario EGP {k['open_indicative_potential_egp']:,.0f} "
         "shown separately"),
        ("Open contract outstanding, MT", f'=SUMIFS({OP("J")},{OP("X")},"Yes",{OP("Y")},"Yes")',
         k["open_outstanding_mt"], f"Not yet delivered · {k['open_available_mt']:,.0f} MT delivered, in stock"),
        ("CBOT pricing advantage, USD", f'=SUMIFS({CB("S")},{CB("S")},">0")', k["cbot_advantage_usd"],
         "Benchmark — days the market was above our fixing"),
        ("CBOT missed opportunity, USD", f'=SUMIFS({CB("S")},{CB("S")},"<0")', k["cbot_missed_usd"],
         "Benchmark — days the market was below our fixing"),
        ("Net CBOT pricing difference, USD", f"=SUM({CB('S')})", k["cbot_net_usd"],
         f"EGP {k['cbot_net_egp']:,.0f} · {(k['cbot_coverage'] or 0) * 100:,.0f}% of fixed-contract tonnes with a stored CBOT"),
    ]
    for i, (label, formula, value, sub) in enumerate(cards):
        c0 = 2 + (i % 3) * 3
        r0 = 5 if i < 3 else 9
        b.put(ws, r0, c0, label, bold=True, color="FFFFFF", fill="1A6EBD", wrap=True)
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + 1)
        b.f(ws, r0 + 1, c0, formula, value, M0)
        ws.cell(r0 + 1, c0).font = Font(bold=True, size=18, color=GREEN if (value or 0) >= 0 else RED)
        ws.merge_cells(start_row=r0 + 1, start_column=c0, end_row=r0 + 1, end_column=c0 + 1)
        b.put(ws, r0 + 2, c0, sub, italic=True, color=GREY, wrap=True)
        ws.merge_cells(start_row=r0 + 2, start_column=c0, end_row=r0 + 2, end_column=c0 + 1)
        ws.row_dimensions[r0].height = 30
        ws.row_dimensions[r0 + 1].height = 28
        ws.row_dimensions[r0 + 2].height = 30
    for c_ in range(1, 12):
        ws.column_dimensions[get_column_letter(c_)].width = (3 if c_ in (1, 4, 7) else 21)

    r = 13
    b.put(ws, r, 2, "WHAT THIS SAYS", bold=True, color=NAVY)
    says = [
        f"Importing instead of buying locally {'saved' if k['historical_saving_egp'] >= 0 else 'cost'} "
        f"EGP {abs(k['historical_saving_egp']):,.0f} on {k['historical_mt']:,.0f} MT consumed "
        f"({k['historical_saving_egp_mt'] or 0:,.0f} EGP/MT), each tonne against the local price observed on its day.",
        f"Not-yet-consumed fixed-price tonnes would save EGP {k['open_fixed_potential_egp']:,.0f} at today's local "
        f"price; unpriced contracts add an indicative EGP {k['open_indicative_potential_egp']:,.0f} (scenario only).",
        f"On the consumption days the CBOT was above our fixing worth USD {k['cbot_advantage_usd']:,.0f} and below it "
        f"worth USD {abs(k['cbot_missed_usd']):,.0f} — net USD {k['cbot_net_usd']:,.0f}. A benchmark, not added to savings.",
        f"Excluded: {qd['excluded_unsourced_mt']:,.0f} MT of unsourced consumption, {qd['missing_cbot_mt']:,.0f} MT "
        "without a stored CBOT for the day — listed on Excluded & Missing Data.",
    ]
    for i, t in enumerate(says):
        b.put(ws, r + 1 + i, 2, f"{i + 1}.  {t}")

    r = 19
    b.put(ws, r, 2, "BY COMMODITY", bold=True, color=NAVY)
    heads = ["Commodity", "Historical savings EGP", "Compared MT", "EGP/MT", "Open potential (fixed) EGP",
             "Open scenario (unpriced) EGP", "CBOT net USD", "CBOT assessed MT"]
    for j, h in enumerate(heads):
        b.put(ws, r + 1, 2 + j, h, bold=True, color="FFFFFF", fill=NAVY, wrap=True)
    for i, c in enumerate(m["commodities"]):
        rr = r + 2 + i
        b.put(ws, rr, 2, c["base"], bold=True)
        b.f(ws, rr, 3, f"=SUMIFS({SV('M')},{SV('S')},B{rr})", c["saving_egp"], M0)
        b.f(ws, rr, 4, f"=SUMIFS({SV('F')},{SV('S')},B{rr})", c["priced_mt"], M0)
        b.f(ws, rr, 5, f'=IF(D{rr}=0,"",C{rr}/D{rr})', c["saving_egp_mt"], M0)
        b.f(ws, rr, 6, f'=SUMIFS({OP("U")},{OP("Z")},B{rr},{OP("V")},"Fixed price")', c["open_fixed_egp"], M0)
        b.f(ws, rr, 7, f'=SUMIFS({OP("U")},{OP("Z")},B{rr},{OP("V")},"Indicative (unpriced)")', c["open_indicative_egp"], M0)
        b.f(ws, rr, 8, f"=SUMIFS({CB('S')},{CB('X')},B{rr})", c["cbot_net_usd"], M0)
        b.f(ws, rr, 9, f'=SUMIFS({CB("F")},{CB("X")},B{rr},{CB("P")},"{MATCHED}")', c["cbot_assessed_mt"], M0)
    com_last = r + 1 + len(m["commodities"])
    b.signs(ws, f"C{r + 2}:H{com_last}")

    r = com_last + 2
    b.put(ws, r, 2, "TOP 10 — LOCAL MARKET SAVINGS", bold=True, color=GREEN)
    b.put(ws, r, 6, "TOP 10 — CBOT MISSED OPPORTUNITY", bold=True, color=RED)
    for j, h in enumerate(("Contract", "Commodity", "Savings EGP")):
        b.put(ws, r + 1, 2 + j, h, bold=True)
    for j, h in enumerate(("Contract", "Commodity", "Net CBOT USD")):
        b.put(ws, r + 1, 6 + j, h, bold=True)
    top = [c for c in m["_cs_rows"] if (c["hist"]["saving"] or 0) > 0][:10]
    cs_index = {c["id"]: FIRST + i for i, c in enumerate(m["_cs_rows"])}
    for i, c in enumerate(top):
        rr = r + 2 + i
        b.put(ws, rr, 2, c["contract"]); b.put(ws, rr, 3, c.get("commodity"))
        b.f(ws, rr, 4, f"={q(SHEETS[5])}!J{cs_index[c['id']]}", c["hist"]["saving"], M0)
    cp_index = {c["id"]: FIRST + i for i, c in enumerate(m["_cp_rows"])}
    worst = [c for c in m["_cp_rows"] if (c["cbot"]["usd"] or 0) < 0][:10]
    for i, c in enumerate(worst):
        rr = r + 2 + i
        b.put(ws, rr, 6, c["contract"]); b.put(ws, rr, 7, c.get("commodity"))
        b.f(ws, rr, 8, f"={q(SHEETS[7])}!Q{cp_index[c['id']]}", c["cbot"]["usd"], M0)
    b.signs(ws, f"D{r + 2}:D{r + 12}")
    b.signs(ws, f"H{r + 2}:H{r + 12}")

    chart = BarChart()
    chart.type = "bar"
    chart.title = "Historical savings vs local by commodity, EGP"
    chart.legend = None
    chart.y_axis.number_format = '#,##0.0,,"M"'
    chart.x_axis.delete = False
    chart.y_axis.delete = False
    chart.add_data(Reference(ws, min_col=3, min_row=20, max_row=com_last), titles_from_data=True)
    chart.set_categories(Reference(ws, min_col=2, min_row=21, max_row=com_last))
    chart.height, chart.width = 7.5, 16
    ws.add_chart(chart, f"B{r + 14}")
