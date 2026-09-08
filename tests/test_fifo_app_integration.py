"""App-level integration tests for the FIFO inventory wiring
(_fifo_inventory_for_commodity / _fifo_replacement_cost in
Prometheus_V10_8_15.py). Run via: python -m unittest discover -s tests

Complements tests/test_fifo_inventory.py (which tests the pure engine in
prometheus_core.py in isolation) by exercising the real App against
state_obj shaped like actual contracts/consumption_log/local_prices data,
including the spec's own worked example.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    import tkinter  # noqa: F401
    _HAS_TK = True
except Exception:
    _HAS_TK = False


@unittest.skipUnless(_HAS_TK, "tkinter not available in this environment")
class TestFifoInventoryForCommodity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import Prometheus_V10_8_15 as P
        cls.P = P
        cls.app = P.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def setUp(self):
        # Each test gets a clean slate for these keys.
        self.app.state_obj["contracts"] = {}
        self.app.state_obj["consumption_log"] = []
        self.app.state_obj["local_prices"] = []
        self.app.state_obj["cbot_history"] = []
        self.app.state_obj["fx_history"] = []

    def test_spec_worked_example_end_to_end(self):
        # Contract A = 5,000 MT @ 13,000 EGP/MT (older), Contract B =
        # 4,000 MT @ 14,000 EGP/MT (newer). Consumption = 6,000 MT.
        self.app.state_obj["contracts"] = {
            "A": {"name": "Contract A", "commodity": "CORN", "status": "Closed",
                  "qty_mt": 5000, "delivery_date": "2026-01-01",
                  "cif_usd_mt": 13000 / 50.0, "delivery_fx": 50.0},
            "B": {"name": "Contract B", "commodity": "CORN", "status": "Open",
                  "qty_mt": 4000, "delivery_date": "2026-02-01",
                  "cif_usd_mt": 14000 / 50.0, "delivery_fx": 50.0},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-02-15", "commodity": "CORN", "consumed_mt": 6000},
        ]
        self.app.state_obj["local_prices"] = [
            {"date": "2026-02-20", "commodity": "CORN", "price_egp_mt": 15000,
             "transport_egp_mt": 0},
        ]

        result = self.app._fifo_inventory_for_commodity("CORN")
        lots = {lot["contract_id"]: lot for lot in result["lots"]}

        self.assertEqual(lots["A"]["remaining_mt"], 0)
        self.assertEqual(lots["B"]["remaining_mt"], 3000)
        self.assertEqual(result["remaining_mt"], 3000)
        # Weighted average must reflect only the surviving lot (14,000),
        # not a blend with the fully-consumed A.
        self.assertAlmostEqual(result["weighted_avg_cost_egp_mt"], 14000.0)
        self.assertAlmostEqual(result["edge_per_mt"], 1000.0)  # 15000 - 14000
        self.assertAlmostEqual(result["edge_total"], 3_000_000.0)
        self.assertEqual(result["unattributed_consumed_mt"], 0)

    def test_partial_consumption_leaves_partial_remaining(self):
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "CORN", "status": "Open",
                  "qty_mt": 5000, "delivery_date": "2026-01-01"},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-01-10", "commodity": "CORN", "consumed_mt": 1200},
        ]
        result = self.app._fifo_inventory_for_commodity("CORN")
        self.assertEqual(result["lots"][0]["remaining_mt"], 3800)

    def test_no_consumption_activity_does_not_silently_zero_inventory(self):
        # A commodity that's never been touched in the Consumption tab
        # must show its full contracted quantity, not a misleading 0 --
        # silence must never be read as "fully consumed".
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "WHEAT", "status": "Open",
                  "qty_mt": 2000, "delivery_date": "2026-01-01"},
        }
        result = self.app._fifo_inventory_for_commodity("WHEAT")
        self.assertEqual(result["remaining_mt"], 2000)
        self.assertFalse(result["has_log_activity"])

    def test_stock_count_adjustment_overrides_prior_layers(self):
        # A physical count of 1,000 MT as of 2026-02-01 is authoritative
        # for everything delivered by then; consumption logged after that
        # date applies on top of it.
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "CORN", "status": "Closed",
                  "qty_mt": 5000, "delivery_date": "2026-01-01"},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-02-01", "commodity": "CORN", "is_adjustment": True,
             "adjusted_qty": 1000},
            {"date": "2026-02-10", "commodity": "CORN", "consumed_mt": 300},
        ]
        result = self.app._fifo_inventory_for_commodity("CORN")
        self.assertEqual(result["remaining_mt"], 700)  # 1000 - 300

    def test_reconciliation_drilldown_lots_sum_to_commodity_total(self):
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "SBM", "status": "Closed",
                  "qty_mt": 3000, "delivery_date": "2026-01-01"},
            "B": {"name": "B", "commodity": "SBM", "status": "Open",
                  "qty_mt": 2000, "delivery_date": "2026-02-01"},
            "C": {"name": "C", "commodity": "SBM", "status": "Open",
                  "qty_mt": 1500, "delivery_date": "2026-03-01"},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-02-15", "commodity": "SBM", "consumed_mt": 4200},
        ]
        result = self.app._fifo_inventory_for_commodity("SBM")
        # This is the identity the dashboard-vs-drill-down reconciliation
        # depends on: the same dict's own lots must sum to its own total.
        self.assertEqual(sum(l["remaining_mt"] for l in result["lots"]),
                          result["remaining_mt"])

    def test_commodity_filtering_isolates_other_commodities(self):
        self.app.state_obj["contracts"] = {
            "A": {"name": "A", "commodity": "CORN", "status": "Open",
                  "qty_mt": 1000, "delivery_date": "2026-01-01"},
            "B": {"name": "B", "commodity": "SOYBEAN", "status": "Open",
                  "qty_mt": 2000, "delivery_date": "2026-01-01"},
        }
        self.app.state_obj["consumption_log"] = [
            {"date": "2026-01-10", "commodity": "CORN", "consumed_mt": 1000},
        ]
        corn = self.app._fifo_inventory_for_commodity("CORN")
        soy = self.app._fifo_inventory_for_commodity("SOYBEAN")
        self.assertEqual(corn["remaining_mt"], 0)
        self.assertEqual(soy["remaining_mt"], 2000)  # untouched by CORN's consumption


@unittest.skipUnless(_HAS_TK, "tkinter not available in this environment")
class TestFifoReplacementCost(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import Prometheus_V10_8_15 as P
        cls.app = P.App()
        cls.app.withdraw()

    @classmethod
    def tearDownClass(cls):
        cls.app.destroy()

    def setUp(self):
        self.app.state_obj["contracts"] = {}
        self.app.state_obj["cbot_history"] = []
        self.app.state_obj["fx_history"] = []

    def test_never_invents_a_missing_premium(self):
        self.app.state_obj["cbot_history"] = [
            {"date": "2026-06-01", "commodity": "CORN", "price": 450.0}]
        self.app.state_obj["fx_history"] = [
            {"date": "2026-06-01", "rate": 50.0}]
        result = self.app._fifo_replacement_cost("CORN")
        self.assertIsNone(result["premium"])
        self.assertIsNone(result["replacement_cost_egp_mt"])
        self.assertTrue(result["incomplete"])

    def test_uses_most_recent_contract_premium_when_no_override(self):
        self.app.state_obj["cbot_history"] = [
            {"date": "2026-06-01", "commodity": "CORN", "price": 450.0}]
        self.app.state_obj["fx_history"] = [
            {"date": "2026-06-01", "rate": 50.0}]
        self.app.state_obj["contracts"] = {
            "A": {"commodity": "CORN", "premium_cents": 80.0,
                  "pricing_date": "2026-05-01"},
            "B": {"commodity": "CORN", "premium_cents": 95.0,
                  "pricing_date": "2026-06-01"},  # most recent
        }
        result = self.app._fifo_replacement_cost("CORN")
        self.assertAlmostEqual(result["premium"], 95.0)
        self.assertFalse(result["incomplete"])
        expected_cif = (450.0 + 95.0) * 0.3937
        self.assertAlmostEqual(result["replacement_cif_usd_mt"], expected_cif)
        self.assertAlmostEqual(result["replacement_cost_egp_mt"], expected_cif * 50.0)

    def test_scenario_premium_override_takes_precedence(self):
        self.app.state_obj["cbot_history"] = [
            {"date": "2026-06-01", "commodity": "CORN", "price": 450.0}]
        self.app.state_obj["fx_history"] = [
            {"date": "2026-06-01", "rate": 50.0}]
        self.app.state_obj["contracts"] = {
            "A": {"commodity": "CORN", "premium_cents": 80.0, "pricing_date": "2026-05-01"},
        }
        result = self.app._fifo_replacement_cost("CORN", premium_override=120.0)
        self.assertAlmostEqual(result["premium"], 120.0)
        self.assertEqual(result["premium_source"], "scenario override")

    def test_wheat_marked_unsupported_no_cbot_feed(self):
        result = self.app._fifo_replacement_cost("WHEAT")
        self.assertFalse(result["cbot_supported"])
        self.assertTrue(result["incomplete"])


if __name__ == "__main__":
    unittest.main()
