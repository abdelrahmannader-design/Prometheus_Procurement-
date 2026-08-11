"""Prometheus Procurement — UI-independent business core.

Prometheus_V10_8_15.py imports this module but it was not part of the
delivered files, so this is a from-scratch reconstruction built from the
formulas, comments and call sites already present in that file (CBOT
conversion factors and their sourcing rationale, the CIF/FX/fees landed-cost
convention, the stress/decision engine's documented input and output
fields). No Tkinter, filesystem or network access — pure calculation only,
so it can be unit-tested and reused by exports/tests independently of the UI.
"""

import datetime as dt

# ══════════════════════════════════════════════════════════════════════
# CBOT → USD/MT conversion factors.
#   CORN/SOYBEAN/WHEAT: cents/bu × factor = USD/MT
#     factor = (bushels per MT) / 100. Corn 39.37 bu/MT -> 0.3937.
#     Soy & wheat share the 60-lb bushel -> 36.745 bu/MT -> 0.36745.
#   SBM: $/short-ton × 1.1023 = $/MT (1 MT = 1.1023 short tons)
# ══════════════════════════════════════════════════════════════════════
CORN_FACTOR = 0.3937
SOYBEAN_FACTOR = 0.36745
WHEAT_FACTOR = 0.36745
SBM_ST_PER_MT = 1.1023

_BASE_FACTORS = {
    "CORN": CORN_FACTOR,
    "SOYBEAN": SOYBEAN_FACTOR,
    "WHEAT": WHEAT_FACTOR,
    "SBM": SBM_ST_PER_MT,
}

STRESS_ENGINE_VERSION = "core-1.0"
DECISION_ENGINE_VERSION = "core-1.0"

# Negative EGP/MT saving below which a scenario is classified "Material Loss".
STRESS_MATERIAL_LOSS_EGP_MT = -300.0

# Fractional shocks applied multiplicatively to CBOT price / FX rate.
STRESS_CBOT_SHOCKS = (-0.05, -0.02, 0.0, 0.02, 0.05)
STRESS_FX_SHOCKS = (-0.03, -0.01, 0.0, 0.01, 0.03)
# Absolute cents/bu (or $/st) shocks applied additively to the premium.
STRESS_PREM_SHOCKS = (-10.0, 0.0, 10.0)

DECISION_ACTIONS = (
    "PRICE_100", "PRICE_PARTIAL", "WAIT",
    "BUY_LOCAL", "RENEGOTIATE_PREMIUM", "INSUFFICIENT_DATA",
)


def to_float(x, default=None):
    if x is None:
        return default
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace(",", "")
    if not s:
        return default
    try:
        return float(s)
    except (TypeError, ValueError):
        return default


def cbot_conv_factor(commodity, strict=False):
    base = (commodity or "").upper().split("-")[0]
    if base in _BASE_FACTORS:
        return _BASE_FACTORS[base]
    if strict:
        return None
    return CORN_FACTOR  # display-only fallback for an unrecognized commodity


def _factor_from_meta(comm_meta):
    if not comm_meta:
        return None
    lf = to_float(comm_meta.get("locked_factor"), None)
    if lf is not None:
        return lf
    cv = to_float(comm_meta.get("conversion_value"), None)
    if cv is None:
        return None
    if comm_meta.get("conversion_type") == "bu_per_mt":
        return cv / 100.0
    return cv  # st_per_mt or a direct multiplier


def cbot_to_usd_mt(comm_meta, cbot_price, premium_input):
    factor = _factor_from_meta(comm_meta)
    cbot_price = to_float(cbot_price, None)
    if factor is None or cbot_price is None:
        return None
    premium = to_float(premium_input, 0.0) or 0.0
    return (cbot_price + premium) * factor


def carry_usd_mt(usd_mt, finance_days, annual_rate_pct):
    usd_mt = to_float(usd_mt, None)
    if usd_mt is None:
        return None
    days = to_float(finance_days, 0.0) or 0.0
    rate = to_float(annual_rate_pct, 0.0) or 0.0
    return usd_mt * (rate / 100.0) * (days / 365.0)


