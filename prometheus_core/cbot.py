"""CBOT unit conversion and finance-carry calculations.

These constants are the corporate calculation source of truth for the modular
version. They reproduce the Finance-verified factors used by V10.4.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .numbers import to_float

CORN_FACTOR = 0.3937
SOYBEAN_FACTOR = 0.36745
WHEAT_FACTOR = 0.36745
SBM_ST_PER_MT = 1.1023

CBOT_CONV: dict[str, float] = {
    "CORN": CORN_FACTOR,
    "SOYBEAN": SOYBEAN_FACTOR,
    "WHEAT": WHEAT_FACTOR,
    "SBM": SBM_ST_PER_MT,
}


def commodity_base(commodity: str | None) -> str:
    """Return the base commodity, making origin suffixes conversion-safe."""
    return (commodity or "").strip().upper().split("-")[0]


def cbot_conv_factor(commodity: str | None, strict: bool = False) -> float | None:
    """Return the canonical CBOT-to-USD/MT conversion factor.

    ``strict=True`` returns ``None`` for unsupported commodities. The legacy
    desktop display path historically falls back to the corn factor, so the
    non-strict behavior is preserved for compatibility.
    """
    factor = CBOT_CONV.get(commodity_base(commodity))
    if factor is not None:
        return factor
    return None if strict else CORN_FACTOR


def cbot_to_usd_mt(
    comm_meta: Mapping[str, Any],
    cbot_price: Any,
    premium_input: Any,
) -> float:
    """Convert a CBOT price and premium to USD/MT.

    The function preserves both V10.4 modes:
    * ``locked_factor``: CBOT and premium share the same quoted unit.
    * legacy conversion metadata: premium can be CBOT-unit or already USD/MT.
    """
    locked = to_float(comm_meta.get("locked_factor"), None)
    cbot = to_float(cbot_price, 0.0) or 0.0
    premium = to_float(premium_input, 0.0) or 0.0

    if locked is not None:
        return (cbot + premium) * locked

    conversion_type = comm_meta.get("conversion_type", "none")
    conversion_value = to_float(comm_meta.get("conversion_value"), 1.0) or 1.0
    premium_in_cbot_unit = comm_meta.get("premium_mode") == "CBOT_UNIT"

    if conversion_type == "bu_per_mt":
        if premium_in_cbot_unit:
            return ((cbot + premium) / 100.0) * conversion_value
        converted = (cbot / 100.0) * conversion_value
    elif conversion_type == "st_per_mt":
        if premium_in_cbot_unit:
            return (cbot + premium) * conversion_value
        converted = cbot * conversion_value
    else:
        converted = cbot

    return converted + premium


def carry_usd_mt(usd_mt: Any, finance_days: Any, annual_rate_pct: Any) -> float:
    """Calculate simple finance carry using the app's 360-day convention."""
    amount = to_float(usd_mt, 0.0) or 0.0
    days = to_float(finance_days, 0.0) or 0.0
    rate = (to_float(annual_rate_pct, 0.0) or 0.0) / 100.0
    return amount * rate * (days / 360.0)
