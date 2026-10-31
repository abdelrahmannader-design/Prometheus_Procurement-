"""Savings judged tonne by tonne, on the day each tonne was consumed."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.inventory import build_daily_fifo_inventory
from prometheus_core.consumption_savings import (cargo_coverage,
                                                 draws_from_inventory,
                                                 consumption_draws,
                                                 nearest_on_or_before,
                                                 savings_report,
                                                 series_from_rows,
                                                 value_draws, within)

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

    def test_the_board_is_read_from_price_as_the_app_stores_it(self):
        """cbot_history rows are {date, price, commodity} — not close."""
        rows = [{"date": "2026-09-10", "commodity": "CORN", "price": 447.5},
                {"date": "2026-09-11", "commodity": "CORN", "close": 450.0}]
        series = series_from_rows(rows, value_key=("close", "price"),
                                  commodity="CORN")
        self.assertEqual(series, {D(2026, 9, 10): 447.5, D(2026, 9, 11): 450.0})

    def test_close_wins_when_a_row_carries_both(self):
        rows = [{"date": "2026-09-10", "commodity": "CORN",
                 "close": 450.0, "price": 449.0}]
        self.assertEqual(series_from_rows(rows, value_key=("close", "price")),
                         {D(2026, 9, 10): 450.0})

    def test_a_row_without_transport_takes_the_default(self):
        """Built like a local purchase: price + its transport, else the default."""
        rows = [{"date": "2026-09-10", "commodity": "CORN",
                 "price_egp_mt": 14000, "transport_egp_mt": 300},
                {"date": "2026-09-11", "commodity": "CORN", "price_egp_mt": 14100}]
        series = series_from_rows(rows, commodity="CORN",
                                  extra="transport_egp_mt", extra_default=323.13)
        self.assertEqual(series, {D(2026, 9, 10): 14300.0,
                                  D(2026, 9, 11): 14423.13})

    def test_a_stated_zero_transport_is_kept_not_defaulted(self):
        rows = [{"date": "2026-09-10", "price_egp_mt": 14000, "transport_egp_mt": 0}]
        self.assertEqual(series_from_rows(rows, extra="transport_egp_mt",
                                          extra_default=323.13),
                         {D(2026, 9, 10): 14000.0})

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

    def test_an_unsourced_draw_is_listed_apart_never_valued(self):
        rep = report(events=[{"date": "2026-11-01", "commodity": "CORN",
                              "consumed_mt": 9000}])
        self.assertFalse([r for r in rep["rows"] if r["contract_ref"] == "(unsourced)"])
        self.assertAlmostEqual(rep["unsourced_mt"], 9000 - 4000)
        self.assertAlmostEqual(rep["totals"]["mt"], 4000)


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


MIXED = [
    {"lot_id": "A", "contract_ref": "Brz cargo", "commodity": "CORN-BRZ",
     "supplier": "Nagi", "delivery_date": "2026-09-01",
     "original_mt": 2000, "cost_egp_mt": 14000.0},
    {"lot_id": "B", "contract_ref": "Arg cargo", "commodity": "CORN-ARG",
     "supplier": "Hassan", "delivery_date": "2026-10-01",
     "original_mt": 2000, "cost_egp_mt": 14800.0},
]


class OriginTests(unittest.TestCase):
    def test_the_origin_rides_along_from_the_layer_not_the_event(self):
        """The yard logs CORN; which cargo it came out of is FIFO's answer."""
        draws = consumption_draws(MIXED, EVENTS, "CORN")
        self.assertEqual([d["origin"] for d in draws], ["BRZ", "BRZ", "ARG"])
        self.assertEqual([d["supplier"] for d in draws],
                         ["Nagi", "Nagi", "Hassan"])

    def test_an_explicit_origin_field_beats_the_commodity_suffix(self):
        lots = [dict(MIXED[0], origin="ukr")]
        draws = consumption_draws(lots, EVENTS[:1], "CORN")
        self.assertEqual([d["origin"] for d in draws], ["UKR"])

    def test_a_layer_with_no_origin_is_bucketed_not_dropped(self):
        draws = consumption_draws(LOTS, EVENTS, "CORN")
        self.assertEqual({d["origin"] for d in draws}, {"(no origin)"})

    def test_filtering_by_origin_keeps_the_cost_the_full_queue_gave(self):
        """ARG only supplies the tail of the October draw, not all of it.

        Filtering the queue before the walk would have handed the ARG layer
        the whole 1,000 MT at its own cost.
        """
        arg = consumption_draws(MIXED, EVENTS, "CORN", origin="ARG")
        self.assertEqual(len(arg), 1)
        self.assertAlmostEqual(arg[0]["mt"], 500.0)
        self.assertAlmostEqual(arg[0]["cost_egp_mt"], 14800.0)

    def test_the_origins_together_are_the_whole_consumption(self):
        whole = consumption_draws(MIXED, EVENTS, "CORN")
        parts = []
        for origin in ("BRZ", "ARG"):
            parts += consumption_draws(MIXED, EVENTS, "CORN", origin=origin)
        self.assertAlmostEqual(sum(d["mt"] for d in parts),
                               sum(d["mt"] for d in whole))

    def test_an_origin_nobody_shipped_yields_nothing(self):
        self.assertEqual(consumption_draws(MIXED, EVENTS, "CORN",
                                           origin="UKR"), [])

    def test_the_by_origin_rollup_adds_back_to_the_total(self):
        rep = report(lots=MIXED)
        self.assertEqual([g["key"] for g in rep["by_origin"]], ["ARG", "BRZ"])
        self.assertAlmostEqual(
            sum(g["saving_vs_local_egp"] for g in rep["by_origin"]),
            rep["totals"]["saving_vs_local_egp"], places=6)
        self.assertAlmostEqual(sum(g["mt"] for g in rep["by_origin"]),
                               rep["totals"]["mt"], places=6)

    def test_a_report_narrowed_to_one_origin_only_counts_that_origin(self):
        rep = report(lots=MIXED, origin="BRZ")
        self.assertEqual([g["key"] for g in rep["by_origin"]], ["BRZ"])
        self.assertAlmostEqual(rep["totals"]["mt"], 2000.0)


