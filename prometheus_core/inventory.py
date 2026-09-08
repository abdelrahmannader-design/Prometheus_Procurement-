"""FIFO inventory analytics for Prometheus Procurement.

Pure business logic only: no Tkinter, file-system, or network code.
The desktop app supplies normalized contract lots, consumption/physical-count
entries, and current market assumptions.
"""

from __future__ import annotations

import datetime as dt
from copy import deepcopy


def _to_float(value, default=None):
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text:
            return default
        return float(text)
    except Exception:
        return default


def _date(value):
    if isinstance(value, dt.date):
        return value
    if value in (None, ""):
        return None
    try:
        return dt.date.fromisoformat(str(value).strip().split(" ")[0])
    except Exception:
        return None


def base_commodity(value):
    """Collapse origin variants (CORN-BRZ/CORN-ARG/...) to management base."""
    return (str(value or "").strip().upper().split("-")[0] or "OTHER")


def effective_freight_egp_mt(base_rate, mode="LEGACY", vat_pct=14.0, all_in_rate=None):
    """Return freight actually charged to landed cost.

    DETAILED: base freight + VAT.
    ALL_IN: user-entered final rate; VAT is not added again.
    LEGACY: existing stored value is preserved unchanged.
    """
    mode = (mode or "LEGACY").strip().upper()
    base = _to_float(base_rate, None)
    all_in = _to_float(all_in_rate, None)
    vat = _to_float(vat_pct, 14.0)
    if mode == "DETAILED":
        if base is None:
            return None
        return base * (1.0 + max(vat or 0.0, 0.0) / 100.0)
    if mode == "ALL_IN":
        return all_in if all_in is not None else base
    return all_in if all_in is not None else base


def _consume_fifo(layers, qty_mt):
    """Consume qty from oldest available layers; return shortage MT."""
    qty = max(_to_float(qty_mt, 0.0) or 0.0, 0.0)
    for layer in layers:
        if qty <= 1e-9:
            break
        rem = max(_to_float(layer.get("remaining_mt"), 0.0) or 0.0, 0.0)
        if rem <= 0:
            continue
        take = min(rem, qty)
        layer["remaining_mt"] = rem - take
        layer["consumed_mt"] = (_to_float(layer.get("consumed_mt"), 0.0) or 0.0) + take
        qty -= take
    return max(qty, 0.0)


def _layer_from_lot(lot):
    row = deepcopy(lot)
    original = max(_to_float(row.get("original_mt"), _to_float(row.get("qty_mt"), 0.0)) or 0.0, 0.0)
    row["original_mt"] = original
    row["consumed_mt"] = max(_to_float(row.get("consumed_mt"), 0.0) or 0.0, 0.0)
    row["remaining_mt"] = max(_to_float(row.get("remaining_mt"), original) or 0.0, 0.0)
    row["base_commodity"] = base_commodity(row.get("base_commodity") or row.get("commodity"))
    d = _date(row.get("delivery_date") or row.get("date"))
    row["delivery_date"] = d.isoformat() if d else ""
    return row


def _rate_by_base(consumption_rates):
    out = {}
    for key, value in (consumption_rates or {}).items():
        v = _to_float(value, None)
        if v is None or v <= 0:
            continue
        b = base_commodity(key)
        out[b] = out.get(b, 0.0) + v
    return out


