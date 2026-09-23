"""Pure stress-testing engine for procurement scenarios."""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping
from typing import Any

from .cbot import cbot_conv_factor, carry_usd_mt
from .numbers import to_float

STRESS_ENGINE_VERSION = "1.2-finance-reconciled"
STRESS_MATERIAL_LOSS_EGP_MT = 250.0
STRESS_CBOT_SHOCKS = (-0.05, 0.0, 0.05, 0.10)
STRESS_FX_SHOCKS = (-0.03, 0.0, 0.03, 0.05, 0.10)
STRESS_PREM_SHOCKS = (-20.0, -10.0, 0.0, 10.0, 20.0)


def _now_ts() -> str:
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def stress_landed_cost_egp_mt(
    cbot: float,
    premium: float,
    factor: float,
    fx: float,
    fees_egp: float,
    finance_days: float = 0.0,
    annual_rate_pct: float = 0.0,
) -> float:
    """Finance-inclusive landed cost used by the deal stress engine.

    This now reconciles exactly to the Single Deal Calculator's direct-cost
    path: ``(CIF USD/MT + finance carry USD/MT) × FX + direct intake``.
    The optional finance arguments default to zero so older call sites remain
    backward compatible.
    """
    cif_usd_mt = (cbot + premium) * factor
    carry = carry_usd_mt(cif_usd_mt, finance_days, annual_rate_pct)
    return (cif_usd_mt + carry) * fx + fees_egp


def stress_classify(
    saving_mt: float,
    marginal: float = 200.0,
    material: float | None = None,
    strong: float = 500.0,
) -> str:
    """Classify a per-MT saving using the same V10.4 boundaries."""
    material = STRESS_MATERIAL_LOSS_EGP_MT if material is None else material
    if saving_mt <= -material:
        return "Material Loss"
    if saving_mt < -marginal:
        return "Loss"
    if abs(saving_mt) <= marginal:
        return "Marginal"
    if saving_mt >= strong:
        return "Strong Advantage"
    return "Advantage"