class CoverageTests(unittest.TestCase):
    """Why a cargo is missing from the draws is itself a reported fact."""

    def coverage(self, **over):
        return {c["key"]: c for c in report(**over)["coverage"]}

    def test_every_cargo_in_scope_is_accounted_for(self):
        self.assertEqual(set(self.coverage()), {"Dec corn", "Oct corn"})

    def test_a_cargo_consumption_reached_reports_what_it_gave_up(self):
        dec = self.coverage()["Dec corn"]
        self.assertEqual(dec["state"], "drawn")
        self.assertAlmostEqual(dec["drawn_mt"], 2000.0)
        self.assertAlmostEqual(dec["remaining_mt"], 0.0)

    def test_a_cargo_fifo_has_not_reached_is_named_not_dropped(self):
        """2,500 MT burned against 4,000 MT landed leaves a layer untouched."""
        oct_lot = self.coverage(events=EVENTS[:1])["Oct corn"]
        self.assertEqual(oct_lot["state"], "untouched")
        self.assertAlmostEqual(oct_lot["drawn_mt"], 0.0)
        self.assertAlmostEqual(oct_lot["remaining_mt"], 2000.0)

    def test_a_cargo_that_lands_after_the_window_says_so(self):
        oct_lot = self.coverage(end="2026-09-30")["Oct corn"]
        self.assertEqual(oct_lot["state"], "later")
        self.assertIn("landed after", oct_lot["why"])

    def test_a_cargo_eaten_before_the_window_is_not_called_untouched(self):
        dec = self.coverage(start="2026-10-20")["Dec corn"]
        self.assertEqual(dec["state"], "earlier")
        self.assertAlmostEqual(dec["drawn_mt"], 0.0)
        self.assertAlmostEqual(dec["drawn_total_mt"], 2000.0)

    def test_a_cargo_eaten_after_the_window_is_not_called_earlier(self):
        """It is ahead of the period, not behind it."""
        oct_lot = self.coverage(end="2026-10-05")["Oct corn"]
        self.assertEqual(oct_lot["state"], "later")
        self.assertIn("consumed after", oct_lot["why"])

    def test_coverage_follows_the_origin_filter(self):
        self.assertEqual(set(self.coverage(lots=MIXED, origin="ARG")),
                         {"Arg cargo"})

    def test_the_tonnes_drawn_add_back_to_the_total_consumed(self):
        rep = report()
        self.assertAlmostEqual(sum(c["drawn_mt"] for c in rep["coverage"]),
                               rep["totals"]["mt"])

    def test_a_window_keeps_both_ends(self):
        draws = consumption_draws(LOTS, EVENTS, "CORN")
        self.assertEqual(len(within(draws, "2026-09-10", "2026-10-10")),
                         len(draws))
        self.assertEqual(len(within(draws, "2026-09-11", "2026-10-09")), 0)

    def test_coverage_can_be_asked_for_on_its_own(self):
        draws = consumption_draws(LOTS, EVENTS[:1], "CORN")
        cover = {c["key"]: c for c in cargo_coverage(LOTS, draws, "CORN")}
        self.assertEqual(cover["Oct corn"]["state"], "untouched")


