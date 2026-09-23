from __future__ import annotations

import datetime as dt
import math
import unittest

from prometheus_core import (
    cbot_history_scenarios,
    evaluate_local_purchase,
    import_parity_egp_mt,
    normalize_shocks,
    parse_shock_percent_text,
    run_stress_test,
    suggested_cbot_shocks,
)


class LocalPurchaseEvaluationTests(unittest.TestCase):
    def test_import_parity_formula(self):
        # (450 + 100) × 0.3937 × 50 + 800 = 11,626.75
        self.assertAlmostEqual(import_parity_egp_mt(450, 100, 0.3937, 50, 800), 11626.75)

    def test_import_parity_includes_finance_carry(self):
        base = (450 + 100) * 0.3937
        expected = base * (1 + 0.22 * 30 / 360) * 50 + 800
        self.assertAlmostEqual(import_parity_egp_mt(450, 100, 0.3937, 50, 800, 30, 22), expected)

    def test_import_parity_missing_input_is_none(self):
        self.assertIsNone(import_parity_egp_mt(None, 100, 0.3937, 50, 800))
        self.assertIsNone(import_parity_egp_mt(450, 100, 0.3937, 50, None))

    def test_local_cheaper_and_at_market_is_good_decision(self):
        ev = evaluate_local_purchase(12000, 1000, import_parity=12500, market_price=12100)
        self.assertEqual(ev["vs_import_egp_mt"], -500)
        self.assertEqual(ev["saving_vs_import_total_egp"], 500000)
        self.assertEqual(ev["source_verdict"], "✔ LOCAL CHEAPER")
        self.assertEqual(ev["price_verdict"], "✔ AT/BELOW MARKET")
        self.assertEqual(ev["overall_verdict"], "✔ GOOD DECISION")

    def test_import_cheaper_is_poor_decision(self):
        ev = evaluate_local_purchase(13000, 1000, import_parity=12500, market_price=13000)
        self.assertEqual(ev["source_verdict"], "✘ IMPORT CHEAPER")
        self.assertEqual(ev["overall_verdict"], "✘ POOR DECISION")

    def test_within_threshold_is_acceptable(self):
        ev = evaluate_local_purchase(12550, 1000, import_parity=12500, market_price=12500,
                                     threshold_egp_mt=200)
        self.assertEqual(ev["source_verdict"], "⚠ ABOUT EQUAL")
        self.assertEqual(ev["price_verdict"], "⚠ SLIGHTLY ABOVE MARKET")
        self.assertEqual(ev["overall_verdict"], "⚠ ACCEPTABLE")

    def test_non_cbot_commodity_judged_on_price_only(self):
        ev = evaluate_local_purchase(16900, 800, import_parity=None, market_price=16750)
        self.assertEqual(ev["source_verdict"], "— no import parity")
        self.assertEqual(ev["overall_verdict"], "⚠ CHECK PRICE")


class StressShockSettingsTests(unittest.TestCase):
    inputs = {
        "commodity": "CORN", "cbot": 450.0, "fx": 50.0, "premium_cents": 100.0,
        "qty_mt": 1000.0, "local_egp_mt": 14000.0, "fees_egp_mt": 800.0,
        "premium_locked": True,
    }

    def test_percent_text_is_parsed_and_base_added(self):
        self.assertEqual(parse_shock_percent_text("-10, -5, 5, 10%"), (-0.1, -0.05, 0.0, 0.05, 0.1))
        self.assertIsNone(parse_shock_percent_text(""))
        self.assertEqual(normalize_shocks([0.2, "0.2", None]), (0.0, 0.2))

    def test_custom_shocks_drive_the_grid(self):
        res = run_stress_test({**self.inputs, "cbot_shocks_custom": (-0.2, 0.15),
                               "fx_shocks_custom": (0.1,)})
        self.assertEqual(res["cbot_shocks_used"], (-0.2, 0.0, 0.15))
        self.assertEqual(res["fx_shocks_used"], (0.0, 0.1))
        self.assertEqual(len(res["rows"]), 6)
        worst = min(res["rows"], key=lambda r: r["saving_egp_mt"])
        self.assertEqual((worst["cbot_shock"], worst["fx_shock"]), (0.15, 0.1))

    def test_default_shocks_unchanged_without_settings(self):
        res = run_stress_test(self.inputs)
        self.assertEqual(res["cbot_shocks_used"], (-0.05, 0.0, 0.05, 0.10))
        self.assertEqual(res["fx_shocks_used"], (-0.03, 0.0, 0.03, 0.05, 0.10))

    def test_locked_cbot_ignores_custom_cbot_shocks(self):
        res = run_stress_test({**self.inputs, "cbot_locked": True, "cbot_shocks_custom": (-0.3, 0.3)})
        self.assertEqual(res["cbot_shocks_used"], (0.0,))


class CbotHistoryScenarioTests(unittest.TestCase):
    def _series(self):
        start = dt.date(2025, 9, 1)
        return [((start + dt.timedelta(days=i)).isoformat(), 400 + 50 * math.sin(i / 30.0))
                for i in range(380)]

    def test_levels_and_dates_come_from_history(self):
        series = self._series()
        hist = cbot_history_scenarios(series, 420.0, 30, today=dt.date(2026, 9, 15))
        last12 = [v for d, v in series if d >= "2025-09-15"]
        self.assertAlmostEqual(hist["low_12m"], min(last12))
        self.assertAlmostEqual(hist["high_12m"], max(last12))
        names = [s["name"] for s in hist["scenarios"]]
        self.assertIn("CBOT at 12-month low", names)
        self.assertIn("Worst 30-day rise repeats", names)
        hi = next(s for s in hist["scenarios"] if s["name"] == "CBOT at 12-month high")
        self.assertAlmostEqual(hi["shock"], hi["cbot"] / 420.0 - 1.0, places=5)
        self.assertLess(hist["worst_fall_pct"], 0)
        self.assertGreater(hist["worst_rise_pct"], 0)

    def test_suggested_shocks_include_base_and_extremes(self):
        hist = cbot_history_scenarios(self._series(), 420.0, 30, today=dt.date(2026, 9, 15))
        shocks = suggested_cbot_shocks(hist)
        self.assertIn(0.0, shocks)
        self.assertLess(shocks[0], 0)
        self.assertGreater(shocks[-1], 0)

    def test_no_history_returns_empty(self):
        self.assertEqual(cbot_history_scenarios([], 420.0), {})
        self.assertIsNone(suggested_cbot_shocks({}))


if __name__ == "__main__":
    unittest.main()
