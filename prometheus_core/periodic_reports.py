"""Daily and weekly procurement reports for the email digest.

Daily
  * Pricing Deadline Sheet (Excel) — every contract not priced yet against the first
    notice day of its futures month, with break-even, headroom, the CBOT's place in its
    30-day range, the alert targets and the EGP at stake per 10 ¢.
  * Stock & Arrivals Watch (PDF) — days of cover per commodity against the next arrival;
    tonnes outstanding without an arrival date are a risk, not a cover.

Weekly
  * Savings & Market Review (PDF) — this week against the previous one: consumption and
    savings vs local, CBOT / FX / local moves, and the local-equivalent premium against
    our latest premium over the last 8 weeks.
  * Procurement Pipeline (Excel) — every live contract by stage (to arrive, in stock,
    consumed), priced / Form 4 flags, value and the cash still to pay.
  * Action List (Excel) — alerts and data to fix, marked new / still open / fixed since
    the last weekly report, with owner and due-date columns for the team.

All figures come from the management report model; nothing here changes them.
"""
from __future__ import annotations

import datetime as dt

from .mgmt_report import first_notice_day

FACTORS = {"CORN": 0.3937, "SOYBEAN": 0.36745, "WHEAT": 0.36745, "SBM": 1.1023}
UNITS = {"CORN": "¢/bu", "SOYBEAN": "¢/bu", "WHEAT": "¢/bu", "SBM": "$/st"}
URGENT_DAYS, SOON_DAYS = 10, 30


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


def _on_or_before(series, day):
    pick = None
    for d, v in series:
        if d <= day:
            pick = (d, v)
        else:
            break
    return pick


def _series(model):
    return {b: [(str(d)[:10], _n(v)) for d, v in rows if _n(v) is not None] for b, rows in (model.get("cbot_series") or {}).items()}


# ── daily: pricing deadlines ─────────────────────────────────────────────

def pricing_deadlines(model):
    as_of = _d(model.get("as_of")) or dt.date.today()
    op = {o["contract_id"]: o for o in model.get("open") or []}
    alerts = {a["contract_id"]: a for a in model.get("alerts") or []}
    ser = _series(model)
    rows = []
    for c in model.get("contracts") or []:
        f = c.get("fix") or {}
        o = op.get(c["id"])
        if not f.get("eligible") or f.get("fixed") or not (c.get("is_open") or (o and (o.get("unconsumed_mt") or 0) > 0)):
            continue
        cm = c.get("contract_month") or {}
        fnd = first_notice_day(cm["year"], cm["month"]) if cm.get("year") and cm.get("month") else None
        days = (fnd - as_of).days if fnd else None
        status = ("No futures month" if fnd is None else "PAST first notice — confirm the roll" if days < 0
                  else "URGENT" if days <= URGENT_DAYS else "Soon" if days <= SOON_DAYS else "OK")
        qty = _n(c.get("qty_mt")) or 0.0
        lots = sum(_n(x.get("qty_mt")) or 0.0 for x in c.get("lots") or [] if _n(x.get("cbot")) is not None)
        unpriced = max(qty - lots, 0.0)
        cur = c.get("current") or {}
        live = _n((o or {}).get("latest_cbot")) or _n(cur.get("cbot"))
        s30 = [v for d, v in ser.get(c["base"], []) if d >= (as_of - dt.timedelta(days=30)).isoformat()]
        lo, hi = (min(s30), max(s30)) if s30 else (None, None)
        pos = ((live - lo) / (hi - lo) * 100) if None not in (live, lo, hi) and hi > lo else None
        fac, fx = FACTORS.get(c["base"]), _n((o or {}).get("fx")) or _n(cur.get("fx"))
        a = alerts.get(c["id"], {})
        be = _n((o or {}).get("be_cbot_incl")) if _n((o or {}).get("be_cbot_incl")) is not None else _n((o or {}).get("be_cbot_excl"))
        hd = _n((o or {}).get("headroom_incl")) if _n((o or {}).get("headroom_incl")) is not None else _n((o or {}).get("headroom_excl"))
        rows.append({"contract_id": c["id"], "contract": c.get("contract", ""), "supplier": c.get("supplier", ""),
                     "commodity": c.get("commodity", ""), "base": c["base"], "unit": UNITS.get(c["base"], ""),
                     "futures": cm.get("code") or c.get("futures_month", ""), "first_notice": fnd.isoformat() if fnd else "",
                     "last_trade": cm.get("last_trade", ""), "days_to_fnd": days, "status": status,
                     "qty_mt": qty, "unpriced_mt": unpriced, "consumed_mt": _n(c.get("consumed_mt")) or 0.0,
                     "premium": _n(c.get("premium")), "live_cbot": live, "cbot_time": (o or {}).get("latest_cbot_date") or cur.get("cbot_date", ""),
                     "cif_now": ((live + _n(c.get("premium"))) * fac) if None not in (live, _n(c.get("premium")), fac) else None,
                     "fx": fx, "be_cbot": be, "headroom": hd,
                     "low30": lo, "high30": hi, "pos30": pos,
                     "egp_per_10": 10 * fac * fx * unpriced if None not in (fac, fx) else None,
                     "fix_at": a.get("cbot_below"), "protect_at": a.get("cbot_above"), "alert": a.get("status", "")})
    rows.sort(key=lambda r: (r["days_to_fnd"] if r["days_to_fnd"] is not None else 99999, r["contract"]))
    return rows


# ── daily: stock & arrivals ──────────────────────────────────────────────