def walked(lots=LOTS, events=EVENTS, rates=None, as_of="2026-10-10",
           estimate=True, commodity="CORN", origin=None, **over):
    """A savings report fed by the inventory walk, plus the walk itself."""
    inv = build_daily_fifo_inventory(lots, events, rates or {}, as_of=as_of,
                                     estimate_daily=estimate,
                                     record_draws=True)[commodity]
    draws = draws_from_inventory(inv["draws"], commodity, origin)
    return report(lots=lots, events=events, draws=draws, origin=origin,
                  **over), inv


class InventoryAgreementTests(unittest.TestCase):
    """The savings tab and the inventory view must agree on what is left."""

    def assert_agrees(self, rep, inv):
        left = {x["lot_id"]: x["remaining_mt"] for x in inv["layers"]}
        for cargo in rep["coverage"]:
            self.assertAlmostEqual(cargo["remaining_mt"],
                                   left.get(cargo["lot_id"], 0.0), places=6,
                                   msg=cargo["key"])

    def test_the_daily_estimate_consumes_cargo_the_log_never_mentions(self):
        """1,500 MT logged on 10 Sep, then 25 MT/day to 10 Oct.

        Twenty days finish the September cargo's last 500 MT; ten more take
        250 MT out of the October one, which the log never mentions.
        """
        rep, inv = walked(events=EVENTS[:1], rates={"CORN": 25})
        cover = {c["key"]: c for c in rep["coverage"]}
        self.assertEqual(cover["Oct corn"]["state"], "drawn")
        self.assertAlmostEqual(cover["Oct corn"]["drawn_estimated_mt"], 250.0)
        self.assertAlmostEqual(cover["Oct corn"]["remaining_mt"], 1750.0)
        self.assertAlmostEqual(rep["totals"]["logged_mt"], 1500.0)
        self.assertAlmostEqual(rep["totals"]["estimated_mt"], 750.0)
        self.assert_agrees(rep, inv)

    def test_an_estimate_that_outruns_the_stock_is_reported_unsourced(self):
        rep, inv = walked(events=EVENTS[:1], rates={"CORN": 100})
        self.assertAlmostEqual(rep["unsourced_mt"], inv["shortage_mt"])
        self.assertFalse([r for r in rep["rows"] if r["contract_ref"] == "(unsourced)"])
        self.assert_agrees(rep, inv)

    def test_every_draw_says_how_its_tonnes_are_known(self):
        rep, _ = walked(events=EVENTS[:1], rates={"CORN": 100})
        self.assertEqual({r["kind"] for r in rep["rows"]},
                         {"actual", "estimated"})

    def test_with_the_estimate_off_it_matches_the_log_alone(self):
        rep, inv = walked(events=EVENTS[:1], rates={"CORN": 100},
                          estimate=False)
        cover = {c["key"]: c for c in rep["coverage"]}
        self.assertEqual(cover["Oct corn"]["state"], "untouched")
        self.assertAlmostEqual(rep["totals"]["mt"], 1500.0)
        self.assert_agrees(rep, inv)

    def test_the_walk_and_the_log_walk_agree_when_there_is_only_a_log(self):
        rep, inv = walked(estimate=False)
        plain = report()
        self.assertAlmostEqual(rep["totals"]["mt"], plain["totals"]["mt"])
        self.assertAlmostEqual(rep["totals"]["saving_vs_local_egp"],
                               plain["totals"]["saving_vs_local_egp"])
        self.assert_agrees(rep, inv)

    def test_a_stock_count_consumes_without_a_day_so_it_is_not_valued(self):
        """4,000 MT landed, 2,500 counted: 1,500 MT gone on no known day."""
        count = [{"date": "2026-10-05", "commodity": "CORN",
                  "is_adjustment": True, "adjusted_qty": 2500}]
        rep, inv = walked(events=count, estimate=False)
        self.assertAlmostEqual(rep["counted_mt"], 1500.0)
        self.assertAlmostEqual(rep["totals"]["mt"], 0.0)
        dec = {c["key"]: c for c in rep["coverage"]}["Dec corn"]
        self.assertEqual(dec["state"], "counted")
        self.assertIn("2026-10-05", dec["why"])
        self.assertEqual(dec["count_date"], "2026-10-05")
        self.assertAlmostEqual(dec["remaining_mt"], 500.0)
        self.assert_agrees(rep, inv)

    def test_consumption_after_a_count_is_valued_on_its_day(self):
        events = [{"date": "2026-10-05", "commodity": "CORN",
                   "is_adjustment": True, "adjusted_qty": 2500},
                  {"date": "2026-10-08", "commodity": "CORN",
                   "consumed_mt": 1000}]
        rep, inv = walked(events=events, estimate=False)
        self.assertAlmostEqual(rep["totals"]["mt"], 1000.0)
        self.assertEqual([r["contract_ref"] for r in rep["rows"]],
                         ["Dec corn", "Oct corn"])
        self.assert_agrees(rep, inv)

    def test_the_origin_filter_reads_the_same_walk(self):
        rep, inv = walked(lots=MIXED, origin="ARG", rates={"CORN": 100},
                          events=EVENTS[:1])
        self.assertEqual({r["origin"] for r in rep["rows"]}, {"ARG"})
        self.assertEqual([c["key"] for c in rep["coverage"]], ["Arg cargo"])
        self.assert_agrees(rep, inv)

    def test_recording_draws_changes_nothing_the_inventory_reports(self):
        args = (LOTS, EVENTS[:1], {"CORN": 100})
        plain = build_daily_fifo_inventory(*args, as_of="2026-10-10")["CORN"]
        rec = build_daily_fifo_inventory(*args, as_of="2026-10-10",
                                         record_draws=True)["CORN"]
        rec.pop("draws")
        self.assertEqual(plain, rec)

    def test_the_draws_add_up_to_what_the_inventory_consumed(self):
        inv = build_daily_fifo_inventory(LOTS, EVENTS[:1], {"CORN": 100},
                                         as_of="2026-10-10",
                                         record_draws=True)["CORN"]
        self.assertAlmostEqual(sum(d["mt"] for d in inv["draws"]),
                               inv["actual_consumed_mt"]
                               + inv["estimated_consumed_mt"])


