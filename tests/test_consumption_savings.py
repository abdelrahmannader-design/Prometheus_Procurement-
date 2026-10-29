"""Savings judged tonne by tonne, on the day each tonne was consumed."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.consumption_savings import (consumption_draws,
                                                 nearest_on_or_before,
                                                 savings_report,
                                                 series_from_rows, value_draws)

D = dt.date
LOTS = [
    {"lot_id": "A", "contract_ref": "Dec corn", "commodity": "CORN",
     "delivery_date": "2026-09-01", "original_mt": 2000, "cost_egp_mt": 14000.0},
    {"lot_id": "B", "contract_ref": "Oct corn", "commodity": "CORN",
     "delivery_date": "2026-10-01", "original_mt": 2000, "cost_egp_mt": 14800.0},
]
EVENTS = [
    {"date": "2026-09-10", "commodity": "CORN", "consumed_mt": 1500},
    {"date": "2026-10-10", "commodity": "CORN", "consumed_mt": 1000},
]
LOCAL = {D(2026, 9, 10): 14500.0, D(2026, 10, 10): 14600.0}
CBOT = {D(2026, 9, 10): 480.0, D(2026, 10, 10): 465.0}
FX = {D(2026, 9, 10): 52.0, D(2026, 10, 10): 54.3}


def report(**over):
    args = dict(lots=LOTS, events=EVENTS, commodity="CORN", local_series=LOCAL,
                cbot_series=CBOT, fx_series=FX, basis_for=lambda d: 190.0)
    args.update(over)
    return savings_report(**args)


class DrawTests(unittest.TestCase):
    def test_consumption_comes_out_oldest_layer_first(self):
        draws = consumption_draws(LOTS, EVENTS, "CORN")
        self.assertEqual([d["contract_ref"] for d in draws],
                         ["Dec corn", "Dec corn", "Oct corn"])

    def test_a_draw_splits_across_layers_when_one_runs_out(self):
        """1,000 MT against 500 left on the old layer and 2,000 on the new."""
        draws = consumption_draws(LOTS, EVENTS, "CORN")
        october = [d for d in draws if d["date"] == D(2026, 10, 10)]
        self.assertEqual([d["mt"] for d in october], [500.0, 500.0])
        self.assertEqual([d["cost_egp_mt"] for d in october], [14000.0, 14800.0])

    def test_a_layer_cannot_supply_a_tonne_before_it_landed(self):
        draws = consumption_draws(
            LOTS, [{"date": "2026-09-05", "commodity": "CORN", "consumed_mt": 100}],
            "CORN")
        self.assertEqual(draws[0]["contract_ref"], "Dec corn")
        self.assertTrue(all(d["landed"] <= "2026-09-05" for d in draws))

    def test_consuming_more_than_was_received_is_reported_not_dropped(self):
        draws = consumption_draws(
            LOTS, [{"date": "2026-11-01", "commodity": "CORN", "consumed_mt": 9000}],
            "CORN")
        unsourced = [d for d in draws if d["contract_ref"] == "(unsourced)"]
        self.assertEqual(len(unsourced), 1)
        self.assertAlmostEqual(unsourced[0]["mt"], 5000.0)
        self.assertAlmostEqual(sum(d["mt"] for d in draws), 9000.0)

    def test_physical_counts_are_not_consumption(self):
        draws = consumption_draws(
            LOTS, [{"date": "2026-09-10", "commodity": "CORN",
                    "consumed_mt": 100, "is_adjustment": True}], "CORN")
        self.assertEqual(draws, [])

    def test_other_commodities_are_left_alone(self):
        draws = consumption_draws(
            LOTS, [{"date": "2026-09-10", "commodity": "SBM", "consumed_mt": 100}],
            "CORN")
        self.assertEqual(draws, [])

    def test_a_date_range_filters_the_draws(self):
        draws = consumption_draws(LOTS, EVENTS, "CORN", start="2026-10-01")
        self.assertTrue(all(d["date"] >= D(2026, 10, 1) for d in draws))


class PriceLookupTests(unittest.TestCase):
    def test_it_looks_backwards_never_forwards(self):
        """Valuing a tonne against a price that did not yet exist is wrong."""
        series = {D(2026, 9, 1): 100.0, D(2026, 9, 20): 200.0}
        value, when, age = nearest_on_or_before(series, D(2026, 9, 10))
        self.assertEqual((value, when, age), (100.0, D(2026, 9, 1), 9))

    def test_an_empty_series_yields_nothing(self):
        self.assertEqual(nearest_on_or_before({}, D(2026, 9, 10)), (None, None, None))

    def test_nothing_before_the_date_yields_nothing(self):
        self.assertEqual(
            nearest_on_or_before({D(2026, 9, 20): 1.0}, D(2026, 9, 10)),
            (None, None, None))

    def test_a_stale_reference_is_flagged_but_still_used(self):
        rows = value_draws(
            [{"date": D(2026, 9, 30), "commodity": "CORN", "mt": 10.0,
              "cost_egp_mt": 14000.0}],
            local_series={D(2026, 9, 1): 14500.0}, stale_days=7)
        self.assertTrue(rows[0]["is_stale"])
        self.assertAlmostEqual(rows[0]["saving_vs_local_egp_mt"], 500.0)

    def test_series_can_fold_transport_into_the_price(self):
        series = series_from_rows(
            [{"date": "2026-09-10", "commodity": "CORN",
              "price_egp_mt": 14000.0, "transport_egp_mt": 323.13}],
            commodity="CORN", extra="transport_egp_mt")
        self.assertAlmostEqual(series[D(2026, 9, 10)], 14323.13)


class ValuationTests(unittest.TestCase):
    def test_saving_vs_local_is_the_alternative_less_the_cost(self):
        row = report()["rows"][0]
        self.assertAlmostEqual(row["saving_vs_local_egp_mt"], 14500.0 - 14000.0)
        self.assertAlmostEqual(row["saving_vs_local_egp"], 500.0 * 1500)

    def test_saving_vs_cbot_uses_that_days_board_and_fx(self):
        row = report()["rows"][0]
        expected = (480.0 + 190.0) * 0.3937 * 52.0
        self.assertAlmostEqual(row["cbot_egp_mt"], expected, places=6)
        self.assertAlmostEqual(row["saving_vs_cbot_egp_mt"], expected - 14000.0,
                               places=6)

    def test_each_day_is_valued_at_its_own_market(self):
        """The whole point: one cargo, two days, two different answers."""
        rows = report()["rows"]
        september = rows[0]["cbot_egp_mt"]
        october = [r for r in rows if r["date"] == D(2026, 10, 10)][0]["cbot_egp_mt"]
        self.assertNotAlmostEqual(september, october, places=0)

    def test_totals_weight_by_tonnes_actually_consumed(self):
        total = report()["totals"]
        self.assertAlmostEqual(total["mt"], 2500.0)
        self.assertAlmostEqual(
            total["saving_vs_local_egp"],
            500.0 * 1500 + 600.0 * 500 + (-200.0) * 500)

    def test_the_per_tonne_average_divides_by_the_tonnes_it_could_price(self):
        """Dividing by every tonne would dilute it with unpriced rows."""
        # Consumed before any local price was logged, so this draw has a
        # cost but no alternative to compare it with.
        events = EVENTS + [{"date": "2026-09-02", "commodity": "CORN",
                            "consumed_mt": 500}]
        total = report(events=events)["totals"]
        self.assertLess(total["saving_vs_local_mt_priced"], total["mt"])
        self.assertAlmostEqual(
            total["saving_vs_local_egp_mt"],
            total["saving_vs_local_egp"] / total["saving_vs_local_mt_priced"])

    def test_a_missing_basis_leaves_the_cbot_leg_empty_not_zero(self):
        row = report(basis_for=None)["rows"][0]
        self.assertIsNone(row["cbot_egp_mt"])
        self.assertIsNone(row["saving_vs_cbot_egp_mt"])
        self.assertIsNotNone(row["saving_vs_local_egp_mt"])

    def test_an_unsourced_draw_has_no_cost_so_no_saving(self):
        rows = report(events=[{"date": "2026-11-01", "commodity": "CORN",
                               "consumed_mt": 9000}])["rows"]
        bad = [r for r in rows if r["contract_ref"] == "(unsourced)"][0]
        self.assertIsNone(bad["saving_vs_local_egp_mt"])


class RollupTests(unittest.TestCase):
    def test_days_and_contracts_both_add_back_to_the_total(self):
        rep = report()
        for bucket in ("by_day", "by_contract"):
            self.assertAlmostEqual(
                sum(g["saving_vs_local_egp"] for g in rep[bucket]),
                rep["totals"]["saving_vs_local_egp"], places=6)
            self.assertAlmostEqual(sum(g["mt"] for g in rep[bucket]),
                                   rep["totals"]["mt"], places=6)

    def test_one_contract_eaten_across_two_days_stays_one_contract_row(self):
        rep = report()
        dec = [g for g in rep["by_contract"] if g["key"] == "Dec corn"][0]
        self.assertEqual(dec["draws"], 2)
        self.assertAlmostEqual(dec["mt"], 2000.0)


if __name__ == "__main__":
    unittest.main()