def run_stress_test(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Run the V10.4 shock grid with explicit missing-input handling."""
    missing: list[str] = []
    commodity = str(inputs.get("commodity") or "").upper()
    if not commodity:
        missing.append("commodity")

    factor = cbot_conv_factor(commodity, strict=True) if commodity else None
    if commodity and factor is None:
        return {
            "error": f"Unsupported commodity conversion: {commodity}",
            "missing": [],
            "resilience": "Unavailable",
            "version": STRESS_ENGINE_VERSION,
        }

    cbot = to_float(inputs.get("cbot"), None)
    fx = to_float(inputs.get("fx"), None)
    premium = to_float(inputs.get("premium_cents"), None)
    quantity = to_float(inputs.get("qty_mt"), None)
    local = to_float(inputs.get("local_egp_mt"), None)
    fees = to_float(inputs.get("fees_egp_mt"), None)
    finance_days = to_float(inputs.get("finance_days"), 0.0) or 0.0
    interest_rate = to_float(inputs.get("interest_rate"), 0.0) or 0.0

    if cbot is None or cbot <= 0:
        missing.append("CBOT (must be > 0)")
    if fx is None or fx <= 0:
        missing.append("FX (must be > 0)")
    if premium is None:
        missing.append("premium")
    if quantity is None or quantity <= 0:
        missing.append("quantity MT (must be > 0)")
    if local is None or local <= 0:
        missing.append("local market price (must be > 0)")
    if fees is None:
        missing.append("local costs (discharge+clearance+freight)")

    if missing:
        return {
            "error": "Stress test unavailable",
            "missing": missing,
            "resilience": "Unavailable",
            "version": STRESS_ENGINE_VERSION,
        }

    # Values are validated above; these assertions help static type checkers.
    assert factor is not None
    assert cbot is not None
    assert fx is not None
    assert premium is not None
    assert quantity is not None
    assert local is not None
    assert fees is not None

    marginal = to_float(inputs.get("marginal_egp_mt"), 200.0) or 200.0
    material = (
        to_float(inputs.get("material_egp_mt"), STRESS_MATERIAL_LOSS_EGP_MT)
        or STRESS_MATERIAL_LOSS_EGP_MT
    )

    premium_locked = bool(inputs.get("premium_locked"))
    cbot_locked = bool(inputs.get("cbot_locked"))
    custom_premium_shocks = inputs.get("prem_shocks_custom")
    premium_shocks = (
        (0.0,)
        if premium_locked
        else tuple(custom_premium_shocks)
        if custom_premium_shocks
        else STRESS_PREM_SHOCKS
    )
    cbot_shocks = (0.0,) if cbot_locked else STRESS_CBOT_SHOCKS

    rows: list[dict[str, Any]] = []
    base_row: dict[str, Any] | None = None
    for cbot_shock in cbot_shocks:
        for fx_shock in STRESS_FX_SHOCKS:
            for premium_shock in premium_shocks:
                shocked_cbot = cbot * (1 + cbot_shock)
                shocked_fx = fx * (1 + fx_shock)
                shocked_premium = premium + premium_shock
                cif = (shocked_cbot + shocked_premium) * factor
                carry = carry_usd_mt(cif, finance_days, interest_rate)
                own_after_usd = cif + carry
                landed = stress_landed_cost_egp_mt(
                    shocked_cbot, shocked_premium, factor, shocked_fx, fees,
                    finance_days, interest_rate
                )
                saving = local - landed
                displayed_saving = round(saving, 2)
                row = {
                    "cbot_shock": cbot_shock,
                    "fx_shock": fx_shock,
                    "prem_shock": premium_shock,
                    "cbot": round(shocked_cbot, 4),
                    "fx": round(shocked_fx, 6),
                    "premium": round(shocked_premium, 4),
                    "cif_usd_mt": round(cif, 4),
                    "carry_usd_mt": round(carry, 4),
                    "own_after_usd_mt": round(own_after_usd, 4),
                    "landed_egp_mt": round(landed, 2),
                    "saving_egp_mt": displayed_saving,
                    "saving_total_egp": round(displayed_saving * quantity, 2),
                    "classification": stress_classify(
                        saving, marginal=marginal, material=material
                    ),
                }
                rows.append(row)
                if cbot_shock == 0.0 and fx_shock == 0.0 and premium_shock == 0.0:
                    base_row = row

    if base_row is None:
        # A custom shock set that omits zero cannot support a base recommendation.
        return {
            "error": "Stress test requires a zero-shock base scenario",
            "missing": [],
            "resilience": "Unavailable",
            "version": STRESS_ENGINE_VERSION,
        }

    best = max(rows, key=lambda row: row["saving_egp_mt"])
    adverse = min(rows, key=lambda row: row["saving_egp_mt"])

    break_even_cbot = break_even_fx = None
    cbot_buffer = cbot_buffer_pct = fx_buffer = fx_buffer_pct = None
    net_local = local - fees
    finance_multiplier = 1.0 + (interest_rate / 100.0) * (finance_days / 360.0)
    if net_local > 0 and fx > 0 and factor > 0 and finance_multiplier > 0:
        candidate = (net_local / fx) / (factor * finance_multiplier) - premium
        if candidate > 0:
            break_even_cbot = round(candidate, 2)
            cbot_buffer = round(break_even_cbot - cbot, 2)
            cbot_buffer_pct = round(cbot_buffer / cbot * 100.0, 1)

    base_cif = (cbot + premium) * factor
    base_own_after_usd = base_cif * finance_multiplier
    if net_local > 0 and base_own_after_usd > 0:
        candidate = net_local / base_own_after_usd
        if candidate > 0:
            break_even_fx = round(candidate, 4)
            fx_buffer = round(break_even_fx - fx, 4)
            fx_buffer_pct = round(fx_buffer / fx * 100.0, 1)

    base_saving = base_row["saving_egp_mt"]
    adverse_saving = adverse["saving_egp_mt"]
    high_risk = base_saving > 0 and adverse_saving <= -material

    return {
        "rows": rows,
        "base": base_row,
        "best": best,
        "adverse": adverse,
        "be_cbot": break_even_cbot,
        "cbot_buffer": cbot_buffer,
        "cbot_buffer_pct": cbot_buffer_pct,
        "be_fx": break_even_fx,
        "fx_buffer": fx_buffer,
        "fx_buffer_pct": fx_buffer_pct,
        "high_risk": high_risk,
        "resilience": "High Risk" if high_risk else "Pass",
        "material_egp_mt": material,
        "marginal_egp_mt": marginal,
        "inputs": {
            "commodity": commodity,
            "cbot": cbot,
            "fx": fx,
            "premium_cents": premium,
            "qty_mt": quantity,
            "local_egp_mt": local,
            "fees_egp_mt": fees,
            "finance_days": finance_days,
            "interest_rate": interest_rate,
            "finance_multiplier": finance_multiplier,
            "factor": factor,
        },
        "premium_locked": premium_locked,
        "cbot_locked": cbot_locked,
        "prem_shocks_used": premium_shocks,
        "cbot_shocks_used": cbot_shocks,
        "version": STRESS_ENGINE_VERSION,
        "ts": _now_ts(),
        "error": None,
        "missing": [],
    }