class DailyRateFromDeliveryTests(unittest.TestCase):
    """Consumption at the configured rate on every day from the first landing."""

    def walk(self, events=(), rate=100, as_of="2026-09-05", **kw):
        return build_daily_fifo_inventory(LOTS, list(events), {"CORN": rate},
                                          as_of=as_of, record_draws=True,
                                          **kw)["CORN"]

    def test_the_first_cargo_is_drawn_on_from_the_day_it_lands(self):
        inv = self.walk(start_on_delivery=True)
        self.assertEqual(min(d["date"] for d in inv["draws"]),
                         dt.date(2026, 9, 1))

    def test_every_day_to_the_valuation_date_is_counted(self):
        """1 Sep to 5 Sep inclusive is five days at 100 MT."""
        inv = self.walk(start_on_delivery=True)
        self.assertAlmostEqual(inv["estimated_consumed_mt"], 500.0)
        self.assertAlmostEqual(inv["remaining_mt"], 2000.0 - 500.0)

    def test_off_by_default_so_existing_figures_do_not_move(self):
        inv = self.walk()
        self.assertEqual(min(d["date"] for d in inv["draws"]),
                         dt.date(2026, 9, 2))
        self.assertAlmostEqual(inv["estimated_consumed_mt"], 400.0)

    def test_a_logged_entry_still_takes_precedence_when_one_is_passed(self):
        inv = self.walk(events=[{"date": "2026-09-03", "commodity": "CORN",
                                 "consumed_mt": 50}], start_on_delivery=True)
        self.assertAlmostEqual(inv["actual_consumed_mt"], 50.0)
        self.assertEqual(min(d["date"] for d in inv["draws"]
                             if d["kind"] == "estimated"), dt.date(2026, 9, 4))

    def test_a_later_cargo_starts_the_day_the_one_before_it_runs_out(self):
        """2,000 MT at 100/day from 1 Sep runs out on 20 Sep; Oct corn lands 1 Oct."""
        inv = self.walk(start_on_delivery=True, as_of="2026-10-05")
        oct_days = sorted(d["date"] for d in inv["draws"]
                          if d.get("contract_ref") == "Oct corn")
        self.assertEqual(oct_days[0], dt.date(2026, 10, 1))
        gap = [d for d in inv["draws"] if d["contract_ref"] == "(unsourced)"]
        self.assertAlmostEqual(sum(d["mt"] for d in gap), 1000.0)


