"""Every daily Open-MTM movement of every contract, from the day it was stored to today.

The Home screen's "Daily Open MTM Movement" table compares today's open book with the previous
stored day. This module produces that same comparison for every stored day in the ledger
(``open_mtm_daily``) and writes it to Excel:

* ``extend_to_storage`` rebuilds, for each contract, the trading days between its storage start
  and its first stored record (it was in the warehouse before it was entered in the app). The
  rows come from the CBOT close, the FX history and the local price of each day, with the fees,
  premium and tonnes of the contract's first record. They are marked RECONSTRUCTED and are used
  only for the export; the stored ledger is not changed.
* ``day_blocks`` repeats the Home table for each stored day against the previous stored day:
  one row per contract (new and exited contracts included, the same way Home shows them) and
  the open-book total with the tonne-weighted reasons.
* ``contract_trails`` gives each contract's own day-by-day trail against its own previous day.
* ``write_movements_excel`` writes Summary, Book by Day, Daily Movement, Contract Trail and one
  sheet per open contract whose movement columns are live formulas.

The split of the change in Sav/MT is the one used on Home (``mtm_attribution``):
from CBOT = −ΔCIF × prior FX, from FX = −today's CIF × ΔFX, from Local = Δ local, Other = rest.
"""
from __future__ import annotations

import datetime as dt
import re

from .mtm_attribution import attribute
from .mtm_history import rebuild_row

PARTS = ("from_cbot", "from_fx", "from_local", "other")


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _sub(a, b):
    return a - b if None not in (a, b) else None


def _base(r):
    return (r.get("base_commodity") or r.get("commodity") or "").upper().split("-")[0]


def _rows(history):
    return [r for r in history or [] if isinstance(r, dict) and r.get("date") and r.get("contract_id")]


def storage_start(contract):
    """The contract's storage start date (YYYY-MM-DD) or ''."""
    v = str((contract or {}).get("storage_start") or "")[:10]
    try:
        dt.date.fromisoformat(v)
        return v
    except ValueError:
        return ""


def first_records(history):
    """{contract_id: its first stored record}."""
    out = {}
    for r in sorted(_rows(history), key=lambda x: x["date"]):
        out.setdefault(r["contract_id"], r)
    return out


def extend_to_storage(history, contracts, trading_days, cbot_on, fx_on, local_on, ids=None, captured_at=""):
    """Rows for the trading days from each contract's storage start up to (not incl.) its first record.

    Returns the new rows; ``history`` is not changed. A contract without a storage start, or whose
    first record is on or before it, gets none.
    """
    out = []
    days = sorted(set(trading_days or []))
    for cid, first in sorted(first_records(history).items()):
        if ids is not None and cid not in ids:
            continue
        c = (contracts or {}).get(cid) or {}
        start = storage_start(c)
        if not start or start >= first["date"]:
            continue
        for day in days:
            if start <= day < first["date"]:
                rec = rebuild_row(day, first, c, cbot_on, fx_on, local_on, captured_at)
                rec["capture_reason"] = "before_first_record"
                rec["reconstructed_from"] = (rec.get("reconstructed_from", "") +
                                             f"; before the contract was entered (storage start {start})")
                out.append(rec)
    return out


def contract_trails(history, ids=None):
    """{contract_id: [rows in date order]}; each row against the contract's own previous day."""
    by = {}
    for r in sorted(_rows(history), key=lambda x: (x["contract_id"], x["date"])):
        if ids is None or r["contract_id"] in ids:
            by.setdefault(r["contract_id"], []).append(r)
    out = {}
    for cid, rs in by.items():
        trail, p = [], None
        for r in rs:
            a = attribute(r, p) if p else {k: None for k in PARTS + ("change",)}
            trail.append({"rec": r, "prior": p, "why": a})
            p = r
        out[cid] = trail
    return out


def _book(rows):
    """Home's open-book totals: (MT, total EGP, weighted Sav/MT = total / MT)."""
    qty = sum(_n(r.get("qty_mt")) or 0.0 for r in rows)
    vals = [_n(r.get("total_saving_egp")) for r in rows]
    total = sum(v for v in vals if v is not None) if any(v is not None for v in vals) else None
    return qty, total, (total / qty if total is not None and qty else None)


