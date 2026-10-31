"""Executive import-savings figures, contract by contract.

Pure logic: no Tkinter, files or network. The app hands in its own FIFO
consumption draws (already valued against the local price of each day),
its cost engine's figures and the stored CBOT history, and this module
answers four questions without counting any tonne twice:

1. Historical savings — every tonne already consumed, against the local
   price on the day it was consumed.
2. Open and in-stock potential — tonnes delivered but not yet consumed,
   and tonnes not yet delivered, against today's local price.
3. CBOT pricing advantage — the contract's CBOT fixing against the CBOT
   prevailing on each day its tonnes were consumed. A benchmark, never
   added to the savings against local.
4. Contract ranking — the same figures per contract, rolled up by
   commodity, with totals that are sums of the rows.

Each contract's quantity is split once: consumed + in stock + not yet
delivered = contract quantity (any shortfall is shown, not hidden).
"""

from __future__ import annotations

import datetime as dt

from . import timing_report as tr

EXEC_SAVINGS_VERSION = "1.0"

#: Plausible CBOT fixing ranges, by commodity, in its own quote unit. A
#: fixing outside them usually means the premium was entered in another
#: unit (USD/MT instead of ¢/bu, say), so it is flagged and not used.
PLAUSIBLE_CBOT = {"CORN": (250.0, 900.0), "SOYBEAN": (700.0, 1900.0),
                  "WHEAT": (350.0, 1300.0), "SBM": (200.0, 650.0)}
UNITS = {"CORN": "¢/bu", "SOYBEAN": "¢/bu", "WHEAT": "¢/bu", "SBM": "$/short ton"}

REALIZED, PROVISIONAL = "Realized", "Provisional (CIF not final)"


def _num(v, default=None):
    try:
        if v is None or (isinstance(v, str) and not v.strip()):
            return default
        return float(str(v).replace(",", ""))
    except Exception:
        return default


def _date(v):
    if isinstance(v, dt.date):
        return v
    try:
        return dt.date.fromisoformat(str(v or "")[:10])
    except Exception:
        return None


# ── 5. the CBOT fixing, actual or implied ────────────────────────────────

def cbot_fixing(contract, factor, base):
    """The CBOT a contract was priced at, and how we know it.

    Pricing lots carry their own CBOT (actual, tonne-weighted). Otherwise,
    for a genuine CBOT + premium contract: CIF ÷ factor − premium — the
    *implied* fixing, labelled as such whether or not a pricing date is
    recorded, because the CBOT itself was never stored. Flat-price
    contracts have no fixing. A result outside the commodity's plausible
    range is flagged as a likely premium-unit problem and not used.
    """
    c = contract or {}
    out = {"value": None, "label": "", "source": "", "flag": "", "unit": UNITS.get(base, "")}
    lots = [x for x in (c.get("pricing_lots") or []) if isinstance(x, dict)
            and _num(x.get("cbot")) is not None and _num(x.get("qty_mt"))]
    if lots:
        q = sum(_num(x["qty_mt"]) for x in lots)
        out.update(value=sum(_num(x["cbot"]) * _num(x["qty_mt"]) for x in lots) / q,
                   label="Actual CBOT fixing (pricing lots)", source="pricing lots",
                   priced_mt=q)
    else:
        premium, cif = _num(c.get("premium_cents")), _num(c.get("cif_usd_mt"))
        if premium in (None, 0.0):
            out["flag"] = "flat price — no CBOT + premium structure"
            return out
        if not factor:
            out["flag"] = "no CBOT conversion factor for this commodity"
            return out
        if not cif:
            out["flag"] = "no CIF recorded"
            return out
        out.update(value=cif / factor - premium, source="CIF ÷ factor − premium",
                   label=("Implied CBOT fixing (pricing date recorded, CBOT not stored)"
                          if c.get("pricing_date") else "Implied CBOT fixing"))
    lo, hi = PLAUSIBLE_CBOT.get(base, (None, None))
    if lo is not None and not (lo <= out["value"] <= hi):
        out["flag"] = (f"implied fixing {out['value']:,.2f} {out['unit']} is outside the usual "
                       f"{lo:,.0f}–{hi:,.0f} range — check the premium's unit")
        out["usable"] = False
    else:
        out["usable"] = True
    return out