class LocalByOriginTests(unittest.TestCase):
    """Each tonne is set against the local price for its own origin."""

    BRZ = {D(2026, 9, 10): 15000.0, D(2026, 10, 10): 15100.0}
    PLAIN = {D(2026, 9, 10): 14500.0, D(2026, 10, 10): 14600.0}

    def lookup(self, draw):
        for series in ((self.BRZ,) if draw.get("origin") == "BRZ" else ()) + (self.PLAIN,):
            found = nearest_on_or_before(series, draw["date"])
            if found[0] is not None:
                return found + ("key",)
        return (None, None, None, "")

    def test_a_brazilian_tonne_meets_the_brazilian_price(self):
        rep = report(lots=MIXED, local_lookup=self.lookup)
        by_origin = {}
        for row in rep["rows"]:
            by_origin.setdefault(row["origin"], set()).add(row["local_egp_mt"])
        self.assertEqual(by_origin["BRZ"], {15000.0, 15100.0})
        self.assertEqual(by_origin["ARG"], {14600.0})

    def test_the_saving_follows_the_price_it_was_set_against(self):
        rep = report(lots=MIXED, local_lookup=self.lookup)
        first = rep["rows"][0]
        self.assertAlmostEqual(first["saving_vs_local_egp_mt"], 15000.0 - 14000.0)

    def test_without_a_lookup_one_series_serves_every_origin(self):
        rep = report(lots=MIXED)
        self.assertEqual({r["local_egp_mt"] for r in rep["rows"]}, {14500.0, 14600.0})


class SavingsBridgeTests(unittest.TestCase):
    """Saving on the day of use = saving on arrival + market move in stock."""

    # A local price on each landing day as well as each day of use.
    PRICED = {D(2026, 9, 1): 14200.0, D(2026, 9, 10): 14500.0,
              D(2026, 10, 1): 14700.0, D(2026, 10, 10): 14600.0}

    def test_the_purchase_effect_is_the_arrival_price_less_the_cost(self):
        """What the Savings Tracker measures: local on the landing day − cost."""
        first = report(local_series=self.PRICED)["rows"][0]
        self.assertAlmostEqual(first["local_at_delivery_egp_mt"], 14200.0)
        self.assertAlmostEqual(first["purchase_effect_egp_mt"], 14200.0 - 14000.0)

    def test_the_timing_effect_is_how_far_local_moved_while_in_stock(self):
        first = report(local_series=self.PRICED)["rows"][0]
        self.assertAlmostEqual(first["timing_effect_egp_mt"], 14500.0 - 14200.0)

    def test_on_every_tonne_the_two_add_up_to_the_saving(self):
        for row in report(local_series=self.PRICED)["rows"]:
            self.assertAlmostEqual(row["purchase_effect_egp"] + row["timing_effect_egp"],
                                   row["saving_vs_local_egp"], places=6)

    def test_a_good_buy_can_still_lose_in_a_falling_market(self):
        """Bought 200 under the market, which then fell 500 before use."""
        falling = {D(2026, 9, 1): 14200.0, D(2026, 9, 10): 13700.0}
        row = report(local_series=falling, events=EVENTS[:1])["rows"][0]
        self.assertGreater(row["purchase_effect_egp_mt"], 0)
        self.assertLess(row["timing_effect_egp_mt"], 0)
        self.assertLess(row["saving_vs_local_egp_mt"], 0)

    def test_the_bridge_closes_on_the_headline(self):
        t = report(local_series=self.PRICED)["totals"]
        self.assertAlmostEqual(t["purchase_effect_egp"] + t["timing_effect_egp"]
                               + t["unsplit_egp"], t["saving_vs_local_egp"], places=6)
        self.assertAlmostEqual(t["unsplit_egp"], 0.0, places=6)

    def test_without_an_arrival_price_the_saving_is_kept_unsplit(self):
        """No local logged on or before 1 Sep: nothing to split against."""
        t = report(events=EVENTS[:1])["totals"]
        self.assertIsNone(t["purchase_effect_egp"])  # nothing split is not assessed, not zero
        self.assertAlmostEqual(t["unsplit_egp"], t["saving_vs_local_egp"], places=6)

    def test_an_unsourced_tonne_is_not_in_the_bridge(self):
        lots = [dict(LOTS[0], original_mt=1000)]
        rep = report(lots=lots, events=EVENTS[:1], local_series=self.PRICED)
        self.assertAlmostEqual(rep["unsourced_mt"], 500)
        self.assertAlmostEqual(rep["totals"]["mt"], 1000)

    def test_a_lookup_by_origin_is_used_for_the_arrival_price_too(self):
        def lookup(draw):
            series = {D(2026, 9, 1): 15000.0, D(2026, 9, 10): 15300.0}
            return nearest_on_or_before(series, draw["date"]) + ("CORN-BRZ",)
        row = report(local_lookup=lookup, events=EVENTS[:1])["rows"][0]
        self.assertAlmostEqual(row["local_at_delivery_egp_mt"], 15000.0)
        self.assertAlmostEqual(row["timing_effect_egp_mt"], 300.0)