def stress_landed_cost_egp_mt(cbot, premium, factor, fx, fees_egp):
    cbot = to_float(cbot, None)
    factor = to_float(factor, None)
    fx = to_float(fx, None)
    if cbot is None or factor is None or fx is None:
        return None
    premium = to_float(premium, 0.0) or 0.0
    fees = to_float(fees_egp, 0.0) or 0.0
    return (cbot + premium) * factor * fx + fees


def stress_classify(saving_mt, marginal=200.0, material=None, strong=500.0):
    if saving_mt is None:
        return "Loss"
    material = material if material is not None else STRESS_MATERIAL_LOSS_EGP_MT
    if saving_mt >= strong:
        return "Strong Advantage"
    if saving_mt >= marginal:
        return "Advantage"
    if saving_mt >= 0:
        return "Marginal"
    if saving_mt >= material:
        return "Loss"
    return "Material Loss"


def run_stress_test(inputs):
    inputs = inputs or {}
    commodity = inputs.get("commodity")
    cbot = to_float(inputs.get("cbot"), None)
    fx = to_float(inputs.get("fx"), None)
    premium_cents = to_float(inputs.get("premium_cents"), None)
    qty_mt = to_float(inputs.get("qty_mt"), None)
    local_egp_mt = to_float(inputs.get("local_egp_mt"), None)
    fees_egp_mt = to_float(inputs.get("fees_egp_mt"), 0.0) or 0.0
    marginal_egp_mt = to_float(inputs.get("marginal_egp_mt"), 200.0) or 200.0
    ts = dt.datetime.now().isoformat(timespec="seconds")

    required = {"commodity": commodity, "cbot": cbot, "fx": fx,
                "premium_cents": premium_cents, "qty_mt": qty_mt,
                "local_egp_mt": local_egp_mt}
    missing = [k for k, v in required.items() if v is None]
    if missing:
        return {"error": "Missing required inputs", "missing": missing,
                "resilience": "Unavailable", "version": STRESS_ENGINE_VERSION,
                "ts": ts}

    factor = cbot_conv_factor(commodity, strict=True)
    if factor is None:
        return {"error": f"No conversion factor for {commodity!r}",
                "missing": [], "resilience": "Unavailable",
                "version": STRESS_ENGINE_VERSION, "ts": ts}

    cbot_locked = bool(inputs.get("cbot_locked"))
    premium_locked = bool(inputs.get("premium_locked"))
    prem_shocks_custom = inputs.get("prem_shocks_custom")

    cbot_shocks_used = (0.0,) if cbot_locked else tuple(STRESS_CBOT_SHOCKS)
    if premium_locked:
        prem_shocks_used = (0.0,)
    elif prem_shocks_custom:
        prem_shocks_used = tuple(prem_shocks_custom)
    else:
        prem_shocks_used = tuple(STRESS_PREM_SHOCKS)

    rows = []
    for cs in cbot_shocks_used:
        cbot_s = cbot * (1 + cs)
        for fs in STRESS_FX_SHOCKS:
            fx_s = fx * (1 + fs)
            for ps in prem_shocks_used:
                prem_s = premium_cents + ps
                landed = stress_landed_cost_egp_mt(cbot_s, prem_s, factor, fx_s, fees_egp_mt)
                saving_mt = (local_egp_mt - landed) if landed is not None else None
                saving_total = (saving_mt * qty_mt) if saving_mt is not None else None
                rows.append({
                    "cbot_shock": cs, "fx_shock": fs, "prem_shock": ps,
                    "cbot": cbot_s, "fx": fx_s, "premium": prem_s,
                    "landed_egp_mt": landed, "saving_egp_mt": saving_mt,
                    "saving_total_egp": saving_total,
                    "classification": stress_classify(
                        saving_mt, marginal=marginal_egp_mt,
                        material=STRESS_MATERIAL_LOSS_EGP_MT),
                })

    base_row = next((r for r in rows if r["cbot_shock"] == 0.0
                      and r["fx_shock"] == 0.0 and r["prem_shock"] == 0.0), rows[0])
    best_row = max(rows, key=lambda r: r["saving_egp_mt"])
    adverse_row = min(rows, key=lambda r: r["saving_egp_mt"])

    high_risk = (base_row["saving_egp_mt"] is not None and base_row["saving_egp_mt"] > 0
                 and adverse_row["classification"] == "Material Loss")
    resilience = ("High Risk" if high_risk else
                  "Fragile" if adverse_row["saving_egp_mt"] < 0 else "Resilient")

    be_cbot = None
    if factor and fx:
        be_cbot = (local_egp_mt - fees_egp_mt) / (factor * fx) - premium_cents
    be_fx = None
    denom = (cbot + premium_cents) * factor
    if denom:
        be_fx = (local_egp_mt - fees_egp_mt) / denom

    cbot_buffer = (be_cbot - cbot) if be_cbot is not None else None
    cbot_buffer_pct = (cbot_buffer / be_cbot * 100.0) if cbot_buffer is not None and be_cbot else None
    fx_buffer = (be_fx - fx) if be_fx is not None else None
    fx_buffer_pct = (fx_buffer / be_fx * 100.0) if fx_buffer is not None and be_fx else None

    return {
        "error": None, "missing": [],
        "resilience": resilience, "high_risk": high_risk,
        "best": best_row, "base": base_row, "adverse": adverse_row, "rows": rows,
        "cbot_locked": cbot_locked, "premium_locked": premium_locked,
        "prem_shocks_used": prem_shocks_used, "cbot_shocks_used": cbot_shocks_used,
        "be_cbot": be_cbot, "be_fx": be_fx,
        "cbot_buffer": cbot_buffer, "cbot_buffer_pct": cbot_buffer_pct,
        "fx_buffer": fx_buffer, "fx_buffer_pct": fx_buffer_pct,
        "version": STRESS_ENGINE_VERSION, "ts": ts,
        "inputs": {"commodity": commodity, "cbot": cbot, "fx": fx,
                   "premium_cents": premium_cents, "qty_mt": qty_mt,
                   "local_egp_mt": local_egp_mt},
    }


