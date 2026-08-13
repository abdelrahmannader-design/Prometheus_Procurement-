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
)
from .decision import (
    DECISION_ENGINE_VERSION,
    DECISION_ACTIONS,
    run_decision_engine,
    compute_decision,
)
from .validation import validate_single_inputs

__all__ = [name for name in globals() if not name.startswith("_")]
