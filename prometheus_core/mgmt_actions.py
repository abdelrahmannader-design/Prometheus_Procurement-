"""Decision and housekeeping sections of the management report.

Built on the finished report model (they never change its figures):

* pricing_alerts  — the targets set on contracts not yet priced, checked against the
                    live CBOT and the headroom against today's local price;
* exposure        — tonnes whose price is not fixed yet, by commodity and futures month,
                    with the EGP effect of a CBOT move and of an FX move;
* since_last      — the headline figures against the previous saved report;
* data_to_fix     — every missing or doubtful input, one row per contract and issue.
"""
from __future__ import annotations

import datetime as dt

CBOT_STEP = {"CORN": 10.0, "SOYBEAN": 10.0, "WHEAT": 10.0, "SBM": 10.0}   # ¢/bu, or $/short ton for SBM
FX_STEP = 1.0                                                            # EGP per USD
SINCE_LAST_KPIS = [
    ("historical_saving_egp", "Historical savings incl. transport", "EGP"),
    ("historical_saving_excl_egp", "Historical savings excl. transport", "EGP"),
    ("historical_mt", "Compared tonnes (incl. transport)", "MT"),
    ("open_fixed_potential_egp", "Open potential — confirmed", "EGP"),
    ("open_indicative_potential_egp", "Open potential — indicative", "EGP"),
    ("cbot_net_usd", "CBOT benchmark net (consumption days)", "USD"),
    ("open_available_mt", "Stock on open contracts", "MT"),
    ("open_outstanding_mt", "Outstanding on open contracts", "MT"),
]


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


def _unfixed(c):
    f = c.get("fix") or {}
    return bool(f.get("eligible")) and not f.get("fixed")


# ── pricing alerts ───────────────────────────────────────────────────────

def pricing_alerts(model, targets):
    """One row per contract with a target; ``triggered`` lists the targets that are hit now.

    Targets per contract id: ``cbot_below`` (fix when CBOT falls to this), ``cbot_above``
    (protect when CBOT rises to this), ``headroom_below`` (warn when the CBOT is this close
    to the break-even against local, including transport when known), ``note``.
    """
    rows = []
    op = {o["contract_id"]: o for o in model.get("open", [])}
    cons = {c["id"]: c for c in model.get("contracts", [])}
    for cid, t in (targets or {}).items():
        if not isinstance(t, dict):
            continue
        c = cons.get(cid)
        if not c:
            continue
        o = op.get(cid, {})
        cur = c.get("current") or {}
        cbot = _n(o.get("latest_cbot", cur.get("cbot")))
        head = _n(o.get("headroom_incl"))
        head_basis = "incl. transport"
        if head is None:
            head, head_basis = _n(o.get("headroom_excl")), "excl. transport"
        lo, hi, hb = _n(t.get("cbot_below")), _n(t.get("cbot_above")), _n(t.get("headroom_below"))
        hits = []
        if not _unfixed(c):
            status = "Priced — target no longer applies"
        else:
            if lo is not None and cbot is not None and cbot <= lo:
                hits.append(f"CBOT {cbot:,.2f} is at or below your target {lo:,.2f}")
            if hi is not None and cbot is not None and cbot >= hi:
                hits.append(f"CBOT {cbot:,.2f} is at or above your limit {hi:,.2f}")
            if hb is not None and head is not None and head <= hb:
                hits.append(f"Headroom {head:,.2f} ({head_basis}) is at or below {hb:,.2f}")
            status = "TRIGGERED" if hits else ("No live CBOT" if cbot is None else "Watching")
        rows.append({
            "contract_id": cid, "contract": c.get("contract", ""), "supplier": c.get("supplier", ""),
            "base": c.get("base", ""), "unit": (c.get("fix") or {}).get("unit", ""),
            "futures": (c.get("contract_month") or {}).get("code") or c.get("futures_month", ""),
            "premium": _n(c.get("premium")), "unpriced_mt": _unpriced_mt(c) if _unfixed(c) else 0.0,
            "remaining_mt": _n(o.get("unconsumed_mt")) or 0.0,
            "cbot": cbot, "cbot_time": o.get("latest_cbot_date") or cur.get("cbot_date", ""),
            "cbot_live": bool(o.get("latest_cbot_live")),
            "be_cbot": _n(o.get("be_cbot_incl")) if _n(o.get("be_cbot_incl")) is not None else _n(o.get("be_cbot_excl")),
            "headroom": head, "headroom_basis": head_basis,
            "cbot_below": lo, "cbot_above": hi, "headroom_below": hb, "note": t.get("note", ""),
            "set_at": t.get("set_at", ""), "status": status, "triggered": hits,
        })
    order = {"TRIGGERED": 0, "Watching": 1, "No live CBOT": 2}
    rows.sort(key=lambda r: (order.get(r["status"], 3), r["base"], r["contract"]))
    return rows