def run_decision_engine(inputs):
    inputs = inputs or {}
    ts = dt.datetime.now().isoformat(timespec="seconds")
    st = run_stress_test(inputs)
    if st.get("error"):
        detail = st["error"]
        if st.get("missing"):
            detail += ": " + ", ".join(st["missing"])
        return {"action": "INSUFFICIENT_DATA", "headline": "Insufficient reliable data",
                "reasons": [detail], "high_risk": False,
                "base_saving_mt": None, "worst_mt": None, "base_total": None,
                "be_fx": None, "fx_now": to_float(inputs.get("fx"), None),
                "be_cbot": None, "cbot_now": to_float(inputs.get("cbot"), None),
                "confidence": 0, "pct": 0.0,
                "version": DECISION_ENGINE_VERSION, "ts": ts}

    base, adverse = st["base"], st["adverse"]
    base_saving_mt, worst_mt = base["saving_egp_mt"], adverse["saving_egp_mt"]
    be_fx, be_cbot = st["be_fx"], st["be_cbot"]
    fx_now, cbot_now = st["inputs"]["fx"], st["inputs"]["cbot"]
    high_risk = st["high_risk"]

    marginal = to_float(inputs.get("marginal_egp_mt"), 200.0) or 200.0
    strong = marginal * 2.5

    confidence = 70
    cbot_age = inputs.get("cbot_age_days")
    fx_age = inputs.get("fx_age_days")
    local_age = inputs.get("local_age_days")
    if cbot_age is not None:
        confidence += 15 if cbot_age <= 2 else (-10 if cbot_age > 7 else 0)
    if fx_age is not None:
        confidence += 15 if fx_age <= 1 else (-10 if fx_age > 3 else 0)
    if local_age is not None and local_age > 14:
        confidence -= 20
    if high_risk:
        confidence -= 15
    confidence = max(0, min(100, confidence))

    days = inputs.get("days_to_deadline")
    pct_priced = inputs.get("pct_priced")
    reasons = []
    pct = 0.0

    if base_saving_mt <= 0:
        action = "BUY_LOCAL"
        headline = f"Buy local — import saving is {base_saving_mt:+.0f} EGP/MT"
        reasons.append("Base-case saving is at or below zero")
    elif high_risk:
        if days is not None and days <= 7:
            action, pct = "PRICE_100", 100.0
            headline = "Price 100% now — deadline is close despite downside risk"
            reasons.append(f"Only {days:.0f} day(s) to deadline — no time to wait out the adverse scenario")
        else:
            action = "WAIT"
            headline = "Wait — adverse scenario produces a material loss"
            reasons.append(f"Adverse-case saving is {worst_mt:+.0f} EGP/MT (Material Loss band)")
    elif base_saving_mt >= strong:
        action, pct = "PRICE_100", 100.0
        headline = f"Price 100% now — strong advantage ({base_saving_mt:+.0f} EGP/MT)"
        reasons.append("Base-case saving clears the strong-advantage threshold")
    elif pct_priced is not None and pct_priced < 100 and days is not None and days <= 14:
        pct = round(min(100.0, max(0.0, 100.0 - pct_priced)), 0)
        action = "PRICE_PARTIAL"
        headline = f"Price {pct:.0f}% more now — deadline approaching"
        reasons.append(f"Only {pct_priced:.0f}% priced with {days:.0f} day(s) to deadline")
    elif (not inputs.get("fx_secured", False) and be_fx and fx_now is not None
          and fx_now >= be_fx * 0.95):
        action = "RENEGOTIATE_PREMIUM"
        headline = "Renegotiate premium — FX is close to break-even and unsecured"
        reasons.append(f"FX {fx_now:.2f} is within 5% of break-even {be_fx:.2f}, and hedge is not secured")
    else:
        action, pct = "PRICE_PARTIAL", 50.0
        headline = f"Price partially — advantage present ({base_saving_mt:+.0f} EGP/MT)"
        reasons.append("Base-case saving is positive but below the strong-advantage threshold")

    return {
        "action": action, "headline": headline, "reasons": reasons,
        "high_risk": high_risk, "base_saving_mt": base_saving_mt, "worst_mt": worst_mt,
        "base_total": base["saving_total_egp"], "be_fx": be_fx, "fx_now": fx_now,
        "be_cbot": be_cbot, "cbot_now": cbot_now, "confidence": confidence,
        "pct": pct, "version": DECISION_ENGINE_VERSION, "ts": ts,
    }


