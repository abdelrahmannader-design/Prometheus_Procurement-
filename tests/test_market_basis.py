"""Traded basis vs implied basis, and the replacement cost built on them."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_ui.cbot_console import BASIS_RECENCY_DAYS, CBOTFeed


def days_ago(n):
    return (dt.date.today() - dt.timedelta(days=n)).isoformat()


def state(**over):
    base = {
        "market_data": {"cbot_quotes": {"CORN": {"price": 483.0}},
                        "fx": {"price": 52.6910}},
        "cbot_history": [], "fx_history": [], "local_prices": [],
        "contracts": {}, "ui": {"basis_expenses_egp_mt": 700.0},
        "market_basis": [],
    }
    base.update(over)
    return base


class WeightedPremiumTests(unittest.TestCase):
    def _contracts(self, rows):
        return {str(i): r for i, r in enumerate(rows)}

    def test_negative_basis_is_counted_not_dropped(self):
        """Dropping sub-board cargoes biased every average upward."""
        feed = CBOTFeed(state(contracts=self._contracts([
            {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
             "premium_cents": 200, "contract_date": days_ago(10)},
            {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
             "premium_cents": -40, "contract_date": days_ago(10)},
        ])))
        self.assertAlmostEqual(feed.weighted_premium("CORN"), 80.0)

    def test_origin_is_honoured(self):
        feed = CBOTFeed(state(contracts=self._contracts([
            {"status": "Open", "commodity": "CORN", "origin": "BRZ", "qty_mt": 1000,
             "premium_cents": 180, "contract_date": days_ago(5)},
            {"status": "Open", "commodity": "CORN", "origin": "UKR", "qty_mt": 3000,
             "premium_cents": 260, "contract_date": days_ago(5)},
        ])))
        self.assertAlmostEqual(feed.weighted_premium("CORN", origin="BRZ"), 180.0)
        self.assertAlmostEqual(feed.weighted_premium("CORN", origin="UKR"), 260.0)
        self.assertAlmostEqual(feed.weighted_premium("CORN"), 240.0)

    def test_origin_falls_back_to_the_commodity_suffix(self):
        feed = CBOTFeed(state(contracts=self._contracts([
            {"status": "Open", "commodity": "CORN-BRZ", "qty_mt": 1000,
             "premium_cents": 180, "contract_date": days_ago(5)},
        ])))
        self.assertAlmostEqual(feed.weighted_premium("CORN", origin="BRZ"), 180.0)

    def test_stale_contracts_are_excluded(self):
        feed = CBOTFeed(state(contracts=self._contracts([
            {"status": "Open", "commodity": "CORN", "qty_mt": 5000,
             "premium_cents": 400, "contract_date": days_ago(BASIS_RECENCY_DAYS + 30)},
            {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
             "premium_cents": 150, "contract_date": days_ago(3)},
        ])))
        self.assertAlmostEqual(feed.weighted_premium("CORN"), 150.0)

    def test_legacy_zero_placeholder_is_still_skipped(self):
        feed = CBOTFeed(state(contracts=self._contracts([
            {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
             "premium_cents": 0, "contract_date": days_ago(3)},
        ])))
        self.assertIsNone(feed.weighted_premium("CORN"))


class BasisReferenceTests(unittest.TestCase):
    def test_market_basis_wins_over_the_book(self):
        feed = CBOTFeed(state(
            market_basis=[{"commodity": "CORN", "origin": "BRZ", "basis": 190.0,
                           "date": days_ago(2), "futures_month": "Dec 2026",
                           "source": "trader"}],
            contracts={"a": {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
                             "premium_cents": 300, "contract_date": days_ago(5)}}))
        ref = feed.basis_reference("CORN", origin="BRZ")
        self.assertEqual(ref["source"], "market")
        self.assertAlmostEqual(ref["value"], 190.0)
        self.assertEqual(ref["age_days"], 2)

    def test_matching_origin_beats_a_newer_other_origin(self):
        feed = CBOTFeed(state(market_basis=[
            {"commodity": "CORN", "origin": "BRZ", "basis": 190.0, "date": days_ago(9)},
            {"commodity": "CORN", "origin": "UKR", "basis": 260.0, "date": days_ago(1)},
        ]))
        self.assertAlmostEqual(feed.basis_reference("CORN", origin="BRZ")["value"], 190.0)

    def test_no_basis_at_all_reports_rather_than_assuming_zero(self):
        ref = CBOTFeed(state()).basis_reference("CORN")
        self.assertIsNone(ref["value"])
        self.assertEqual(ref["source"], "none")


class ImpliedBasisTests(unittest.TestCase):
    def _feed(self):
        return CBOTFeed(state(local_prices=[
            {"date": days_ago(1), "commodity": "CORN",
             "price_egp_mt": 13976.87, "transport_egp_mt": 323.13}]))

    def test_implied_basis_inverts_the_parity_formula(self):
        feed = self._feed()
        implied = feed.implied_basis("CORN")["value"]
        expected = ((14300.0 - 700.0) / 52.6910) / 0.3937 - 483.0
        self.assertAlmostEqual(implied, expected, places=6)

    def test_feeding_implied_back_in_collapses_to_the_local_price(self):
        """Why implied basis cannot drive replacement: the board cancels."""
        feed = self._feed()
        implied = feed.implied_basis("CORN")["value"]
        allin, _note, _fees = feed.replacement_all_in_egp_mt("CORN", premium=implied)
        self.assertAlmostEqual(allin, 14300.0, places=4)

    def test_sbm_has_no_implied_basis(self):
        result = CBOTFeed(state()).implied_basis("SBM")
        self.assertIsNone(result["value"])
        self.assertIn("SBM", result["note"])

    def test_missing_inputs_are_named_not_zeroed(self):
        result = CBOTFeed(state(market_data={})).implied_basis("CORN")
        self.assertIsNone(result["value"])
        self.assertIn("needs", result["note"])


class ReplacementTests(unittest.TestCase):
    def test_all_in_adds_the_fee_stack_to_cif(self):
        feed = CBOTFeed(state(market_basis=[
            {"commodity": "CORN", "basis": 185.5, "date": days_ago(1)}]))
        cif, _note = feed.replacement_egp_mt("CORN")
        allin, _n, fees = feed.replacement_all_in_egp_mt("CORN")
        self.assertAlmostEqual(fees, 700.0)
        self.assertAlmostEqual(allin - cif, 700.0, places=6)
        self.assertAlmostEqual(cif, (483.0 + 185.5) * 0.3937 * 52.6910, places=4)

    def test_without_a_basis_the_note_says_so(self):
        _value, note = CBOTFeed(state()).replacement_egp_mt("CORN")
        self.assertIn("zero basis", note)


if __name__ == "__main__":
    unittest.main()
