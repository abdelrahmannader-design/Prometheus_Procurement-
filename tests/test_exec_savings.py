"""Executive import savings: history, open position and CBOT advantage."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.exec_savings import (
    REALIZED, cbot_fixing, check_against_market, clean_on_or_before, commodity_rollup, contract_history,
    kpis, position, possible_fixing_dates, potential)
from prometheus_core.timing_report import Series

D = dt.date
F = 0.3937


def draw(day, mt=500, cost=14000.0, local=14600.0):
    return {"date": D(2026, 9, day), "mt": mt, "cost_egp_mt": cost, "local_egp_mt": local,
            "local_price_date": f"2026-09-{day:02d}", "saving_vs_local_egp":
            (local - cost) * mt if None not in (local, cost) else None, "is_stale": False, "stale": 0}


class FixingTests(unittest.TestCase):
    def test_the_user_example_cif_285_premium_207_is_about_517(self):
        f = cbot_fixing({"cif_usd_mt": 285, "premium_cents": 207}, F, "CORN")
        self.assertAlmostEqual(f["value"], 285 / F - 207, places=6)
        self.assertAlmostEqual(f["value"], 516.9, places=1)
        self.assertEqual(f["label"], "Implied CBOT fixing")
        self.assertTrue(f["usable"])

    def test_sbm_uses_its_own_factor_and_unit(self):
        f = cbot_fixing({"cif_usd_mt": 409.39, "premium_cents": 79}, 1.1023, "SBM")
        self.assertAlmostEqual(f["value"], 409.39 / 1.1023 - 79, places=6)
        self.assertEqual(f["unit"], "$/short ton")

    def test_a_flat_price_has_no_fixing(self):
        f = cbot_fixing({"cif_usd_mt": 282, "premium_cents": 0}, None, "SFM")
        self.assertIsNone(f["value"])
        self.assertIn("flat price", f["flag"])

    def test_pricing_lots_give_the_actual_weighted_fixing(self):
        c = {"pricing_lots": [{"qty_mt": 1000, "cbot": 530}, {"qty_mt": 3000, "cbot": 526}]}
        f = cbot_fixing(c, F, "CORN")
        self.assertAlmostEqual(f["value"], (530 * 1000 + 526 * 3000) / 4000)
        self.assertEqual(f["source"], "pricing lots")

    def test_an_absurd_fixing_is_flagged_not_used(self):
        """A premium far too large leaves corn's implied CBOT below any real price."""
        f = cbot_fixing({"cif_usd_mt": 250, "premium_cents": 600}, F, "CORN")
        self.assertFalse(f["usable"])
        self.assertIn("check the premium", f["flag"])

    def test_a_fixing_the_market_never_traded_near_is_flagged(self):
        """A premium typed in USD/MT (80) gives 555 ¢ while corn traded 440–460."""
        h = Series([(D(2026, 8, 1) + dt.timedelta(days=i), 440.0 + (i % 20)) for i in range(60)])
        f = cbot_fixing({"cif_usd_mt": 250, "premium_cents": 80}, F, "CORN")
        self.assertIn("check the premium", check_against_market(f["value"], h, "2026-09-29"))
        self.assertEqual(check_against_market(450.0, h, "2026-09-29"), "")

    def test_possible_dates_are_the_closest_matches_only(self):
        h = Series([(D(2026, 8, 1) + dt.timedelta(days=i), 500.0 + i) for i in range(30)])
        found = possible_fixing_dates(h, 517.0, "2026-08-30")
        self.assertEqual(found[0]["date"], "2026-08-18")
        self.assertLessEqual(len(found), 3)