def day_blocks(history, ids=None):
    """The Home comparison for every stored day against the previous stored day.

    Returns [{"date", "prior_date", "rows": [...], "book": {...}}] in date order. Row keys follow the
    Home table: ref, contract_id, commodity, flag (''/new/exited), mt, cbot / cbot_prior / d_cbot,
    sav / sav_prior / d_sav, from_cbot, from_fx, from_local, other, total / total_prior / d_total,
    plus cif, fx, local (today and prior), local_date, mode, stale and note.
    """
    by_date = {}
    for r in _rows(history):
        if ids is None or r["contract_id"] in ids:
            by_date.setdefault(r["date"], {})[r["contract_id"]] = r
    out, prior_date = [], ""
    for day in sorted(by_date):
        cur, prv = by_date[day], by_date.get(prior_date, {})
        keys = sorted(set(cur) | set(prv), key=lambda k: (_base(cur.get(k) or prv.get(k)),
                                                         (cur.get(k) or prv.get(k)).get("contract_ref") or k))
        rows, wsum, wq = [], dict.fromkeys(PARTS, 0.0), 0.0
        for cid in keys:
            c, p = cur.get(cid), prv.get(cid)
            a = c or p
            why = attribute(c, p) if (c and p) else {}
            g = lambda rec, k: _n((rec or {}).get(k))
            d_sav, d_tot = _sub(g(c, "saving_egp_mt"), g(p, "saving_egp_mt")), _sub(g(c, "total_saving_egp"), g(p, "total_saving_egp"))
            flag = ""
            if c is None:
                flag = "exited"
                d_sav = -g(p, "saving_egp_mt") if g(p, "saving_egp_mt") is not None else None
                d_tot = -g(p, "total_saving_egp") if g(p, "total_saving_egp") is not None else None
            elif p is None and prior_date:
                flag = "new"
                d_sav, d_tot = g(c, "saving_egp_mt"), g(c, "total_saving_egp")
            q = g(c, "qty_mt") or 0.0
            if why and all(why.get(k) is not None for k in PARTS) and q:
                wq += q
                for k in PARTS:
                    wsum[k] += why[k] * q
            rows.append({
                "date": day, "prior_date": prior_date, "contract_id": cid, "ref": a.get("contract_ref") or cid,
                "commodity": a.get("base_commodity") or a.get("commodity") or "", "supplier": a.get("supplier") or "",
                "flag": flag, "mt": g(c, "qty_mt") if c else g(p, "qty_mt"),
                "cbot": g(c, "cbot_price"), "cbot_prior": g(p, "cbot_price"), "d_cbot": _sub(g(c, "cbot_price"), g(p, "cbot_price")),
                "sav": g(c, "saving_egp_mt"), "sav_prior": g(p, "saving_egp_mt"), "d_sav": d_sav,
                **{k: why.get(k) for k in PARTS},
                "total": g(c, "total_saving_egp"), "total_prior": g(p, "total_saving_egp"), "d_total": d_tot,
                "cif": g(c, "cif_usd_mt"), "cif_prior": g(p, "cif_usd_mt"), "fx": g(c, "fx"), "fx_prior": g(p, "fx"),
                "fx_source": (c or {}).get("fx_source", ""), "local": g(c, "local_egp_mt"), "local_prior": g(p, "local_egp_mt"),
                "local_date": (c or {}).get("local_price_date", ""), "own": g(c, "own_after_egp_mt"),
                "mode": "Rebuilt" if (c or {}).get("mode") == "RECONSTRUCTED" else ("Live" if c else ""),
                "stale": "; ".join((c or {}).get("stale_quotes") or []), "note": (c or {}).get("reconstructed_from", ""),
            })
            if c and p and (g(c, "total_saving_egp") is None) != (g(p, "total_saving_egp") is None):
                gap = day if g(c, "total_saving_egp") is None else prior_date
                rows[-1]["note"] = (f"no saving on {gap} (a price was missing); the book total that day leaves it out"
                                    + ("; " + rows[-1]["note"] if rows[-1]["note"] else ""))
        q1, t1, s1 = _book(list(cur.values()))
        q0, t0, s0 = _book(list(prv.values()))
        cbot = {}
        for side, recs in (("today", cur), ("prior", prv)):
            for r in recs.values():
                b = _base(r)
                if _n(r.get("cbot_price")) is not None and (b, side) not in cbot:
                    cbot[(b, side)] = (_n(r.get("cbot_price")), r.get("cbot_unit") or "")
        bases = sorted({b for b, _s in cbot})
        book = {
            "contracts": len(cur), "contracts_prior": len(prv), "mt": q1, "mt_prior": q0,
            "total": t1, "total_prior": t0 if prior_date else None, "d_total": _sub(t1, t0) if prior_date else None,
            "sav": s1, "sav_prior": s0 if prior_date else None, "d_sav": _sub(s1, s0) if prior_date else None,
            **{k: (wsum[k] / wq if wq else None) for k in PARTS},
            "cbot": {b: ((cbot.get((b, "today")) or (None,))[0], (cbot.get((b, "prior")) or (None,))[0]) for b in bases},
            "units": {b: (cbot.get((b, "today")) or cbot.get((b, "prior")) or (None, ""))[1] for b in bases},
            "mode": _mode({r.get("mode") for r in cur.values()}),
            "prior_mode": _mode({r.get("mode") for r in prv.values()}) if prv else "",
            "stale": "; ".join(sorted({s for r in cur.values() for s in (r.get("stale_quotes") or [])})),
        }
        book["text"] = headline(day, prior_date, book)
        out.append({"date": day, "prior_date": prior_date, "rows": rows, "book": book})
        prior_date = day
    return out


