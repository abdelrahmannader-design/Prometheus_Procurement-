"""Explainable procurement decision and landed-cost engines."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .cbot import carry_usd_mt, cbot_to_usd_mt
from .numbers import to_float
from .stress import run_stress_test

DECISION_ENGINE_VERSION = "1.1-modular"
DECISION_ACTIONS = (
    "PRICE_100",
    "PRICE_PARTIAL",
    "WAIT",
    "BUY_LOCAL",
    "RENEGOTIATE_PREMIUM",
    "INSUFFICIENT_DATA",
)


def run_decision_engine(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Generate one transparent action from stress results and context."""
    stress = run_stress_test(inputs)
    if stress.get("error"):
        return {
            "action": "INSUFFICIENT_DATA",
            "pct": 0,
            "headline": "Insufficient reliable data",
            "reasons": (
                [stress["error"]]
                if not stress.get("missing")
                else ["Missing: " + ", ".join(stress["missing"])]
            ),
            "confidence": 0,
            "stress": stress,
            "version": DECISION_ENGINE_VERSION,
        }

    base_saving = stress["base"]["saving_egp_mt"]
    worst_saving = stress["adverse"]["saving_egp_mt"]
    total_saving = stress["base"]["saving_total_egp"]
    marginal = stress["marginal_egp_mt"]
    fx_now = stress["inputs"]["fx"]
    cbot_now = stress["inputs"]["cbot"]
    premium = stress["inputs"]["premium_cents"]
    reasons: list[str] = []

    days = to_float(inputs.get("days_to_deadline"), None)
    pct_priced = to_float(inputs.get("pct_priced"), 0.0) or 0.0
    remaining = max(0.0, 100.0 - pct_priced)
    fx_secured = bool(inputs.get("fx_secured"))
    implied_basis = to_float(inputs.get("implied_basis_cents"), None)

    confidence = 100
    for key, label, limit in (
        ("cbot_age_days", "CBOT", 1),
        ("fx_age_days", "FX", 1),
        ("local_age_days", "local price", 2),
    ):
        age = to_float(inputs.get(key), None)
        if age is None:
            confidence -= 5
        elif age > limit * 5:
            confidence -= 20
            reasons.append(f"{label} data {age:.0f}d old — verify before acting")
        elif age > limit:
            confidence -= 10

    if stress["fx_buffer_pct"] is not None and stress["fx_buffer_pct"] < 3:
        confidence -= 10
    if base_saving != 0 and abs(worst_saving - base_saving) > 3 * max(abs(base_saving), 1):
        confidence -= 10
    confidence = max(20, min(100, confidence))

    renegotiate = False
    if implied_basis is not None and premium - implied_basis >= 15:
        renegotiate = True
        reasons.append(
            f"premium {premium:,.0f} is {premium - implied_basis:,.0f}¢ above "
            f"market implied {implied_basis:,.0f} — room to renegotiate"
        )

    urgent = days is not None and days <= 7
    if days is not None:
        reasons.append(
            f"{days:.0f} day(s) to deadline · {remaining:.0f}% still unpriced"
            + ("" if fx_secured else " · FX not secured")
        )

    if base_saving <= -marginal:
        action, pct = "BUY_LOCAL", 0.0
        reasons.insert(0, f"import loses {abs(base_saving):,.0f} EGP/MT to local at base case")
    elif abs(base_saving) <= marginal:
        if urgent and remaining > 0:
            action, pct = "PRICE_PARTIAL", 50.0
            reasons.insert(0, "economics marginal but deadline forces partial coverage")
        else:
            action, pct = "WAIT", 0.0
            reasons.insert(
                0,
                f"saving {base_saving:+,.0f} EGP/MT is inside the ±{marginal:,.0f} marginal band",
            )
    else:
        if renegotiate and not urgent:
            action, pct = "RENEGOTIATE_PREMIUM", 0.0
        elif stress["high_risk"]:
            action, pct = "PRICE_PARTIAL", 75.0 if urgent else 50.0
            reasons.insert(
                0,
                f"attractive base (+{base_saving:,.0f}) but adverse case "
                f"{worst_saving:+,.0f} — partial pricing caps the regret either way",
            )
        elif (
            stress["fx_buffer_pct"] is not None
            and stress["fx_buffer_pct"] >= 5
            and stress["cbot_buffer_pct"] is not None
            and stress["cbot_buffer_pct"] >= 5
            and base_saving >= 500
        ):
            action, pct = "PRICE_100", 100.0
            reasons.insert(
                0,
                f"strong saving (+{base_saving:,.0f} EGP/MT) with comfortable buffers to both break-evens",
            )
        elif stress["fx_buffer_pct"] is not None and stress["fx_buffer_pct"] < 3 and not urgent:
            action, pct = "PRICE_PARTIAL", 25.0
            reasons.insert(
                0,
                f"positive base but FX buffer only {stress['fx_buffer_pct']:.1f}% — small tranche, keep powder dry",
            )
        else:
            action, pct = "PRICE_PARTIAL", 75.0 if urgent else 50.0
            reasons.insert(
                0,
                f"positive saving (+{base_saving:,.0f} EGP/MT); partial pricing balances upside and risk",
            )

    if action in ("PRICE_100", "PRICE_PARTIAL") and remaining <= 0:
        action, pct = "WAIT", 0.0
        reasons.insert(0, "contract already fully priced — nothing to do")
    elif action in ("PRICE_100", "PRICE_PARTIAL"):
        pct = min(pct, remaining) if action == "PRICE_PARTIAL" else remaining

    headline = {
        "PRICE_100": f"Price {remaining:.0f}% now (all remaining)",
        "PRICE_PARTIAL": f"Price {pct:.0f}% now, keep {max(0.0, remaining - pct):.0f}% open",
        "WAIT": "Wait and monitor",
        "BUY_LOCAL": "Buy local",
        "RENEGOTIATE_PREMIUM": "Renegotiate the premium",
    }.get(action, action)

    return {
        "action": action,
        "pct": pct,
        "headline": headline,
        "reasons": reasons[:4],
        "confidence": int(confidence),
        "base_saving_mt": base_saving,
        "base_total": total_saving,
        "worst_mt": worst_saving,
        "be_fx": stress["be_fx"],
        "fx_now": fx_now,
        "be_cbot": stress["be_cbot"],
        "cbot_now": cbot_now,
        "high_risk": stress["high_risk"],
        "stress": stress,
        "version": DECISION_ENGINE_VERSION,
    }


