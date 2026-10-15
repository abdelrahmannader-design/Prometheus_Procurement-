"""What-if: hold local grain, or book an import arriving later.

The desk's import manager circulates this comparison by email every time
offers move, and the app has to produce the identical number or the two
cannot be argued from the same page. So the arithmetic here follows that
email's layout line for line, including the order of operations and the
names of the intermediate figures:

    price                   local market price, EGP/MT
    interest amount/annum   price x rate
    interest per day        that / year basis
    carry cost/MT           per-day x carry days
    price with carry cost   price + carry
    local expenses          deducted, to reach an import-comparable level
    net price               price with carry - expenses
    price in USD            net / FX
    price in c/bu           that / conversion
    premium with carry      price in c/bu - CBOT

Why local expenses are *subtracted*: an import premium is quoted CIF at the
port, before discharge, clearance and the run inland. A local price is not.
Deducting the costs that sit between the two puts both on the same footing.
Whether a given local quote already excludes them is a question about that
quote, not about the arithmetic, so the deduction is an input and the
no-deduction figure is always reported beside it.

Carry exists because the two sides arrive at different times. Local grain is
owned today; an offer for November delivery is not. Carrying the local price
to the offer's arrival date is what makes them comparable, and the carry
days should be the days to that arrival, not a round number.

Pure functions only — no Tk, no I/O — so the numbers can be checked against
the email in a test rather than by eye.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from .numbers import to_float

__all__ = ["WHATIF_VERSION", "MAIL_REFERENCE", "DEFAULT_YEAR_BASIS",
           "carry_cost", "local_premium_equivalent", "whatif_scenario",
           "scenario_ladder", "offer_comparison", "days_until"]

WHATIF_VERSION = "1.0-mail-aligned"

#: Day-count the email uses. Not 360: the local facility is quoted per annum
#: on a 365-day year, while the USD finance carry elsewhere in the app is a
#: 360-day money-market convention. Mixing them is a real error, so this is
#: an explicit input rather than a shared constant.
DEFAULT_YEAR_BASIS = 365.0

#: The reference case, from the YC offers mail of 14 Oct 2026. Kept so the
#: app can show its working against a figure the desk already agreed, and so
#: a regression in the arithmetic fails a test instead of a meeting.
MAIL_REFERENCE: dict[str, Any] = {
    "label": "YC offers · 14 Oct 2026",
    "local_price_egp_mt": 14350.0,
    "interest_rate_pct": 20.0,
    "year_basis": 365.0,
    "carry_days": 30,
    "local_expenses_egp_mt": 500.0,
    "fx_egp_usd": 53.0,
    "conversion": 0.3937,
    "cbot": 480.0,
    "futures_month": "Dec",
    # What the mail prints, to check against.
    "expected": {
        "interest_amount_per_annum": 2870.0,
        "interest_per_day": 7.86,
        "carry_cost_egp_mt": 236.0,
        "price_with_carry_egp_mt": 14586.0,
        "net_price_egp_mt": 14086.0,
        "price_usd_mt": 266.0,
        "price_cents_bu": 675.0,
        "premium": 195.0,
    },
    "offers": [
        {"supplier": "Cofco", "eta_text": "First week of November",
         "eta": "2026-11-04", "premium": 190.0, "origin": "ARG/BRZ"},
        {"supplier": "ADM", "eta_text": "Mid November",
         "eta": "2026-11-15", "premium": 190.0, "origin": "ARG/BRZ"},
        {"supplier": "El-Magd", "eta_text": "End November / first half December",
         "eta": "2026-12-05", "premium": 205.0, "origin": "ARG/BRZ"},
    ],
}


def carry_cost(price, interest_rate_pct, carry_days,
               year_basis=DEFAULT_YEAR_BASIS):
    """Cost of holding ``price`` for ``carry_days``, the email's way.

    Deliberately computed as annual-amount → per-day → times days, rather
    than collapsed into one multiplication, so each printed line can be
    checked against the mail.
    """
    price = to_float(price, 0.0) or 0.0
    rate = (to_float(interest_rate_pct, 0.0) or 0.0) / 100.0
    days = to_float(carry_days, 0.0) or 0.0
    year = to_float(year_basis, DEFAULT_YEAR_BASIS) or DEFAULT_YEAR_BASIS
    per_annum = price * rate
    per_day = per_annum / year if year else 0.0
    return {
        "interest_amount_per_annum": per_annum,
        "interest_per_day": per_day,
        "carry_days": days,
        "carry_cost_egp_mt": per_day * days,
    }


def local_premium_equivalent(price_egp_mt, fx_egp_usd, conversion, cbot,
                             local_expenses_egp_mt=0.0):
    """Convert an EGP/MT local price into a premium over the board.

    Returns every step, because the single output number is impossible to
    argue with and the steps are not.
    """
    price = to_float(price_egp_mt, None)
    fx = to_float(fx_egp_usd, None)
    conv = to_float(conversion, None)
    board = to_float(cbot, None)
    expenses = to_float(local_expenses_egp_mt, 0.0) or 0.0

    missing = [name for name, value in (("local price", price), ("FX", fx),
                                        ("conversion", conv), ("CBOT", board))
               if value is None]
    if missing or not fx or not conv:
        return {"net_price_egp_mt": None, "price_usd_mt": None,
                "price_cents_bu": None, "premium": None,
                "local_expenses_egp_mt": expenses,
                "note": "needs " + ", ".join(missing or ["FX"])}

    net = price - expenses
    usd = net / fx
    cents = usd / conv
    return {
        "net_price_egp_mt": net,
        "price_usd_mt": usd,
        "price_cents_bu": cents,
        "premium": cents - board,
        "local_expenses_egp_mt": expenses,
        "note": "",
    }


def whatif_scenario(local_price_egp_mt, fx_egp_usd, conversion, cbot,
                    interest_rate_pct=0.0, carry_days=0,
                    local_expenses_egp_mt=0.0,
                    year_basis=DEFAULT_YEAR_BASIS, label=""):
    """One full row of the email's what-if table.

    ``premium`` carries the expense deduction; ``premium_raw`` does not. Both
    are returned because which one is right depends on where the local quote
    was measured, and that is not something the arithmetic can decide.
    """
    price = to_float(local_price_egp_mt, None)
    carry = carry_cost(price, interest_rate_pct, carry_days, year_basis)
    with_carry = (price + carry["carry_cost_egp_mt"]) if price is not None else None

    net = local_premium_equivalent(with_carry, fx_egp_usd, conversion, cbot,
                                   local_expenses_egp_mt)
    raw = local_premium_equivalent(with_carry, fx_egp_usd, conversion, cbot, 0.0)

    return {
        "label": label,
        "local_price_egp_mt": price,
        "interest_rate_pct": to_float(interest_rate_pct, 0.0) or 0.0,
        "year_basis": to_float(year_basis, DEFAULT_YEAR_BASIS) or DEFAULT_YEAR_BASIS,
        **carry,
        "price_with_carry_egp_mt": with_carry,
        "local_expenses_egp_mt": net["local_expenses_egp_mt"],
        "net_price_egp_mt": net["net_price_egp_mt"],
        "price_usd_mt": net["price_usd_mt"],
        "price_cents_bu": net["price_cents_bu"],
        "premium": net["premium"],
        "premium_raw": raw["premium"],
        "fx_egp_usd": to_float(fx_egp_usd, None),
        "conversion": to_float(conversion, None),
        "cbot": to_float(cbot, None),
        "note": net["note"],
    }


def days_until(eta, today=None):
    """Whole days from ``today`` to ``eta`` (YYYY-MM-DD), floored at zero."""
    text = str(eta or "")[:10]
    if not text:
        return None
    try:
        target = dt.date.fromisoformat(text)
    except ValueError:
        return None
    base = today or dt.date.today()
    return max(0, (target - base).days)


def scenario_ladder(day_counts, **kwargs):
    """The same scenario at several holding periods.

    A single carry figure hides how fast the answer moves with time, which
    is the whole point when offers arrive weeks apart.
    """
    out = []
    for days in day_counts:
        row = dict(kwargs)
        row["carry_days"] = days
        row.setdefault("label", f"{days:.0f} days")
        out.append(whatif_scenario(**row))
    return out


def offer_comparison(offers, local_price_egp_mt, fx_egp_usd, conversion, cbot,
                     interest_rate_pct=0.0, local_expenses_egp_mt=0.0,
                     year_basis=DEFAULT_YEAR_BASIS, today=None):
    """Each offer against local carried to that offer's own arrival date.

    Comparing a November cargo with a local price held for a flat thirty days
    flatters whichever supplier happens to land near day thirty. Every offer
    is scored against local carried to its own ETA instead.
    """
    rows = []
    for offer in offers or []:
        premium = to_float(offer.get("premium"), None)
        days = offer.get("carry_days")
        if days is None:
            days = days_until(offer.get("eta"), today)
        scenario = whatif_scenario(
            local_price_egp_mt, fx_egp_usd, conversion, cbot,
            interest_rate_pct=interest_rate_pct,
            carry_days=days or 0,
            local_expenses_egp_mt=local_expenses_egp_mt,
            year_basis=year_basis,
            label=offer.get("supplier", ""))
        local_premium = scenario["premium"]
        gap = (local_premium - premium) if (local_premium is not None
                                            and premium is not None) else None
        rows.append({
            "supplier": offer.get("supplier", ""),
            "origin": offer.get("origin", ""),
            "eta": offer.get("eta", ""),
            "eta_text": offer.get("eta_text", ""),
            "carry_days": days,
            "offer_premium": premium,
            "local_premium_with_carry": local_premium,
            # Positive: local costs more over the board than the offer, so
            # the import is the cheaper way to own the same tonne.
            "gap": gap,
            "verdict": ("—" if gap is None else
                        "import cheaper" if gap > 0 else
                        "local cheaper" if gap < 0 else "level"),
            "scenario": scenario,
        })
    return rows


#: The order inputs are swapped when bridging one premium to another. Local
#: price first because it is the largest and the most argued-about; the board
#: last because it is the one nobody disputes.
BRIDGE_ORDER = ("local_price_egp_mt", "local_expenses_egp_mt", "carry_days",
                "interest_rate_pct", "year_basis", "fx_egp_usd",
                "conversion", "cbot")

BRIDGE_LABELS = {
    "local_price_egp_mt": "Local price EGP/MT",
    "local_expenses_egp_mt": "Local expenses EGP/MT",
    "carry_days": "Carry days",
    "interest_rate_pct": "Interest %/annum",
    "year_basis": "Year basis",
    "fx_egp_usd": "FX EGP/USD",
    "conversion": "Conversion",
    "cbot": "CBOT",
}


def premium_bridge(base, target, order=BRIDGE_ORDER):
    """Why two premiums differ, one input at a time, adding up exactly.

    Two desks quoting the same market reach different premiums because they
    disagree about several inputs at once, and an argument about the total
    goes nowhere. Swapping one input at a time and recomputing after each
    attributes the whole difference without any of it going missing: the
    deltas sum to the gap by construction, because each is measured against
    the figure the previous swap produced rather than against the start.

    That matters here because the chain divides. Taking each input's effect
    in isolation and adding them up would not reconcile, and the residual
    would look like a mistake in one of the inputs when it is only an
    artefact of the arithmetic.

    ``base`` and ``target`` are whatif_scenario kwargs. Returns the starting
    premium, a step per input that actually differs, and the ending premium.
    """
    def premium_of(values):
        return whatif_scenario(
            values.get("local_price_egp_mt"), values.get("fx_egp_usd"),
            values.get("conversion"), values.get("cbot"),
            interest_rate_pct=values.get("interest_rate_pct", 0.0),
            carry_days=values.get("carry_days", 0),
            local_expenses_egp_mt=values.get("local_expenses_egp_mt", 0.0),
            year_basis=values.get("year_basis", DEFAULT_YEAR_BASIS))["premium"]

    running = dict(base)
    start = premium_of(running)
    previous = start
    steps = []
    for field in order:
        if field not in target:
            continue
        was = to_float(running.get(field), None)
        now = to_float(target.get(field), None)
        if was is None or now is None or abs(was - now) < 1e-12:
            continue
        running[field] = target[field]
        current = premium_of(running)
        steps.append({
            "field": field,
            "label": BRIDGE_LABELS.get(field, field),
            "from": was,
            "to": now,
            "delta": (current - previous) if (current is not None
                                              and previous is not None) else None,
            "premium_after": current,
        })
        previous = current
    return {"start_premium": start, "end_premium": previous, "steps": steps,
            "total_delta": (previous - start) if (previous is not None
                                                  and start is not None) else None}