def stock_watch(model):
    as_of = _d(model.get("as_of")) or dt.date.today()
    rates = model.get("rates") or {}
    cons = {c["id"]: c for c in model.get("contracts") or []}
    by = {}
    for o in model.get("open") or []:
        c = cons.get(o["contract_id"], {})
        code = c.get("commodity") or o["base"]
        g = by.setdefault(code, {"code": code, "base": o["base"], "stock_mt": 0.0, "arrivals": [], "undated_mt": 0.0, "undated": []})
        g["stock_mt"] += o.get("available_mt") or 0.0
        out = o.get("outstanding_mt") or 0.0
        if out > 1e-6:
            eta = _d(c.get("delivery_date") or c.get("storage_start"))
            if eta and eta >= as_of:
                g["arrivals"].append({"date": eta.isoformat(), "mt": out, "contract": o["contract"]})
            else:
                g["undated_mt"] += out
                g["undated"].append(o["contract"])
    out_rows = []
    for code in sorted(set(by) | {k for k, v in rates.items() if _n(v)}):
        g = by.get(code) or {"code": code, "base": code.split("-")[0], "stock_mt": 0.0, "arrivals": [], "undated_mt": 0.0, "undated": []}
        rate = _n(rates.get(code))
        g["arrivals"].sort(key=lambda a: a["date"])
        cover = g["stock_mt"] / rate if rate else None
        stockout = (as_of + dt.timedelta(days=cover)) if cover is not None else None
        nxt = g["arrivals"][0] if g["arrivals"] else None
        gap = ((_d(nxt["date"]) - stockout).days if (nxt and stockout) else None)
        if not rate:
            status = "No daily rate configured"
        elif g["stock_mt"] <= 0 and not g["arrivals"] and not g["undated_mt"]:
            status = "No stock and nothing on order"
        elif nxt and gap is not None and gap > 0:
            status = f"GAP of {gap} days before the next arrival"
        elif cover is not None and cover < 14 and not nxt and g["undated_mt"]:
            status = (f"Runs out {stockout.isoformat()} ({cover:.0f} days) — {g['undated_mt']:,.0f} MT on order "
                      "has no arrival date")
        elif cover is not None and cover < 14 and not nxt:
            status = f"Runs out {stockout.isoformat()} ({cover:.0f} days) — nothing on order"
        elif cover is not None and cover < 14:
            status = f"Low — {cover:.0f} days of cover"
        else:
            status = "Covered"
        out_rows.append({"code": code, "base": g["base"], "daily_rate": rate, "stock_mt": g["stock_mt"],
                         "cover_days": cover, "stockout": stockout.isoformat() if stockout else "",
                         "next_arrival": nxt["date"] if nxt else "", "next_arrival_mt": nxt["mt"] if nxt else None,
                         "next_arrival_contract": nxt["contract"] if nxt else "",
                         "dated_on_order_mt": sum(a["mt"] for a in g["arrivals"]), "undated_mt": g["undated_mt"],
                         "undated_contracts": ", ".join(g["undated"]),
                         "need_30d": rate * 30 if rate else None,
                         "covered_30d": (g["stock_mt"] + sum(a["mt"] for a in g["arrivals"] if _d(a["date"]) <= as_of + dt.timedelta(days=30)))
                         if rate else None,
                         "gap_days": gap, "status": status, "arrivals": g["arrivals"]})
    risk = {"GAP": 0, "Runs": 1, "Low": 2, "No stock": 3}
    out_rows.sort(key=lambda r: (min([v for k, v in risk.items() if r["status"].startswith(k)] or [9]), r["code"]))
    return out_rows


# ── weekly: savings & market review ──────────────────────────────────────

