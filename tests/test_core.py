from __future__ import annotations

import math
import unittest

from prometheus_core import (
    CORN_FACTOR,
    cbot_conv_factor,
    cbot_to_usd_mt,
    carry_usd_mt,
    compute_decision,
    run_decision_engine,
    run_stress_test,
    stress_classify,
    validate_single_inputs,
)


class CbotTests(unittest.TestCase):
    def test_suffix_uses_base_commodity_factor(self):
        self.assertEqual(cbot_conv_factor("corn-brz", strict=True), CORN_FACTOR)

    def test_unknown_strict_is_rejected(self):
        self.assertIsNone(cbot_conv_factor("SFM", strict=True))

    def test_finance_verified_corn_conversion(self):
        meta = {"type": "CBOT", "locked_factor": CORN_FACTOR}
        self.assertAlmostEqual(cbot_to_usd_mt(meta, 450, 25), 475 * CORN_FACTOR, places=8)

    def test_finance_carry_uses_360_day_year(self):
        self.assertAlmostEqual(carry_usd_mt(200, 90, 12), 6.0, places=8)


class StressTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {
            "commodity": "CORN",
            "cbot": 450,
            "fx": 50,
            "premium_cents": 25,
            "qty_mt": 10_000,
            "local_egp_mt": 11_000,
            "fees_egp_mt": 500,
        }

    def test_open_deal_has_100_feasible_scenarios(self):
        result = run_stress_test(self.inputs)
        self.assertIsNone(result["error"])
        self.assertEqual(len(result["rows"]), 100)
        expected = 11_000 - ((450 + 25) * CORN_FACTOR * 50 + 500)
        self.assertAlmostEqual(result["base"]["saving_egp_mt"], round(expected, 2), places=2)

    def test_locked_dimensions_reduce_grid(self):
        result = run_stress_test({**self.inputs, "premium_locked": True, "cbot_locked": True})
        self.assertEqual(len(result["rows"]), 5)

    def test_missing_data_is_explicit(self):
        result = run_stress_test({"commodity": "CORN"})
        self.assertEqual(result["resilience"], "Unavailable")
        self.assertIn("FX (must be > 0)", result["missing"])

    def test_classification_boundaries(self):
        self.assertEqual(stress_classify(-250), "Material Loss")
        self.assertEqual(stress_classify(0), "Marginal")
        self.assertEqual(stress_classify(500), "Strong Advantage")


class DecisionTests(unittest.TestCase):
    def test_clear_loss_recommends_local(self):
        result = run_decision_engine({
            "commodity": "CORN",
            "cbot": 500,
            "fx": 55,
            "premium_cents": 50,
            "qty_mt": 1_000,
            "local_egp_mt": 10_000,
            "fees_egp_mt": 1_000,
        })
        self.assertEqual(result["action"], "BUY_LOCAL")

    def test_missing_inputs_never_create_fake_recommendation(self):
        result = run_decision_engine({"commodity": "CORN"})
        self.assertEqual(result["action"], "INSUFFICIENT_DATA")
        self.assertEqual(result["confidence"], 0)

    def test_full_pricing_cannot_recommend_another_tranche(self):
        result = run_decision_engine({
            "commodity": "CORN",
            "cbot": 400,
            "fx": 45,
            "premium_cents": 10,
            "qty_mt": 1_000,
            "local_egp_mt": 12_000,
            "fees_egp_mt": 300,
            "pct_priced": 100,
        })
        self.assertEqual(result["action"], "WAIT")


class CalculationTests(unittest.TestCase):
    def test_cbot_landed_cost_and_intake(self):
        result = compute_decision({
            "comm_meta": {"type": "CBOT", "locked_factor": CORN_FACTOR},
            "cbot": 450,
            "premium_usd_mt": 25,
            "fx": 50,
            "qty_mt": 1_000,
            "finance_days": 90,
            "interest_rate": 12,
            "local_egp_mt": 11_000,
            "supplier_direct_egp_mt": 300,
            "supplier_indirect_egp_mt": 500,
        })
        import_usd = 475 * CORN_FACTOR
        carry = import_usd * 0.12 * 90 / 360
        self.assertAlmostEqual(result["import_usd_mt"], import_usd, places=8)
        self.assertAlmostEqual(result["carry_usd_mt"], carry, places=8)
        self.assertAlmostEqual(result["direct_own_after_egp_mt"], (import_usd + carry) * 50 + 300, places=8)

    def test_non_cbot_egp_input_requires_fx(self):
        result = compute_decision({
            "comm_meta": {"type": "NONCBOT"},
            "import_egp_mt": 9_000,
        })
        self.assertEqual(result["error"], "FX required to convert EGP→USD")


class ValidationTests(unittest.TestCase):
    def test_rejects_invalid_interest(self):
        ok, message = validate_single_inputs(
            {"type": "CBOT"},
            {"fx": 50, "cbot": 450, "premium_usd_mt": 0, "interest_rate": 101},
        )
        self.assertFalse(ok)
        self.assertIn("between 0 and 100", message)

    def test_accepts_valid_cbot_inputs(self):
        ok, message = validate_single_inputs(
            {"type": "CBOT"},
            {"fx": 50, "cbot": 450, "premium_usd_mt": 0, "qty_mt": 1_000},
        )
        self.assertTrue(ok, message)


if __name__ == "__main__":
    unittest.main()
