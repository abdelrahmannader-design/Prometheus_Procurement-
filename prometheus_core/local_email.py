"""Read the 'Commodities local market prices' email into local price rows.

The email carries a small table: a header ``YC <newer date> … <older date>`` and
one line per commodity with one or two ranges ``14900 LE to 15000 LE / Ton``
(newer first). Rows are YC ARG, YC UKR, SBM Hi pro 46%, Soybeans, DDGS and
Sunflower; prices are without transport. The emails have no Brazil corn row:
Brazil corn trades at the Argentina price, so CORN-BRZ takes the YC ARG row.
"""
from __future__ import annotations

import datetime as dt
import re

LABELS = [("(YC ARG)", "ARG"), ("(YC UKR)", "UKR"), ("SBM Hi pro 46%", "SBM"), ("Soybeans", "SOYBEAN"),
          ("DDGS", "DDGS"), ("Sunflower", "SFM")]
# Email row → the app's local price commodity codes it fills (only codes the app already uses are filled).
COMMODITY_MAP = {"ARG": ["CORN-ARG", "CORN-BRZ", "CORN"], "UKR": ["CORN-UKR"], "SBM": ["SBM"],
                 "SOYBEAN": ["SOYBEAN", "SBS"], "DDGS": ["DDGS"], "SFM": ["SFM"]}
ROW_LABEL = {"ARG": "YC ARG", "UKR": "YC UKR", "SBM": "SBM Hi pro 46%", "SOYBEAN": "Soybeans", "DDGS": "DDGS",
             "SFM": "Sunflower"}
_PAIR = re.compile(r"(\d{4,5})\s*LE\s*to\s*\*?\s*(\d{4,5})|N/A", re.I)
_HEAD = re.compile(r"YC\s+(\d{1,2}/\d{1,2}/\d{4})(.*?)(\d{1,2}/\d{1,2}/\d{4})", re.S)
_ONE = re.compile(r"YC\s+(\d{1,2}/\d{1,2}/\d{4})")


def _date(s):
    a, b, c = s.split("/")
    return dt.date(int(c), int(b), int(a)).isoformat()


def parse_email(text):
    """Return [{date, key, low, high, column, note}] for every range in the pasted email."""
    body = "\n".join(line.lstrip(">").strip() for line in (text or "").splitlines())
    h = _HEAD.search(body)
    if h and "LE" not in h.group(2):
        d1, d2, start = _date(h.group(1)), _date(h.group(3)), h.end()
        dates = [d1] if (d1 == d2 or re.search(r"update|end day", h.group(2), re.I)) else [d1, d2]
    else:
        one = _ONE.search(body)
        if not one:
            return []
        dates, start = [_date(one.group(1))], one.end()
    end = body.find("The prices", start)
    seg = body[start: end if end >= 0 else None]
    pos = sorted((seg.find(lab), key, lab) for lab, key in LABELS if seg.find(lab) >= 0)
    out = []
    for i, (p, key, lab) in enumerate(pos):
        part = seg[p + len(lab): pos[i + 1][0] if i + 1 < len(pos) else len(seg)]
        ranges = [(int(m.group(1)), int(m.group(2))) if m.group(1) else None for m in _PAIR.finditer(part)]
        for j, day in enumerate(dates):
            if j < len(ranges) and ranges[j]:
                lo, hi = ranges[j]
                if lo > hi:
                    lo, hi = hi, lo
                out.append({"date": day, "key": key, "low": lo, "high": hi, "column": j + 1,
                            "note": "limited quantity" if key == "SOYBEAN" and "limited" in part.lower() and j == 0 else ""})
    return out


def to_local_rows(entries, local_prices, point="high", source="pasted email"):
    """Turn parsed ranges into rows for the local price import preview.

    ``point`` picks high / mid / low of each range. Transport is the commodity's last
    stored transport on or before that date. Rows whose stored price for the date is
    already the same are left out; changed ones are marked as updates.
    """
    by_com = {}
    for r in local_prices or []:
        if isinstance(r, dict) and r.get("commodity") and r.get("date"):
            by_com.setdefault(r["commodity"], []).append(r)
    for v in by_com.values():
        v.sort(key=lambda r: str(r["date"]))
    stored = {(str(r["date"])[:10], r["commodity"]): r for v in by_com.values() for r in v}
    rows, seen = [], set()
    for e in sorted(entries, key=lambda e: (e["date"], e["column"])):
        lo, hi = e["low"], e["high"]
        price = hi if point == "high" else lo if point == "low" else (lo + hi) / 2.0
        for com in COMMODITY_MAP.get(e["key"], []):
            if com not in by_com or (e["date"], com) in seen:
                continue
            seen.add((e["date"], com))
            prev = [x for x in by_com[com] if str(x["date"])[:10] <= e["date"]]
            trans = prev[-1].get("transport_egp_mt") if prev else by_com[com][0].get("transport_egp_mt")
            hit = stored.get((e["date"], com))
            if hit and abs(float(hit.get("price_egp_mt") or 0) - price) < 0.005:
                continue
            note = (f"{source}: row {ROW_LABEL[e['key']]} {lo:,}–{hi:,} EGP/MT without transport, {point} of range"
                    + ("; Brazil corn priced as Argentina corn" if com == "CORN-BRZ" else "")
                    + (f"; {e['note']}" if e["note"] else ""))
            rows.append({"date": e["date"], "commodity": com, "price_egp_mt": float(price),
                         "transport_egp_mt": float(trans) if trans not in (None, "") else 0.0,
                         "_known": True, "_source": note,
                         "_update": bool(hit), "_previous": hit.get("price_egp_mt") if hit else None})
    return rows
