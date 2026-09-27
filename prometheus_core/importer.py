"""Excel import: one template workbook, one sheet per data type.

Pure logic (no Tk): header matching, row validation and the upsert plan
(NEW / UPDATE / SAME / ERROR per row) against the data already saved.
Nothing is written here — the app shows the plan first and applies it only
after the user confirms.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import Any

from .numbers import to_float

IMPORT_ENGINE_VERSION = "1.0"

# sheet → [(field, required, kind, help)]
#   kind: text | upper | date | num | int | choice:<A|B>
IMPORT_SHEETS: dict[str, list[tuple[str, bool, str, str]]] = {
    "Contracts": [
        ("contract_id", False, "text", "Leave empty for a new contract; an existing ID updates that contract"),
        ("contract_ref", False, "text", "Your contract number"),
        ("name", True, "text", "Short name"),
        ("supplier", True, "text", ""),
        ("commodity", True, "upper", "e.g. CORN, SBM, SOYBEAN, CORN-BRZ"),
        ("origin", False, "upper", "e.g. BRZ, ARG, UKR, USA"),
        ("status", False, "choice:Open|Closed", "Open (default) or Closed"),
        ("qty_mt", True, "num", "Quantity MT"),
        ("contract_date", False, "date", ""),
        ("delivery_date", False, "date", ""),
        ("storage_start", False, "date", ""),
        ("pricing_date", False, "date", ""),
        ("futures_month", False, "text", "e.g. Dec 2026"),
        ("premium_cents", False, "num", "Premium over CBOT (cents or USD/short ton for SBM)"),
        ("cif_usd_mt", False, "num", "Fixed CIF USD/MT (priced contracts)"),
        ("delivery_fx", False, "num", "FX at delivery"),
        ("form4_fx", False, "num", "Form 4 FX (if secured)"),
        ("discharge_egp_mt", False, "num", "Intake / discharge EGP/MT"),
        ("clearance_egp_mt", False, "num", "Clearance EGP/MT"),
        ("freight_egp_mt", False, "num", "Inland freight EGP/MT"),
        ("note", False, "text", ""),
    ],
    "Local Purchases": [
        ("date", True, "date", "Purchase date"),
        ("commodity", True, "upper", ""),
        ("supplier", False, "text", ""),
        ("qty_mt", True, "num", ""),
        ("price_egp_mt", True, "num", "Price EGP/MT (without transport)"),
        ("transport_egp_mt", False, "num", "Empty = the app's default transport"),
        ("note", False, "text", ""),
    ],
    "Local Prices": [
        ("date", True, "date", "Market price date"),
        ("commodity", True, "upper", ""),
        ("price_egp_mt", True, "num", "Local market price EGP/MT"),
        ("transport_egp_mt", False, "num", "Empty = the app's default transport"),
    ],
    "Budgets": [
        ("commodity", True, "upper", ""),
        ("year", True, "int", "Year the budget year starts in, e.g. 2026"),
        ("currency", False, "choice:USD|EGP", "USD (default) or EGP"),
        ("basis", False, "choice:CIF|DELIVERED", "CIF (default) or DELIVERED"),
        ("price_mt", True, "num", "Budget price per MT"),
        ("qty_mt", False, "num", "Budget quantity MT (optional)"),
        ("note", False, "text", ""),
    ],
    "FX History": [
        ("date", True, "date", ""),
        ("rate", True, "num", "USD/EGP"),
    ],
    "CBOT History": [
        ("date", True, "date", ""),
        ("commodity", True, "choice:CORN|SBM|SOYBEAN|WHEAT", ""),
        ("close", True, "num", "Settlement / close (cents/bu; USD/short ton for SBM)"),
    ],
}

EXAMPLES: dict[str, list[Any]] = {
    "Contracts": ["", "CPG-26-014", "Corn Nov", "Supplier A", "CORN", "BRZ", "Open", 30000, "2026-09-01",
                  "2026-11-15", "", "", "Dec 2026", 95, "", "", "", 180, 95, 250, "example — delete this row"],
    "Local Purchases": ["2026-09-20", "CORN", "Mill A", 2000, 14500, 150, "example — delete this row"],
    "Local Prices": ["2026-09-20", "CORN", 14600, 150],
    "Budgets": ["CORN", 2026, "USD", "CIF", 232.5, 140000, "example — delete this row"],
    "FX History": ["2026-09-20", 48.25],
    "CBOT History": ["2026-09-20", "CORN", 428.25],
}


def _norm(h: Any) -> str:
    s = str(h or "").strip().lower()
    s = re.sub(r"\(.*?\)", "", s).replace("*", "")
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def parse_date(v: Any) -> str | None:
    if v is None or v == "":
        return None
    if isinstance(v, dt.datetime):
        return v.date().isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, (int, float)) and 20000 < float(v) < 80000:      # Excel serial day
        return (dt.date(1899, 12, 30) + dt.timedelta(days=int(v))).isoformat()
    s = str(v).strip().split(" ")[0].split("T")[0]
    try:
        return dt.date.fromisoformat(s).isoformat()
    except ValueError:
        pass
    m = re.match(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})$", s)
    if m:
        try:
            return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            return None
    return None


def match_sheet(name: str) -> str | None:
    n = _norm(name)
    for sheet in IMPORT_SHEETS:
        if _norm(sheet) == n:
            return sheet
    return None


def parse_sheet(sheet: str, rows: list[list[Any]]) -> dict[str, Any]:
    """rows = raw cell values, header row first (blank rows / an instruction
    row above the header are skipped).  Returns {records, errors, missing_cols}."""
    spec = IMPORT_SHEETS[sheet]
    fields = {f for f, *_ in spec}
    hdr_i, colmap = None, {}
    for i, row in enumerate(rows[:6]):
        m = {}
        for ci, cell in enumerate(row or []):
            key = _norm(cell)
            if key in fields and key not in m:
                m[key] = ci
        if sum(1 for f, req, *_ in spec if req and f in m) >= max(1, sum(1 for _f, req, *_ in spec if req) - 1):
            hdr_i, colmap = i, m
            break
    missing = [f for f, req, *_ in spec if req and f not in colmap]
    out = {"sheet": sheet, "records": [], "errors": [], "missing_cols": missing}
    if hdr_i is None or missing:
        return out
    for ri in range(hdr_i + 1, len(rows)):
        row = rows[ri] or []
        vals = {f: (row[ci] if ci < len(row) else None) for f, ci in colmap.items()}
        if all(v is None or str(v).strip() == "" for v in vals.values()):
            continue
        if any("example" in str(v).lower() and "delete" in str(v).lower() for v in vals.values()):
            continue
        rec, errs = {}, []
        for f, req, kind, _help in spec:
            v = vals.get(f)
            blank = v is None or str(v).strip() == ""
            if blank:
                if req:
                    errs.append(f"{f} is required")
                continue
            if kind == "date":
                d = parse_date(v)
                if d is None:
                    errs.append(f"{f} '{v}' is not a date (use YYYY-MM-DD)")
                else:
                    rec[f] = d
            elif kind in ("num", "int"):
                n = to_float(str(v).replace(",", "") if isinstance(v, str) else v, None)
                if n is None:
                    errs.append(f"{f} '{v}' is not a number")
                elif kind == "int":
                    rec[f] = int(n)
                else:
                    rec[f] = n
            elif kind.startswith("choice:"):
                opts = kind.split(":", 1)[1].split("|")
                hit = next((o for o in opts if o.upper() == str(v).strip().upper()), None)
                if hit is None:
                    errs.append(f"{f} '{v}' must be one of {', '.join(opts)}")
                else:
                    rec[f] = hit
            elif kind == "upper":
                rec[f] = str(v).strip().upper()
            else:
                rec[f] = str(v).strip()
        for f in ("qty_mt", "price_egp_mt", "price_mt", "rate", "close"):
            if f in rec and rec[f] <= 0 and not (f == "qty_mt" and sheet == "Budgets"):
                errs.append(f"{f} must be > 0")
        if sheet == "Budgets" and "year" in rec and not (1990 <= rec["year"] <= 2100):
            errs.append("year must be like 2026")
        if errs:
            out["errors"].append({"row": ri + 1, "errors": errs, "values": vals})
        else:
            rec["_row"] = ri + 1
            out["records"].append(rec)
    return out


def _same(a: Any, b: Any) -> bool:
    fa, fb = to_float(a, None), to_float(b, None)
    if fa is not None and fb is not None:
        return abs(fa - fb) < 1e-9
    return str(a or "").strip().upper() == str(b or "").strip().upper()


def plan_import(sheet: str, records: list[dict[str, Any]], state: dict[str, Any]) -> list[dict[str, Any]]:
    """[{action NEW|UPDATE|SAME, key, rec, target, changes}] — target identifies the existing item."""
    plan = []
    seen: dict[Any, int] = {}

    def add(key, action, rec, target=None, changes=None):
        if key in seen:                       # a later row with the same key wins
            plan[seen[key]]["action"] = "DUPLICATE"
        seen[key] = len(plan)
        plan.append({"action": action, "key": key, "rec": rec, "target": target, "changes": changes or []})

    def diff(old, rec, fields):
        return [f for f in fields if f in rec and not _same(old.get(f), rec[f])]

    if sheet == "Contracts":
        contracts = state.get("contracts", {}) or {}
        by_name = {}
        for cid, c in contracts.items():
            by_name.setdefault((str(c.get("name", "")).strip().upper(), str(c.get("supplier", "")).strip().upper(),
                                str(c.get("commodity", "")).strip().upper()), cid)
        fields = [f for f, *_ in IMPORT_SHEETS["Contracts"] if f != "contract_id"]
        for rec in records:
            cid = rec.get("contract_id") if rec.get("contract_id") in contracts else None
            if cid is None:
                cid = by_name.get((rec["name"].upper(), rec["supplier"].upper(), rec["commodity"]))
            if cid is None:
                add(("new", rec["_row"]), "NEW", rec)
            else:
                ch = diff(contracts[cid], rec, fields)
                add(("cid", cid), "UPDATE" if ch else "SAME", rec, cid, ch)
    elif sheet == "Local Purchases":
        lps = state.get("local_purchases", []) or []
        for rec in records:
            key = (rec["date"], rec["commodity"], str(rec.get("supplier", "")).upper(), rec["qty_mt"],
                   rec["price_egp_mt"])
            hit = next((i for i, r in enumerate(lps)
                        if (str(r.get("date")), str(r.get("commodity", "")).upper(),
                            str(r.get("supplier", "")).upper()) == key[:3]
                        and _same(r.get("qty_mt"), key[3]) and _same(r.get("price_egp_mt"), key[4])), None)
            if hit is None:
                add(key, "NEW", rec)
            else:
                ch = diff(lps[hit], rec, ["transport_egp_mt", "note"])
                add(key, "UPDATE" if ch else "SAME", rec, hit, ch)
    elif sheet == "Local Prices":
        lp = state.get("local_prices", []) or []
        idx = {(str(r.get("date")), str(r.get("commodity", "")).upper()): i for i, r in enumerate(lp)}
        for rec in records:
            key = (rec["date"], rec["commodity"])
            i = idx.get(key)
            if i is None:
                add(key, "NEW", rec)
            else:
                ch = diff(lp[i], rec, ["price_egp_mt", "transport_egp_mt"])
                add(key, "UPDATE" if ch else "SAME", rec, i, ch)
    elif sheet == "Budgets":
        bl = state.get("budgets", []) or []
        for rec in records:
            rec["currency"] = rec.get("currency") or "USD"
            rec["basis"] = "LANDED" if rec.get("basis") == "DELIVERED" else "CIF"
            key = (rec["commodity"], rec["year"])
            i = next((j for j, b in enumerate(bl) if str(b.get("commodity", "")).upper() == key[0]
                      and int(to_float(b.get("year"), 0) or 0) == key[1]), None)
            if i is None:
                add(key, "NEW", rec)
            else:
                old = dict(bl[i])
                old.setdefault("price_mt", old.get("price_egp_mt"))
                old.setdefault("currency", "EGP")      # budgets saved before currency existed
                old.setdefault("basis", "LANDED")
                ch = diff(old, rec, ["price_mt", "qty_mt", "currency", "basis", "note"])
                add(key, "UPDATE" if ch else "SAME", rec, i, ch)
    elif sheet == "FX History":
        fx = state.get("fx_history", []) or []
        idx = {str(r.get("date")): i for i, r in enumerate(fx)}
        for rec in records:
            i = idx.get(rec["date"])
            if i is None:
                add(rec["date"], "NEW", rec)
            else:
                ch = [] if _same(fx[i].get("rate"), rec["rate"]) else ["rate"]
                add(rec["date"], "UPDATE" if ch else "SAME", rec, i, ch)
    elif sheet == "CBOT History":
        ch_ = state.get("cbot_history", []) or []
        idx = {(str(r.get("date")), str(r.get("commodity", "")).upper()): i for i, r in enumerate(ch_)}
        for rec in records:
            key = (rec["date"], rec["commodity"])
            i = idx.get(key)
            if i is None:
                add(key, "NEW", rec)
            else:
                old = ch_[i].get("close", ch_[i].get("price"))
                ch = [] if _same(old, rec["close"]) else ["close"]
                add(key, "UPDATE" if ch else "SAME", rec, i, ch)
    return plan
