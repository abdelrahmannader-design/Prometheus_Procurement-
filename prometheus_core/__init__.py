"""Pure business logic for Prometheus Procurement.

This package deliberately has no Tkinter, file-system, or network dependencies.
That makes the financially important calculations testable and reusable by a
future web/API application.
"""

from .numbers import to_float, safe_div
from .cbot import (
    CORN_FACTOR,
    SOYBEAN_FACTOR,
    WHEAT_FACTOR,
    SBM_ST_PER_MT,
    CBOT_CONV,
    cbot_conv_factor,
    cbot_to_usd_mt,
    carry_usd_mt,
)
from .stress import (
    STRESS_ENGINE_VERSION,
    STRESS_MATERIAL_LOSS_EGP_MT,
    STRESS_CBOT_SHOCKS,
    STRESS_FX_SHOCKS,
    STRESS_PREM_SHOCKS,
    stress_landed_cost_egp_mt,
    stress_classify,
    run_stress_test,
    normalize_shocks,
    parse_shock_percent_text,
    cbot_history_scenarios,
    suggested_cbot_shocks,
)
from .decision import (
    DECISION_ENGINE_VERSION,
    DECISION_ACTIONS,
    run_decision_engine,
    compute_decision,
)
from .validation import validate_single_inputs

__all__ = [name for name in globals() if not name.startswith("_")]

from .inventory import (
    base_commodity, effective_freight_egp_mt,
    build_daily_fifo_inventory, summarize_inventory_market,
    calculate_inventory_scenario, inventory_market_layer_metrics,
)

from .local_purchase import (
    LOCAL_EVAL_VERSION, import_parity_egp_mt, evaluate_local_purchase,
)

from .offers import OFFERS_ENGINE_VERSION, compare_offers

from .planning import PLANNING_ENGINE_VERSION, stock_cover_plan

from .targets import TARGETS_ENGINE_VERSION, evaluate_target, suggest_ladder

from .market_signals import (
    SIGNALS_ENGINE_VERSION, CFTC_CODES, parse_cot_rows, cot_signal, parse_nass_condition,
    crop_condition_signal, wasde_signal, deferred_contract, curve_signal, trend_signal,
    seasonality, seasonal_signal, combine_signals, report_calendar,
)

from .budget import (
    BUDGET_ENGINE_VERSION, budget_year_of, budget_year_label, budget_year_range, budget_vs_actual,
)