# ── price exposure ───────────────────────────────────────────────────────

def _unpriced_mt(c):
    qty = _n(c.get("qty_mt")) or 0.0
    lots = sum(_n(x.get("qty_mt")) or 0.0 for x in c.get("lots") or [] if _n(x.get("cbot")) is not None)
    return max(qty - lots, 0.0)


def exposure(model):
    """Tonnes not priced yet, by commodity and futures month, and FX not yet fixed (no Form 4).

    CBOT effect: step × factor × FX × unpriced MT (the CIF moves by step × factor $/MT).
    FX effect: 1 EGP × CIF × MT for contracts still on the provisional market FX.
    """
    groups, fx_rows = {}, []
    for c in model.get("contracts", []):
        cur = c.get("current") or {}
        f = c.get("fix") or {}
        if _unfixed(c) and (c.get("is_open") or (c.get("consumed_mt") or 0) > 0 or (c.get("available_mt") or 0) > 0):
            mt = _unpriced_mt(c)
            if mt > 1e-6:
                key = (c["base"], (c.get("contract_month") or {}).get("code") or c.get("futures_month") or "—")
                g = groups.setdefault(key, {"base": key[0], "futures": key[1], "unit": f.get("unit", ""),
                                            "factor": f.get("factor"), "contracts": [], "mt": 0.0, "prem_mt": 0.0,
                                            "prem_w": 0.0, "egp_per_step": 0.0, "cbot": _n(cur.get("cbot")),
                                            "cbot_time": cur.get("cbot_date", ""), "consumed_unpriced_mt": 0.0})
                fx = _n(cur.get("fx")) or _n(c.get("fx"))
                g["contracts"].append(c.get("contract", ""))
                g["mt"] += mt
                g["consumed_unpriced_mt"] += min(_n(c.get("consumed_mt")) or 0.0, mt)
                if _n(c.get("premium")) is not None:
                    g["prem_mt"] += mt
                    g["prem_w"] += _n(c.get("premium")) * mt
                if f.get("factor") and fx:
                    g["egp_per_step"] += CBOT_STEP.get(c["base"], 10.0) * f["factor"] * fx * mt
        if c.get("is_open") and str(cur.get("fx_basis") or "").startswith("Latest") and _n(cur.get("cif")):
            mt = _n(c.get("qty_mt")) or 0.0
            fx_rows.append({"base": c["base"], "contract": c.get("contract", ""), "contract_id": c["id"],
                            "mt": mt, "cif": _n(cur.get("cif")), "fx": _n(cur.get("fx")),
                            "egp_per_step": FX_STEP * _n(cur.get("cif")) * mt})
    cbot = []
    for g in sorted(groups.values(), key=lambda x: (x["base"], x["futures"])):
        step = CBOT_STEP.get(g["base"], 10.0)
        cbot.append({"base": g["base"], "futures": g["futures"], "unit": g["unit"], "step": step,
                     "contracts": len(g["contracts"]), "contract_names": ", ".join(g["contracts"]),
                     "unpriced_mt": g["mt"], "consumed_unpriced_mt": g["consumed_unpriced_mt"],
                     "avg_premium": g["prem_w"] / g["prem_mt"] if g["prem_mt"] else None,
                     "cbot": g["cbot"], "cbot_time": g["cbot_time"],
                     "egp_per_step": g["egp_per_step"], "egp_up": g["egp_per_step"], "egp_down": -g["egp_per_step"]})
    fx_by = {}
    for r in fx_rows:
        b = fx_by.setdefault(r["base"], {"base": r["base"], "contracts": 0, "mt": 0.0, "usd": 0.0, "egp_per_step": 0.0})
        b["contracts"] += 1
        b["mt"] += r["mt"]
        b["usd"] += r["cif"] * r["mt"]
        b["egp_per_step"] += r["egp_per_step"]
    return {"cbot": cbot, "fx": sorted(fx_by.values(), key=lambda x: x["base"]), "fx_contracts": fx_rows,
            "cbot_step": CBOT_STEP, "fx_step": FX_STEP,
            "total_unpriced_mt": sum(r["unpriced_mt"] for r in cbot),
            "total_cbot_egp_per_step": sum(r["egp_per_step"] for r in cbot),
            "total_fx_mt": sum(r["mt"] for r in fx_by.values()),
            "total_fx_egp_per_step": sum(r["egp_per_step"] for r in fx_by.values())}