def check_against_market(value, history, end, lookback_days=150, margin=0.10, after_days=120):
    """Does an implied fixing sit where the stored CBOT actually traded?

    Searched from ``lookback_days`` before arrival to ``after_days`` after
    it, because a contract can be priced after its cargo lands. A fixing
    more than ``margin`` outside that range usually means the premium is in
    the wrong unit or belongs to another futures month. Returns a flag or "".
    """
    end = _date(end)
    if value is None or end is None or len(history) == 0:
        return ""
    vals = [v for _, v in history.between(end - dt.timedelta(days=lookback_days),
                                          end + dt.timedelta(days=after_days))]
    if not vals:
        return ""
    lo, hi = min(vals), max(vals)
    if value < lo * (1 - margin) or value > hi * (1 + margin):
        return (f"implied fixing {value:,.2f} is outside the {lo:,.2f}–{hi:,.2f} the CBOT traded from "
                f"{lookback_days} days before to {after_days} days after arrival — check the premium's "
                f"unit and futures month")
    return ""


def possible_fixing_dates(history, value, end, lookback_days=150, tolerance=None, limit=3):
    """Days whose stored CBOT was closest to an implied fixing — indicative.

    Searched in the ``lookback_days`` before ``end`` (arrival). The stored
    series is the front month, not the contract's own futures month, so a
    match is a lead to check, not evidence of the fixing date.
    """
    end = _date(end)
    if value is None or end is None or len(history) == 0:
        return []
    tol = tolerance if tolerance is not None else max(abs(value) * 0.004, 0.5)
    window = history.between(end - dt.timedelta(days=lookback_days), end)
    near = sorted(((abs(v - value), d, v) for d, v in window if abs(v - value) <= tol),
                  key=lambda x: (x[0], x[1]))
    return [{"date": d.isoformat(), "cbot": v, "gap": round(g, 4)} for g, d, v in near[:limit]]


def clean_on_or_before(history, day, spikes):
    """The last stored CBOT on or before ``day`` that is not a stray print."""
    v, d = history.on_or_before(day)
    while d is not None and d in spikes:
        v, d = history.on_or_before(d - dt.timedelta(days=1))
    return v, d


# ── 1 & 6. history of one contract, day by day ───────────────────────────

