"""Read the daily raw-material stock email (Nobaria / Saaf / Total) and turn it into the app's stock counts.

The email table is pasted as text. Its rows are a material name, then per site five figures — current stock,
actual daily consumption, days of supply, average daily forecast consumption, days of supply at the forecast —
for Nobaria, then Saaf, then the total (at least stock, actual consumption and days). Cells can arrive tab
separated or one per line, and "#DIV/0!" stands for an empty figure.

``read_report(text)`` returns the date and one row per material; ``plan(report, state)`` says what would be
stored: a physical count per material on the report's date (with zero counts for the other keys of the same
commodity, e.g. CORN and CORN-ARG next to CORN-BRZ, so the day's total is unambiguous), the actual daily
consumption against the app's rate, days of supply and alerts; ``apply(state, plan)`` stores it.
"""

from __future__ import annotations

import datetime as dt
import re

MATERIALS = [  # (pattern, app commodity key, label); most specific first
    (r"soy\w*\s*bean\s*meal|soybean\s*meal|\bsbm\b", "SBM", "Soybean meal"),
    (r"yellow\s*corn|\bcorn\b|\bmaize\b", "CORN-BRZ", "Yellow corn"),
    (r"\bddgs\b", "DDGS", "DDGS"),
    (r"sun\s*flower|\bsfm\b", "SFM", "Sunflower meal"),
    (r"soy\w*\s*bean\s*\(?ffs\)?|full\s*fat|\bffs\b|\bsoybean\b", "SOYBEAN", "Soybean (FFS)"),
    (r"gluten", "GLUTEN", "Gluten meal"),
]
SITES = ("Nobaria", "Saaf")
FIELDS = ("stock", "actual", "days", "forecast", "days_forecast")
_NUM = re.compile(r"^-?[\d,]*\.?\d+$")


def _num(tok):
    t = str(tok).strip().replace(",", "")
    if t.upper().startswith("#DIV") or t in ("-", "—", ""):
        return None
    return float(t) if _NUM.match(t) else "x"


def _material(tok):
    t = str(tok or "").strip()
    if not t or _num(t) != "x":
        return None
    for pat, key, name in MATERIALS:
        if re.search(pat, t, re.I):
            return key, name, t
    return None


def read_report(text):
    """{date, rows: [{key, label, name, sites: {Nobaria: {...}, Saaf: {...}}, total: {...}, figures}], notes}."""
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", text or "")
    date = None
    if m:
        try:
            date = dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
        except ValueError:
            date = None
    tokens = [t for t in re.split(r"[\t\r\n]+|\s{2,}", text or "") if t.strip()]
    rows, notes, i = [], [], 0
    while i < len(tokens):
        mat = _material(tokens[i])
        if not mat:
            i += 1
            continue
        figs, j = [], i + 1
        while j < len(tokens) and _num(tokens[j]) != "x":
            figs.append(_num(tokens[j]))
            j += 1
        if len(figs) >= 13:
            key, name, raw = mat
            sites = {s: dict(zip(FIELDS, figs[k * 5:(k + 1) * 5])) for k, s in enumerate(SITES)}
            total = dict(zip(FIELDS, figs[10:15]))
            rows.append({"key": key, "label": name, "name": raw, "sites": sites, "total": total, "figures": figs})
            parts = [sites[s]["stock"] for s in SITES]
            if None not in parts and total.get("stock") is not None and abs(sum(parts) - total["stock"]) > 2:
                notes.append(f"{raw}: Nobaria + Saaf = {sum(parts):,.0f} but the total says {total['stock']:,.0f}")
        i = j if j > i + 1 else i + 1
    return {"date": date, "rows": rows, "notes": notes}


def _base(key):
    return str(key or "").upper().split("-")[0]