def _mode(modes):
    modes = {m or "LIVE" for m in modes}
    return "Live" if modes <= {"LIVE"} else "Rebuilt" if modes == {"RECONSTRUCTED"} else "Mixed"


def _sg(v, d=0):
    return "—" if v is None else f"{v:+,.{d}f}".replace("-", "−")


def headline(day, prior_date, b):
    """The Home summary line, e.g. '2026-11-09 → 2026-11-10 · Open MTM edge EGP 6,959,716 → …'."""
    money = lambda v: "—" if v is None else f"EGP {v:,.0f}"
    if not prior_date:
        return f"{day} · first stored day · {b['contracts']} contracts, {b['mt']:,.0f} MT, Open MTM edge {money(b['total'])}"
    bits = [f"{prior_date} → {day}",
            f"Open MTM edge {money(b['total_prior'])} → {money(b['total'])} (Δ {_sg(b['d_total'])})",
            f"Weighted Saving/MT Δ {_sg(b['d_sav'])}"]
    for base, (t, p) in b["cbot"].items():
        if t is not None and p is not None:
            bits.append(f"{base} {p:,.2f}→{t:,.2f}")
    if b["from_cbot"] is not None:
        bits.append("Why (EGP/MT, tonne-weighted): " + " · ".join(
            f"{lab} {_sg(b[k])}" for k, lab in (("from_cbot", "CBOT"), ("from_fx", "FX"), ("from_local", "local"), ("other", "other"))))
    if b["prior_mode"] in ("Rebuilt", "Mixed"):
        bits.append(f"{prior_date} was rebuilt from stored closes")
    return " · ".join(bits)


# ── Excel ────────────────────────────────────────────────────────────────

NAVY, GREEN, RED, GREY, AMBER = "1F3A5F", "1A7A1A", "B3261E", "6B7280", "9A6B00"
F0, F2, F4 = "#,##0;-#,##0", "#,##0.00;-#,##0.00", "0.0000"
S0, S2 = "+#,##0;-#,##0;0", "+#,##0.00;-#,##0.00;0.00"
REBUILT_FILL, TOTAL_FILL, NEW_FILL = "F3F0FF", "E8EEF6", "FFF7E0"


def sheet_name(ref, used):
    """A valid, unique sheet name for a contract reference."""
    base = re.sub(r"[\[\]\*\?/\\:]", "-", str(ref or "Contract")).strip("' ")[:28] or "Contract"
    name, i = base, 2
    while name.lower() in used:
        name = f"{base[:25]}~{i}"
        i += 1
    used.add(name.lower())
    return name