# ── since the last report ────────────────────────────────────────────────

def snapshot(model, fx=None):
    """What is stored after each export so the next report can show what changed."""
    k = model.get("kpis", {})
    return {"generated": model.get("generated", ""), "as_of": model.get("as_of", ""),
            "checksum": model.get("checksum", ""),
            "kpis": {key: k.get(key) for key, _, _ in SINCE_LAST_KPIS},
            "cbot": {b: q.get("price") for b, q in (model.get("live_cbot") or {}).items()},
            "fx": fx,
            # the to-fix items, so the weekly action list can mark them new / still open / fixed
            "fix_keys": [f"{x['category']}|{x.get('contract_id') or x.get('detail', '')[:60]}" for x in model.get("data_to_fix") or []]}


def since_last(model, history, fx=None):
    """The headline figures against the latest report saved on an earlier day (else the latest one saved)."""
    hist = [h for h in history or [] if isinstance(h, dict) and h.get("generated") and h.get("generated") != model.get("generated")]
    earlier = [h for h in hist if str(h.get("as_of") or "") < str(model.get("as_of") or "")]
    prev = (earlier or hist or [None])[-1]
    if not prev:
        return {"previous": None, "rows": []}
    now = snapshot(model, fx)
    rows = []
    for key, label, unit in SINCE_LAST_KPIS:
        a, b = _n(prev.get("kpis", {}).get(key)), _n(now["kpis"].get(key))
        rows.append({"key": key, "label": label, "unit": unit, "previous": a, "now": b,
                     "change": (b - a) if None not in (a, b) else None})
    for base in sorted(set(prev.get("cbot") or {}) | set(now["cbot"])):
        a, b = _n((prev.get("cbot") or {}).get(base)), _n(now["cbot"].get(base))
        rows.append({"key": f"cbot_{base}", "label": f"Live CBOT {base}", "unit": "¢/bu" if base != "SBM" else "$/st",
                     "previous": a, "now": b, "change": (b - a) if None not in (a, b) else None})
    a, b = _n(prev.get("fx")), _n(fx)
    rows.append({"key": "fx", "label": "FX EGP/USD", "unit": "EGP", "previous": a, "now": b,
                 "change": (b - a) if None not in (a, b) else None})
    return {"previous": {"generated": prev.get("generated"), "as_of": prev.get("as_of"),
                         "checksum": prev.get("checksum")}, "rows": rows}


# ── data to fix ──────────────────────────────────────────────────────────

SEVERITY = {"High": 0, "Medium": 1, "Low": 2}


