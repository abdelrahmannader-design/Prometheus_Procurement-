"""Receiving end dates typed into a CBOT workbook, read back into the contracts (their ``receiving_end``).

The CBOT export (prometheus_core.cbot_overview) shows each contract's receiving period; people fill the end
in the workbook, either in the "Receiving end" column of the Receiving date sheet or in a block header on the
Fixed / Not fixed consumption sheets ("received 2026-10-26 (end 2026-10-28)" or "received X to Y"). This
module finds those dates and matches them to the app's contracts: by the exact contract name, else by a
contract whose name and the workbook's differ only by a suffix (".1" or " 2000" added in the workbook, "-COPY"
in the app) and that has the same receiving date. Nothing is matched on a guess: ambiguous or unmatched rows are reported, not applied.
"""

from __future__ import annotations

import datetime as dt
import re

_HEAD = re.compile(r"  ·  received (\d{4}-\d{2}-\d{2})\s*(?:\(\s*end\s*(\d{4}-\d{2}-\d{2})\s*\)|to (\d{4}-\d{2}-\d{2}))")
_SEP = (" ", ".", "-", "_", "/", "(")


def _iso(v):
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return v.strip()
    return ""


def _extends(longer, shorter):
    """``longer`` is ``shorter`` plus a suffix after a separator ('TRADE#SC-33039.1', '460/20050010-COPY')."""
    return longer != shorter and longer.startswith(shorter) and longer[len(shorter):len(shorter) + 1] in _SEP


def norm(name):
    """A contract name as compared: no warning marks, single spaces, upper case."""
    return re.sub(r"\s+", " ", str(name or "").replace("⚠", "")).strip().upper()


def read_end_dates(path):
    """[{contract, start, end, where}] from a CBOT workbook. The Receiving date sheet wins over a block header
    for the same contract; a non-date end ("Still receiving") is not a date and is skipped."""
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    found = {}
    if "Receiving date" in wb.sheetnames:
        ws = wb["Receiving date"]
        head = next((r for r in range(1, min(ws.max_row, 12) + 1)
                     if any(str(ws.cell(r, c).value or "").strip() == "Receiving end" for c in range(1, ws.max_column + 1))),
                    None)
        if head:
            cols = {str(ws.cell(head, c).value or "").strip(): c for c in range(1, ws.max_column + 1)}
            c_name, c_start, c_end = cols.get("Contract", 1), cols.get("Receiving date", 4), cols["Receiving end"]
            for r in range(head + 1, ws.max_row + 1):
                name, end = ws.cell(r, c_name).value, _iso(ws.cell(r, c_end).value)
                if name and end:
                    found[norm(name)] = {"contract": str(name).strip(), "start": _iso(ws.cell(r, c_start).value),
                                         "end": end, "where": f"Receiving date!{ws.cell(r, c_end).coordinate}"}
    for sheet in ("Fixed consumption", "Not fixed consumption"):
        if sheet not in wb.sheetnames:
            continue
        ws = wb[sheet]
        for r in range(1, ws.max_row + 1):
            t = ws.cell(r, 1).value
            m = _HEAD.search(t) if isinstance(t, str) else None
            if not m:
                continue
            name = t.split("  ·  ")[0].strip()
            if norm(name) not in found:
                found[norm(name)] = {"contract": name, "start": m.group(1), "end": m.group(2) or m.group(3),
                                     "where": f"{sheet}!A{r}"}
    return list(found.values())


def plan_updates(contracts, found):
    """One line per workbook date: {contract, cid, app_name, start, app_start, end, current, action, note}.
    action: 'set' | 'replace' | 'same' | 'skip'."""
    by_name = {}
    for cid, c in (contracts or {}).items():
        if isinstance(c, dict):
            by_name.setdefault(norm(c.get("name") or cid), []).append(cid)
    out = []
    for f in found:
        key, start, end = norm(f["contract"]), f.get("start") or "", f["end"]
        cands = by_name.get(key, [])
        how = "same name"
        if len(cands) > 1 and start:
            cands = [cid for cid in cands if str(contracts[cid].get("storage_start") or "")[:10] == start]
        if not cands:            # a suffix on one side (".1" in the workbook, "-COPY" in the app): same date needed
            how = "name + same receiving date"
            cands = [cid for name, ids in by_name.items() for cid in ids
                     if (_extends(key, name) or _extends(name, key)) and start
                     and str(contracts[cid].get("storage_start") or "")[:10] == start]
        line = {"contract": f["contract"], "start": start, "end": end, "where": f.get("where", ""), "cid": "",
                "app_name": "", "app_start": "", "current": "", "action": "skip", "note": ""}
        if len(cands) != 1:
            line["note"] = "no contract in the app matches" if not cands else \
                f"{len(cands)} contracts match — enter it on the contract"
            out.append(line)
            continue
        cid = cands[0]
        c = contracts[cid]
        app_start, current = str(c.get("storage_start") or "")[:10], str(c.get("receiving_end") or "")[:10]
        line.update(cid=cid, app_name=c.get("name") or cid, app_start=app_start, current=current)
        if app_start and end < app_start:
            line["note"] = f"end {end} is before the app's receiving date {app_start}"
        elif current == end:
            line.update(action="same", note="already entered")
        else:
            line.update(action="replace" if current else "set",
                        note=how + (f" · the app's receiving date is {app_start or 'empty'}" if app_start != start else ""))
        out.append(line)
    return out


def apply_updates(contracts, plan, stamp=None):
    """Write the 'set' / 'replace' lines into the contracts; return how many changed."""
    n = 0
    for line in plan:
        if line["action"] in ("set", "replace") and line["cid"] in contracts:
            c = contracts[line["cid"]]
            c["receiving_end"] = line["end"]
            if stamp:
                c["updated_ts"] = stamp
            n += 1
    return n