def plan(report, state, date=None):
    """What would be stored. Lines: {key, label, stock, nobaria, saaf, actual, days, rate, tracked, counts:
    [(commodity key, MT)], alert}. A material the app does not track (no rate, no contract, no count) is
    listed but stores nothing."""
    date = date or report.get("date")
    log = state.get("consumption_log", []) or []
    rates = state.get("consumption", {}) or {}
    known = set(rates) | {str(e.get("commodity") or "").upper() for e in log} | \
        {str(c.get("commodity") or "").upper() for c in (state.get("contracts", {}) or {}).values()} | \
        set((state.get("commodities", {}) or {}).keys())
    lines = []
    for r in report.get("rows", []):
        key, total = r["key"], r["total"]
        stock = total.get("stock")
        if stock is None:
            stock = sum(r["sites"][s]["stock"] or 0 for s in SITES)
        actual = total.get("actual")
        days = stock / actual if actual else None
        tracked = key in known or any(_base(k) == _base(key) for k in known)
        aliases = sorted({str(e.get("commodity") or "").upper() for e in log
                          if e.get("is_adjustment") and _base(e.get("commodity")) == _base(key)} - {key})
        counts = [(key, float(stock))] + [(a, 0.0) for a in aliases] if tracked else []
        rate = sum(float(v or 0) for k, v in rates.items() if _base(k) == _base(key)) or None
        alert = None
        if days is not None and days < 7:
            alert = ("High", f"{r['label']}: {days:.0f} days of supply ({stock:,.0f} MT at {actual:,.0f} MT/day)")
        elif days is not None and days < 14:
            alert = ("Medium", f"{r['label']}: {days:.0f} days of supply ({stock:,.0f} MT at {actual:,.0f} MT/day)")
        lines.append({"key": key, "label": r["label"], "name": r["name"], "stock": stock,
                      "nobaria": r["sites"]["Nobaria"]["stock"], "saaf": r["sites"]["Saaf"]["stock"],
                      "actual": actual, "forecast": sum((r["sites"][s].get("forecast") or 0) for s in SITES) or None,
                      "days": days, "rate": rate, "tracked": tracked, "counts": counts, "alert": alert})
    return {"date": date, "lines": lines, "notes": list(report.get("notes") or [])}


def apply(state, p, set_counts=True, set_rates=False, stamp="", note_source="stock report"):
    """Store the plan in ``state``: counts in the consumption log (replacing a count of the same commodity and
    day), optionally the actual daily consumption as the rate, and the report itself under stock_reports
    (per site, for later). Returns {counts, rates}."""
    log = state.setdefault("consumption_log", [])
    date = p["date"]
    n_counts, n_rates = 0, 0
    for line in p["lines"]:
        if set_counts:
            for key, qty in line["counts"]:
                log[:] = [e for e in log if not (e.get("is_adjustment") and str(e.get("commodity") or "").upper() == key
                                                 and e.get("date") == date)]
                site = (f"Nobaria {line['nobaria']:,.0f} + Saaf {line['saaf']:,.0f} MT"
                        if key == line["key"] and line["nobaria"] is not None and line["saaf"] is not None else
                        f"same-day total is under {line['key']}")
                log.append({"date": date, "commodity": key, "is_adjustment": True, "adjusted_qty": qty,
                            "received_mt": None, "consumed_mt": None,
                            "note": f"Manual physical stock count — {note_source} {date}: {site}", "ts": stamp})
                n_counts += 1
        if set_rates and line["tracked"] and line["actual"]:
            rates = state.setdefault("consumption", {})
            keys = [k for k in rates if _base(k) == _base(line["key"])] or [line["key"]]
            rates[keys[0]] = float(line["actual"])
            for k in keys[1:]:
                rates[k] = 0.0
            n_rates += 1
    state.setdefault("stock_reports", []).append({
        "date": date, "stored_ts": stamp,
        "lines": [{k: line[k] for k in ("key", "label", "stock", "nobaria", "saaf", "actual", "forecast")}
                  for line in p["lines"]]})
    state["stock_reports"] = state["stock_reports"][-400:]
    return {"counts": n_counts, "rates": n_rates}
