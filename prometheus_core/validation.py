"""Input validation shared by the desktop UI and future API."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .numbers import to_float


def validate_single_inputs(
    comm_meta: Mapping[str, Any], inputs: Mapping[str, Any]
) -> tuple[bool, str]:
    """Validate the single-deal calculator without depending on Tkinter."""
    fx = to_float(inputs.get("fx"), None)
    quantity = to_float(inputs.get("qty_mt"), None)
    finance_days = to_float(inputs.get("finance_days"), 0.0) or 0.0
    rate = to_float(inputs.get("interest_rate"), 0.0) or 0.0

    if fx is None or fx <= 0:
        return False, "FX must be > 0."
    if quantity is not None and quantity < 0:
        return False, "Quantity (MT) must be >= 0."
    if finance_days < 0:
        return False, "Finance days must be >= 0."
    if rate < 0 or rate > 100:
        return False, "Interest rate must be between 0 and 100."

    local = to_float(inputs.get("local_egp_mt"), None)
    if local is not None and local < 0:
        return False, "Local price must be >= 0."

    if comm_meta.get("type", "NONCBOT") == "CBOT":
        if to_float(inputs.get("cbot"), None) is None:
            return False, "For CBOT commodities, CBOT price is required."
        if to_float(inputs.get("premium_usd_mt"), None) is None:
            return False, "For CBOT commodities, Premium/Basis is required (use 0 if none)."
    else:
        import_usd = to_float(inputs.get("import_usd_mt"), None)
        import_egp = to_float(inputs.get("import_egp_mt"), None)
        if import_usd is None and import_egp is None:
            return False, "For Non-CBOT commodities, enter Import USD/MT or Import EGP/MT."

    return True, ""