def weekly_review(model, weeks=8):
    as_of = _d(model.get("as_of")) or dt.date.today()
    w0, w1 = as_of - dt.timedelta(days=6), as_of - dt.timedelta(days=13)
    week = lambda d: "this" if d >= w0 else ("previous" if d >= w1 else None)
    sav = {}
    for r in model.get("savings") or []:
        d = _d(r["date"])
        k = week(d) if d and d <= as_of else None
        if not k:
            continue
        s = sav.setdefault((r["base"], k), {"mt": 0.0, "sav": 0.0, "sav_mt": 0.0, "savx": 0.0, "savx_mt": 0.0})
        s["mt"] += r["mt"]
        if r.get("saving") is not None:
            s["sav"] += r["saving"]; s["sav_mt"] += r["mt"]
        if r.get("saving_excl") is not None:
            s["savx"] += r["saving_excl"]; s["savx_mt"] += r["mt"]
    consumption = []
    for base in sorted({b for b, _k in sav}):
        t, p = sav.get((base, "this"), {}), sav.get((base, "previous"), {})
        per = lambda s, a, m: (s.get(a, 0.0) / s[m]) if s.get(m) else None
        consumption.append({"base": base, "mt": t.get("mt", 0.0), "mt_prev": p.get("mt", 0.0),
                            "saving": t.get("sav", 0.0), "saving_prev": p.get("sav", 0.0),
                            "saving_mt": per(t, "sav", "sav_mt"), "saving_mt_prev": per(p, "sav", "sav_mt"),
                            "saving_excl": t.get("savx", 0.0), "saving_excl_prev": p.get("savx", 0.0)})
    ser = _series(model)
    live = model.get("live_cbot") or {}
    market = []
    for base in sorted(ser):
        s = ser[base]
        now = (_n((live.get(base) or {}).get("price")), str((live.get(base) or {}).get("time") or "")[:10]) if live.get(base) else (s[-1][1], s[-1][0]) if s else (None, "")
        wk = _on_or_before(s, (as_of - dt.timedelta(days=7)).isoformat())
        m4 = _on_or_before(s, (as_of - dt.timedelta(days=28)).isoformat())
        market.append({"item": f"CBOT {base}", "unit": UNITS.get(base, ""), "now": now[0], "date": now[1],
                       "week_ago": wk[1] if wk else None, "chg_week": (now[0] - wk[1]) if (wk and now[0] is not None) else None,
                       "chg_4w": (now[0] - m4[1]) if (m4 and now[0] is not None) else None,
                       "trend": [v for d, v in s if d >= (as_of - dt.timedelta(days=7 * 12)).isoformat()]})
    fxs = [(str(d)[:10], _n(v)) for d, v in model.get("fx_series") or [] if _n(v) is not None]
    if fxs:
        wk, m4 = _on_or_before(fxs, (as_of - dt.timedelta(days=7)).isoformat()), _on_or_before(fxs, (as_of - dt.timedelta(days=28)).isoformat())
        market.append({"item": "FX EGP/USD", "unit": "EGP", "now": fxs[-1][1], "date": fxs[-1][0], "week_ago": wk[1] if wk else None,
                       "chg_week": fxs[-1][1] - wk[1] if wk else None, "chg_4w": fxs[-1][1] - m4[1] if m4 else None,
                       "trend": [v for d, v in fxs if d >= (as_of - dt.timedelta(days=7 * 12)).isoformat()]})
    loc = {}
    for o in model.get("local_obs") or []:
        loc.setdefault(o["key"], []).append((o["date"], _n(o.get("price"))))
    local = []
    for key in sorted(loc):
        s = sorted(x for x in loc[key] if x[1] is not None)
        if not s:
            continue
        wk, m4 = _on_or_before(s, (as_of - dt.timedelta(days=7)).isoformat()), _on_or_before(s, (as_of - dt.timedelta(days=28)).isoformat())
        local.append({"key": key, "now": s[-1][1], "date": s[-1][0], "chg_week": s[-1][1] - wk[1] if wk else None,
                      "chg_4w": s[-1][1] - m4[1] if m4 else None})
    # local-equivalent premium at each of the last ``weeks`` week-ends, against the latest contract's premium
    from .daily_brief import build as _brief
    refs = [p for p in _brief(model)["parity"] if p.get("premium") is not None]
    prem_trend = []
    ends = [(as_of - dt.timedelta(days=7 * i)).isoformat() for i in range(weeks - 1, -1, -1)]
    for p in refs:
        ls = sorted(x for x in loc.get(p["local_key"] or p["code"], []) if x[1] is not None)
        pts = []
        for e in ends:
            lo_, cb_, fx_ = _on_or_before(ls, e), _on_or_before(ser.get(p["base"], []), e), _on_or_before(fxs, e)
            pts.append((e, ((lo_[1] - p["discharge"] - p["clearance"]) / fx_[1] / p["factor"] - cb_[1])
                        if (lo_ and cb_ and fx_) else None))
        vals = [v for _e, v in pts if v is not None]
        prem_trend.append({"code": p["code"], "unit": p["unit"], "ref_contract": p["ref_contract"], "ref_premium": p["premium"],
                           "points": pts, "now": pts[-1][1], "week_ago": pts[-2][1] if len(pts) > 1 else None,
                           "avg": sum(vals) / len(vals) if vals else None,
                           "gap_now": (pts[-1][1] - p["premium"]) if pts[-1][1] is not None else None})
    k = model.get("kpis") or {}
    return {"as_of": as_of.isoformat(), "week": f"{w0.isoformat()} → {as_of.isoformat()}",
            "previous_week": f"{w1.isoformat()} → {(w0 - dt.timedelta(days=1)).isoformat()}",
            "consumption": consumption, "market": market, "local": local, "premium_trend": prem_trend,
            "since_last": model.get("since_last") or {}, "kpis": k, "checksum": model.get("checksum", ""),
            "generated": model.get("generated", "")}


# ── weekly: pipeline ─────────────────────────────────────────────────────

def pipeline(model):
    as_of = _d(model.get("as_of")) or dt.date.today()
    op = {o["contract_id"]: o for o in model.get("open") or []}
    rows = []
    for c in model.get("contracts") or []:
        o = op.get(c["id"])
        live = c.get("is_open") or (o and ((o.get("available_mt") or 0) > 0 or (o.get("outstanding_mt") or 0) > 0))
        if not live:
            continue
        cur = c.get("current") or {}
        out, stock, consumed = _n(c.get("outstanding_mt")) or 0.0, _n(c.get("available_mt")) or 0.0, _n(c.get("consumed_mt")) or 0.0
        stage = ("To arrive" if out > 1e-6 and not c.get("received") else "Arriving / partly received" if out > 1e-6
                 else "In stock" if stock > 1e-6 else "Consumed — open in the app")
        f = c.get("fix") or {}
        priced = "Flat price" if not f.get("eligible") else ("Priced" if f.get("fixed") else "NOT PRICED")
        form4 = "Recorded" if (c.get("form4_fx") or cur.get("form4")) else ("n/a (SBM)" if c["base"] == "SBM" else "Pending")
        cif, fx = _n(cur.get("cif")) or _n(c.get("cif_usd_mt")), _n(cur.get("fx")) or _n(c.get("fx"))
        qty = _n(c.get("qty_mt")) or 0.0
        eta = c.get("delivery_date") or c.get("storage_start") or ""
        rows.append({"contract_id": c["id"], "contract": c.get("contract", ""), "supplier": c.get("supplier", ""),
                     "commodity": c.get("commodity", ""), "base": c["base"], "origin": c.get("origin", ""), "stage": stage,
                     "priced": priced, "form4": form4, "qty_mt": qty, "outstanding_mt": out, "stock_mt": stock,
                     "consumed_mt": consumed, "arrival": eta[:10] if eta else "not recorded",
                     "arrival_month": eta[:7] if eta and _d(eta) and _d(eta) >= as_of.replace(day=1) else ("not recorded" if not eta else "arrived"),
                     "cif": cif, "cif_basis": cur.get("cif_basis", ""), "fx": fx, "fx_basis": cur.get("fx_basis", ""),
                     "value_usd": cif * qty if cif is not None else None,
                     "value_egp": cif * qty * fx if None not in (cif, fx) else None,
                     "to_arrive_usd": cif * out if cif is not None else None,
                     "to_arrive_egp": cif * out * fx if None not in (cif, fx) else None,
                     "payment_terms": "not recorded"})
    order = ["To arrive", "Arriving / partly received", "In stock", "Consumed — open in the app"]
    rows.sort(key=lambda r: (order.index(r["stage"]), r["base"], r["arrival"], r["contract"]))
    summ = {}
    for r in rows:
        s = summ.setdefault((r["base"], r["stage"]), {"base": r["base"], "stage": r["stage"], "contracts": 0, "mt": 0.0, "usd": 0.0, "egp": 0.0,
                                                        "not_priced_mt": 0.0, "form4_pending": 0})
        s["contracts"] += 1
        s["mt"] += r["outstanding_mt"] if r["stage"] in order[:2] else r["stock_mt"] if r["stage"] == "In stock" else r["qty_mt"]
        s["usd"] += r["value_usd"] or 0.0
        s["egp"] += r["value_egp"] or 0.0
        s["not_priced_mt"] += r["qty_mt"] if r["priced"] == "NOT PRICED" else 0.0
        s["form4_pending"] += r["form4"] == "Pending"
    months = {}
    for r in rows:
        if r["outstanding_mt"] > 1e-6:
            mth = months.setdefault((r["arrival_month"], r["base"]), {"month": r["arrival_month"], "base": r["base"], "mt": 0.0, "usd": 0.0, "egp": 0.0})
            mth["mt"] += r["outstanding_mt"]
            mth["usd"] += r["to_arrive_usd"] or 0.0
            mth["egp"] += r["to_arrive_egp"] or 0.0
    return {"rows": rows, "summary": sorted(summ.values(), key=lambda s: (s["base"], order.index(s["stage"]))),
            "arrivals": sorted(months.values(), key=lambda m: (m["month"] == "not recorded", m["month"], m["base"])),
            "to_arrive_usd": sum(r["to_arrive_usd"] or 0 for r in rows), "to_arrive_egp": sum(r["to_arrive_egp"] or 0 for r in rows)}