class ImportLikeForLikeTests(unittest.TestCase):
    """The import alternative carries the cargo's own landed fees, and the
    gap to it splits into board move + basis + FX."""

    F = 0.3937
    CIF, COST_FX, PREMIUM, FEES = 262.17, 54.4363, 193.5, 941.05
    DRAW = {"date": D(2026, 5, 4), "mt": 500.0, "lot_id": "C012",
            "cost_egp_mt": 262.17 * 54.4363 + 941.05}

    def value(self, **kw):
        return value_draws([dict(self.DRAW)], {}, {D(2026, 5, 4): 473.75}, {D(2026, 5, 4): 53.494},
                           basis_for=lambda d: 177.5, factor=self.F, **kw)[0]

    def test_without_fees_the_import_is_cif_only_as_before(self):
        row = self.value()
        self.assertAlmostEqual(row["cbot_egp_mt"], (473.75 + 177.5) * self.F * 53.494)

    def test_the_cargos_own_fees_are_added_to_the_import(self):
        row = self.value(import_fees_for=lambda d: self.FEES)
        self.assertAlmostEqual(row["cbot_egp_mt"], (473.75 + 177.5) * self.F * 53.494 + self.FEES)
        self.assertAlmostEqual(row["import_fees_egp_mt"], self.FEES)

    def test_unknown_fees_leave_the_import_unpriced_not_guessed(self):
        row = self.value(import_fees_for=lambda d: None)
        self.assertIsNone(row["cbot_egp_mt"])
        self.assertIsNone(row["saving_vs_cbot_egp_mt"])

    def test_board_basis_and_fx_add_up_to_the_saving_vs_import(self):
        row = self.value(import_fees_for=lambda d: self.FEES,
                         import_terms_for=lambda d: (self.CIF, self.COST_FX, self.PREMIUM))
        fixing = self.CIF / self.F - self.PREMIUM
        self.assertAlmostEqual(row["imp_cbot_egp_mt"], self.F * 53.494 * (473.75 - fixing))
        self.assertAlmostEqual(row["imp_basis_egp_mt"], self.F * 53.494 * (177.5 - self.PREMIUM))
        self.assertAlmostEqual(row["imp_fx_egp_mt"], self.CIF * (53.494 - self.COST_FX))
        parts = row["imp_cbot_egp_mt"] + row["imp_basis_egp_mt"] + row["imp_fx_egp_mt"]
        self.assertAlmostEqual(parts, row["saving_vs_cbot_egp_mt"], places=6)
        self.assertAlmostEqual(row["imp_cbot_egp"], row["imp_cbot_egp_mt"] * 500.0)

    def test_a_flat_price_cargo_is_left_unsplit(self):
        row = self.value(import_fees_for=lambda d: self.FEES,
                         import_terms_for=lambda d: (self.CIF, self.COST_FX, 0.0))
        self.assertIsNone(row["imp_cbot_egp_mt"])
        self.assertIsNotNone(row["saving_vs_cbot_egp_mt"])

    def test_the_report_totals_close_on_the_import_saving(self):
        rep = savings_report(LOTS, EVENTS, commodity="CORN", local_series=LOCAL, cbot_series=CBOT,
                             fx_series=FX, basis_for=lambda d: 180.0,
                             import_fees_for=lambda d: 900.0,
                             import_terms_for=lambda d: (250.0, 50.0, 190.0))
        t = rep["totals"]
        self.assertAlmostEqual(t["imp_cbot_egp"] + t["imp_basis_egp"] + t["imp_fx_egp"]
                               + t["imp_unsplit_egp"], t["saving_vs_cbot_egp"], places=4)


if __name__ == "__main__":
    unittest.main()