def build_daily_fifo_inventory(lots, events=None, consumption_rates=None, as_of=None,
                               estimate_daily=True):
    """Build current FIFO layers for every base commodity.

    Parameters
    ----------
    lots:
        Contract/receipt lots. Each row should provide delivery_date,
        commodity/base_commodity, original_mt and (ideally) cost_egp_mt.
        Future-dated lots are returned as inbound, not current inventory.
    events:
        Consumption log rows. Physical counts use is_adjustment=True and
        adjusted_qty. Non-adjustment received_mt is only treated as a receipt
        when no contract_id is present, preventing duplicate contract receipts.
    consumption_rates:
        Configured MT/day. Used only after the last actual consumption/physical
        confirmation when estimate_daily=True. It never writes consumption log.
    as_of:
        Inventory valuation date (default today).
    """
    as_of_d = _date(as_of) or dt.date.today()
    as_of_s = as_of_d.isoformat()
    events = [dict(e) for e in (events or []) if isinstance(e, dict)]
    prepared_lots = [_layer_from_lot(x) for x in (lots or []) if isinstance(x, dict)]

    bases = {x["base_commodity"] for x in prepared_lots}
    bases.update(base_commodity(e.get("commodity")) for e in events if e.get("commodity"))
    bases.update(_rate_by_base(consumption_rates))
    rates = _rate_by_base(consumption_rates)

    # Latest physical count per original commodity key; aggregate aliases into
    # one management commodity. Current CPC data uses same-day alias counts.
    latest_adjustment_by_alias = {}
    for e in events:
        if not e.get("is_adjustment"):
            continue
        ed = _date(e.get("date"))
        if ed is None or ed > as_of_d:
            continue
        alias = str(e.get("commodity") or "").strip().upper()
        if not alias:
            continue
        prev = latest_adjustment_by_alias.get(alias)
        if prev is None or ed >= prev[0]:
            latest_adjustment_by_alias[alias] = (ed, max(_to_float(e.get("adjusted_qty"), 0.0) or 0.0, 0.0), e)

    results = {}
    for base in sorted(bases):
        base_lots = [deepcopy(x) for x in prepared_lots if x["base_commodity"] == base]
        base_lots.sort(key=lambda x: (x.get("delivery_date") or "9999-12-31", x.get("contract_id") or "", x.get("lot_id") or ""))
        inbound = [x for x in base_lots if (_date(x.get("delivery_date")) or dt.date.max) > as_of_d]
        delivered = [x for x in base_lots if (_date(x.get("delivery_date")) or dt.date.max) <= as_of_d]

        alias_adjustments = [v for alias, v in latest_adjustment_by_alias.items() if base_commodity(alias) == base]
        baseline_date = max((v[0] for v in alias_adjustments), default=None)
        baseline_qty = sum(v[1] for v in alias_adjustments) if alias_adjustments else None
        baseline_dates = sorted({v[0].isoformat() for v in alias_adjustments})
        issues = []
        if len(baseline_dates) > 1:
            issues.append("Physical counts for this base commodity come from mixed dates; reconcile a same-day total count.")

        layers = []
        shortage = 0.0
        consumed_actual = 0.0
        consumed_estimated = 0.0

        if baseline_date is not None:
            pre = [_layer_from_lot(x) for x in delivered if (_date(x.get("delivery_date")) or dt.date.min) <= baseline_date]
            total_pre = sum(x["original_mt"] for x in pre)
            layers = pre
            if baseline_qty is not None:
                if baseline_qty <= total_pre + 1e-9:
                    shortage += _consume_fifo(layers, max(total_pre - baseline_qty, 0.0))
                else:
                    # Physical stock exceeds identified contract receipts.
                    # Preserve the difference as an explicit unknown-cost lot.
                    layers.append({
                        "lot_id": f"PHYSICAL-{base}-{baseline_date.isoformat()}",
                        "contract_id": "",
                        "contract_ref": "Physical stock adjustment",
                        "commodity": base,
                        "base_commodity": base,
                        "delivery_date": baseline_date.isoformat(),
                        "original_mt": baseline_qty - total_pre,
                        "remaining_mt": baseline_qty - total_pre,
                        "consumed_mt": 0.0,
                        "cost_egp_mt": None,
                        "status": "Physical adjustment",
                        "source": "physical_adjustment_unallocated",
                    })
                    issues.append(
                        f"Physical stock exceeds identified delivered contract lots by {baseline_qty-total_pre:,.0f} MT; cost is unallocated.")
            timeline_start = baseline_date
        else:
            layers = []
            timeline_start = min((_date(x.get("delivery_date")) for x in delivered if _date(x.get("delivery_date"))), default=None)

        # Actual consumption after baseline (or all history without a baseline).
        actual_events = []
        standalone_receipts = []
        for idx, e in enumerate(events):
            if e.get("is_adjustment") or base_commodity(e.get("commodity")) != base:
                continue
            ed = _date(e.get("date"))
            if ed is None or ed > as_of_d:
                continue
            if baseline_date is not None and ed <= baseline_date:
                continue
            cons = max(_to_float(e.get("consumed_mt"), 0.0) or 0.0, 0.0)
            rec = max(_to_float(e.get("received_mt"), 0.0) or 0.0, 0.0)
            if cons > 0:
                actual_events.append((ed, idx, cons, e))
            # Contract-linked receipt is already represented by the contract lot.
            if rec > 0 and not (e.get("contract_id") or "").strip():
                standalone_receipts.append((ed, idx, rec, e))

        last_actual_date = max((x[0] for x in actual_events), default=None)
        actual_cutoff = last_actual_date or baseline_date
        if actual_cutoff is None:
            actual_cutoff = as_of_d if not estimate_daily else (timeline_start or as_of_d)

        # Add/process delivered contract lots and standalone receipts up to the
        # actual cutoff. Receipts occur before consumption on the same date.
        timeline = []
        existing_ids = {(x.get("lot_id") or x.get("contract_id"), x.get("delivery_date")) for x in layers}
        for x in delivered:
            xd = _date(x.get("delivery_date"))
            if xd is None:
                continue
            if baseline_date is not None and xd <= baseline_date:
                continue
            if xd <= actual_cutoff:
                timeline.append((xd, 0, "lot", _layer_from_lot(x)))
        for ed, idx, rec, e in standalone_receipts:
            if ed <= actual_cutoff:
                timeline.append((ed, 0, "standalone", {
                    "lot_id": f"LOG-{base}-{ed.isoformat()}-{idx}",
                    "contract_id": "",
                    "contract_ref": e.get("note") or "Manual receipt",
                    "commodity": e.get("commodity") or base,
                    "base_commodity": base,
                    "delivery_date": ed.isoformat(),
                    "original_mt": rec,
                    "remaining_mt": rec,
                    "consumed_mt": 0.0,
                    "cost_egp_mt": _to_float(e.get("cost_egp_mt"), None),
                    "status": "Manual receipt",
                    "source": "consumption_log_receipt",
                }))
        for ed, idx, cons, e in actual_events:
            if ed <= actual_cutoff:
                timeline.append((ed, 1, "consume", cons))
        timeline.sort(key=lambda x: (x[0], x[1]))
        for _ed, _order, kind, payload in timeline:
            if kind in ("lot", "standalone"):
                layers.append(payload)
                layers.sort(key=lambda x: (x.get("delivery_date") or "9999-12-31", x.get("contract_id") or "", x.get("lot_id") or ""))
            else:
                consumed_actual += payload
                shortage += _consume_fifo(layers, payload)

        # Automatic daily projection after the last confirmed actual-consumption
        # point. It is analytical only and clearly labelled ESTIMATED.
        rate = max(_to_float(rates.get(base), 0.0) or 0.0, 0.0)
        estimate_start = actual_cutoff + dt.timedelta(days=1) if actual_cutoff else None
        estimate_days = 0
        if estimate_daily and rate > 0 and estimate_start and estimate_start <= as_of_d:
            current = estimate_start
            # Remaining contract lots after actual cutoff are introduced on
            # their delivery date; daily consumption is then applied.
            remaining_receipts = {}
            for x in delivered:
                xd = _date(x.get("delivery_date"))
                if xd and xd > actual_cutoff:
                    remaining_receipts.setdefault(xd, []).append(_layer_from_lot(x))
            for ed, idx, rec, e in standalone_receipts:
                if ed > actual_cutoff:
                    remaining_receipts.setdefault(ed, []).append({
                        "lot_id": f"LOG-{base}-{ed.isoformat()}-{idx}",
                        "contract_id": "",
                        "contract_ref": e.get("note") or "Manual receipt",
                        "commodity": e.get("commodity") or base,
                        "base_commodity": base,
                        "delivery_date": ed.isoformat(),
                        "original_mt": rec,
                        "remaining_mt": rec,
                        "consumed_mt": 0.0,
                        "cost_egp_mt": _to_float(e.get("cost_egp_mt"), None),
                        "status": "Manual receipt",
                        "source": "consumption_log_receipt",
                    })
            while current <= as_of_d:
                for layer in remaining_receipts.get(current, []):
                    layers.append(layer)
                layers.sort(key=lambda x: (x.get("delivery_date") or "9999-12-31", x.get("contract_id") or "", x.get("lot_id") or ""))
                consumed_estimated += rate
                shortage += _consume_fifo(layers, rate)
                estimate_days += 1
                current += dt.timedelta(days=1)
        else:
            # If no estimate is being made, still include delivered lots after
            # the actual cutoff through as-of so current physical receipts show.
            for x in delivered:
                xd = _date(x.get("delivery_date"))
                if xd and xd > actual_cutoff:
                    layers.append(_layer_from_lot(x))

        layers.sort(key=lambda x: (x.get("delivery_date") or "9999-12-31", x.get("contract_id") or "", x.get("lot_id") or ""))
        remaining_layers = [x for x in layers if (_to_float(x.get("remaining_mt"), 0.0) or 0.0) > 1e-6]
        remaining_qty = sum(_to_float(x.get("remaining_mt"), 0.0) or 0.0 for x in remaining_layers)
        known_cost_qty = sum((_to_float(x.get("remaining_mt"), 0.0) or 0.0)
                             for x in remaining_layers if _to_float(x.get("cost_egp_mt"), None) is not None)
        value = sum((_to_float(x.get("remaining_mt"), 0.0) or 0.0) * (_to_float(x.get("cost_egp_mt"), 0.0) or 0.0)
                    for x in remaining_layers if _to_float(x.get("cost_egp_mt"), None) is not None)
        cost_complete = remaining_qty <= 1e-9 or abs(known_cost_qty - remaining_qty) <= 1e-6
        weighted_cost = value / known_cost_qty if known_cost_qty > 0 else None
        if not cost_complete:
            issues.append(f"{remaining_qty-known_cost_qty:,.0f} MT of remaining stock has no allocatable historical cost.")
        if shortage > 1e-6:
            issues.append(f"FIFO consumption exceeded available received stock by {shortage:,.0f} MT.")

        contract_layers = [x for x in remaining_layers if (x.get("contract_id") or "").strip()]
        oldest = contract_layers[0] if contract_layers else (remaining_layers[0] if remaining_layers else None)
        newest = contract_layers[-1] if contract_layers else (remaining_layers[-1] if remaining_layers else None)
        if estimate_days > 0:
            status = "ESTIMATED"
        elif baseline_date is not None:
            status = "ACTUAL"
        elif actual_events:
            status = "FIFO_FROM_LOG"
        else:
            status = "MODELLED"

        results[base] = {
            "commodity": base,
            "as_of": as_of_s,
            "status": status,
            "baseline_date": baseline_date.isoformat() if baseline_date else "",
            "baseline_dates": baseline_dates,
            "baseline_qty": baseline_qty,
            "last_actual_consumption_date": last_actual_date.isoformat() if last_actual_date else "",
            "daily_consumption_rate": rate if rate > 0 else None,
            "estimate_days": estimate_days,
            "actual_consumed_mt": consumed_actual,
            "estimated_consumed_mt": consumed_estimated,
            "shortage_mt": shortage,
            "remaining_mt": remaining_qty,
            "inventory_value_egp": value if known_cost_qty > 0 else None,
            "known_cost_mt": known_cost_qty,
            "cost_complete": cost_complete,
            "weighted_avg_cost_egp_mt": weighted_cost,
            "oldest": oldest,
            "newest": newest,
            "layers": remaining_layers,
            "inbound": inbound,
            "inbound_mt": sum(_to_float(x.get("original_mt"), 0.0) or 0.0 for x in inbound),
            "issues": issues,
        }
    return results