# ── weekly: action list ──────────────────────────────────────────────────

def _fix_key(x):
    return f"{x['category']}|{x.get('contract_id') or x.get('detail', '')[:60]}"


def action_list(model, history=None):
    """Alerts and data to fix, each marked against the last report saved at least 6 days earlier."""
    as_of = _d(model.get("as_of")) or dt.date.today()
    hist = [h for h in history or [] if isinstance(h, dict) and _d(h.get("as_of")) and isinstance(h.get("fix_keys"), list)]
    older = [h for h in hist if (as_of - _d(h["as_of"])).days >= 6]
    prev = (older or [h for h in hist if _d(h["as_of"]) < as_of] or [None])[-1]
    before = set(prev["fix_keys"]) if prev else None
    first_seen = {}
    for h in hist:
        for k in h["fix_keys"]:
            first_seen.setdefault(k, h["as_of"])
    rows = []
    for a in model.get("alerts") or []:
        if a["status"] == "TRIGGERED":
            rows.append({"type": "Pricing alert", "severity": "High", "category": "Pricing alert triggered", "contract": a["contract"],
                         "contract_id": a["contract_id"], "base": a["base"], "detail": "; ".join(a["triggered"]),
                         "action": "Decide: fix now, protect, or move the target", "mt": a.get("unpriced_mt"),
                         "status": "Open", "since": as_of.isoformat()})
    now_keys = set()
    for x in model.get("data_to_fix") or []:
        k = _fix_key(x)
        now_keys.add(k)
        status = "New" if before is not None and k not in before else ("Still open" if before is not None else "Open")
        rows.append({"type": "Data to fix", "severity": x["severity"], "category": x["category"], "contract": x["contract"],
                     "contract_id": x["contract_id"], "base": x["base"], "detail": x["detail"], "action": x["action"],
                     "mt": x.get("mt"), "status": status, "since": first_seen.get(k, as_of.isoformat())})
    fixed = sorted(before - now_keys) if before is not None else []
    names = {c["id"]: c.get("contract", "") for c in model.get("contracts") or []}
    for k in fixed:
        cat, _, ref = k.partition("|")
        rows.append({"type": "Data to fix", "severity": "", "category": cat, "contract": names.get(ref, ref), "contract_id": ref, "base": "",
                     "detail": "No longer flagged", "action": "", "mt": None, "status": "FIXED", "since": ""})
    order = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    rows.sort(key=lambda r: (r["status"] == "FIXED", order.get(r["severity"], 3), r["category"], r["contract"]))
    return {"rows": rows, "previous": {"as_of": prev["as_of"], "generated": prev.get("generated")} if prev else None,
            "new": sum(r["status"] == "New" for r in rows), "fixed": len(fixed),
            "open": sum(r["status"] in ("Open", "New", "Still open") for r in rows)}


# ── writers ──────────────────────────────────────────────────────────────

def _xl(path, as_of, sheets, cache=None):
    """sheets: [(title, note, heads, rows, widths, formats {col: fmt}, bold_rows set, colour {col: fn(value)->'good'|'bad'|None})]"""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    navy, light, band = PatternFill("solid", fgColor="1F2A44"), PatternFill("solid", fgColor="EEF2F8"), PatternFill("solid", fgColor="DCE3EF")
    wb = Workbook()
    for k, (title, note, heads, rows, widths, fmt, bold_rows, colour) in enumerate(sheets):
        ws = wb.active if k == 0 else wb.create_sheet()
        ws.title = title[:31]
        ws["A1"] = f"{title} — {as_of}"
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = note
        ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max(len(heads), 1))
        ws.row_dimensions[2].height = 44
        for j, h in enumerate(heads, 1):
            c = ws.cell(row=4, column=j, value=h)
            c.fill, c.font, c.alignment = navy, Font(color="FFFFFF", bold=True), Alignment(wrap_text=True, vertical="center")
        ws.row_dimensions[4].height = 32
        for i, r in enumerate(rows, 5):
            for j, v in enumerate(r, 1):
                c = ws.cell(row=i, column=j, value=v)
                if fmt and j in fmt:
                    c.number_format = fmt[j]
                if (i - 5) in (bold_rows or ()):
                    c.font, c.fill = Font(bold=True), band
                elif i % 2 == 0:
                    c.fill = light
                tone = (colour or {}).get(j)
                t = tone(v) if tone else None
                if t:
                    c.font = Font(bold=c.font.bold, color="1B7F3B" if t == "good" else "B00020" if t == "bad" else "9A6B00")
        for j, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(j)].width = w
        ws.freeze_panes = "B5"
        ws.page_setup.orientation = "landscape"
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    wb.save(path)
    return path


