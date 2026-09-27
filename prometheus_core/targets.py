"""CBOT price targets for unpriced contract quantity.

A buyer fixing CBOT wants to price *low*: a BUY_BELOW target is hit when
the market trades at or below the level.  A PROTECT_ABOVE level is a cap:
if the market rises to it, price anyway to stop the cost rising further.
"""

from __future__ import annotations

from typing import Any

from .numbers import to_float

TARGETS_ENGINE_VERSION = "1.0"


def evaluate_target(target: dict[str, Any], price: Any, near_pct: float = 1.0) -> dict[str, Any]:
    level = to_float(target.get("level"), None)
    px = to_float(price, None)
    direction = str(target.get("direction") or "BUY_BELOW").upper()
    if str(target.get("status") or "ACTIVE").upper() == "DONE":
        return {"state": "DONE", "distance": None, "distance_pct": None}
    if level is None or px is None or level <= 0:
        return {"state": "NO_PRICE", "distance": None, "distance_pct": None}
    # Distance the market still has to move to reach the level
    # (positive = not reached yet).
    distance = (px - level) if direction == "BUY_BELOW" else (level - px)
    pct = distance / level * 100.0
    if distance <= 0:
        state = "HIT"
    elif pct <= near_pct:
        state = "NEAR"
    else:
        state = "WAITING"
    return {"state": state, "distance": distance, "distance_pct": pct}


def suggest_ladder(spot: Any, unpriced_mt: Any, steps_pct=(-2.0, -4.0, -6.0),
                   protect_pct: float | None = 5.0, tick: float = 0.25) -> list[dict[str, Any]]:
    """Split the unpriced quantity into equal BUY_BELOW tranches below spot,
    plus an optional PROTECT_ABOVE level (priced with the balance)."""
    spot = to_float(spot, None)
    qty = to_float(unpriced_mt, 0.0) or 0.0
    if not spot or spot <= 0 or qty <= 0:
        return []
    steps = [s for s in steps_pct if s is not None]
    n = len(steps) or 1
    each = round(qty / n, 0)
    out = []
    for i, s in enumerate(steps):
        lvl = round(spot * (1 + s / 100.0) / tick) * tick
        q = each if i < n - 1 else qty - each * (n - 1)
        out.append({"level": lvl, "qty_mt": q, "direction": "BUY_BELOW",
                    "note": f"ladder {s:+.0f}% vs {spot:,.2f}"})
    if protect_pct:
        lvl = round(spot * (1 + protect_pct / 100.0) / tick) * tick
        out.append({"level": lvl, "qty_mt": qty, "direction": "PROTECT_ABOVE",
                    "note": f"cap +{protect_pct:.0f}%: price the balance if CBOT rises here"})
    return out