class HistoryTests(unittest.TestCase):
    def test_daily_local_saving_is_price_less_cost_times_tonnes(self):
        h = contract_history([draw(1), draw(2, local=14200.0)])
        self.assertAlmostEqual(h["saving_egp"], 600 * 500 + 200 * 500)
        self.assertAlmostEqual(h["local_wavg"], (14600 + 14200) / 2)
        self.assertEqual((h["first_date"], h["last_date"]), ("2026-09-01", "2026-09-02"))

    def test_the_saving_percentage_is_against_what_local_would_have_cost(self):
        h = contract_history([draw(1)])
        self.assertAlmostEqual(h["saving_pct"], 600 / 14600 * 100)

    def test_a_day_without_a_local_price_is_counted_as_consumed_not_saved(self):
        h = contract_history([draw(1), draw(2, local=None)])
        self.assertAlmostEqual(h["consumed_mt"], 1000)
        self.assertAlmostEqual(h["unpriced_mt"], 500)
        self.assertAlmostEqual(h["saving_egp"], 600 * 500)

    def test_the_recorded_cost_replaces_the_draw_cost(self):
        """A contract's recorded landed cost wins over the FIFO estimate."""
        h = contract_history([draw(1, cost=12000.0), draw(2, cost=12000.0)], cost=14100.0)
        self.assertAlmostEqual(h["saving_egp"], (14600 - 14100) * 1000)
        self.assertAlmostEqual(h["landed_egp_mt"], 14100.0)

    def test_the_user_example_cbot_540_against_517_on_500_mt(self):
        hist = Series([(D(2026, 9, 1), 540.0)])
        h = contract_history([draw(1)], fixing=517.0, factor=F, fx=50.0, history=hist)
        day = h["daily"][0]
        self.assertAlmostEqual(day["cbot_diff"], 23.0)
        self.assertAlmostEqual(day["adv_usd_mt"], 9.0551)
        self.assertAlmostEqual(day["adv_usd"], 4527.55)
        self.assertAlmostEqual(h["adv_egp"], 4527.55 * 50.0)

    def test_the_advantage_is_weighted_by_the_tonnes_of_each_day(self):
        hist = Series([(D(2026, 9, 1), 520.0), (D(2026, 9, 2), 540.0)])
        h = contract_history([draw(1, mt=100), draw(2, mt=300)], fixing=517.0, factor=F, history=hist)
        self.assertAlmostEqual(h["cbot_wavg"], (520 * 100 + 540 * 300) / 400)
        self.assertAlmostEqual(h["adv_usd"], (3 * 100 + 23 * 300) * F)

    def test_a_stray_one_day_cbot_print_is_stepped_over(self):
        hist = Series([(D(2026, 9, 1), 500.0), (D(2026, 9, 2), 560.0), (D(2026, 9, 3), 501.0)])
        v, d = clean_on_or_before(hist, D(2026, 9, 2), hist.spikes())
        self.assertEqual((v, d), (500.0, D(2026, 9, 1)))


class PositionTests(unittest.TestCase):
    def test_the_tonnes_are_split_once(self):
        p = position(5000, 5000, 3500, 1500)
        self.assertEqual((p["outstanding_mt"], p["unreconciled_mt"]), (0, 0))

    def test_an_undelivered_contract_is_all_outstanding(self):
        p = position(4000, 0, 0, 0)
        self.assertEqual(p["outstanding_mt"], 4000)

    def test_a_gap_between_delivered_and_accounted_is_shown(self):
        self.assertEqual(position(5000, 5000, 3000, 1000)["unreconciled_mt"], 1000)

    def test_potential_is_todays_local_less_todays_landed_cost(self):
        self.assertEqual(potential(1500, 14500, 14000), {"saving_egp_mt": 500, "saving_egp": 750000})
        self.assertEqual(potential(1500, None, 14000)["saving_egp"], None)


class RollupTests(unittest.TestCase):
    def rows(self):
        return [
            {"base": "CORN", "saving_kind": REALIZED, "is_open": False, "contract_value_usd": 1,
             "history": {"consumed_mt": 1000, "local_priced_mt": 1000, "saving_egp": 600000,
                         "local_wavg": 14600, "adv_usd": 9000, "adv_egp": 450000, "cbot_mt": 1000},
             "open": {"in_stock_mt": 0, "outstanding_mt": 0, "stock_saving_egp": 0,
                      "outstanding_saving_egp": 0, "potential_priced_mt": 0}},
            {"base": "CORN", "saving_kind": "Provisional (CIF not final)", "is_open": True,
             "contract_value_usd": 500000,
             "history": {"consumed_mt": 500, "local_priced_mt": 500, "saving_egp": -100000,
                         "local_wavg": 14000},
             "open": {"in_stock_mt": 1500, "outstanding_mt": 0, "stock_saving_egp": 750000,
                      "outstanding_saving_egp": 0, "potential_priced_mt": 1500,
                      "open_value_usd": 375000}},
        ]

    def test_commodity_figures_are_sums_of_the_contracts(self):
        corn = commodity_rollup(self.rows())[0]
        self.assertEqual(corn["historical_saving_egp"], 500000)
        self.assertEqual(corn["realized_saving_egp"], 600000)
        self.assertEqual(corn["provisional_saving_egp"], -100000)
        self.assertEqual(corn["potential_saving_egp"], 750000)

    def test_cbot_advantage_is_never_added_to_the_savings(self):
        k = kpis(self.rows(), commodity_rollup(self.rows()))
        self.assertEqual(k["combined_benefit_egp"], 500000 + 750000)
        self.assertEqual(k["cbot_adv_egp"], 450000)

    def test_the_weighted_saving_divides_by_the_tonnes_priced(self):
        k = kpis(self.rows(), commodity_rollup(self.rows()))
        self.assertAlmostEqual(k["weighted_saving_egp_mt"], 1250000 / 3000)

    def test_open_figures_come_from_open_contracts_only(self):
        k = kpis(self.rows(), commodity_rollup(self.rows()))
        self.assertEqual((k["open_contracts"], k["open_in_stock_mt"], k["open_value_usd"]), (1, 1500, 375000))


if __name__ == "__main__":
    unittest.main()