def summarize_inventory_market(fifo_row, local_price_egp_mt=None, cbot=None,
                               premium=None, fx=None, conversion_factor=None,
                               replacement_fees_egp_mt=0.0):
    """Add current local and CBOT replacement comparisons to one FIFO summary."""
    row = deepcopy(fifo_row or {})
    qty = _to_float(row.get("remaining_mt"), 0.0) or 0.0
    avg = _to_float(row.get("weighted_avg_cost_egp_mt"), None)
    local = _to_float(local_price_egp_mt, None)
    if avg is not None and local is not None:
        row["local_egp_mt"] = local
        row["inventory_edge_egp_mt"] = local - avg
        row["inventory_edge_egp"] = (local - avg) * qty
    else:
        row["local_egp_mt"] = local
        row["inventory_edge_egp_mt"] = None
        row["inventory_edge_egp"] = None

    cbot_v = _to_float(cbot, None)
    prem_v = _to_float(premium, None)
    fx_v = _to_float(fx, None)
    factor = _to_float(conversion_factor, None)
    fees = _to_float(replacement_fees_egp_mt, 0.0) or 0.0
    row.update({"cbot": cbot_v, "premium": prem_v, "current_fx": fx_v})
    if None not in (cbot_v, prem_v, fx_v, factor) and fx_v > 0 and factor > 0:
        cif = (cbot_v + prem_v) * factor
        replacement = cif * fx_v + fees
        row["replacement_cif_usd_mt"] = cif
        row["replacement_cost_egp_mt"] = replacement
        if avg is not None:
            row["inventory_vs_replacement_egp_mt"] = replacement - avg
            row["inventory_vs_replacement_egp"] = (replacement - avg) * qty
        else:
            row["inventory_vs_replacement_egp_mt"] = None
            row["inventory_vs_replacement_egp"] = None
    else:
        row["replacement_cif_usd_mt"] = None
        row["replacement_cost_egp_mt"] = None
        row["inventory_vs_replacement_egp_mt"] = None
        row["inventory_vs_replacement_egp"] = None
    return row


