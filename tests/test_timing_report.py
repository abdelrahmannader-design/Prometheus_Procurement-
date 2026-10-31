"""Purchasing-timing analysis: what each contract's CBOT fixing was worth."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.timing_report import (
    ACCEPTABLE, FAVORABLE, INSUFFICIENT, NOT_APPLICABLE, PENDING, UNFAVORABLE,
    Series, arrival_coverage, assess_event, assess_local, assess_timing,
    contract_timing, executive_summary, final_assessment, pricing_events,
    stock_before)

D = dt.date
F = 0.3937


def history(start=D(2026, 3, 1), days=60, base=450.0, step=1.0):
    """A rising front-month series: day i costs base + i × step."""
    return Series([(start + dt.timedelta(days=i), base + i * step) for i in range(days)])


def corn(**over):
    c = {"commodity": "CORN-BRZ", "status": "Closed", "qty_mt": 5000,
         "premium_cents": 190.0, "pricing_date": "2026-03-31", "cif_usd_mt": (470 + 190) * F}
    c.update(over)
    return c


class PricingEventTests(unittest.TestCase):
    def test_the_priced_cbot_comes_from_the_contract_own_numbers(self):
        events, source, _ = pricing_events(corn(), F)
        self.assertEqual(source, "pricing date")
        self.assertAlmostEqual(events[0][2], 470.0)

    def test_pricing_lots_win_and_keep_their_own_cbot(self):
        c = corn(pricing_lots=[{"date": "2026-03-10", "qty_mt": 2000, "cbot": 455},
                               {"date": "2026-03-20", "qty_mt": 3000, "cbot": 466}])
        events, source, _ = pricing_events(c, F)
        self.assertEqual(source, "pricing lots")
        self.assertEqual([e[2] for e in events], [455, 466])

    def test_a_flat_price_has_no_cbot_to_time(self):
        self.assertEqual(pricing_events(corn(premium_cents=0), F)[2],
                         "flat price — no CBOT component")

    def test_no_pricing_date_is_reported_not_guessed(self):
        self.assertEqual(pricing_events(corn(pricing_date=""), F)[2],
                         "no pricing date recorded")


class EventTests(unittest.TestCase):
    def test_the_best_day_is_the_lowest_in_the_window(self):
        a = assess_event((D(2026, 3, 31), 5000, 470.0), history())
        self.assertEqual(a["best_date"], "2026-03-01")
        self.assertAlmostEqual(a["opportunity_cbot"], 480.0 - 450.0)

    def test_the_alternative_moves_the_priced_cbot_by_the_history_move(self):
        """Priced at 470 on a day the front month read 480: the spread is kept."""
        a = assess_event((D(2026, 3, 31), 5000, 470.0), history())
        self.assertAlmostEqual(a["best_priced_equivalent"], 470.0 - 30.0)

    def test_the_view_at_the_time_never_reads_a_later_price(self):
        h = history()
        a = assess_event((D(2026, 3, 31), 5000, 470.0), h)
        trail = [v for d, v in zip(h.dates, h.values) if d <= D(2026, 3, 31)][-20:]
        self.assertAlmostEqual(a["trailing_avg"], sum(trail) / len(trail))

    def test_the_window_never_runs_past_the_valuation_date(self):
        a = assess_event((D(2026, 3, 31), 5000, 470.0), history(), as_of=D(2026, 4, 5))
        self.assertEqual(a["window_end"], "2026-04-05")

    def test_a_weekend_pricing_day_uses_the_last_close_before_it(self):
        h = Series([(D(2026, 3, 6), 440.0), (D(2026, 3, 9), 445.0)])   # Fri, Mon
        a = assess_event((D(2026, 3, 8), 1000, 440.0), h, {"window_after_days": 0})
        self.assertEqual(a["history_date"], "2026-03-06")

    def test_no_history_before_the_day_is_insufficient(self):
        a = assess_event((D(2026, 2, 1), 1000, 450.0), history())
        self.assertEqual(a["status"], INSUFFICIENT)


class ContractTimingTests(unittest.TestCase):
    def test_opportunity_is_the_cost_gap_times_the_tonnes(self):
        """(actual − best) × factor × qty, in USD; × FX for EGP; ÷ CIF for %."""
        t = contract_timing(corn(), history(), F, cost_fx=50.0)
        per_mt = 30.0 * F
        self.assertAlmostEqual(t["opportunity_usd_mt"], per_mt)
        self.assertAlmostEqual(t["opportunity_usd"], per_mt * 5000)
        self.assertAlmostEqual(t["opportunity_egp"], per_mt * 5000 * 50.0)
        self.assertAlmostEqual(t["opportunity_pct"], per_mt / ((470 + 190) * F) * 100)

    def test_buying_at_the_low_is_favorable(self):
        t = contract_timing(corn(pricing_date="2026-03-01", cif_usd_mt=(450 + 190) * F),
                            history(), F)
        self.assertEqual(t["assessment"], FAVORABLE)
        self.assertAlmostEqual(t["opportunity_usd"], 0.0)

    def test_buying_at_the_top_of_the_range_is_unfavorable(self):
        t = contract_timing(corn(pricing_date="2026-04-29"), history(), F,
                            params={"window_after_days": 0})
        self.assertEqual(t["assessment"], UNFAVORABLE)

    def test_lots_are_weighted_by_their_tonnes(self):
        c = corn(pricing_lots=[{"date": "2026-03-11", "qty_mt": 1000, "cbot": 460},
                               {"date": "2026-03-31", "qty_mt": 4000, "cbot": 480}])
        t = contract_timing(c, history(), F)
        self.assertAlmostEqual(t["actual_cbot"], (460 * 1000 + 480 * 4000) / 5000)
        self.assertAlmostEqual(t["qty_priced"], 5000)

    def test_without_a_pricing_date_it_is_insufficient_data(self):
        t = contract_timing(corn(pricing_date=""), history(), F)
        self.assertEqual(t["assessment"], INSUFFICIENT)
        self.assertIsNone(t["opportunity_usd"])

    def test_a_flat_price_contract_is_not_applicable(self):
        t = contract_timing(corn(premium_cents=0), history(), F)
        self.assertEqual(t["assessment"], NOT_APPLICABLE)

    def test_an_open_unpriced_contract_gets_a_forward_view_only(self):
        t = contract_timing(corn(pricing_date="", status="Open", pricing_status="UNPRICED"),
                            history(), F, as_of=D(2026, 4, 29))
        self.assertEqual(t["assessment"], PENDING)
        self.assertIsNone(t["opportunity_usd"])
        self.assertIn("range_position", t["forward"])

    def test_no_stored_history_is_insufficient(self):
        self.assertEqual(contract_timing(corn(), Series([]), F)["assessment"], INSUFFICIENT)


class VerdictTests(unittest.TestCase):
    def test_a_tiny_opportunity_is_favorable_whatever_the_range(self):
        self.assertEqual(assess_timing(0.9, 0.5), FAVORABLE)

    def test_the_range_is_split_in_thirds(self):
        self.assertEqual(assess_timing(0.2, 5), FAVORABLE)
        self.assertEqual(assess_timing(0.5, 5), ACCEPTABLE)
        self.assertEqual(assess_timing(0.9, 5), UNFAVORABLE)

    def test_local_is_judged_against_a_one_percent_band(self):
        self.assertEqual(assess_local(300, 15000), FAVORABLE)
        self.assertEqual(assess_local(50, 15000), ACCEPTABLE)
        self.assertEqual(assess_local(-300, 15000), UNFAVORABLE)
        self.assertEqual(assess_local(None, 15000), INSUFFICIENT)

    def test_the_final_verdict_adds_the_two_scores(self):
        self.assertEqual(final_assessment(FAVORABLE, FAVORABLE), FAVORABLE)
        self.assertEqual(final_assessment(FAVORABLE, UNFAVORABLE), ACCEPTABLE)
        self.assertEqual(final_assessment(ACCEPTABLE, UNFAVORABLE), UNFAVORABLE)
        self.assertEqual(final_assessment(FAVORABLE, ACCEPTABLE), FAVORABLE)

    def test_without_timing_the_local_result_stands(self):
        for timing in (INSUFFICIENT, NOT_APPLICABLE, PENDING):
            self.assertEqual(final_assessment(UNFAVORABLE, timing), UNFAVORABLE)

    def test_without_a_local_result_it_is_insufficient(self):
        self.assertEqual(final_assessment(INSUFFICIENT, FAVORABLE), INSUFFICIENT)


class StockTests(unittest.TestCase):
    LOTS = [{"delivery_date": "2026-03-01", "original_mt": 2000},
            {"delivery_date": "2026-03-10", "original_mt": 3000}]
    DRAWS = [{"date": D(2026, 3, d), "mt": 500, "contract_ref": "x"} for d in range(1, 10)]

    def test_stock_is_landed_before_less_used_before(self):
        self.assertAlmostEqual(stock_before(self.LOTS, self.DRAWS, "2026-03-03"), 2000 - 1000)

    def test_unsourced_tonnes_did_not_come_out_of_the_yard(self):
        draws = self.DRAWS + [{"date": D(2026, 3, 2), "mt": 999, "contract_ref": "(unsourced)"}]
        self.assertAlmostEqual(stock_before(self.LOTS, draws, "2026-03-03"), 1000)

    def test_little_cover_means_the_cargo_prevented_a_shortage(self):
        self.assertTrue(arrival_coverage(1000, 500, 3000)["verdict"].startswith("Needed"))

    def test_lots_of_cover_means_it_arrived_early(self):
        self.assertTrue(arrival_coverage(30000, 500, 3000)["verdict"].startswith("Early"))

    def test_no_rate_is_insufficient(self):
        self.assertEqual(arrival_coverage(1000, None, 3000)["verdict"], INSUFFICIENT)


class SummaryTests(unittest.TestCase):
    def rows(self):
        return [
            {"id": "a", "qty_mt": 1000, "contract_value_usd": 250000, "saving_local_egp": 100,
             "saving_kind": "Realized", "final_assessment": FAVORABLE,
             "timing": {"assessment": UNFAVORABLE, "opportunity_usd": 9000, "opportunity_egp": 450000}},
            {"id": "b", "qty_mt": 1000, "contract_value_usd": 260000, "saving_local_egp": -50,
             "saving_kind": "Estimated", "final_assessment": ACCEPTABLE,
             "timing": {"assessment": FAVORABLE, "opportunity_usd": 1000, "opportunity_egp": 50000}},
            {"id": "c", "qty_mt": 500, "saving_local_egp": None, "final_assessment": INSUFFICIENT,
             "timing": {"assessment": INSUFFICIENT}},
        ]

    def test_realized_and_estimated_savings_are_kept_apart(self):
        s = executive_summary(self.rows())
        self.assertEqual(s["saving_local_realized_egp"], 100)
        self.assertEqual(s["saving_local_estimated_egp"], -50)

    def test_timing_is_reported_beside_local_never_added_to_it(self):
        s = executive_summary(self.rows())
        self.assertEqual(s["timing_opportunity_usd"], 10000)
        self.assertNotIn("total_savings", s)

    def test_the_ranking_runs_from_the_largest_opportunity(self):
        self.assertEqual(executive_summary(self.rows())["ranking"], ["a", "b"])

    def test_insufficient_and_unfavorable_need_review(self):
        s = executive_summary(self.rows())
        self.assertEqual(s["needs_review"], 1)
        self.assertEqual(s["missed_savings"], 1)


class SpikeTests(unittest.TestCase):
    """A one-day stray print is not a purchasing opportunity."""

    def spiky(self):
        days = [D(2026, 3, 1) + dt.timedelta(days=i) for i in range(30)]
        values = [450.0] * 30
        values[10] = 420.0          # one day 6.7 % below both neighbours
        values[20] = 480.0          # one day 6.7 % above
        return Series(list(zip(days, values)))

    def test_a_reversing_one_day_jump_is_flagged(self):
        self.assertEqual(self.spiky().spikes(), {D(2026, 3, 11), D(2026, 3, 21)})

    def test_a_real_step_is_not_a_spike(self):
        days = [D(2026, 3, 1) + dt.timedelta(days=i) for i in range(10)]
        step = Series([(d, 450.0 if i < 5 else 480.0) for i, d in enumerate(days)])
        self.assertEqual(step.spikes(), set())

    def test_a_spike_is_never_the_best_day(self):
        a = assess_event((D(2026, 3, 15), 1000, 450.0), self.spiky())
        self.assertNotEqual(a["best_date"], "2026-03-11")
        self.assertAlmostEqual(a["opportunity_cbot"], 0.0)
        self.assertEqual(a["spikes_excluded"], 2)

    def test_a_spike_on_the_pricing_day_lowers_the_confidence(self):
        c = corn(pricing_date="2026-03-21", cif_usd_mt=(480 + 190) * F)
        t = contract_timing(c, self.spiky(), F)
        self.assertTrue(t["confidence"].startswith("Low"))


if __name__ == "__main__":
    unittest.main()
