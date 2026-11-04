"""Open-contract MTM history: fill the days the app was not opened, and read the trail back.

The app stores one Open-MTM record per open contract per day (``open_mtm_daily``) only when
its Home screen refreshes. This module

* finds the trading days between the first stored day and yesterday that have no record,
* rebuilds them from what the app stores by date — the CBOT close, the daily FX and the local
  price — with the contract's fees and tonnes from the nearest stored record, marked
  ``mode = "RECONSTRUCTED"`` so they are never mistaken for a live record,
* turns the records into a day-by-day book (totals, change, and why it changed: CBOT, FX,
  local, other) and a contract-by-day trail, and
* flags records taken with an old CBOT or FX quote.
"""
from __future__ import annotations

import datetime as dt

from .mtm_attribution import attribute

PARTS = ("from_cbot", "from_fx", "from_local", "other")


def _n(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def _d(v):
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def business_days_between(a, b):
    """Weekdays after ``a`` up to and including ``b``."""
    if not a or not b or b <= a:
        return 0
    n, d = 0, a
    while d < b:
        d += dt.timedelta(days=1)
        n += d.weekday() < 5
    return n


def stale_flags(record_date, cbot_as_of, fx_market_date, max_business_days=1):
    """Notes for a record whose CBOT or FX quote is older than the previous business day."""
    out = []
    day = _d(record_date)
    cb, fx = _d(cbot_as_of), _d(fx_market_date)
    if day and cb and business_days_between(cb, day) > max_business_days:
        out.append(f"CBOT quote from {cb.isoformat()}")
    if day and fx and business_days_between(fx, day) > max_business_days + 1:
        out.append(f"FX market date {fx.isoformat()}")
    return out


# ── filling the missing days ─────────────────────────────────────────────

def missing_days(history, trading_days, today):
    """Trading days between the first stored record and yesterday that have no record."""
    stored = {r.get("date") for r in history or [] if isinstance(r, dict) and r.get("date")}
    if not stored:
        return []
    first = min(stored)
    end = (today - dt.timedelta(days=1)).isoformat()
    return sorted(d for d in set(trading_days) if first < d <= end and d not in stored)


def reconstruct_day(day, history, contracts, cbot_on, fx_on, local_on, captured_at=""):
    """Rows for ``day`` rebuilt from the stored records around it.

    cbot_on(base, day) -> (price, date) · fx_on(day) -> (rate, date) · local_on(contract, day) -> (price incl. transport, date)
    A contract is in the book that day if it is in the records on both sides of the day, or on one
    side when its created / closed dates say it was open then.
    """
    by_date = {}
    for r in history or []:
        if isinstance(r, dict) and r.get("date") and r.get("contract_id"):
            by_date.setdefault(r["date"], {})[r["contract_id"]] = r
    before = [d for d in by_date if d < day]
    after = [d for d in by_date if d > day]
    prev = by_date[max(before)] if before else {}
    nxt = by_date[min(after)] if after else {}
    rows = []
    for cid in sorted(set(prev) | set(nxt)):
        c = (contracts or {}).get(cid) or {}
        created = str(c.get("created_ts") or "")[:10]
        closed = str(c.get("closed_date") or c.get("last_closed_date") or "")[:10]
        if cid not in prev and not (created and created <= day):
            continue
        if cid not in nxt and not (closed and closed > day):
            continue
        t = prev.get(cid) or nxt.get(cid)
        base = t.get("base_commodity") or (t.get("commodity") or "").split("-")[0]
        conv, prem = _n(t.get("cbot_conversion")), _n(t.get("premium_quote"))
        cif_t, cbot_t = _n(t.get("cif_usd_mt")), _n(t.get("cbot_price"))
        # Treat the contract as the app did around that day (not as it is today): its CIF followed the
        # CBOT if the nearest record's CIF equals (CBOT + premium) × factor.
        floating = None not in (conv, prem, cif_t, cbot_t) and abs(cif_t - (cbot_t + prem) * conv) < 0.01
        cb, cb_date = cbot_on(base, day) if base in ("CORN", "SOYBEAN", "WHEAT", "SBM") else (None, None)
        cif = ((cb + prem) * conv) if (floating and cb is not None) else cif_t
        f4, fx_t = _n(c.get("form4_fx")), _n(t.get("fx"))
        if f4 and fx_t is not None and abs(fx_t - f4) < 0.0005:
            fx, fx_date, fx_src = f4, str(c.get("form4_date") or "")[:10], "Form 4"
        else:
            fx, fx_date = fx_on(day)
            fx_src = "FX history"
        loc, loc_date = local_on(c or t, day)
        disc, clr, fr = _n(t.get("discharge_egp_mt")) or 0.0, _n(t.get("clearance_egp_mt")) or 0.0, _n(t.get("freight_egp_mt")) or 0.0
        own_t = _n(t.get("own_after_egp_mt"))
        other_fee = (own_t - (cif_t * _n(t.get("fx")) + disc + clr + fr)) if None not in (own_t, cif_t, _n(t.get("fx"))) else 0.0
        own = (cif * fx + disc + clr + fr + other_fee) if None not in (cif, fx) else None
        sav = (loc - own) if None not in (loc, own) else None
        qty = _n(t.get("qty_mt"))
        rec = dict(t)
        rec.update({
            "date": day, "captured_at": captured_at, "capture_reason": "backfill", "mode": "RECONSTRUCTED",
            "cbot_price": round(cb, 6) if cb is not None else None,
            "cbot_source": "CBOT close (history)" if cb is not None else "",
            "cbot_as_of": cb_date or "",
            "cif_usd_mt": round(cif, 6) if cif is not None else None, "fx": round(fx, 6) if fx is not None else None,
            "fx_source": fx_src, "fx_as_of": fx_date or "", "local_egp_mt": round(loc, 4) if loc is not None else None,
            "local_price_date": loc_date or "", "own_after_egp_mt": round(own, 4) if own is not None else None,
            "saving_egp_mt": round(sav, 4) if sav is not None else None,
            "total_saving_egp": round(sav * qty, 2) if None not in (sav, qty) else None,
            "reconstructed_from": (f"CBOT close {cb_date or '—'}, {fx_src} {fx_date or '—'}, local {loc_date or '—'}; "
                                   f"fees and tonnes from the record of {t.get('date')}"),
            "stale_quotes": [],
        })
        if floating and cb is None:
            rec["stale_quotes"] = ["no CBOT close on or before this day"]
        rows.append(rec)
    return rows


def backfill(history, contracts, trading_days, today, cbot_on, fx_on, local_on, captured_at=""):
    """Rebuild every missing trading day; returns the new rows (``history`` is not changed)."""
    new = []
    work = list(history or [])
    for day in missing_days(work, trading_days, today):
        rows = reconstruct_day(day, work, contracts, cbot_on, fx_on, local_on, captured_at)
        new += rows
        work += rows
    return new


# ── reading the trail ────────────────────────────────────────────────────

def _base(r):
    return (r.get("base_commodity") or r.get("commodity") or "").upper().split("-")[0]


def contract_trail(history, start=None, end=None, commodity="ALL"):
    """One row per contract per stored day, against that contract's previous stored day."""
    rows = sorted((r for r in history or [] if isinstance(r, dict) and r.get("date") and r.get("contract_id")
                   and (commodity == "ALL" or _base(r) == commodity)),
                  key=lambda r: (r["contract_id"], r["date"]))
    out, last = [], {}
    for r in rows:
        p = last.get(r["contract_id"])
        last[r["contract_id"]] = r
        if (start and r["date"] < start) or (end and r["date"] > end):
            continue
        a = attribute(r, p) if p else {k: None for k in PARTS + ("change",)}
        t1, t0 = _n(r.get("total_saving_egp")), _n((p or {}).get("total_saving_egp"))
        out.append({"date": r["date"], "prior_date": (p or {}).get("date", ""), "contract_id": r["contract_id"],
                    "contract": r.get("contract_ref") or r["contract_id"], "base": _base(r), "mode": r.get("mode", "LIVE"),
                    "qty_mt": _n(r.get("qty_mt")), "cbot": _n(r.get("cbot_price")), "cif": _n(r.get("cif_usd_mt")),
                    "fx": _n(r.get("fx")), "fx_source": r.get("fx_source", ""), "own_after": _n(r.get("own_after_egp_mt")),
                    "local": _n(r.get("local_egp_mt")), "local_date": r.get("local_price_date", ""),
                    "saving_mt": _n(r.get("saving_egp_mt")), "total": t1,
                    "d_saving_mt": a.get("change"), "d_total": (t1 - t0) if None not in (t1, t0) else None,
                    **{k: a.get(k) for k in PARTS},
                    "stale": "; ".join(r.get("stale_quotes") or []), "note": r.get("reconstructed_from", "")})
    out.sort(key=lambda x: (x["date"], x["base"], x["contract"]))
    return out


def book_by_day(history, start=None, end=None, commodity="ALL"):
    """The open book per stored day: totals, change against the previous stored day, and why."""
    trail = contract_trail(history, None, end, commodity)
    days = {}
    for t in trail:
        days.setdefault(t["date"], []).append(t)
    out, prev_total, prev_sav, cum = [], None, None, 0.0
    for day in sorted(days):
        rows = days[day]
        qty = sum(r["qty_mt"] or 0 for r in rows)
        tot_rows = [r["total"] for r in rows if r["total"] is not None]
        total = sum(tot_rows) if tot_rows else None
        w = [(r["saving_mt"], r["qty_mt"]) for r in rows if r["saving_mt"] is not None and r["qty_mt"]]
        sav = sum(v * q for v, q in w) / sum(q for _v, q in w) if w else None
        both = [r for r in rows if r["prior_date"] and all(r[k] is not None for k in PARTS) and r["qty_mt"]]
        bq = sum(r["qty_mt"] for r in both)
        parts = {k: (sum(r[k] * r["qty_mt"] for r in both) / bq if bq else None) for k in PARTS}
        d_total = (total - prev_total) if None not in (total, prev_total) else None
        modes = {r["mode"] for r in rows}
        rec = {"date": day, "contracts": len(rows), "qty_mt": qty, "total": total, "saving_mt": sav,
               "d_total": d_total, "d_saving_mt": (sav - prev_sav) if None not in (sav, prev_sav) else None, **parts,
               "mode": "Live" if modes <= {"LIVE"} else "Reconstructed" if modes == {"RECONSTRUCTED"} else "Mixed",
               "stale": "; ".join(sorted({s for r in rows for s in (r["stale"].split("; ") if r["stale"] else [])})),
               "cbot": {b: next((r["cbot"] for r in rows if r["base"] == b and r["cbot"] is not None), None)
                        for b in sorted({r["base"] for r in rows})},
               "fx_market": next((r["fx"] for r in rows if r["fx_source"] not in ("Form 4",) and r["fx"] is not None), None)}
        prev_total, prev_sav = total, sav
        if start and day < start:
            continue
        cum += d_total or 0.0
        rec["cumulative_d_total"] = cum
        out.append(rec)
    return out


def write_history_excel(history, path, start=None, end=None, commodity="ALL", as_of=None):
    """Book by day and contract by day for a period (uses the report writer's sheet helper)."""
    from .periodic_reports import _xl
    book = book_by_day(history, start, end, commodity)
    trail = contract_trail(history, start, end, commodity)
    bases = sorted({b for r in book for b in r["cbot"]})
    sg, sg2 = "+#,##0;-#,##0", "+#,##0.00;-#,##0.00"
    tone = lambda v: ("good" if (v or 0) > 0 else "bad" if (v or 0) < 0 else None) if isinstance(v, (int, float)) else None
    b_rows = [[r["date"], r["mode"], r["contracts"], r["qty_mt"], r["total"], r["d_total"], r["cumulative_d_total"], r["saving_mt"],
               r["d_saving_mt"], r["from_cbot"], r["from_fx"], r["from_local"], r["other"]] + [r["cbot"].get(b) for b in bases]
              + [r["fx_market"], r["stale"]] for r in book]
    c_rows = [[r["date"], r["prior_date"], r["mode"], r["contract"], r["base"], r["qty_mt"], r["cbot"], r["cif"], r["fx"], r["fx_source"],
               r["own_after"], r["local"], r["local_date"], r["saving_mt"], r["d_saving_mt"], r["from_cbot"], r["from_fx"], r["from_local"],
               r["other"], r["total"], r["d_total"], r["stale"], r["note"]] for r in trail]
    period = f"{start or (book[0]['date'] if book else '—')} → {end or (book[-1]['date'] if book else '—')}"
    return _xl(path, as_of or (end or ""), [
        ("Book by Day", f"Open book per stored day, {period}{'' if commodity == 'ALL' else ' · ' + commodity}. Change is against the "
                        "previous stored day. Why (EGP/MT, tonne-weighted over contracts on both days): from CBOT = CIF change at the "
                        "prior FX; from FX = FX change on today's CIF (0 with Form 4); from local = local price change; other = fees. "
                        "Reconstructed = rebuilt from the stored CBOT close, FX history and local prices for a day the app was not opened.",
         ["Date", "Record", "Contracts", "MT", "Total saving EGP", "Change EGP", "Cumulative change EGP", "Saving/MT", "Change/MT",
          "from CBOT", "from FX", "from Local", "Other"] + [f"CBOT {b}" for b in bases] + ["Market FX", "Old quotes"],
         b_rows, [11, 13, 9, 10, 15, 13, 15, 10, 10, 10, 9, 10, 8] + [10] * len(bases) + [9, 34],
         {4: "#,##0", 5: "#,##0", 6: sg, 7: sg, 8: "#,##0", 9: sg, 10: sg, 11: sg, 12: sg, 13: sg,
          **{14 + i: "#,##0.00" for i in range(len(bases))}, 14 + len(bases): "0.0000"}, set(), {6: tone, 7: tone}),
        ("Contract by Day", "Every open contract on every stored day, against its own previous stored day; the four parts add up to the "
                            "change in saving/MT.",
         ["Date", "Prior date", "Record", "Contract", "Commodity", "MT", "CBOT", "CIF $/MT", "FX", "FX source", "Own cost", "Local",
          "Local date", "Saving/MT", "Change/MT", "from CBOT", "from FX", "from Local", "Other", "Total EGP", "Change EGP", "Old quotes",
          "How it was rebuilt"],
         c_rows, [11, 11, 13, 22, 10, 9, 9, 9, 9, 16, 10, 10, 11, 10, 10, 10, 9, 10, 8, 13, 12, 26, 60],
         {6: "#,##0", 7: "#,##0.00", 8: "#,##0.00", 9: "0.0000", 11: "#,##0", 12: "#,##0", 14: "#,##0", 15: sg, 16: sg, 17: sg,
          18: sg, 19: sg, 20: "#,##0", 21: sg}, set(), {15: tone, 21: tone})])