def inventory_market_layer_metrics(*, remaining_mt, fifo_cost_egp_mt, cbot=None,
                                   premium=None, conversion_factor=None, fx=None,
                                   freight_egp_mt=0.0, discharge_egp_mt=0.0,
                                   clearance_egp_mt=0.0, local_egp_mt=None):
    """Compare one remaining FIFO layer with today's local and CBOT replacement.

    Historical FIFO cost is never revalued. Replacement cost is a current
    benchmark: (CBOT + premium) * factor * current FX + current local fees.
    Positive edges mean the already-owned inventory is cheaper than today's
    alternative. Missing premium/CBOT/FX keeps replacement explicitly blank.
    """
    qty = max(_to_float(remaining_mt, 0.0) or 0.0, 0.0)
    fifo = _to_float(fifo_cost_egp_mt, None)
    local = _to_float(local_egp_mt, None)
    cbot_v = _to_float(cbot, None)
    prem_v = _to_float(premium, None)
    factor = _to_float(conversion_factor, None)
    fx_v = _to_float(fx, None)
    freight = _to_float(freight_egp_mt, None)
    discharge = _to_float(discharge_egp_mt, 0.0) or 0.0
    clearance = _to_float(clearance_egp_mt, 0.0) or 0.0

    local_edge_mt = local - fifo if local is not None and fifo is not None else None
    local_edge_total = local_edge_mt * qty if local_edge_mt is not None else None

    replacement_cif = None
    replacement_cost = None
    replacement_edge_mt = None
    replacement_edge_total = None
    if (None not in (cbot_v, prem_v, factor, fx_v, freight) and
            factor > 0 and fx_v > 0):
        replacement_cif = (cbot_v + prem_v) * factor
        replacement_cost = replacement_cif * fx_v + freight + discharge + clearance
        if fifo is not None:
            replacement_edge_mt = replacement_cost - fifo
            replacement_edge_total = replacement_edge_mt * qty

    if local_edge_mt is None and replacement_edge_mt is None:
        decision = "Missing market data"
    elif replacement_edge_mt is None:
        decision = "Ahead of local" if local_edge_mt is not None and local_edge_mt >= 0 else "Local cheaper"
    elif local_edge_mt is None:
        decision = "Ahead of CBOT replacement" if replacement_edge_mt >= 0 else "CBOT replacement cheaper"
    elif local_edge_mt >= 0 and replacement_edge_mt >= 0:
        decision = "Ahead of local + CBOT"
    elif local_edge_mt >= 0:
        decision = "Ahead local; CBOT cheaper"
    elif replacement_edge_mt >= 0:
        decision = "Local cheaper; ahead CBOT"
    else:
        decision = "Local + CBOT cheaper"

    return {
        "remaining_mt": qty,
        "fifo_cost_egp_mt": fifo,
        "local_egp_mt": local,
        "replacement_cif_usd_mt": replacement_cif,
        "replacement_cost_egp_mt": replacement_cost,
        "inventory_vs_local_egp_mt": local_edge_mt,
        "inventory_vs_local_egp": local_edge_total,
        "inventory_vs_replacement_egp_mt": replacement_edge_mt,
        "inventory_vs_replacement_egp": replacement_edge_total,
        "decision": decision,
    }


