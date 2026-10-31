"""Which FX a contract's cost is converted at.

Form 4 is the Egyptian bank import form; "FX at Form 4" is the rate the
bank actually charged for the dollars — the cash cost of the cargo. Once it
is entered, a contract's cost uses it, for every commodity except SBM.

SBM keeps its delivery FX: its savings sit inside an equivalent-price
comparison (local base ÷ contract FX ÷ 1.1023) where the same FX converts
both sides, and changing one side alone would break that comparison.

Without a Form 4 rate the contract falls back to its delivery FX, and only
then to whatever the caller passes (usually today's market FX).
"""

from __future__ import annotations

CONTRACT_FX_VERSION = "1.0"

#: Commodities whose cost stays at delivery FX even when Form 4 is entered.
DELIVERY_FX_ONLY = frozenset({"SBM"})

SOURCE_FORM4 = "Form 4"
SOURCE_DELIVERY = "delivery"
SOURCE_FALLBACK = "market today"


def _num(value):
    try:
        if value is None or str(value).strip() == "":
            return None
        out = float(str(value).replace(",", ""))
        return out if out > 0 else None
    except Exception:
        return None


def base_commodity(contract):
    return str((contract or {}).get("commodity") or "CORN").strip().upper().split("-")[0]


def uses_form4(contract):
    """True when this contract's cost is taken at its Form 4 FX."""
    return (base_commodity(contract) not in DELIVERY_FX_ONLY
            and _num((contract or {}).get("form4_fx")) is not None)


def cost_fx(contract, fallback=None):
    """``(fx, source)`` the contract's cost is converted at.

    Form 4 FX (not for SBM), else delivery FX, else ``fallback``. ``source``
    names which one was used, so a screen can say so.
    """
    c = contract or {}
    if uses_form4(c):
        return _num(c.get("form4_fx")), SOURCE_FORM4
    delivery = _num(c.get("delivery_fx"))
    if delivery is not None:
        return delivery, SOURCE_DELIVERY
    fallback = _num(fallback)
    return fallback, (SOURCE_FALLBACK if fallback is not None else "")
