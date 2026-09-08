"""App-level tests for the Scenario Lab computation engine
(_scenario_default_inputs / _scenario_compute in Prometheus_V10_8_15.py).
Run via: python -m unittest discover -s tests
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter  # noqa: F401
    _HAS_TK = True
except Exception:
    _HAS_TK = False

from _app_test_helpers import start_isolated_app


@unittest.skipUnless(_HAS_TK, "tkinter not available in this environment")
class TestScenarioLab(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import Prometheus_V10_8_15 as P
        cls.P = P
        cls.app, cls._tmp_dir, cls._restore = start_isolated_app(P)

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()
        cls._restore()

    def setUp(self):
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "CORN", "status": "Closed",
                  "qty_mt": 5000, "delivery_date": "2026-06-01",
                  "cif_usd_mt": 260.0, "delivery_fx": 50.0},
            "B": {"name": "B", "commodity": "CORN", "status": "Open",
                  "qty_mt": 4000, "delivery_date": "2026-07-01",
                  "cif_usd_mt": 280.0, "delivery_fx": 50.0,
                  "premium_cents": 80.0, "pricing_date": "2026-07-01"},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-07-15", "commodity": "CORN", "consumed_mt": 6000}]
        self.app.state_obj["local_prices"] = [
            {"date": "2026-08-01", "commodity": "CORN", "price_egp_mt": 15000,
             "transport_egp_mt": 0}]
        self.app.state_obj["cbot_history"] = [
            {"date": "2026-08-01", "commodity": "CORN", "price": 450.0}]
        self.app.state_obj["fx_history"] = [{"date": "2026-08-01", "rate": 50.0}]
        self.app.state_obj["scenarios"] = {}

    def test_default_inputs_mirror_current_market(self):
        defaults = self.app._scenario_default_inputs("CORN")
        self.assertEqual(defaults["cbot"], 450.0)
        self.assertEqual(defaults["fx"], 50.0)
        self.assertEqual(defaults["premium"], 80.0)
        self.assertEqual(defaults["local_price"], 15000.0)

    def test_unchanged_scenario_reflects_current_case(self):
        defaults = self.app._scenario_default_inputs("CORN")
        result = self.app._scenario_compute("CORN", defaults)
        self.assertEqual(result["current"]["remaining_mt"], 3000.0)
        self.assertEqual(result["scenario"]["projected_inventory_mt"], 3000.0)

    def test_changing_cbot_changes_scenario_purchase_cost_only(self):
        defaults = self.app._scenario_default_inputs("CORN")
        base = self.app._scenario_compute("CORN", defaults)
        bumped = dict(defaults)
        bumped["cbot"] = defaults["cbot"] + 50
        result = self.app._scenario_compute("CORN", bumped)
        self.assertGreater(result["scenario"]["purchase_cost_egp_mt"],
                            base["scenario"]["purchase_cost_egp_mt"])
        # Current case must be completely unaffected by scenario inputs.
        self.assertEqual(result["current"], base["current"])

    def test_new_contract_price_overrides_formula_cost(self):
        defaults = self.app._scenario_default_inputs("CORN")
        inputs = dict(defaults)
        inputs["new_contract_price"] = 12000.0
        result = self.app._scenario_compute("CORN", inputs)
        self.assertEqual(result["scenario"]["purchase_cost_egp_mt"], 12000.0)
        # The formula-based figure is still reported for reference.
        self.assertIsNotNone(result["scenario"]["formula_purchase_cost_egp_mt"])
        self.assertNotEqual(result["scenario"]["formula_purchase_cost_egp_mt"], 12000.0)

    def test_saving_per_mt_and_total_impact(self):
        defaults = self.app._scenario_default_inputs("CORN")
        inputs = dict(defaults)
        inputs["new_contract_price"] = 13000.0
        inputs["purchase_qty"] = 1500
        result = self.app._scenario_compute("CORN", inputs)
        # local (15000) - purchase cost (13000) = 2000 saving/MT
        self.assertAlmostEqual(result["scenario"]["saving_per_mt"], 2000.0)
        self.assertAlmostEqual(result["scenario"]["total_impact_egp"], 2000.0 * 1500)

    def test_projected_inventory_nets_consumption_and_purchase(self):
        defaults = self.app._scenario_default_inputs("CORN")
        inputs = dict(defaults)
        inputs["consumption_qty"] = 1000
        inputs["purchase_qty"] = 2500
        result = self.app._scenario_compute("CORN", inputs)
        # current remaining 3000 - 1000 + 2500 = 4500
        self.assertAlmostEqual(result["scenario"]["projected_inventory_mt"], 4500.0)
        self.assertFalse(result["scenario"]["projected_shortfall"])

    def test_projected_shortfall_flagged_and_floored_at_zero(self):
        defaults = self.app._scenario_default_inputs("CORN")
        inputs = dict(defaults)
        inputs["consumption_qty"] = 10000  # far more than remaining 3000
        inputs["purchase_qty"] = 0
        result = self.app._scenario_compute("CORN", inputs)
        self.assertTrue(result["scenario"]["projected_shortfall"])
        self.assertEqual(result["scenario"]["projected_inventory_mt"], 0.0)

    def test_coverage_days_from_horizon_and_consumption_rate(self):
        defaults = self.app._scenario_default_inputs("CORN")
        inputs = dict(defaults)
        inputs["consumption_qty"] = 1000
        inputs["consumption_horizon_days"] = 30
        inputs["purchase_qty"] = 2000
        result = self.app._scenario_compute("CORN", inputs)
        # projected = 3000 - 1000 + 2000 = 4000; rate = 1000/30
        self.assertAlmostEqual(result["scenario"]["coverage_days"], 4000.0 / (1000.0 / 30.0))

    def test_freight_all_in_mode_matches_detailed_equivalent(self):
        defaults = self.app._scenario_default_inputs("CORN")
        detailed = dict(defaults)
        detailed["freight_mode"] = "detailed"
        detailed["freight_base"] = 400.0
        detailed["freight_vat_pct"] = 14.0
        result_detailed = self.app._scenario_compute("CORN", detailed)

        all_in = dict(defaults)
        all_in["freight_mode"] = "all_in"
        all_in["freight_base"] = 456.0
        result_all_in = self.app._scenario_compute("CORN", all_in)

        self.assertAlmostEqual(result_detailed["scenario"]["freight_egp_mt"],
                                result_all_in["scenario"]["freight_egp_mt"])
        self.assertAlmostEqual(result_all_in["scenario"]["freight_egp_mt"], 456.0)

    def test_scenario_compute_never_mutates_state(self):
        import json
        before = json.dumps(self.app.state_obj, sort_keys=True, default=str)
        defaults = self.app._scenario_default_inputs("CORN")
        for _ in range(5):
            self.app._scenario_compute("CORN", defaults)
        after = json.dumps(self.app.state_obj, sort_keys=True, default=str)
        self.assertEqual(before, after)

    def test_scenario_compute_does_not_mutate_input_dict(self):
        defaults = self.app._scenario_default_inputs("CORN")
        before = copy.deepcopy(defaults)
        self.app._scenario_compute("CORN", defaults)
        self.assertEqual(defaults, before)


if __name__ == "__main__":
    unittest.main()