def _pdf(path, title, sub, blocks):
    """blocks: ("h", text) | ("p", text) | ("note", text) | ("table", heads, rows, widths_cm, colour_cols) | ("chart", drawing)"""
    import re
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Title"], fontSize=16, alignment=0, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=11, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor("#1F2A44"))
    body = ParagraphStyle("b", parent=ss["Normal"], fontSize=8.5, leading=11)
    small = ParagraphStyle("s", parent=ss["Normal"], fontSize=7.5, leading=9.5, textColor=colors.HexColor("#555555"))
    navy, light = colors.HexColor("#1F2A44"), colors.HexColor("#EEF2F8")
    num = re.compile(r"^[+\-±]?[\d,]+(\.\d+)?( ?(d|days|EGP|MT|%))?$|^—$")
    el = [Paragraph(title, h1), Paragraph(sub, small), Spacer(1, 4)]
    for b in blocks:
        if b[0] == "h":
            el.append(Paragraph(b[1], h2))
        elif b[0] == "p":
            el.append(Paragraph(b[1], body))
        elif b[0] == "note":
            el.append(Paragraph(b[1], small))
        elif b[0] == "chart":
            el.append(b[1])
        elif b[0] == "table":
            _t, heads, rows, widths, cc = b[:5]
            hot = b[5] if len(b) > 5 else ()
            th = ParagraphStyle("th", parent=body, fontSize=7.5, leading=9, textColor=colors.white)
            tdp = ParagraphStyle("td", parent=body, fontSize=7.5, leading=9)
            data = [[Paragraph(f"<b>{h}</b>", th) for h in heads]]
            data += [[Paragraph(str(c), tdp) if isinstance(c, str) and len(c) > 15 else c for c in r] for r in rows]
            t = Table(data, colWidths=[w * cm for w in widths], repeatRows=1)
            st = [("BACKGROUND", (0, 0), (-1, 0), navy), ("FONTSIZE", (0, 1), (-1, -1), 7.5),
                  ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, light]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                  ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#C9D1E0")),
                  ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
            for i, r in enumerate(rows, 1):
                for j, v in enumerate(r):
                    if j and (isinstance(v, (int, float)) or (isinstance(v, str) and num.match(v.strip()))):
                        st.append(("ALIGN", (j, i), (j, i), "RIGHT"))
                    if j in cc and isinstance(v, str):
                        if v.startswith("+"):
                            st.append(("TEXTCOLOR", (j, i), (j, i), colors.HexColor("#1B7F3B")))
                        elif v.startswith("-") or v.startswith("−"):
                            st.append(("TEXTCOLOR", (j, i), (j, i), colors.HexColor("#B00020")))
                if i - 1 in hot:
                    st.append(("BACKGROUND", (0, i), (-1, i), colors.HexColor("#FDECEE")))
            t.setStyle(TableStyle(st))
            el.append(t)
    doc = SimpleDocTemplate(path, pagesize=landscape(A4), leftMargin=1.2 * cm, rightMargin=1.2 * cm, topMargin=1.0 * cm,
                            bottomMargin=1.0 * cm, title=title)
    doc.build(el)
    return path


def _f(v, d=0, sign=False):
    if v is None or v == "":
        return "—"
    if isinstance(v, str):
        return v
    return f"{v:+,.{d}f}" if sign else f"{v:,.{d}f}"


SIGNED = "+#,##0;-#,##0"
SIGNED2 = "+#,##0.00;-#,##0.00"


def write_pricing_deadlines_excel(model, path):
    rows = pricing_deadlines(model)
    tone = lambda v: "bad" if isinstance(v, str) and (v.startswith("URGENT") or v.startswith("PAST")) else ("warn" if v == "Soon" else None)
    data = [[r["status"], r["days_to_fnd"], r["first_notice"], r["futures"], r["contract"], r["supplier"], r["commodity"], r["unpriced_mt"],
             r["consumed_mt"], r["premium"], r["live_cbot"], r["low30"], r["high30"], r["pos30"], r["cif_now"], r["be_cbot"], r["headroom"],
             r["egp_per_10"], r["fix_at"], r["protect_at"], r["alert"], r["last_trade"]] for r in rows]
    tot = [len(data)] if data else []
    if data:
        data.append(["Total", None, "", "", f"{len(rows)} contracts", "", "", sum(r["unpriced_mt"] for r in rows), sum(r["consumed_mt"] for r in rows),
                     None, None, None, None, None, None, None, None, sum(r["egp_per_10"] or 0 for r in rows), None, None, "", ""])
    note = (f"Contracts not priced yet, soonest deadline first. First notice day = last business day before the futures month; "
            f"price (or roll) before it. URGENT ≤ {URGENT_DAYS} days, Soon ≤ {SOON_DAYS} days. 30-day position: 0% = at the 30-day low, "
            "100% = at the high. Break-even / headroom against today's local price (incl. transport when known). "
            "EGP per 10 ¢ = what a 10 ¢/bu (10 $/st for SBM) CBOT move changes the cost of the tonnes not priced.")
    return _xl(path, model.get("as_of"), [("Pricing Deadlines", note,
        ["Status", "Days to first notice", "First notice day", "Futures", "Contract", "Supplier", "Commodity", "Not priced MT",
         "of which consumed", "Premium", "Live CBOT", "30-day low", "30-day high", "30-day position %", "CIF now $/MT",
         "Break-even CBOT", "Headroom", "EGP per 10 ¢", "Alert: fix at ≤", "Alert: protect ≥", "Alert status", "Last trade day"],
        data, [14, 10, 12, 9, 22, 16, 11, 11, 11, 9, 10, 10, 10, 10, 11, 11, 10, 14, 11, 11, 12, 12],
        {2: "0", 8: "#,##0", 9: "#,##0", 10: "#,##0.00", 11: "#,##0.00", 12: "#,##0.00", 13: "#,##0.00", 14: "0", 15: "#,##0.00",
         16: "#,##0.00", 17: SIGNED2, 18: "#,##0", 19: "#,##0.00", 20: "#,##0.00"}, set(tot), {1: tone})])


