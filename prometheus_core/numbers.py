"""Small numeric helpers shared by the calculation modules."""

from __future__ import annotations

from typing import Any


def to_float(value: Any, default: float | None = None) -> float | None:
    """Convert common numeric input formats to ``float``.

    Commas are accepted because procurement values are commonly copied from
    Excel as strings such as ``"25,000"``. Invalid or blank input returns the
    caller-provided default instead of raising inside a calculation.
    """
    try:
        if value is None:
            return default
        if isinstance(value, (int, float)):
            return float(value)
        text = str(value).strip().replace(",", "")
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Divide safely, returning ``default`` for zero or invalid input."""
    try:
        if denominator == 0:
            return default
        return numerator / denominator
    except (TypeError, ValueError, ZeroDivisionError):
        return default