def contract_history(rows, fixing=None, factor=None, fx=None, history=None, spikes=frozenset(),
                     cost=None):
    """Consumed tonnes of one contract against local and against the CBOT.

    ``rows`` are the contract's valued FIFO draws (one per consumption day).
    ``cost`` replaces the draws' cost per MT when given — the contract's
    recorded landed cost — and every day's saving is recomputed from it.
    Savings vs local only count days with both a cost and a local price;
    the CBOT advantage only days with a CBOT on or before them.
    """
    rows = sorted(rows or [], key=lambda r: r["date"])
    if cost is not None:
        rows = [dict(r, cost_egp_mt=cost,
                     saving_vs_local_egp=((r["local_egp_mt"] - cost) * r["mt"]
                                          if r.get("local_egp_mt") is not None else None))
                for r in rows]
    mt = sum(r["mt"] for r in rows)
    out = {"consumed_mt": mt, "days": len(rows),
           "first_date": rows[0]["date"].isoformat() if rows else "",
           "last_date": rows[-1]["date"].isoformat() if rows else "",
           "daily": []}
    priced = [r for r in rows if r.get("saving_vs_local_egp") is not None]
    p_mt = sum(r["mt"] for r in priced)
    local_cost = sum(r["local_egp_mt"] * r["mt"] for r in priced)
    saving = sum(r["saving_vs_local_egp"] for r in priced)
    out.update(local_priced_mt=p_mt, unpriced_mt=mt - p_mt,
               local_wavg=(local_cost / p_mt) if p_mt else None,
               landed_egp_mt=(sum(r["cost_egp_mt"] * r["mt"] for r in priced) / p_mt) if p_mt else
               next((r["cost_egp_mt"] for r in rows if r.get("cost_egp_mt") is not None), None),
               saving_egp=saving if p_mt else None,
               saving_egp_mt=(saving / p_mt) if p_mt else None,
               saving_pct=(saving / local_cost * 100.0) if local_cost else None,
               stale_mt=sum(r["mt"] for r in priced if r.get("is_stale")),
               oldest_obs_days=max((r.get("stale") or 0) for r in priced) if priced else None)
    cb_mt = cb_sum = adv_usd = 0.0
    spike_days = 0
    for r in rows:
        day = {"date": r["date"].isoformat(), "mt": r["mt"], "cost": r.get("cost_egp_mt"),
               "local": r.get("local_egp_mt"), "local_date": r.get("local_price_date") or "",
               "local_key": r.get("local_key") or "", "saving": r.get("saving_vs_local_egp"),
               "kind": r.get("kind") or ""}
        if fixing is not None and factor and history is not None and len(history):
            raw_v, raw_d = history.on_or_before(r["date"])
            v, d = clean_on_or_before(history, r["date"], spikes)
            if raw_d is not None and raw_d in spikes:
                spike_days += 1
            if v is not None:
                diff = v - fixing
                day.update(cbot=v, cbot_date=d.isoformat(), cbot_diff=diff,
                           adv_usd_mt=diff * factor, adv_usd=diff * factor * r["mt"])
                cb_mt += r["mt"]; cb_sum += v * r["mt"]; adv_usd += diff * factor * r["mt"]
        out["daily"].append(day)
    if cb_mt:
        wavg = cb_sum / cb_mt
        out.update(cbot_wavg=wavg, cbot_diff=wavg - fixing, adv_usd_mt=(wavg - fixing) * factor,
                   adv_usd=adv_usd, adv_egp=(adv_usd * fx) if fx else None,
                   cbot_mt=cb_mt, cbot_spike_days=spike_days)
    return out


# ── 2. what is still to come ─────────────────────────────────────────────

def position(qty, delivered, consumed, in_stock):
    """Split a contract's tonnes once: consumed, in stock, not yet delivered."""
    qty = _num(qty, 0.0) or 0.0
    delivered = min(max(_num(delivered, 0.0) or 0.0, 0.0), qty)
    consumed = max(_num(consumed, 0.0) or 0.0, 0.0)
    in_stock = max(_num(in_stock, 0.0) or 0.0, 0.0)
    outstanding = qty - delivered
    return {"qty_mt": qty, "delivered_mt": delivered, "consumed_mt": consumed,
            "in_stock_mt": in_stock, "outstanding_mt": outstanding,
            "unreconciled_mt": round(delivered - consumed - in_stock, 6)}


def potential(qty_mt, local_today, landed_today):
    """Savings of tonnes not yet consumed, against today's local price."""
    qty_mt, local_today, landed_today = _num(qty_mt, 0.0), _num(local_today), _num(landed_today)
    if not qty_mt or local_today is None or landed_today is None:
        return {"saving_egp_mt": None, "saving_egp": None}
    per = local_today - landed_today
    return {"saving_egp_mt": per, "saving_egp": per * qty_mt}


# ── 4. roll-ups ──────────────────────────────────────────────────────────

def _s(rows, fn):
    return sum(v for v in (fn(r) for r in rows) if isinstance(v, (int, float)))