def compute_decision(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Calculate import cost, carry, savings, break-evens, and hedge impacts."""
    comm_meta = inputs.get("comm_meta", {})
    fx = to_float(inputs.get("fx"), None)
    quantity = to_float(inputs.get("qty_mt"), 0.0) or 0.0
    finance_days = to_float(inputs.get("finance_days"), 0.0) or 0.0
    rate = to_float(inputs.get("interest_rate"), 0.0) or 0.0
    local = to_float(inputs.get("local_egp_mt"), None)

    is_cbot = comm_meta.get("type", "NONCBOT") == "CBOT"
    if is_cbot:
        cbot = to_float(inputs.get("cbot"), 0.0) or 0.0
        premium = to_float(inputs.get("premium_usd_mt"), 0.0) or 0.0
        import_usd_mt = cbot_to_usd_mt(comm_meta, cbot, premium)
    elif inputs.get("import_usd_mt") not in (None, ""):
        import_usd_mt = to_float(inputs.get("import_usd_mt"), 0.0) or 0.0
    else:
        import_egp_mt = to_float(inputs.get("import_egp_mt"), 0.0) or 0.0
        import_usd_mt = None if not fx else import_egp_mt / fx

    if import_usd_mt is None:
        return {
            "import_usd_mt": None,
            "carry_usd_mt": None,
            "own_after_usd_mt": None,
            "own_after_egp_mt": None,
            "saving_egp_mt": None,
            "error": "FX required to convert EGP→USD",
        }

    carry = carry_usd_mt(import_usd_mt, finance_days, rate)
    own_after_usd_mt = import_usd_mt + carry
    own_after_egp_mt = own_after_usd_mt * fx if fx not in (None, 0) else None
    saving_egp_mt = local - own_after_egp_mt if local is not None and own_after_egp_mt is not None else None

    direct_intake = to_float(inputs.get("supplier_direct_egp_mt"), None)
    indirect_intake = to_float(inputs.get("supplier_indirect_egp_mt"), None)

    direct_own = own_after_egp_mt + direct_intake if own_after_egp_mt is not None and direct_intake is not None else None
    indirect_own = own_after_egp_mt + indirect_intake if own_after_egp_mt is not None and indirect_intake is not None else None
    direct_saving = local - direct_own if local is not None and direct_own is not None else None
    indirect_saving = local - indirect_own if local is not None and indirect_own is not None else None

    break_even_fx_direct = None
    break_even_fx_indirect = None
    if own_after_usd_mt and local is not None:
        if direct_intake is not None:
            break_even_fx_direct = (local - direct_intake) / own_after_usd_mt
        if indirect_intake is not None:
            break_even_fx_indirect = (local - indirect_intake) / own_after_usd_mt

    hedge_pct_raw = to_float(inputs.get("hedge_pct"), 0.0) or 0.0
    hedge_pct = hedge_pct_raw / 100.0 if hedge_pct_raw > 1.0 else hedge_pct_raw
    hedge_pct = max(0.0, min(1.0, hedge_pct))
    hedge_fx = to_float(inputs.get("hedge_fx"), None)
    if hedge_fx is None:
        hedge_fx = fx

    blended_fx = None
    if fx is not None and hedge_fx is not None:
        blended_fx = hedge_pct * hedge_fx + (1.0 - hedge_pct) * fx

    hedged_own = own_after_usd_mt * blended_fx if blended_fx is not None else None
    hedged_direct_own = hedged_own + (direct_intake or 0.0) if hedged_own is not None else None
    hedged_indirect_own = hedged_own + (indirect_intake or 0.0) if hedged_own is not None else None
    hedged_direct_saving = local - hedged_direct_own if local is not None and hedged_direct_own is not None else None
    hedged_indirect_saving = local - hedged_indirect_own if local is not None and hedged_indirect_own is not None else None

    sell_price = to_float(inputs.get("sell_price_egp_mt"), None)
    direct_margin = sell_price - direct_own if sell_price is not None and direct_own is not None else None
    indirect_margin = sell_price - indirect_own if sell_price is not None and indirect_own is not None else None
    hedged_direct_margin = sell_price - hedged_direct_own if sell_price is not None and hedged_direct_own is not None else None
    hedged_indirect_margin = sell_price - hedged_indirect_own if sell_price is not None and hedged_indirect_own is not None else None

    return {
        "import_usd_mt": import_usd_mt,
        "carry_usd_mt": carry,
        "own_after_usd_mt": own_after_usd_mt,
        "own_after_egp_mt": own_after_egp_mt,
        "saving_egp_mt": saving_egp_mt,
        "direct_own_after_egp_mt": direct_own,
        "indirect_own_after_egp_mt": indirect_own,
        "direct_saving_egp_mt": direct_saving,
        "indirect_saving_egp_mt": indirect_saving,
        "qty_mt": quantity,
        "fx": fx,
        "break_even_fx_direct": break_even_fx_direct,
        "break_even_fx_indirect": break_even_fx_indirect,
        "hedge_pct": hedge_pct,
        "hedge_fx": hedge_fx,
        "blended_fx": blended_fx,
        "hedged_own_after_egp_mt": hedged_own,
        "hedged_direct_own_after_egp_mt": hedged_direct_own,
        "hedged_indirect_own_after_egp_mt": hedged_indirect_own,
        "hedged_direct_saving_egp_mt": hedged_direct_saving,
        "hedged_indirect_saving_egp_mt": hedged_indirect_saving,
        "sell_price_egp_mt": sell_price,
        "direct_margin_egp_mt": direct_margin,
        "indirect_margin_egp_mt": indirect_margin,
        "hedged_direct_margin_egp_mt": hedged_direct_margin,
        "hedged_indirect_margin_egp_mt": hedged_indirect_margin,
    }