def write_stock_watch_pdf(model, path):
    rows = stock_watch(model)
    hot = {i for i, r in enumerate(rows) if r["status"].startswith(("GAP", "Runs"))}
    blocks = [("p", "Days of cover per commodity at the configured daily rate, against the next dated arrival. Tonnes on order "
                    "without an arrival date cannot be counted as cover — enter the expected delivery date on the contract."),
              ("h", "Cover and next arrival"),
              ("table", ["Commodity", "Status", "Stock MT", "Daily rate", "Days of cover", "Runs out", "Next arrival", "Arrival MT",
                         "On order — dated", "On order — no date", "Need next 30 days", "Covered next 30 days"],
               [[r["code"], r["status"], _f(r["stock_mt"]), _f(r["daily_rate"]), _f(r["cover_days"], 1), r["stockout"] or "—",
                 (f"{r['next_arrival']} ({r['next_arrival_contract']})" if r["next_arrival"] else "none dated"), _f(r["next_arrival_mt"]),
                 _f(r["dated_on_order_mt"]), _f(r["undated_mt"]), _f(r["need_30d"]), _f(r["covered_30d"])] for r in rows],
               [2.0, 5.6, 1.6, 1.5, 1.6, 2.0, 3.6, 1.6, 1.8, 1.8, 1.8, 2.0], (), hot)]
    und = [r for r in rows if r["undated_mt"]]
    if und:
        blocks += [("h", "On order without an arrival date"),
                   ("table", ["Commodity", "MT", "Contracts"], [[r["code"], _f(r["undated_mt"]), r["undated_contracts"]] for r in und],
                    [2.4, 2.0, 18.0], ())]
    dated = [(r["code"], a) for r in rows for a in r["arrivals"]]
    if dated:
        blocks += [("h", "Dated arrivals"), ("table", ["Commodity", "Date", "MT", "Contract"],
                                             [[c, a["date"], _f(a["mt"]), a["contract"]] for c, a in dated], [2.4, 2.4, 2.0, 8.0], ())]
    blocks.append(("note", "Stock = FIFO stock on hand on open and closed contracts; consumption days are FIFO estimates at the configured rate."))
    return _pdf(path, f"Stock & Arrivals Watch — {model.get('as_of')}", f"Prometheus Procurement · generated {model.get('generated', '')}", blocks)


def _line_chart(series_list, width=760, height=150, labels=None):
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    d = Drawing(width, height)
    pal = [colors.HexColor(c) for c in ("#2F6DB5", "#C8553D", "#1B7F3B", "#8E44AD", "#9A6B00", "#555555")]
    data = [[(i, v) for i, v in enumerate(s) if v is not None] for s in series_list]
    data = [x for x in data if len(x) > 1]
    if not data:
        return d
    lp = LinePlot()
    lp.x, lp.y, lp.width, lp.height = 40, 20, width - 200, height - 35
    lp.data = data
    for i in range(len(data)):
        lp.lines[i].strokeColor = pal[i % len(pal)]
        lp.lines[i].strokeWidth = 1.4
    lp.xValueAxis.visibleLabels = False
    lp.yValueAxis.labels.fontSize = 7
    lp.yValueAxis.labels.fontName = "Helvetica"
    d.add(lp)
    for i, lab in enumerate(labels or []):
        d.add(String(width - 150, height - 20 - i * 11, lab, fontSize=7.5, fontName="Helvetica", fillColor=pal[i % len(pal)]))
    return d


