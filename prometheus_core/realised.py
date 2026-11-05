"""Realised savings per closed contract, from the management report engine.

The app's Realised Savings, the dashboard and the workbook all value a closed
contract the same way:

* cost   = the contract's fixed CIF x FX (Form 4, else delivery FX)
           + its discharge + clearance + route freight on the delivery date.
           The cost is the same every day.
* local  = the local price in force on each consumption day (origin-matched),
           incl. transport; excl. transport is kept alongside.
* tonnes = the tonnes actually consumed (FIFO estimate). Tonnes of a closed
           contract still in stock are reported, not realised.

``aggregate(model)`` turns the engine's per-day savings rows into one record
per contract. It does no pricing of its own, so it cannot drift from the
engine.
"""
from __future__ import annotations

STALE_DAYS = 5   # a local quote older than this on a consumption day gets a warning


def _num(v):
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _empty(contract):
    return {
        "contract_id": contract.get("id"),
        "status": contract.get("status") or "",
        "consumed_mt": 0.0, "compared_mt": 0.0, "compared_excl_mt": 0.0,
        "no_local_mt": 0.0, "no_cost_mt": 0.0,
        "saving": 0.0, "saving_excl": 0.0,
        "_cost": 0.0, "_cost_excl": 0.0, "_local": 0.0, "_local_excl": 0.0,
        "_freight": 0.0,
        "cif_used": None, "fx_used": None, "discharge": None, "clearance": None,
        "freight_basis": "",
        "first_day": "", "last_day": "", "local_from": "", "local_to": "",
        "local_age_max": None, "stale_mt": 0.0,
        "days": [],
        "in_stock_mt": max(_num(contract.get("available_mt")) or 0.0, 0.0),
    }


def aggregate(model, stale_days=STALE_DAYS):
    """One record per contract in ``model["contracts"]``, keyed by contract id.

    Record keys: consumed_mt, compared_mt (tonnes with a local price and a
    landed cost), compared_excl_mt, no_local_mt, no_cost_mt (local known but no
    landed cost, e.g. no route freight), saving / saving_excl (EGP), saving_mt / saving_excl_mt,
    cost / cost_excl / local / local_excl (tonne-weighted EGP/MT), cif_used,
    fx_used, discharge, clearance, freight, freight_basis, first_day /
    last_day (consumption), local_from / local_to (dates of the local quotes
    used), local_age_max (days), stale (oldest quote older than
    ``stale_days``), stale_mt, in_stock_mt and days: a list of
    (date, mt, saving, saving_excl) in date order.
    """
    out = {}
    for c in model.get("contracts") or []:
        if c.get("id"):
            out[c["id"]] = _empty(c)
    for r in sorted(model.get("savings") or [], key=lambda x: (x.get("date") or "")):
        cid = r.get("contract_id")
        if not cid:
            continue
        a = out.get(cid)
        if a is None:
            a = out[cid] = _empty({"id": cid})
        mt = _num(r.get("mt")) or 0.0
        if mt <= 0:
            continue
        day = str(r.get("date") or "")[:10]
        a["consumed_mt"] += mt
        a["first_day"] = a["first_day"] or day
        a["last_day"] = day or a["last_day"]
        sav, sav_x = _num(r.get("saving")), _num(r.get("saving_excl"))
        cost, local = _num(r.get("cost")), _num(r.get("local"))
        cost_x, local_x = _num(r.get("cost_excl")), _num(r.get("local_excl"))
        ok = sav is not None and cost is not None and local is not None
        ok_x = sav_x is not None and cost_x is not None and local_x is not None
        if local is None and local_x is None:
            a["no_local_mt"] += mt
        elif not ok:
            a["no_cost_mt"] += mt          # local known, landed cost not (e.g. no route freight)
        if ok_x:
            a["compared_excl_mt"] += mt
            a["saving_excl"] += sav_x
            a["_cost_excl"] += cost_x * mt
            a["_local_excl"] += local_x * mt
        for k in ("cif_used", "fx_used", "discharge", "clearance"):
            if a[k] is None and _num(r.get(k)) is not None:
                a[k] = _num(r.get(k))
        if not a["freight_basis"] and r.get("freight_basis"):
            a["freight_basis"] = r["freight_basis"]
        ld = str(r.get("local_date") or "")[:10]
        if ld and (ok or ok_x):
            a["local_from"] = min(a["local_from"], ld) if a["local_from"] else ld
            a["local_to"] = max(a["local_to"], ld) if a["local_to"] else ld
        age = _num(r.get("local_age"))
        if age is not None and (ok or ok_x):
            a["local_age_max"] = age if a["local_age_max"] is None else max(a["local_age_max"], age)
            if age > stale_days:
                a["stale_mt"] += mt
        if not ok:
            a["days"].append((day, mt, None, sav_x if ok_x else None))
            continue
        a["compared_mt"] += mt
        a["saving"] += sav
        a["_cost"] += cost * mt
        a["_local"] += local * mt
        a["_freight"] += (_num(r.get("freight")) or 0.0) * mt
        a["days"].append((day, mt, sav, sav_x))
    for a in out.values():
        q, qx = a["compared_mt"], a["compared_excl_mt"]
        a["cost"] = a.pop("_cost") / q if q else None
        a["local"] = a.pop("_local") / q if q else None
        a["freight"] = a.pop("_freight") / q if q else None
        a["cost_excl"] = a.pop("_cost_excl") / qx if qx else None
        a["local_excl"] = a.pop("_local_excl") / qx if qx else None
        a["saving_mt"] = a["saving"] / q if q else None
        a["saving_excl_mt"] = a["saving_excl"] / qx if qx else None
        if not q:
            a["saving"] = None
        if not qx:
            a["saving_excl"] = None
        a["stale"] = a["local_age_max"] is not None and a["local_age_max"] > stale_days
    return out


def dated_values(days, excl=False):
    """[(date, saving)] for the compared days of one record (``days`` list)."""
    i = 3 if excl else 2
    return [(d[0], d[i]) for d in days or [] if d[i] is not None]


def split_by_month(days, excl=False):
    """{YYYY-MM: saving} for one record's days."""
    out = {}
    for d, v in dated_values(days, excl):
        out[d[:7]] = out.get(d[:7], 0.0) + v
    return out


def slice_days(days, keep):
    """(mt, saving, saving_excl) over the compared days whose date passes ``keep``."""
    mt = s = sx = 0.0
    for d, m, v, vx in days or []:
        if v is None or not keep(d):
            continue
        mt += m
        s += v
        sx += vx or 0.0
    return mt, s, sx


def age_label(rec, stale_days=STALE_DAYS):
    """'2026-04-14 → 2026-04-26 · 3d' with a ⚠ when the oldest quote is stale."""
    if not rec or not rec.get("local_from"):
        return "—"
    span = rec["local_from"] if rec["local_from"] == rec["local_to"] else f"{rec['local_from']} → {rec['local_to']}"
    age = rec.get("local_age_max")
    if age is None:
        return span
    return f"{span} · {age:.0f}d" + (" ⚠" if age > stale_days else "")