def write_movements_excel(history, contracts, path, as_of=None, ids=None, scope_label="All contracts",
                          extension=None, ledger_start=None):
    """Write the workbook; ``history`` should already include ``extension`` rows if they are wanted.

    ``ids``: limit to these contract ids (None = every contract in the ledger). ``extension``: the rows
    ``extend_to_storage`` returned (only used to count and to mark them). Returns a dict with the
    counts written.
    """
    from openpyxl import Workbook
    from openpyxl.chart import LineChart, Reference
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter as L
    from openpyxl.worksheet.table import Table, TableStyleInfo

    from .xlsx_cache import store_formula_results

    contracts = contracts or {}
    rows_all = _rows(history)
    if ledger_start is None:
        ledger_start = min((r["date"] for r in rows_all if r.get("capture_reason") != "before_first_record"), default="")
    blocks = day_blocks(rows_all, ids)
    trails = contract_trails(rows_all, ids)
    as_of = as_of or (blocks[-1]["date"] if blocks else dt.date.today().isoformat())
    last_day = blocks[-1]["date"] if blocks else ""
    open_now = {cid for cid in trails if trails[cid][-1]["rec"]["date"] == last_day
                and str(contracts.get(cid, {}).get("status") or "Open").lower() != "closed"}

    wb = Workbook()
    cache = {}

    def put(ws, r, c, v, fmt=None, bold=False, color=None, fill=None, italic=False, size=None, wrap=False):
        cell = ws.cell(r, c, v)
        if fmt:
            cell.number_format = fmt
        if bold or color or italic or size:
            cell.font = Font(bold=bold, color=color, italic=italic, size=size)
        if fill:
            cell.fill = PatternFill("solid", fgColor=fill)
        if wrap:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        return cell

    def f(ws, r, c, formula, value, fmt=None, **kw):
        put(ws, r, c, formula, fmt, **kw)
        cache.setdefault(ws.title, {})[f"{L(c)}{r}"] = "" if value is None else value

    def title(ws, text, sub):
        put(ws, 1, 1, text, bold=True, size=15, color=NAVY)
        put(ws, 2, 1, sub, italic=True, color=GREY)

    def table(ws, name, heads, widths, n, hr=4, style="TableStyleMedium2"):
        for i, h in enumerate(heads, start=1):
            c = ws.cell(hr, i, h)
            c.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[L(i)].width = widths[i - 1]
        ws.row_dimensions[hr].height = 32
        t = Table(displayName=name, ref=f"A{hr}:{L(len(heads))}{hr + max(n, 1)}")
        t.tableStyleInfo = TableStyleInfo(name=style, showRowStripes=True)
        ws.add_table(t)

    def signs(ws, ref):
        ws.conditional_formatting.add(ref, CellIsRule(operator="lessThan", formula=["0"], font=Font(color=RED)))
        ws.conditional_formatting.add(ref, CellIsRule(operator="greaterThan", formula=["0"], font=Font(color=GREEN)))

    n_ext = len(extension or [])
    period = f"{blocks[0]['date']} → {last_day}" if blocks else "—"
    sub = (f"{scope_label} · {period} · as of {as_of} · ledger started {ledger_start or '—'}"
           + (f" · {n_ext} contract-days before entry rebuilt back to the storage start" if n_ext else ""))

    # ── Summary ──
    ws = wb.active
    ws.title = "Summary"
    title(ws, "Open MTM — every daily movement since storage", sub)
    notes = [
        "How to read it: each day is compared with the previous stored day, exactly like the Home table "
        "\"Daily Open MTM Movement\". Δ Sav/MT is split into four parts that add up to it (EGP/MT):",
        "from CBOT = −(CIF today − CIF prior) × FX prior · from FX = −CIF today × (FX today − FX prior), 0 under Form 4 · "
        "from Local = local today − local prior · Other = the rest (discharge, clearance, freight, fees).",
        "Rebuilt = a day the app was not opened, or a day between the storage start and the day the contract was entered "
        "in the app; rebuilt from the stored CBOT close, FX history and local price, with the fees and tonnes of the "
        "nearest stored record. Live = recorded by the app that day.",
        "Book totals before the ledger started only hold the contracts entered later, so they are partial.",
    ]
    for i, t in enumerate(notes):
        put(ws, 3 + i, 1, t, italic=True, color=GREY)
    heads = ["Ref", "Contract ID", "Commodity", "Supplier", "Status", "Storage start", "Entered app", "First day",
             "Last day", "Days", "Rebuilt days", "MT", "CBOT first", "CBOT last", "Δ CBOT", "Sav/MT first", "Sav/MT last",
             "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", "Total first", "Total last", "Δ Total", "Sheet"]
    hr = 8
    order = sorted(trails, key=lambda k: (k not in open_now, _base(trails[k][-1]["rec"]), trails[k][0]["rec"]["date"],
                                          trails[k][-1]["rec"].get("contract_ref") or k))
    used = {"summary", "book by day", "daily movement", "contract trail"}
    sheets = {cid: sheet_name(trails[cid][-1]["rec"].get("contract_ref") or cid, used) for cid in order if cid in open_now}
    table(ws, "ContractSummary", heads, [16, 10, 10, 16, 8, 11, 11, 11, 11, 7, 8, 9, 9, 9, 8, 10, 10, 10, 9, 9, 9, 9,
                                         13, 13, 13, 14], len(order), hr=hr)
    for i, cid in enumerate(order):
        r = hr + 1 + i
        tr = trails[cid]
        f0, f1 = tr[0]["rec"], tr[-1]["rec"]
        c = contracts.get(cid, {})
        parts = {k: sum(x["why"][k] for x in tr if x["why"].get(k) is not None) for k in PARTS}
        vals = [f1.get("contract_ref") or cid, cid, _base(f1), f1.get("supplier") or c.get("supplier") or "",
                "Open" if cid in open_now else (c.get("status") or "Closed"), storage_start(c),
                str(c.get("created_ts") or "")[:10], f0["date"], f1["date"], len(tr),
                sum(1 for x in tr if x["rec"].get("mode") == "RECONSTRUCTED"), _n(f1.get("qty_mt")),
                _n(f0.get("cbot_price")), _n(f1.get("cbot_price")), _sub(_n(f1.get("cbot_price")), _n(f0.get("cbot_price"))),
                _n(f0.get("saving_egp_mt")), _n(f1.get("saving_egp_mt")),
                _sub(_n(f1.get("saving_egp_mt")), _n(f0.get("saving_egp_mt"))),
                *[parts[k] for k in PARTS], _n(f0.get("total_saving_egp")), _n(f1.get("total_saving_egp")),
                _sub(_n(f1.get("total_saving_egp")), _n(f0.get("total_saving_egp"))), sheets.get(cid, "")]
        fmts = [None] * 11 + [F0, F2, F2, S2, F0, F0, S0, S0, S0, S0, S0, F0, F0, S0, None]
        for j, v in enumerate(vals, start=1):
            put(ws, r, j, v, fmts[j - 1])
        if cid in sheets:
            ws.cell(r, 26).hyperlink = f"#'{sheets[cid]}'!A1"
            ws.cell(r, 26).font = Font(color="1F5FBF", underline="single")
    if order:
        signs(ws, f"O{hr + 1}:V{hr + len(order)}")
        signs(ws, f"Y{hr + 1}:Y{hr + len(order)}")
    ws.freeze_panes = f"B{hr + 1}"

    # ── Book by Day ──
    wsb = wb.create_sheet("Book by Day")
    title(wsb, "Open book by day — the Home summary line for every day", sub)
    bases = sorted({b for blk in blocks for b in blk["book"]["cbot"]})
    heads = ["Date", "Prior date", "Record", "Prior record", "Contracts", "Contracts prior", "MT", "Open MTM prior",
             "Open MTM today", "Δ Open MTM", "Sav/MT prior", "Sav/MT today", "Δ Sav/MT", "from CBOT", "from FX",
             "from Local", "Other", "Cumulative Δ Open MTM"]
    for b in bases:
        heads += [f"{b} prior", f"{b} today", f"Δ {b}"]
    heads += ["Partial book", "Old quotes", "Summary (as on Home)"]
    table(wsb, "BookByDay", heads, [11, 11, 8, 8, 8, 8, 10, 14, 14, 13, 9, 9, 9, 9, 8, 9, 8, 14] + [9, 9, 8] * len(bases)
          + [9, 24, 120], len(blocks))
    for i, blk in enumerate(blocks):
        r, b = 5 + i, blk["book"]
        put(wsb, r, 1, blk["date"]); put(wsb, r, 2, blk["prior_date"]); put(wsb, r, 3, b["mode"]); put(wsb, r, 4, b["prior_mode"])
        put(wsb, r, 5, b["contracts"]); put(wsb, r, 6, b["contracts_prior"] if blk["prior_date"] else None)
        put(wsb, r, 7, b["mt"], F0); put(wsb, r, 8, b["total_prior"], F0); put(wsb, r, 9, b["total"], F0)
        f(wsb, r, 10, f'=IF(AND(ISNUMBER(H{r}),ISNUMBER(I{r})),I{r}-H{r},"")', b["d_total"], S0)
        put(wsb, r, 11, b["sav_prior"], F0); put(wsb, r, 12, b["sav"], F0)
        f(wsb, r, 13, f'=IF(AND(ISNUMBER(K{r}),ISNUMBER(L{r})),L{r}-K{r},"")', b["d_sav"], S0)
        for j, k in enumerate(PARTS):
            put(wsb, r, 14 + j, b[k], S0)
        cum = sum(x["book"]["d_total"] or 0.0 for x in blocks[:i + 1])
        f(wsb, r, 18, f"=SUM($J$5:J{r})", cum, S0)
        col = 19
        for base in bases:
            t, p = b["cbot"].get(base, (None, None))
            put(wsb, r, col, p, F2); put(wsb, r, col + 1, t, F2)
            f(wsb, r, col + 2, f'=IF(AND(ISNUMBER({L(col)}{r}),ISNUMBER({L(col + 1)}{r})),{L(col + 1)}{r}-{L(col)}{r},"")',
              _sub(t, p), S2)
            col += 3
        put(wsb, r, col, "yes" if ledger_start and blk["date"] < ledger_start else "")
        put(wsb, r, col + 1, b["stale"]); put(wsb, r, col + 2, b["text"])
        if b["mode"] != "Live":
            for j in (1, 3):
                wsb.cell(r, j).fill = PatternFill("solid", fgColor=REBUILT_FILL)
    if blocks:
        last = 4 + len(blocks)
        signs(wsb, f"J5:J{last}"); signs(wsb, f"M5:R{last}")
        ch = LineChart()
        ch.title, ch.height, ch.width = "Open MTM edge (EGP)", 8, 26
        ch.add_data(Reference(wsb, min_col=9, min_row=4, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(wsb, min_col=1, min_row=5, max_row=last))
        ch.y_axis.numFmt = "#,##0"
        ch.legend = None
        wsb.add_chart(ch, f"A{last + 3}")
    wsb.freeze_panes = "B5"

    # ── Daily Movement ──
    wsd = wb.create_sheet("Daily Movement")
    title(wsd, "Daily Open MTM Movement — every day, as on Home",
          sub + " · newest day first · TOTAL rows are the open book of that day (Row = TOTAL to filter them)")
    heads = ["Date", "Prior date", "Row", "Ref", "Commodity", "Supplier", "Flag", "MT", "CBOT Today", "CBOT Prior", "Δ CBOT",
             "Sav/MT Today", "Sav/MT Prior", "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", "Total Today",
             "Total Prior", "Δ Total", "CIF Today", "CIF Prior", "FX Today", "FX Prior", "FX source", "Local Today",
             "Local Prior", "Local date", "Own cost", "Record", "Old quotes", "How it was rebuilt"]
    lines = []
    for blk in reversed(blocks):
        b = blk["book"]
        for x in blk["rows"]:
            lines.append(("row", x))
        lines.append(("total", blk))
    table(wsd, "DailyMovement", heads, [11, 11, 7, 18, 10, 14, 7, 9, 9, 9, 8, 10, 10, 9, 9, 8, 9, 8, 13, 13, 12, 9, 9,
                                        8, 8, 16, 10, 10, 11, 10, 8, 22, 60], len(lines))
    fm = [None] * 7 + [F0, F2, F2, S2, F0, F0, S0, S0, S0, S0, S0, F0, F0, S0, F2, F2, F4, F4, None, F0, F0, None, F0,
                       None, None, None]
    for i, (kind, x) in enumerate(lines):
        r = 5 + i
        if kind == "row":
            vals = [x["date"], x["prior_date"], "Contract", x["ref"], x["commodity"], x["supplier"], x["flag"], x["mt"],
                    x["cbot"], x["cbot_prior"], x["d_cbot"], x["sav"], x["sav_prior"], x["d_sav"],
                    *[x[k] for k in PARTS], x["total"], x["total_prior"], x["d_total"], x["cif"], x["cif_prior"],
                    x["fx"], x["fx_prior"], x["fx_source"], x["local"], x["local_prior"], x["local_date"], x["own"],
                    x["mode"], x["stale"], x["note"]]
            for j, v in enumerate(vals, start=1):
                put(wsd, r, j, v, fm[j - 1])
            if x["mode"] == "Rebuilt":
                wsd.cell(r, 31).fill = PatternFill("solid", fgColor=REBUILT_FILL)
            if x["flag"]:
                wsd.cell(r, 7).fill = PatternFill("solid", fgColor=NEW_FILL)
        else:
            blk, b = x, x["book"]
            vals = [blk["date"], blk["prior_date"], "TOTAL",
                    f"TOTAL OPEN BOOK ({b['contracts']} today / {b['contracts_prior']} prior)", "", "", "", b["mt"],
                    None, None, None, b["sav"], b["sav_prior"], b["d_sav"], *[b[k] for k in PARTS],
                    b["total"], b["total_prior"], b["d_total"]] + [None] * 9 + [b["mode"], b["stale"], b["text"]]
            for j, v in enumerate(vals, start=1):
                put(wsd, r, j, v, fm[j - 1], bold=True, fill=TOTAL_FILL)
    if lines:
        signs(wsd, f"K5:K{4 + len(lines)}"); signs(wsd, f"N5:R{4 + len(lines)}"); signs(wsd, f"U5:U{4 + len(lines)}")
    wsd.freeze_panes = "E5"

    # ── Contract Trail ──
    wst = wb.create_sheet("Contract Trail")
    title(wst, "Contract trail — each contract against its own previous day", sub)
    heads = ["Ref", "Contract ID", "Commodity", "Date", "Prior date", "Record", "MT", "CBOT", "Δ CBOT", "CIF $/MT", "FX",
             "Local", "Local date", "Own cost", "Sav/MT", "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other",
             "Total EGP", "Δ Total", "Cumulative Δ Sav/MT", "Old quotes", "How it was rebuilt"]
    tl = [(cid, x) for cid in order for x in trails[cid]]
    table(wst, "ContractTrail", heads, [16, 10, 10, 11, 11, 8, 9, 9, 8, 9, 8, 10, 11, 10, 10, 9, 9, 8, 9, 8, 13, 12, 11,
                                        22, 60], len(tl))
    fm = [None] * 6 + [F0, F2, S2, F2, F4, F0, None, F0, F0, S0, S0, S0, S0, S0, F0, S0, S0, None, None]
    first_sav = {}
    for i, (cid, x) in enumerate(tl):
        r, rec, p = 5 + i, x["rec"], x["prior"]
        first_sav.setdefault(cid, _n(rec.get("saving_egp_mt")))
        vals = [rec.get("contract_ref") or cid, cid, _base(rec), rec["date"], (p or {}).get("date", ""),
                "Rebuilt" if rec.get("mode") == "RECONSTRUCTED" else "Live", _n(rec.get("qty_mt")), _n(rec.get("cbot_price")),
                _sub(_n(rec.get("cbot_price")), _n((p or {}).get("cbot_price"))), _n(rec.get("cif_usd_mt")), _n(rec.get("fx")),
                _n(rec.get("local_egp_mt")), rec.get("local_price_date", ""), _n(rec.get("own_after_egp_mt")),
                _n(rec.get("saving_egp_mt")), x["why"].get("change"), *[x["why"].get(k) for k in PARTS],
                _n(rec.get("total_saving_egp")), _sub(_n(rec.get("total_saving_egp")), _n((p or {}).get("total_saving_egp"))),
                _sub(_n(rec.get("saving_egp_mt")), first_sav[cid]), "; ".join(rec.get("stale_quotes") or []),
                rec.get("reconstructed_from", "")]
        for j, v in enumerate(vals, start=1):
            put(wst, r, j, v, fm[j - 1])
        if rec.get("mode") == "RECONSTRUCTED":
            wst.cell(r, 6).fill = PatternFill("solid", fgColor=REBUILT_FILL)
    if tl:
        signs(wst, f"I5:I{4 + len(tl)}"); signs(wst, f"P5:T{4 + len(tl)}"); signs(wst, f"V5:W{4 + len(tl)}")
    wst.freeze_panes = "D5"

    # ── one sheet per open contract, movement columns as formulas ──
    for cid, name in sheets.items():
        tr = trails[cid]
        last_rec = tr[-1]["rec"]
        c = contracts.get(cid, {})
        w = wb.create_sheet(name)
        title(w, f"{last_rec.get('contract_ref') or cid} · {_base(last_rec)} · {last_rec.get('supplier') or c.get('supplier') or ''}",
              f"Contract {cid} · storage start {storage_start(c) or '—'} · entered {str(c.get('created_ts') or '')[:10] or '—'}"
              f" · {len(tr)} days · movement columns are formulas over the row above (EGP/MT unless EGP)")
        heads = ["Date", "Prior date", "Record", "MT", "CBOT", "Δ CBOT", "CIF $/MT", "FX", "Local", "Local date", "Own cost",
                 "Sav/MT", "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", "Total EGP", "Δ Total EGP",
                 "Cumulative Δ Sav/MT", "Old quotes", "How it was rebuilt"]
        table(w, "T_" + re.sub(r"\W", "_", cid), heads, [11, 11, 8, 9, 9, 8, 9, 8, 10, 11, 10, 10, 9, 9, 8, 9, 8, 13, 12,
                                                        11, 22, 60], len(tr))
        s0 = _n(tr[0]["rec"].get("saving_egp_mt"))
        for i, x in enumerate(tr):
            r, rec, p, a = 5 + i, x["rec"], x["prior"], x["why"]
            g = lambda k: _n(rec.get(k))
            put(w, r, 1, rec["date"]); put(w, r, 2, (p or {}).get("date", ""))
            put(w, r, 3, "Rebuilt" if rec.get("mode") == "RECONSTRUCTED" else "Live",
                fill=REBUILT_FILL if rec.get("mode") == "RECONSTRUCTED" else None)
            put(w, r, 4, g("qty_mt"), F0); put(w, r, 5, g("cbot_price"), F2); put(w, r, 7, g("cif_usd_mt"), F2)
            put(w, r, 8, g("fx"), F4); put(w, r, 9, g("local_egp_mt"), F0); put(w, r, 10, rec.get("local_price_date", ""))
            put(w, r, 11, g("own_after_egp_mt"), F0); put(w, r, 12, g("saving_egp_mt"), F0); put(w, r, 18, g("total_saving_egp"), F0)
            put(w, r, 21, "; ".join(rec.get("stale_quotes") or [])); put(w, r, 22, rec.get("reconstructed_from", ""))
            if i == 0:
                for col in (6, 13, 14, 15, 16, 17, 19):
                    put(w, r, col, None)
            else:
                q = r - 1
                ok = lambda *cells: "AND(" + ",".join(f"ISNUMBER({cl})" for cl in cells) + ")"
                f(w, r, 6, f'=IF({ok(f"E{r}", f"E{q}")},E{r}-E{q},"")', _sub(g("cbot_price"), _n(p.get("cbot_price"))), S2)
                f(w, r, 13, f'=IF({ok(f"L{r}", f"L{q}")},L{r}-L{q},"")', a.get("change"), S0)
                f(w, r, 14, f'=IF({ok(f"G{r}", f"G{q}", f"H{q}")},-(G{r}-G{q})*H{q},"")', a.get("from_cbot"), S0)
                f(w, r, 15, f'=IF({ok(f"G{r}", f"H{r}", f"H{q}")},-G{r}*(H{r}-H{q}),"")', a.get("from_fx"), S0)
                f(w, r, 16, f'=IF({ok(f"I{r}", f"I{q}")},I{r}-I{q},"")', a.get("from_local"), S0)
                f(w, r, 17, f'=IF({ok(f"M{r}", f"N{r}", f"O{r}", f"P{r}")},M{r}-N{r}-O{r}-P{r},"")', a.get("other"), S0)
                f(w, r, 19, f'=IF({ok(f"R{r}", f"R{q}")},R{r}-R{q},"")',
                  _sub(g("total_saving_egp"), _n(p.get("total_saving_egp"))), S0)
            f(w, r, 20, f'=IF({"AND(ISNUMBER(L%d),ISNUMBER($L$5))" % r},L{r}-$L$5,"")', _sub(g("saving_egp_mt"), s0), S0)
        last = 4 + len(tr)
        tr_row = last + 2
        put(w, tr_row, 1, "Since the first day", bold=True, fill=TOTAL_FILL)
        for col in range(2, 21):
            w.cell(tr_row, col).fill = PatternFill("solid", fgColor=TOTAL_FILL)
        e0, e1 = _n(tr[0]["rec"].get("cbot_price")), _n(last_rec.get("cbot_price"))
        f(w, tr_row, 6, f'=IF(AND(ISNUMBER(E{last}),ISNUMBER(E5)),E{last}-E5,"")', _sub(e1, e0), S2, bold=True)
        f(w, tr_row, 13, f'=IF(AND(ISNUMBER(L{last}),ISNUMBER(L5)),L{last}-L5,"")',
          _sub(_n(last_rec.get("saving_egp_mt")), s0), S0, bold=True)
        for col, k in zip((14, 15, 16, 17), PARTS):
            f(w, tr_row, col, f"=SUM({L(col)}5:{L(col)}{last})", sum(x["why"][k] for x in tr if x["why"].get(k) is not None),
              S0, bold=True)
        f(w, tr_row, 19, f"=SUM(S5:S{last})", sum((_sub(_n(x["rec"].get("total_saving_egp")), _n((x["prior"] or {}).get("total_saving_egp"))) or 0.0)
                                                  for x in tr[1:]), S0, bold=True)
        put(w, tr_row + 1, 1, "The four parts add up to Δ Sav/MT on every row; their sums add up to the change since "
                              "the first day when no day is missing a price.", italic=True, color=GREY)
        signs(w, f"F5:F{tr_row}"); signs(w, f"M5:Q{tr_row}"); signs(w, f"S5:T{tr_row}")
        w.freeze_panes = "B5"
        if len(tr) > 1:
            ch = LineChart()
            ch.title, ch.height, ch.width = "Sav/MT (EGP)", 7, 22
            ch.add_data(Reference(w, min_col=12, min_row=4, max_row=last), titles_from_data=True)
            ch.set_categories(Reference(w, min_col=1, min_row=5, max_row=last))
            ch.legend = None
            w.add_chart(ch, f"A{tr_row + 3}")

    for s in wb.worksheets:
        s.page_setup.orientation = "landscape"
        s.page_setup.paperSize = s.PAPERSIZE_A4
        s.sheet_properties.pageSetUpPr.fitToPage = True
        s.page_setup.fitToWidth, s.page_setup.fitToHeight = 1, 0
        s.oddFooter.center.text = "&A · page &P of &N"
    wb.calculation.fullCalcOnLoad = True
    wb.save(path)
    store_formula_results(path, cache)
    return {"days": len(blocks), "contracts": len(trails), "open_sheets": len(sheets), "movement_rows": len(lines),
            "rebuilt_before_entry": n_ext, "first_day": blocks[0]["date"] if blocks else "", "last_day": last_day}