def data_to_fix(model, quote_status=None, stale_quote_days=1):
    """Every missing or doubtful input, with what it affects and what to do."""
    out = []
    as_of = _d(model.get("as_of"))
    op = {o["contract_id"]: o for o in model.get("open", [])}

    def add(sev, cat, c, detail, action, mt=None):
        out.append({"severity": sev, "category": cat, "contract_id": (c or {}).get("id", ""),
                    "contract": (c or {}).get("contract", ""), "supplier": (c or {}).get("supplier", ""),
                    "base": (c or {}).get("base", ""), "detail": detail, "action": action, "mt": mt})

    for c in model.get("contracts", []):
        o = op.get(c["id"])
        live = bool(c.get("is_open") or (o and (o.get("unconsumed_mt") or 0) > 0))
        used = (c.get("consumed_mt") or 0) > 0 or live
        if not used:
            continue
        rem = (o or {}).get("unconsumed_mt") or 0.0
        if c.get("clr_missing"):
            add("High" if rem > 0 else "Low", "Clearance not recorded", c,
                "Cost uses 0 clearance, so the import cost is understated" + (f" on {rem:,.0f} MT still to consume" if rem > 0 else ""),
                "Enter the clearance (EGP/MT) on the contract — or confirm it was bought cleared", rem or c.get("consumed_mt"))
        if c.get("disc_missing"):
            add("High" if rem > 0 else "Low", "Discharge not recorded", c, "Cost uses 0 discharge",
                "Enter the discharge (EGP/MT) on the contract", rem or c.get("consumed_mt"))
        if c.get("freight_egp_mt") is None:
            add("Medium", "Inland freight missing", c, c.get("freight_note") or "No freight route for this contract",
                "Add the route to the freight table or enter the freight on the contract", rem or c.get("consumed_mt"))
        elif "shows 0" in (c.get("freight_note") or ""):
            add("Medium", "Freight route rate is 0", c, c.get("freight_note"),
                "Correct the rate in the freight table", rem or c.get("consumed_mt"))
        if c.get("storage_status") == "Not recorded":
            add("Medium", "Storage date not recorded", c,
                "Consumption dates and the storage-date CBOT benchmark rely on it",
                "Enter the storage start date", c.get("qty_mt"))
        cur = c.get("current") or {}
        if c.get("is_open") and c.get("base") != "SBM" and str(cur.get("fx_basis") or "").startswith("Latest"):
            arrived = c.get("received") or (c.get("consumed_mt") or 0) > 0
            add("Medium" if arrived else "Low", "Form 4 pending", c,
                f"Valued at the provisional market FX {cur.get('fx') or 0:,.4f}" + ("" if arrived else " (not received yet)"),
                "Enter the Form 4 FX and date when issued", c.get("qty_mt"))
        if (c.get("fix") or {}).get("type") == "Check CIF / premium":
            add("High", "CBOT fixing looks wrong", c, (c.get("fix") or {}).get("status", ""),
                "Check the CIF and premium on the contract", c.get("qty_mt"))
        if o and (o.get("unconsumed_mt") or 0) > 0:
            if not o.get("local_date"):
                add("Medium", "No local price", c, "No local market price for this commodity",
                    "Enter today's local price", rem)
            elif o.get("local_stale"):
                add("Low", "Local price is old", c, f"Latest local quote {o['local_date']} ({o.get('local_age')} days old)",
                    "Enter today's local price", rem)
    qs = quote_status or {}
    for base, q in (model.get("live_cbot") or {}).items():
        t = _d(q.get("time"))
        if as_of and t and (as_of - t).days > stale_quote_days:
            add("Medium", "CBOT quote is old", None, f"{base} live quote is from {q.get('time')}",
                "Refresh market data in the app before exporting")
    fxq = qs.get("fx") or {}
    md, fetched = _d(fxq.get("market_date")), _d(fxq.get("fetched_at"))
    if as_of and md and (as_of - md).days > stale_quote_days:
        add("Medium", "FX quote is old", None,
            f"FX {fxq.get('price')} has market date {md.isoformat()}" + (f" (fetched {fxq.get('fetched_at')})" if fetched else ""),
            "Refresh the FX or enter today's rate")
    for r in model.get("freight_map") or []:
        if not _n(r.get("rate")):
            out.append({"severity": "Medium", "category": "Freight route rate is 0", "contract_id": "", "contract": "",
                        "supplier": "", "base": r.get("commodity", ""),
                        "detail": f"{r.get('commodity')}: {r.get('place')} → {r.get('destination')} is 0 in the freight table",
                        "action": "Correct the rate in the freight table", "mt": None})
    out.sort(key=lambda r: (SEVERITY.get(r["severity"], 9), r["category"], r["contract"]))
    return out


def add_sections(model, inp):
    """Attach the four sections to a built model (called by mgmt_report.build)."""
    fx = _n((inp.get("latest_fx") or {}).get("rate"))
    model["alerts"] = pricing_alerts(model, inp.get("pricing_alerts") or {})
    model["exposure"] = exposure(model)
    model["since_last"] = since_last(model, inp.get("report_history") or [], fx)
    model["data_to_fix"] = data_to_fix(model, inp.get("quote_status") or {})
    model["snapshot"] = snapshot(model, fx)
    return model
