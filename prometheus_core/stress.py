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


def normalize_shocks(values: Any) -> tuple[float, ...] | None:
    """Clean a user shock list (fractions, e.g. -0.05 = -5%).

    Accepts any iterable of numbers or numeric strings; drops blanks and
    duplicates, always includes the zero-shock base, and sorts ascending.
    Returns None when nothing usable was given (caller uses defaults).
    """
    if values is None:
        return None
    if isinstance(values, (str, bytes)):
        values = [v for v in str(values).replace(";", ",").split(",")]
    out = set()
    for v in values:
        f = to_float(v, None)
        if f is None or math.isnan(f) or f <= -1.0:
            continue
        out.add(round(f, 6))
    if not out:
        return None
    out.add(0.0)
    return tuple(sorted(out))


def parse_shock_percent_text(text: Any) -> tuple[float, ...] | None:
    """'-10, -5, 5, 10' (percent) → (-0.10, -0.05, 0.0, 0.05, 0.10)."""
    if text is None:
        return None
    parts = [p.strip().rstrip("%") for p in str(text).replace(";", ",").split(",")]
    vals = [to_float(p, None) for p in parts if p.strip()]
    vals = [v / 100.0 for v in vals if v is not None]
    return normalize_shocks(vals)


def cbot_history_scenarios(
    series: Any,
    spot: Any,
    horizon_days: Any = 30,
    today: dt.date | None = None,
) -> dict[str, Any]:
    """Turn a CBOT close history into realistic stress levels.

    ``series`` is ``[(iso_date, close)]``.  Returns 12-month and full-history
    highs/lows (with dates), the worst/best move seen over any
    ``horizon_days`` window (as %), the 5th/95th percentile of those moves,
    and a list of named scenarios expressed both as a CBOT level and as a %
    shock off ``spot``.  Empty dict when there is no usable data.
    """
    spot = to_float(spot, None)
    horizon = max(1, int(to_float(horizon_days, 30) or 30))
    pts = []
    for d, v in series or []:
        fv = to_float(v, None)
        if not d or fv is None or fv <= 0:
            continue
        try:
            pts.append((dt.date.fromisoformat(str(d)[:10]), fv))
        except ValueError:
            continue
    if not pts or spot is None or spot <= 0:
        return {}
    pts.sort()
    today = today or pts[-1][0]
    last12 = [(d, v) for d, v in pts if d >= today - dt.timedelta(days=365)] or pts
    lo12 = min(last12, key=lambda t: t[1])
    hi12 = max(last12, key=lambda t: t[1])
    lo_all = min(pts, key=lambda t: t[1])
    hi_all = max(pts, key=lambda t: t[1])

    # Moves over the horizon: compare each close with the last close at
    # least ``horizon`` days later (calendar days, gaps tolerated).
    moves = []
    j = 0
    for i, (d0, v0) in enumerate(pts):
        target = d0 + dt.timedelta(days=horizon)
        j = max(j, i + 1)
        while j < len(pts) and pts[j][0] < target:
            j += 1
        if j >= len(pts):
            break
        if (pts[j][0] - target).days <= max(7, horizon // 4):
            moves.append(pts[j][1] / v0 - 1.0)

    def pct(q: float) -> float | None:
        if not moves:
            return None
        s = sorted(moves)
        k = (len(s) - 1) * q
        f = math.floor(k)
        c = min(f + 1, len(s) - 1)
        return s[f] + (s[c] - s[f]) * (k - f)

    worst_fall = min(moves) if moves else None
    worst_rise = max(moves) if moves else None
    p05, p95 = pct(0.05), pct(0.95)

    scenarios = []

    def add(name: str, level: float | None, note: str) -> None:
        if level is None or level <= 0:
            return
        scenarios.append({"name": name, "cbot": round(level, 4),
                          "shock": round(level / spot - 1.0, 6), "note": note})

    add("CBOT at 12-month low", lo12[1], f"low {lo12[1]:,.2f} on {lo12[0].isoformat()}")
    add("CBOT at 12-month high", hi12[1], f"high {hi12[1]:,.2f} on {hi12[0].isoformat()}")
    if (lo_all[0], hi_all[0]) != (lo12[0], hi12[0]):
        add("CBOT at all-history low", lo_all[1], f"low {lo_all[1]:,.2f} on {lo_all[0].isoformat()}")
        add("CBOT at all-history high", hi_all[1], f"high {hi_all[1]:,.2f} on {hi_all[0].isoformat()}")
    if worst_fall is not None:
        add(f"Worst {horizon}-day fall repeats", spot * (1 + worst_fall),
            f"{worst_fall:+.1%} over {horizon} days (worst seen)")
        add(f"Worst {horizon}-day rise repeats", spot * (1 + worst_rise),
            f"{worst_rise:+.1%} over {horizon} days (worst seen)")
    if p05 is not None:
        add(f"Typical bad {horizon}-day rise (95th pct)", spot * (1 + p95),
            f"{p95:+.1%} — exceeded in only 5% of {horizon}-day windows")
        add(f"Typical good {horizon}-day fall (5th pct)", spot * (1 + p05),
            f"{p05:+.1%} — only 5% of {horizon}-day windows fell further")

    return {
        "spot": spot,
        "horizon_days": horizon,
        "points": len(pts),
        "first_date": pts[0][0].isoformat(),
        "last_date": pts[-1][0].isoformat(),
        "low_12m": lo12[1], "low_12m_date": lo12[0].isoformat(),
        "high_12m": hi12[1], "high_12m_date": hi12[0].isoformat(),
        "low_all": lo_all[1], "low_all_date": lo_all[0].isoformat(),
        "high_all": hi_all[1], "high_all_date": hi_all[0].isoformat(),
        "worst_fall_pct": worst_fall, "worst_rise_pct": worst_rise,
        "p05_pct": p05, "p95_pct": p95,
        "moves_count": len(moves),
        "scenarios": scenarios,
    }


def suggested_cbot_shocks(hist: Mapping[str, Any]) -> tuple[float, ...] | None:
    """A CBOT shock set built from history: 12-month low/high plus the
    worst horizon fall/rise, rounded to 0.5%."""
    if not hist:
        return None
    spot = hist.get("spot")
    vals = []
    for key in ("low_12m", "high_12m"):
        v = hist.get(key)
        if v and spot:
            vals.append(v / spot - 1.0)
    for key in ("worst_fall_pct", "worst_rise_pct"):
        v = hist.get(key)
        if v is not None:
            vals.append(v)
    vals = [round(v * 200) / 200 for v in vals]
    return normalize_shocks(vals)


def run_stress_test(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Run the V10.4 shock grid with explicit missing-input handling."""
    missing: list[str] = []
    commodity = str(inputs.get("commodity") or "").upper()
    if not commodity:
        missing.append("commodity")

    # Flat-price deals (SFM, DDGS, fixed $/MT contracts): the "CBOT" axis
    # becomes the flat CIF price itself (factor 1, no premium), so the same
    # grid stresses price and FX.
    flat_price = to_float(inputs.get("flat_price_usd_mt"), None)
    is_flat = flat_price is not None
    if is_flat:
        inputs = {**inputs, "cbot": flat_price, "premium_cents": 0.0,
                  "premium_locked": True}

    factor = 1.0 if is_flat else (cbot_conv_factor(commodity, strict=True) if commodity else None)
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
        missing.append("flat price CIF USD/MT (must be > 0)" if is_flat else "CBOT (must be > 0)")
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
    custom_cbot = normalize_shocks(inputs.get("cbot_shocks_custom"))
    custom_fx = normalize_shocks(inputs.get("fx_shocks_custom"))
    cbot_shocks = (0.0,) if cbot_locked else (custom_cbot or STRESS_CBOT_SHOCKS)
    fx_shocks = custom_fx or STRESS_FX_SHOCKS

    rows: list[dict[str, Any]] = []
    base_row: dict[str, Any] | None = None
    for cbot_shock in cbot_shocks:
        for fx_shock in fx_shocks:
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
        "flat_price": is_flat,
        "prem_shocks_used": premium_shocks,
        "cbot_shocks_used": cbot_shocks,
        "fx_shocks_used": fx_shocks,
        "version": STRESS_ENGINE_VERSION,
        "ts": _now_ts(),
        "error": None,
        "missing": [],
    }
