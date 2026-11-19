"""'MTM DAILY & LOCKED': the Home MTM tables on one sheet of the CBOT export, with each contract's receiving period.

Three sections, each the table the app exports on its own (prometheus_core.mtm_daily_excel and
prometheus_core.open_mtm_excel), with "Receiving date" and "Receiving end" inserted after Ref as links to the
Receiving date sheet:

* Changes From Prior: the Daily Open MTM Movement table (today against the previous stored day);
* Savings In The Date Of Receiving Commodity: the Open Mark-to-Market table in Locked mode (the contract's FX
  and the local price of its receiving date), excl. transport;
* LIVE V LIVE: the same table in Live mode (today's FX and local price), excl. transport.

The tables are written by their own writers and moved here cell by cell; every formula keeps working (its
references are moved with it) and keeps its cached value.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
from copy import copy

SHEET = "MTM DAILY & LOCKED"
RECV_SHEET = "Receiving date"
EPOCH = dt.datetime(1899, 12, 30)
_REF = re.compile(r"(\$?)([A-Z]{1,3})(\$?)(\d+)")


def _col_num(s):
    n = 0
    for ch in s:
        n = n * 26 + ord(ch) - 64
    return n


def _col_str(n):
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def shift_formula(formula, drow, insert_at=2, width=2):
    """Move a formula with its table: every reference without a sheet name goes ``drow`` rows down, and columns
    from ``insert_at`` on move ``width`` to the right (two columns inserted after A). Absolute references move
    too, as they would when the whole table is cut and pasted."""
    from openpyxl.formula.tokenizer import Token, Tokenizer

    tok = Tokenizer(formula)
    out = []
    for t in tok.items:
        v = t.value
        if t.type == Token.OPERAND and t.subtype == Token.RANGE and "!" not in v:
            def mv(m):
                c, r = _col_num(m.group(2)), int(m.group(4))
                c = c + width if c >= insert_at else c
                return f"{m.group(1)}{_col_str(c)}{m.group(3)}{r + drow}"
            v = _REF.sub(mv, v)
        out.append(v)
    return "=" + "".join(out)


def _serial(v):
    if isinstance(v, dt.datetime):
        return (v - EPOCH).days + (v - EPOCH).seconds / 86400
    if isinstance(v, dt.date):
        return (dt.datetime(v.year, v.month, v.day) - EPOCH).days
    return "" if v is None else v


def _render(kind, data):
    """Write one table with its own writer into a temporary file; return (worksheet, cache, result)."""
    import openpyxl

    from .mtm_daily_excel import write_daily_mtm
    from .open_mtm_excel import write_open_mtm

    fd, path = tempfile.mkstemp(suffix=".xlsx")
    os.close(fd)
    try:
        if kind == "daily":
            res = write_daily_mtm(path, data["rows"], today=data.get("today") or "", prior=data.get("prior") or "",
                                  commodity=data.get("commodity") or "ALL", summary="")
        else:
            res = write_open_mtm(path, data["groups"], view=data.get("view") or "excl", today=data.get("today") or "",
                                 commodity=data.get("commodity") or "ALL", fx_mode=data.get("fx_mode") or "live")
        wb = openpyxl.load_workbook(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return wb.active, res.get("cache") or {}, res


def write_mtm_sheet(wb, cache, daily=None, locked=None, live=None, recv_rows=None, recv_values=None, index=0,
                    name=SHEET, recv_sheet=RECV_SHEET):
    """Add the sheet at ``index``. ``daily``: {rows, today, prior, commodity} (rows as for write_daily_mtm, each
    with contract_id); ``locked`` / ``live``: {groups, today, commodity, fx_mode, view} (as for write_open_mtm,
    rows with contract_id). ``recv_rows``: {contract id: row on the Receiving date sheet}; ``recv_values``:
    {(contract id, 'date' | 'end'): value} for the cached results. Returns {cache, sections}."""
    from openpyxl.styles import Alignment, Font

    recv_rows, recv_values = recv_rows or {}, recv_values or {}
    ws = wb.create_sheet(name, index)
    C = cache.setdefault(name, {})
    widths = {}
    sections = []
    r_out = 1

    def link(row, cid, src_head):
        """B and C: the contract's receiving date and receiving end, linked to the Receiving date sheet."""
        rr = recv_rows.get(cid)
        for col, key, src_col in ((2, "date", "D"), (3, "end", "Q")):
            x = ws.cell(row, col)
            x.border = copy(src_head.border)
            x.alignment = Alignment(horizontal="center", vertical="center")
            if rr:
                x.value = f"='{recv_sheet}'!{src_col}{rr}"
                v = recv_values.get((cid, key))
                C[x.coordinate] = _serial(v)
                x.number_format = "dd mmm yyyy"
            else:
                x.value = "—"
                x.font = Font(color="8A8F98")

    def section(title, note, kind, data, head_row, body_from, body_to_fn, cid_of_row):
        nonlocal r_out
        t = ws.cell(r_out, 1, title)
        t.font = Font(bold=True, size=12, color="1F3A5F")
        n = ws.cell(r_out, 4, note)
        n.font = Font(italic=True, size=9, color="555555")
        r_out += 1
        if not data or not (data.get("rows") if kind == "daily" else any(r for _, r in data.get("groups") or [])):
            ws.cell(r_out, 1, "No rows: refresh Home first (no Open-MTM record is stored for today)."
                    if kind == "daily" else "No open contract.").font = Font(italic=True, color="8A8F98")
            sections.append({"title": title, "rows": 0})
            r_out += 2
            return
        src, src_cache, res = _render(kind, data)
        body_to = body_to_fn(res)
        rows = [head_row] + list(range(body_from, body_to + 1))
        for i, sr in enumerate(rows):
            dr = r_out + i
            drow = dr - sr
            for c in range(1, src.max_column + 1):
                s_cell = src.cell(sr, c)
                dc = c if c == 1 else c + 2
                d_cell = ws.cell(dr, dc)
                v = s_cell.value
                if isinstance(v, str) and v.startswith("="):
                    d_cell.value = shift_formula(v, drow)
                    if s_cell.coordinate in src_cache:
                        C[d_cell.coordinate] = src_cache[s_cell.coordinate]
                else:
                    d_cell.value = v
                if s_cell.has_style:
                    d_cell.font, d_cell.fill = copy(s_cell.font), copy(s_cell.fill)
                    d_cell.border, d_cell.alignment = copy(s_cell.border), copy(s_cell.alignment)
                    d_cell.number_format = s_cell.number_format
            if src.row_dimensions[sr].height:
                ws.row_dimensions[dr].height = src.row_dimensions[sr].height
            if i == 0:                                    # the two inserted headings
                for col, text in ((2, "Receiving date"), (3, "Receiving end")):
                    h = ws.cell(dr, col, text)
                    s_h = src.cell(sr, 2)
                    h.font, h.fill, h.border = copy(s_h.font), copy(s_h.fill), copy(s_h.border)
                    h.alignment = copy(s_h.alignment)
            else:
                cid = cid_of_row(i - 1)
                if cid:
                    link(dr, cid, src.cell(sr, 2))
                else:                                     # group / total rows: carry their fill across B:C
                    for col in (2, 3):
                        ws.cell(dr, col).fill = copy(src.cell(sr, 2).fill)
                        ws.cell(dr, col).border = copy(src.cell(sr, 2).border)
        for k, d in src.column_dimensions.items():
            c = _col_num(k)
            dc = c if c == 1 else c + 2
            if d.width:
                widths[dc] = max(widths.get(dc, 0), d.width)
        sections.append({"title": title, "rows": len(rows) - 1, "top": r_out, "result": res})
        r_out += len(rows) + 1

    if daily is not None:
        drows = daily.get("rows") or []
        section("Changes From Prior :-", f"Today {daily.get('today') or '—'} vs the previous stored day "
                f"{daily.get('prior') or '—'} · the parts (from CBOT, FX, Local, Other) add up to Δ Sav/MT (EGP/MT)",
                "daily", daily, 5, 6, lambda res: res["total_row"],
                lambda i: (drows[i].get("contract_id") if i < len(drows) else None))
    for title, note, data in (
            ("Savings In The Date Of Receiving Commodity",
             "Locked: the contract's FX and the local price of its receiving date · excl. transport", locked),
            ("LIVE V LIVE", "Live: today's FX and local price · excl. transport", live)):
        if data is None:
            continue
        order = []
        for _comm, rows_ in data.get("groups") or []:
            order.append(None)
            order.extend(x.get("contract_id") for x in rows_)
        section(title, note, "open", data, 4, 5, lambda res: res["total_row"] - 1,
                lambda i, order=order: order[i] if i < len(order) else None)
    for c, w in widths.items():
        ws.column_dimensions[_col_str(c)].width = w
    ws.column_dimensions["B"].width, ws.column_dimensions["C"].width = 14, 15
    ws.sheet_view.showGridLines = False
    return {"cache": C, "sections": sections}
