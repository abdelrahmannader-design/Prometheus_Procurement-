from __future__ import annotations

import datetime as dt
import math
import unittest

from prometheus_core import (
    evaluate_target,
    suggest_ladder,
    stock_cover_plan,
    compare_offers,
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

    def test_flat_price_deal_is_stressed_on_price_and_fx(self):
        res = run_stress_test({"commodity": "SFM", "flat_price_usd_mt": 290.0, "fx": 50.0,
                               "qty_mt": 1000.0, "local_egp_mt": 16000.0, "fees_egp_mt": 650.0,
                               "cbot_shocks_custom": (-0.1, 0.1), "fx_shocks_custom": (0.05,)})
        self.assertIsNone(res["error"])
        self.assertTrue(res["flat_price"])
        self.assertAlmostEqual(res["base"]["saving_egp_mt"], 16000 - (290 * 50 + 650))
        worst = min(res["rows"], key=lambda r: r["saving_egp_mt"])
        self.assertAlmostEqual(worst["saving_egp_mt"], round(16000 - (290 * 1.1 * 52.5 + 650), 2))

    def test_fixed_flat_price_only_stresses_fx(self):
        res = run_stress_test({"commodity": "SFM", "flat_price_usd_mt": 290.0, "fx": 50.0,
                               "qty_mt": 1000.0, "local_egp_mt": 16000.0, "fees_egp_mt": 650.0,
                               "cbot_locked": True})
        self.assertEqual(res["cbot_shocks_used"], (0.0,))

    def test_locked_cbot_ignores_custom_cbot_shocks(self):
        res = run_stress_test({**self.inputs, "cbot_locked": True, "cbot_shocks_custom": (-0.3, 0.3)})
        self.assertEqual(res["cbot_shocks_used"], (0.0,))


class OfferComparisonTests(unittest.TestCase):
    shared = {"commodity": "CORN", "cbot": 445.0, "fx": 51.5, "interest_rate_pct": 24, "local_egp_mt": 15000}

    def test_ranking_and_landed_cost(self):
        res = compare_offers(self.shared, [
            {"name": "A", "premium": 175, "freight_egp_mt": 485, "intake_egp_mt": 235, "qty_mt": 3000},
            {"name": "B", "premium": 165, "freight_egp_mt": 485, "intake_egp_mt": 320, "payment_days": 60},
            {"name": "C", "price_type": "FLAT", "flat_cif": 240, "freight_egp_mt": 300,
             "intake_egp_mt": 235, "quality_adj_egp_mt": 150},
        ])
        by = {r["name"]: r for r in res["rows"]}
        self.assertAlmostEqual(by["A"]["landed_egp_mt"], (445 + 175) * 0.3937 * 51.5 + 720)
        self.assertAlmostEqual(by["B"]["landed_egp_mt"],
                               (445 + 165) * 0.3937 * (1 + 0.24 * 60 / 360) * 51.5 + 805)
        self.assertEqual([r["name"] for r in res["rows"]], ["C", "A", "B"])
        self.assertEqual(res["best"]["name"], "C")

    def test_price_to_match_best_really_matches(self):
        res = compare_offers(self.shared, [
            {"name": "A", "premium": 175, "freight_egp_mt": 485},
            {"name": "B", "premium": 150, "freight_egp_mt": 600, "payment_days": 30}])
        worse = [r for r in res["rows"] if r["rank"] == 2][0]
        again = compare_offers(self.shared, [{"name": "X", "premium": worse["match_best_price"],
                                              "freight_egp_mt": worse["fees_egp_mt"],
                                              "payment_days": worse["payment_days"]}])
        self.assertAlmostEqual(again["rows"][0]["landed_egp_mt"], res["best"]["landed_egp_mt"])

    def test_direct_or_indirect_intake_only_the_chosen_one(self):
        base = {"premium": 175, "freight_egp_mt": 485, "intake_direct_egp_mt": 235,
                "intake_indirect_egp_mt": 365}
        res = compare_offers(self.shared, [{**base, "name": "D"}, {**base, "name": "I", "intake_mode": "INDIRECT"}])
        by = {r["name"]: r for r in res["rows"]}
        self.assertEqual(by["D"]["intake_egp_mt"], 235)
        self.assertEqual(by["I"]["intake_egp_mt"], 365)
        self.assertAlmostEqual(by["I"]["landed_egp_mt"] - by["D"]["landed_egp_mt"], 130)

    def test_incomplete_offer_is_not_ranked(self):
        res = compare_offers(self.shared, [{"name": "No premium"}])
        self.assertIsNone(res["rows"][0]["rank"])
        self.assertIn("premium", res["rows"][0]["missing"])


class StockCoverPlanTests(unittest.TestCase):
    today = dt.date(2026, 9, 27)

    def test_dates_and_quantity(self):
        r = stock_cover_plan(30000, 500, [{"date": "2026-10-20", "qty_mt": 20000, "ref": "A"}],
                             today=self.today, horizon_days=180, lead_time_days=45, safety_days=15)
        # 50,000 MT at 500/day drops below 7,500 after 86 days, runs out after 101
        self.assertEqual(r["below_safety_date"], self.today + dt.timedelta(days=86))
        self.assertEqual(r["runout_date"], self.today + dt.timedelta(days=101))
        self.assertEqual(r["buy_by_date"], r["below_safety_date"] - dt.timedelta(days=45))
        self.assertAlmostEqual(r["qty_to_buy_mt"], 7500 - (50000 - 500 * 180))
        self.assertEqual(r["status"], "PLAN")

    def test_late_when_lead_time_no_longer_fits(self):
        r = stock_cover_plan(10000, 500, [], today=self.today, lead_time_days=45, safety_days=10)
        self.assertEqual(r["status"], "LATE")

    def test_covered_and_undated_arrivals_not_counted(self):
        r = stock_cover_plan(200000, 100, [{"date": None, "qty_mt": 5000, "ref": "X"}],
                             today=self.today, horizon_days=180)
        self.assertEqual(r["status"], "COVERED")
        self.assertEqual(len(r["undated_arrivals"]), 1)
        self.assertEqual(r["arrivals"], [])

    def test_no_rate(self):
        self.assertEqual(stock_cover_plan(1000, None)["status"], "NO_RATE")


class CbotTargetTests(unittest.TestCase):
    def test_buy_below_states(self):
        t = {"level": 440, "direction": "BUY_BELOW"}
        self.assertEqual(evaluate_target(t, 439)["state"], "HIT")
        self.assertEqual(evaluate_target(t, 444)["state"], "NEAR")      # within 1%
        self.assertEqual(evaluate_target(t, 460)["state"], "WAITING")
        self.assertEqual(evaluate_target({**t, "status": "DONE"}, 439)["state"], "DONE")

    def test_protect_above_is_hit_when_market_rises(self):
        t = {"level": 470, "direction": "PROTECT_ABOVE"}
        self.assertEqual(evaluate_target(t, 471)["state"], "HIT")
        self.assertEqual(evaluate_target(t, 450)["state"], "WAITING")

    def test_ladder_splits_quantity_exactly(self):
        ladder = suggest_ladder(445.25, 25000)
        buys = [l for l in ladder if l["direction"] == "BUY_BELOW"]
        self.assertAlmostEqual(sum(l["qty_mt"] for l in buys), 25000)
        self.assertTrue(all(l["level"] < 445.25 for l in buys))
        self.assertTrue(any(l["direction"] == "PROTECT_ABOVE" and l["level"] > 445.25 for l in ladder))
        self.assertEqual(suggest_ladder(None, 1000), [])


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