def validate_single_inputs(comm_meta, inputs):
    inputs = inputs or {}
    if to_float(inputs.get("fx"), None) is None:
        return False, "Enter FX rate (EGP/USD)."
    if to_float(inputs.get("qty_mt"), None) is None:
        return False, "Enter Quantity (MT)."
    if to_float(inputs.get("local_egp_mt"), None) is None:
        return False, "Enter Local Price (EGP/MT)."

    ctype = ((comm_meta or {}).get("type") or "NONCBOT").upper()
    if to_float(inputs.get("import_usd_mt"), None) is None:
        if ctype == "CBOT":
            if to_float(inputs.get("cbot"), None) is None:
                return False, "Enter CBOT price."
            if to_float(inputs.get("premium_usd_mt"), None) is None:
                return False, "Enter Premium."
        elif to_float(inputs.get("import_egp_mt"), None) is None:
            return False, "Enter Import USD/MT (Non-CBOT)."

    if to_float(inputs.get("finance_days"), None) is None:
        return False, "Enter Finance Days."
    if to_float(inputs.get("interest_rate"), None) is None:
        return False, "Enter Interest Rate."
    return True, ""


def compute_decision(inputs):
    inputs = inputs or {}
    fx = to_float(inputs.get("fx"), None)
    local_egp_mt = to_float(inputs.get("local_egp_mt"), None)
    finance_days = to_float(inputs.get("finance_days"), 0.0) or 0.0
    interest_rate = to_float(inputs.get("interest_rate"), 0.0) or 0.0
    direct = to_float(inputs.get("supplier_direct_egp_mt"), 0.0) or 0.0
    indirect = to_float(inputs.get("supplier_indirect_egp_mt"), 0.0) or 0.0
    hedge_pct = to_float(inputs.get("hedge_pct"), 0.0) or 0.0
    hedge_fx = to_float(inputs.get("hedge_fx"), None)
    sell_price = to_float(inputs.get("sell_price_egp_mt"), None)

    import_usd_mt = to_float(inputs.get("import_usd_mt"), None)
    comm_meta = inputs.get("comm_meta")
    if import_usd_mt is None and comm_meta and (comm_meta.get("type") or "").upper() == "CBOT":
        import_usd_mt = cbot_to_usd_mt(comm_meta, inputs.get("cbot"), inputs.get("premium_usd_mt"))
    if import_usd_mt is None:
        import_egp_mt = to_float(inputs.get("import_egp_mt"), None)
        if import_egp_mt is not None and fx:
            import_usd_mt = import_egp_mt / fx

    carry = carry_usd_mt(import_usd_mt, finance_days, interest_rate)
    own_after_usd_mt = (import_usd_mt + carry) if (import_usd_mt is not None and carry is not None) else None
    own_after_egp_mt = (own_after_usd_mt * fx) if (own_after_usd_mt is not None and fx is not None) else None

    direct_own_after_egp_mt = (own_after_egp_mt + direct) if own_after_egp_mt is not None else None
    indirect_own_after_egp_mt = (own_after_egp_mt + indirect) if own_after_egp_mt is not None else None
    direct_saving_egp_mt = (local_egp_mt - direct_own_after_egp_mt) if (local_egp_mt is not None and direct_own_after_egp_mt is not None) else None
    indirect_saving_egp_mt = (local_egp_mt - indirect_own_after_egp_mt) if (local_egp_mt is not None and indirect_own_after_egp_mt is not None) else None

    def _break_even_fx(fee):
        if own_after_usd_mt is None or local_egp_mt is None or not own_after_usd_mt:
            return None
        return (local_egp_mt - fee) / own_after_usd_mt

    break_even_fx_direct = _break_even_fx(direct)
    break_even_fx_indirect = _break_even_fx(indirect)

    if hedge_fx is not None and hedge_pct and fx is not None:
        blended_fx = hedge_fx * (hedge_pct / 100.0) + fx * (1 - hedge_pct / 100.0)
    else:
        blended_fx = fx

    hedged_own_after_egp_mt = (own_after_usd_mt * blended_fx) if (own_after_usd_mt is not None and blended_fx is not None) else None
    hedged_direct_saving_egp_mt = (local_egp_mt - (hedged_own_after_egp_mt + direct)) if (local_egp_mt is not None and hedged_own_after_egp_mt is not None) else None
    hedged_indirect_saving_egp_mt = (local_egp_mt - (hedged_own_after_egp_mt + indirect)) if (local_egp_mt is not None and hedged_own_after_egp_mt is not None) else None

    direct_margin_egp_mt = (sell_price - direct_own_after_egp_mt) if (sell_price is not None and direct_own_after_egp_mt is not None) else None
    indirect_margin_egp_mt = (sell_price - indirect_own_after_egp_mt) if (sell_price is not None and indirect_own_after_egp_mt is not None) else None
    hedged_direct_margin_egp_mt = (sell_price - (hedged_own_after_egp_mt + direct)) if (sell_price is not None and hedged_own_after_egp_mt is not None) else None
    hedged_indirect_margin_egp_mt = (sell_price - (hedged_own_after_egp_mt + indirect)) if (sell_price is not None and hedged_own_after_egp_mt is not None) else None

    return {
        "import_usd_mt": import_usd_mt, "carry_usd_mt": carry,
        "own_after_usd_mt": own_after_usd_mt, "own_after_egp_mt": own_after_egp_mt,
        "direct_own_after_egp_mt": direct_own_after_egp_mt,
        "indirect_own_after_egp_mt": indirect_own_after_egp_mt,
        "direct_saving_egp_mt": direct_saving_egp_mt,
        "indirect_saving_egp_mt": indirect_saving_egp_mt,
        "saving_egp_mt": direct_saving_egp_mt,
        "break_even_fx_direct": break_even_fx_direct,
        "break_even_fx_indirect": break_even_fx_indirect,
        "fx": fx, "blended_fx": blended_fx,
        "hedged_direct_saving_egp_mt": hedged_direct_saving_egp_mt,
        "hedged_indirect_saving_egp_mt": hedged_indirect_saving_egp_mt,
        "direct_margin_egp_mt": direct_margin_egp_mt,
        "indirect_margin_egp_mt": indirect_margin_egp_mt,
        "hedged_direct_margin_egp_mt": hedged_direct_margin_egp_mt,
        "hedged_indirect_margin_egp_mt": hedged_indirect_margin_egp_mt,
    }
