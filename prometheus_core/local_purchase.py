"""How a local purchase decision is judged.

A local purchase is judged on the day it was made, with information that
existed on that day (no later prices), on two separate questions:

1. Source decision — was buying locally cheaper than importing?
   Import parity on the purchase date =
   (CBOT on date + premium reference) × factor × (1 + finance carry)
   × FX on date + import fees (intake + clearance + freight).
2. Price quality — did we pay a fair local price?
   Compared with the last local market price logged on or before the date.

The overall verdict combines both.  All thresholds are EGP/MT.
"""

from __future__ import annotations

from typing import Any

from .numbers import to_float

LOCAL_EVAL_VERSION = "1.0-parity-on-purchase-date"


def import_parity_egp_mt(
    cbot: Any,
    premium: Any,
    factor: Any,
    fx: Any,
    import_fees_egp_mt: Any,
    finance_days: Any = 0.0,
    annual_rate_pct: Any = 0.0,
) -> float | None:
    """Landed import cost on a given day, or None when an input is missing."""
    cbot = to_float(cbot, None)
    premium = to_float(premium, None)
    factor = to_float(factor, None)
    fx = to_float(fx, None)
    fees = to_float(import_fees_egp_mt, None)
    if None in (cbot, premium, factor, fx, fees) or not factor or not fx:
        return None
    days = to_float(finance_days, 0.0) or 0.0
    rate = to_float(annual_rate_pct, 0.0) or 0.0
    carry_multiplier = 1.0 + (rate / 100.0) * (days / 360.0)
    return (cbot + premium) * factor * carry_multiplier * fx + fees


def evaluate_local_purchase(
    local_all_in: Any,
    qty_mt: Any,
    import_parity: Any = None,
    market_price: Any = None,
    threshold_egp_mt: Any = 200.0,
) -> dict[str, Any]:
    """Judge one local purchase.  Sign convention: negative = local cheaper."""
    allin = to_float(local_all_in, None)
    qty = to_float(qty_mt, 0.0) or 0.0
    parity = to_float(import_parity, None)
    market = to_float(market_price, None)
    th = abs(to_float(threshold_egp_mt, 200.0) or 0.0)

    vs_import = (allin - parity) if (allin is not None and parity is not None) else None
    saving_vs_import_total = (-vs_import * qty) if vs_import is not None else None
    vs_market = (allin - market) if (allin is not None and market) else None

    if vs_import is None:
        source = "— no import parity"
    elif vs_import <= -th:
        source = "✔ LOCAL CHEAPER"
    elif vs_import < th:
        source = "⚠ ABOUT EQUAL"
    else:
        source = "✘ IMPORT CHEAPER"

    if vs_market is None:
        price = "—"
    elif vs_market <= 0:
        price = "✔ AT/BELOW MARKET"
    elif vs_market < th:
        price = "⚠ SLIGHTLY ABOVE MARKET"
    else:
        price = "✘ ABOVE MARKET"

    if vs_import is None:
        if vs_market is None:
            overall = "—"
        elif price.startswith("✔"):
            overall = "✔ GOOD PRICE"
        else:
            overall = "⚠ CHECK PRICE"
    elif source.startswith("✘"):
        overall = "✘ POOR DECISION"
    elif source.startswith("✔") and not price.startswith("✘"):
        overall = "✔ GOOD DECISION"
    else:
        overall = "⚠ ACCEPTABLE"

    return {
        "local_all_in": allin,
        "import_parity": parity,
        "vs_import_egp_mt": vs_import,
        "saving_vs_import_total_egp": saving_vs_import_total,
        "market_price": market,
        "vs_market_egp_mt": vs_market,
        "source_verdict": source,
        "price_verdict": price,
        "overall_verdict": overall,
        "threshold_egp_mt": th,
        "version": LOCAL_EVAL_VERSION,
    }