def write_weekly_review_pdf(model, path):
    w = weekly_review(model)
    blocks = [("p", f"Week {w['week']} against the previous week ({w['previous_week']}). Consumption days are FIFO estimates; "
                    "savings are against the local price in force each day.")]
    if w["consumption"]:
        blocks += [("h", "Consumption and savings vs local"),
                   ("table", ["Commodity", "MT this week", "MT previous", "Saving incl. EGP", "previous", "Saving/MT incl.", "previous",
                              "Saving excl. EGP", "previous"],
                    [[c["base"], _f(c["mt"]), _f(c["mt_prev"]), _f(c["saving"], 0, True), _f(c["saving_prev"], 0, True),
                      _f(c["saving_mt"], 0, True), _f(c["saving_mt_prev"], 0, True), _f(c["saving_excl"], 0, True),
                      _f(c["saving_excl_prev"], 0, True)] for c in w["consumption"]],
                    [2.4, 2.2, 2.2, 2.8, 2.8, 2.4, 2.4, 2.8, 2.8], (3, 4, 5, 6, 7, 8))]
    blocks += [("h", "Market moves"),
               ("table", ["Item", "Now", "Date", "Week ago", "Change 1 week", "Change 4 weeks"],
                [[m["item"], _f(m["now"], 2 if "FX" not in m["item"] else 4), m["date"], _f(m["week_ago"], 2), _f(m["chg_week"], 2, True),
                  _f(m["chg_4w"], 2, True)] for m in w["market"]], [3.6, 2.4, 2.4, 2.4, 2.6, 2.6], ()),
               ("note", "CBOT over the last 12 weeks, indexed (12 weeks ago = 100) so the commodities can be compared."),
               ("chart", _line_chart([[v / m["trend"][0] * 100 for v in m["trend"]] for m in w["market"] if "CBOT" in m["item"] and m["trend"]],
                                     labels=[f"{m['item']} (now {m['now']:,.2f})" for m in w["market"] if "CBOT" in m["item"] and m["trend"]])),
               ("h", "Local market (EGP/MT, without transport)"),
               ("table", ["Commodity", "Now", "Date", "Change 1 week", "Change 4 weeks"],
                [[r["key"], _f(r["now"]), r["date"], _f(r["chg_week"], 0, True), _f(r["chg_4w"], 0, True)] for r in w["local"]],
                [3.0, 2.4, 2.4, 2.6, 2.6], ())]
    if w["premium_trend"]:
        blocks += [("h", "Local-equivalent premium vs our latest premium (8 week-ends)"),
                   ("p", "The premium the local price amounts to over that day's CBOT, after discharge and clearance. Above our premium "
                         "= the local market is dearer than importing at our terms; a falling line = local getting cheaper relative to imports."),
                   ("table", ["Commodity", "Reference contract", "Our premium"] + [e[5:] for e, _v in w["premium_trend"][0]["points"]] + ["Gap now"],
                    [[p["code"], p["ref_contract"], _f(p["ref_premium"], 1)] + [_f(v, 1) for _e, v in p["points"]] + [_f(p["gap_now"], 1, True)]
                     for p in w["premium_trend"]], [2.2, 3.6, 1.8] + [1.5] * len(w["premium_trend"][0]["points"]) + [1.8],
                    (3 + len(w["premium_trend"][0]["points"]),)),
                   ("chart", _line_chart([[v for _e, v in p["points"]] for p in w["premium_trend"]],
                                         labels=[f"{p['code']} (ours {p['ref_premium']:.0f})" for p in w["premium_trend"]]))]
    sl = w["since_last"] or {}
    if sl.get("previous"):
        blocks += [("h", f"Headline figures since the report of {sl['previous'].get('generated')}"),
                   ("table", ["Figure", "Previous", "Now", "Change"],
                    [[r["label"], _f(r["previous"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0),
                      _f(r["now"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0),
                      _f(r["change"], 2 if "CBOT" in r["label"] or "FX" in r["label"] else 0, True)] for r in sl["rows"]],
                    [7.0, 3.0, 3.0, 3.0], ())]
    return _pdf(path, f"Weekly Savings & Market Review — week to {w['as_of']}",
                f"Prometheus Procurement · generated {w['generated']} · checksum {w['checksum']}", blocks)


def write_pipeline_excel(model, path):
    p = pipeline(model)
    rows = [[r["stage"], r["contract"], r["supplier"], r["commodity"], r["origin"], r["priced"], r["form4"], r["qty_mt"], r["outstanding_mt"],
             r["stock_mt"], r["consumed_mt"], r["arrival"], r["cif"], r["cif_basis"], r["fx"], r["fx_basis"], r["value_usd"], r["value_egp"],
             r["to_arrive_usd"], r["to_arrive_egp"], r["payment_terms"]] for r in p["rows"]]
    tone_p = lambda v: "bad" if v == "NOT PRICED" else None
    tone_f = lambda v: "warn" if v == "Pending" else None
    summ = [[s["base"], s["stage"], s["contracts"], s["mt"], s["usd"], s["egp"], s["not_priced_mt"], s["form4_pending"]] for s in p["summary"]]
    arr = [[a["month"], a["base"], a["mt"], a["usd"], a["egp"]] for a in p["arrivals"]]
    arr.append(["Total to arrive", "", sum(a["mt"] for a in p["arrivals"]), p["to_arrive_usd"], p["to_arrive_egp"]])
    return _xl(path, model.get("as_of"), [
        ("Pipeline", "Every live contract by stage: to arrive → in stock → consumed (still open in the app). Value = CIF × contract MT "
                     "(indicative CIF at the live CBOT for contracts not priced; FX = Form 4, else today's market FX). Payment terms are not "
                     "recorded on the contracts, so due dates cannot be shown — add them to get a payment calendar.",
         ["Stage", "Contract", "Supplier", "Commodity", "Origin", "Priced?", "Form 4", "Contract MT", "To arrive MT", "In stock MT",
          "Consumed MT", "Arrival", "CIF $/MT", "CIF basis", "FX", "FX basis", "Value USD", "Value EGP", "To arrive USD", "To arrive EGP",
          "Payment terms"], rows, [22, 22, 15, 11, 10, 11, 10, 10, 10, 10, 10, 12, 9, 30, 9, 30, 13, 15, 13, 15, 13],
         {8: "#,##0", 9: "#,##0", 10: "#,##0", 11: "#,##0", 13: "#,##0.00", 15: "0.0000", 17: "#,##0", 18: "#,##0", 19: "#,##0", 20: "#,##0"},
         set(), {6: tone_p, 7: tone_f}),
        ("By Stage", "Contracts, tonnes and value per commodity and stage; tonnes not priced and Form 4 still pending.",
         ["Commodity", "Stage", "Contracts", "MT", "Value USD", "Value EGP", "Not priced MT", "Form 4 pending"], summ,
         [12, 26, 10, 12, 15, 17, 14, 13], {3: "0", 4: "#,##0", 5: "#,##0", 6: "#,##0", 7: "#,##0", 8: "0"}, set(), {}),
        ("Arrivals & Cash", "Tonnes still to arrive and the CIF value still to pay, by expected arrival month (not recorded = no delivery "
                            "date on the contract).", ["Arrival month", "Commodity", "MT", "USD", "EGP at FX used"], arr,
         [16, 12, 12, 15, 17], {3: "#,##0", 4: "#,##0", 5: "#,##0"}, {len(arr) - 1}, {})])


def write_action_list_excel(model, path, history=None):
    a = action_list(model, history)
    rows = [[r["status"], r["severity"], r["type"], r["category"], r["contract"], r["base"], r["mt"], r["detail"], r["action"], r["since"], "", "", ""]
            for r in a["rows"]]
    st = lambda v: "bad" if v in ("New", "Open") else ("good" if v == "FIXED" else None)
    sv = lambda v: "bad" if v == "High" else ("warn" if v == "Medium" else None)
    prev = a["previous"]
    note = ((f"Against the report of {prev['generated']} (data as of {prev['as_of']}): {a['new']} new, {a['fixed']} fixed, "
             f"{a['open']} open. " if prev else "First weekly list — the next one will mark items new / still open / fixed. ")
            + "Owner, due date and comment are for the team to fill in.")
    return _xl(path, model.get("as_of"), [("Action List", note,
        ["Status", "Severity", "Type", "Issue", "Contract", "Commodity", "MT", "Detail", "What to do", "Open since", "Owner", "Due date", "Comment"],
        rows, [11, 9, 13, 26, 22, 10, 10, 60, 44, 12, 14, 12, 30], {7: "#,##0"}, set(), {1: st, 2: sv})])


def weekly_email_summary(model, history=None):
    """Body of the weekly pack email: (plain text, HTML)."""
    from html import escape as esc
    w, a, p = weekly_review(model), action_list(model, history), pricing_deadlines(model)
    s = stock_watch(model)
    urgent = [r for r in p if r["status"] in ("URGENT", "Soon") or r["status"].startswith("PAST")]
    risks = [r for r in s if r["status"].startswith(("GAP", "Runs"))]
    tot = lambda k: sum(c[k] or 0 for c in w["consumption"])
    lines = [f"Prometheus Procurement — Weekly Pack, week {w['week']}", "",
             f"Consumed {tot('mt'):,.0f} MT (previous week {tot('mt_prev'):,.0f}); saving vs local incl. transport "
             f"EGP {tot('saving'):+,.0f} (previous {tot('saving_prev'):+,.0f})."]
    lines += ["", "MARKET (1 week / 4 weeks)"] + [f"  {m['item']}: {_f(m['now'], 2)} ({_f(m['chg_week'], 2, True)} / {_f(m['chg_4w'], 2, True)})" for m in w["market"]]
    lines += ["", "LOCAL vs OUR PREMIUM (local-equivalent premium now, ours, gap)"] + [
        f"  {t['code']}: {_f(t['now'], 1)} vs {_f(t['ref_premium'], 1)} → {_f(t['gap_now'], 1, True)}" for t in w["premium_trend"]]
    if urgent:
        lines += ["", f"PRICING DEADLINES: {sum(r['unpriced_mt'] for r in urgent):,.0f} MT not priced, first notice "
                      f"{urgent[0]['first_notice']} ({urgent[0]['days_to_fnd']} days)"]
    if risks:
        lines += ["", "STOCK RISKS"] + [f"  {r['code']}: {r['status']}" for r in risks]
    lines += ["", f"ACTION LIST: {a['open']} open · {a['new']} new · {a['fixed']} fixed since last week", "",
              "Attached: Weekly Savings & Market Review (PDF), Procurement Pipeline (Excel), Action List (Excel)."]
    hh = [f'<div style="font:14px Arial,sans-serif;color:#222"><h2 style="margin:0 0 4px;color:#1F2A44">Weekly Pack — week {esc(w["week"])}</h2>']
    hh.append(f"<p>Consumed <b>{tot('mt'):,.0f} MT</b> (previous week {tot('mt_prev'):,.0f}) · saving vs local incl. transport "
              f"<b>EGP {tot('saving'):+,.0f}</b> (previous {tot('saving_prev'):+,.0f}).</p>")
    if urgent:
        hh.append(f'<p style="background:#fff4d6;padding:8px;border-radius:4px"><b>Pricing deadline:</b> '
                  f"{sum(r['unpriced_mt'] for r in urgent):,.0f} MT not priced, first notice day {esc(urgent[0]['first_notice'])} "
                  f"({urgent[0]['days_to_fnd']} days). CBOT {_f(urgent[0]['live_cbot'], 2)} — "
                  f"{_f(urgent[0]['pos30'], 0)}% of its 30-day range.</p>")
    for r in risks:
        hh.append(f'<p style="background:#fdecee;color:#B00020;padding:8px;border-radius:4px"><b>{esc(r["code"])}:</b> {esc(r["status"])}</p>')
    td = 'style="padding:4px 8px;border-bottom:1px solid #e3e8f0;text-align:right"'
    tl = 'style="padding:4px 8px;border-bottom:1px solid #e3e8f0"'
    th = 'style="padding:5px 8px;background:#1F2A44;color:#fff;text-align:left"'
    hh.append('<table cellspacing="0" style="border-collapse:collapse;font:13px Arial"><tr>' + "".join(f"<th {th}>{h}</th>" for h in
              ("Market", "Now", "1 week", "4 weeks")) + "</tr>" + "".join(
              f"<tr><td {tl}>{esc(m['item'])}</td><td {td}>{_f(m['now'], 2)}</td><td {td}>{_f(m['chg_week'], 2, True)}</td><td {td}>{_f(m['chg_4w'], 2, True)}</td></tr>"
              for m in w["market"]) + "</table>")
    if w["premium_trend"]:
        hh.append("<p style='margin:12px 0 2px'><b>Local market vs our premium</b> (the premium the local price amounts to over CBOT; "
                  "above ours = local dearer than importing)</p>"
                  '<table cellspacing="0" style="border-collapse:collapse;font:13px Arial"><tr>' + "".join(f"<th {th}>{h}</th>" for h in
                  ("Commodity", "Local-equivalent now", "Week ago", "Our premium", "Gap")) + "</tr>" + "".join(
                  f"<tr><td {tl}>{esc(t['code'])}</td><td {td}>{_f(t['now'], 1)}</td><td {td}>{_f(t['week_ago'], 1)}</td>"
                  f"<td {td}>{_f(t['ref_premium'], 1)}</td><td {td}><b>{_f(t['gap_now'], 1, True)}</b></td></tr>" for t in w["premium_trend"]) + "</table>")
    hh.append(f"<p><b>Action list:</b> {a['open']} open · {a['new']} new · {a['fixed']} fixed since last week.</p>"
              "<p style='color:#666;font-size:12px'>Attached: Weekly Savings &amp; Market Review (PDF), Procurement Pipeline (Excel), Action List (Excel).</p></div>")
    return "\n".join(lines), "".join(hh)