def calculate_inventory_scenario(*, current_remaining_mt, avg_inventory_cost_egp_mt,
                                 local_base_egp_mt, local_transport_egp_mt=0.0,
                                 cbot=None, premium=None, conversion_factor=None,
                                 fx=None, freight_input_egp_mt=0.0,
                                 freight_mode="DETAILED", freight_vat_pct=14.0,
                                 other_fees_egp_mt=0.0, purchase_qty_mt=0.0,
                                 consumption_qty_mt=0.0, horizon_days=0.0,
                                 daily_consumption_mt=0.0, proposed_cif_usd_mt=None):
    """Pure what-if calculation used by Scenario Lab.

    Explicit consumption_qty_mt wins when >0; otherwise horizon_days × daily
    rate is used. This prevents silently double-counting both controls.
    """
    current_qty = max(_to_float(current_remaining_mt, 0.0) or 0.0, 0.0)
    avg_cost = _to_float(avg_inventory_cost_egp_mt, None)
    local_base = _to_float(local_base_egp_mt, None)
    local_transport = _to_float(local_transport_egp_mt, 0.0) or 0.0
    local_all_in = (local_base + local_transport) if local_base is not None else None
    factor = _to_float(conversion_factor, None)
    fx_v = _to_float(fx, None)
    cbot_v = _to_float(cbot, None)
    prem_v = _to_float(premium, None)
    proposed = _to_float(proposed_cif_usd_mt, None)
    effective_freight = effective_freight_egp_mt(
        freight_input_egp_mt, mode=freight_mode, vat_pct=freight_vat_pct,
        all_in_rate=freight_input_egp_mt)
    other_fees = _to_float(other_fees_egp_mt, 0.0) or 0.0

    cif = proposed
    cif_source = "proposed CIF" if proposed is not None else "CBOT + premium"
    if cif is None and None not in (cbot_v, prem_v, factor):
        cif = (cbot_v + prem_v) * factor
    purchase_cost = None
    if cif is not None and fx_v is not None and fx_v > 0 and effective_freight is not None:
        purchase_cost = cif * fx_v + effective_freight + other_fees

    saving_mt = None
    if local_all_in is not None and purchase_cost is not None:
        saving_mt = local_all_in - purchase_cost
    purchase_qty = max(_to_float(purchase_qty_mt, 0.0) or 0.0, 0.0)
    total_impact = saving_mt * purchase_qty if saving_mt is not None else None

    explicit_consumption = max(_to_float(consumption_qty_mt, 0.0) or 0.0, 0.0)
    horizon = max(_to_float(horizon_days, 0.0) or 0.0, 0.0)
    daily = max(_to_float(daily_consumption_mt, 0.0) or 0.0, 0.0)
    projected_consumption = explicit_consumption if explicit_consumption > 0 else horizon * daily
    projected_inventory = max(current_qty + purchase_qty - projected_consumption, 0.0)
    coverage = projected_inventory / daily if daily > 0 else None

    current_edge_mt = local_all_in - avg_cost if local_all_in is not None and avg_cost is not None else None
    return {
        "local_all_in_egp_mt": local_all_in,
        "current_inventory_edge_egp_mt": current_edge_mt,
        "scenario_cif_usd_mt": cif,
        "cif_source": cif_source if cif is not None else "incomplete",
        "effective_freight_egp_mt": effective_freight,
        "scenario_purchase_cost_egp_mt": purchase_cost,
        "scenario_saving_egp_mt": saving_mt,
        "total_scenario_impact_egp": total_impact,
        "projected_consumption_mt": projected_consumption,
        "projected_inventory_mt": projected_inventory,
        "coverage_days": coverage,
    }