def commodity_rollup(contracts):
    """Per commodity, every figure a plain sum of its contract rows."""
    out = {}
    for c in contracts:
        b = out.setdefault(c["base"], {"base": c["base"], "contracts": 0})
        b["contracts"] += 1
    for base, b in out.items():
        rows = [c for c in contracts if c["base"] == base]
        h = lambda c: c.get("history") or {}
        p = lambda c: c.get("open") or {}
        b.update(
            consumed_mt=_s(rows, lambda c: h(c).get("consumed_mt")),
            local_priced_mt=_s(rows, lambda c: h(c).get("local_priced_mt")),
            historical_saving_egp=_s(rows, lambda c: h(c).get("saving_egp")),
            realized_saving_egp=_s(rows, lambda c: h(c).get("saving_egp") if c.get("saving_kind") == REALIZED else None),
            provisional_saving_egp=_s(rows, lambda c: h(c).get("saving_egp") if c.get("saving_kind") != REALIZED else None),
            local_cost_egp=_s(rows, lambda c: (h(c).get("local_wavg") or 0) * (h(c).get("local_priced_mt") or 0)),
            in_stock_mt=_s(rows, lambda c: p(c).get("in_stock_mt")),
            outstanding_mt=_s(rows, lambda c: p(c).get("outstanding_mt")),
            stock_saving_egp=_s(rows, lambda c: p(c).get("stock_saving_egp")),
            outstanding_saving_egp=_s(rows, lambda c: p(c).get("outstanding_saving_egp")),
            cbot_adv_usd=_s(rows, lambda c: h(c).get("adv_usd")),
            cbot_adv_egp=_s(rows, lambda c: h(c).get("adv_egp")),
            cbot_mt=_s(rows, lambda c: h(c).get("cbot_mt")),
        )
        b["historical_saving_egp_mt"] = (b["historical_saving_egp"] / b["local_priced_mt"]
                                         if b["local_priced_mt"] else None)
        b["historical_saving_pct"] = (b["historical_saving_egp"] / b["local_cost_egp"] * 100.0
                                      if b["local_cost_egp"] else None)
        b["potential_saving_egp"] = b["stock_saving_egp"] + b["outstanding_saving_egp"]
    return [out[k] for k in sorted(out)]


def kpis(contracts, commodities):
    """The six management figures, each a sum of the rows beneath it.

    Historical (consumed) and potential (in stock + not yet delivered) are
    separate figures; the combined line is their sum because the two cover
    different tonnes. The CBOT advantage is reported apart and never added.
    """
    s = lambda key: _s(commodities, lambda b: b.get(key))
    hist, pot = s("historical_saving_egp"), s("potential_saving_egp")
    hist_mt = s("local_priced_mt")
    pot_mt = _s(contracts, lambda c: (c.get("open") or {}).get("potential_priced_mt"))
    open_rows = [c for c in contracts if c.get("is_open")]
    return {
        "historical_saving_egp": hist,
        "realized_saving_egp": s("realized_saving_egp"),
        "provisional_saving_egp": s("provisional_saving_egp"),
        "historical_priced_mt": hist_mt,
        "potential_saving_egp": pot,
        "stock_saving_egp": s("stock_saving_egp"),
        "outstanding_saving_egp": s("outstanding_saving_egp"),
        "potential_priced_mt": pot_mt,
        "combined_benefit_egp": hist + pot,
        "weighted_saving_egp_mt": ((hist + pot) / (hist_mt + pot_mt)) if (hist_mt + pot_mt) else None,
        "historical_saving_egp_mt": (hist / hist_mt) if hist_mt else None,
        "open_contracts": len(open_rows),
        "open_outstanding_mt": _s(open_rows, lambda c: (c.get("open") or {}).get("outstanding_mt")),
        "open_in_stock_mt": _s(open_rows, lambda c: (c.get("open") or {}).get("in_stock_mt")),
        "open_value_usd": _s(open_rows, lambda c: (c.get("open") or {}).get("open_value_usd")),
        "open_full_value_usd": _s(open_rows, lambda c: c.get("contract_value_usd")),
        "cbot_adv_usd": s("cbot_adv_usd"),
        "cbot_adv_egp": s("cbot_adv_egp"),
        "contracts": len(contracts),
    }
