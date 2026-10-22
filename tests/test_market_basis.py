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


class LocalDerivedBasisTests(unittest.TestCase):
    """basis = (local price / FX) / factor - board, with the desk's settings."""

    def _state(self, **ui):
        base = state(local_prices=[{"date": days_ago(1), "commodity": "CORN",
                                    "price_egp_mt": 14300.0,
                                    "transport_egp_mt": 323.13}])
        base["ui"].update({"basis_source": "local"})
        base["ui"].update(ui)
        return base

    def test_transport_is_not_added_by_default(self):
        """The quoted local figure is a whole price, not a base plus haulage."""
        feed = CBOTFeed(self._state())
        local, _date = feed.local_quote("CORN")
        self.assertAlmostEqual(local, 14300.0)

    def test_transport_is_added_when_the_desk_asks_for_it(self):
        feed = CBOTFeed(self._state(basis_local_use_transport=True))
        local, _date = feed.local_quote("CORN")
        self.assertAlmostEqual(local, 14623.13)

    def test_the_formula(self):
        feed = CBOTFeed(self._state())
        expected = (14300.0 / 52.6910) / 0.3937 - 483.0
        self.assertAlmostEqual(feed.local_implied_basis("CORN")["value"],
                               expected, places=8)

    def test_no_expenses_are_deducted_unless_asked(self):
        feed = CBOTFeed(self._state())
        plain = feed.local_implied_basis("CORN")["value"]
        deducted = feed.local_implied_basis("CORN", expenses=500)["value"]
        self.assertAlmostEqual(plain - deducted, (500 / 52.6910) / 0.3937, places=8)

    def test_that_setting_drives_basis_reference(self):
        ref = CBOTFeed(self._state()).basis_reference("CORN")
        self.assertEqual(ref["source"], "local")
        self.assertTrue(ref["circular"])

    def test_replacement_equals_the_local_price_and_says_so(self):
        """The round trip cancels the board — intended, and flagged."""
        feed = CBOTFeed(self._state())
        # no at-port fee stack, so the identity is exact
        feed.state["ui"]["basis_expenses_egp_mt"] = 0.0
        allin, _note, fees = feed.replacement_all_in_egp_mt("CORN")
        self.assertAlmostEqual(allin, 14300.0, places=4)
        self.assertEqual(fees, 0.0)
        self.assertTrue(feed.basis_reference("CORN")["circular"])

    def test_other_sources_are_not_marked_circular(self):
        s = self._state()
        s["ui"]["basis_source"] = "market"
        s["market_basis"] = [{"commodity": "CORN", "basis": 190.0,
                              "date": days_ago(1)}]
        ref = CBOTFeed(s).basis_reference("CORN")
        self.assertEqual(ref["source"], "market")
        self.assertFalse(ref["circular"])

    def test_traded_basis_never_comes_from_local(self):
        """What the gap tile falls back on when the basis is local-derived."""
        s = self._state()
        s["market_basis"] = [{"commodity": "CORN", "basis": 190.0,
                              "date": days_ago(1)}]
        feed = CBOTFeed(s)
        self.assertEqual(feed.basis_reference("CORN")["source"], "local")
        self.assertEqual(feed.traded_basis("CORN")["source"], "market")
        self.assertAlmostEqual(feed.traded_basis("CORN")["value"], 190.0)

    def test_local_source_falls_through_when_there_is_no_local_price(self):
        s = state(contracts={"a": {"status": "Open", "commodity": "CORN",
                                   "qty_mt": 1000, "premium_cents": 185.5,
                                   "contract_date": days_ago(5)}})
        s["ui"]["basis_source"] = "local"
        ref = CBOTFeed(s).basis_reference("CORN")
        self.assertEqual(ref["source"], "book")
        self.assertAlmostEqual(ref["value"], 185.5)


class ReplacementParityTests(unittest.TestCase):
    """Replacement is the basis at which an import matches the local price."""

    def _feed(self, local=14600.0, board=465.0, fx=54.3250,
              market=None, book=185.5, manual=None, choice=None):
        s = state(local_prices=[{"date": days_ago(0), "commodity": "CORN",
                                 "price_egp_mt": local, "transport_egp_mt": 323.13}])
        s["ui"].update({"basis_expenses_egp_mt": 500.0,
                        "basis_local_use_transport": False})
        if choice:
            s["ui"]["replacement_basis"] = choice
        if manual is not None:
            s["ui"]["replacement_manual_basis"] = {"CORN": manual}
        s["market_data"] = {"cbot_quotes": {"CORN": {"price": board}},
                            "fx": {"price": fx}}
        if market is not None:
            s["market_basis"] = [{"commodity": "CORN", "basis": market,
                                  "date": days_ago(1)}]
        if book is not None:
            s["contracts"] = {"a": {"status": "Open", "commodity": "CORN",
                                    "qty_mt": 16000, "premium_cents": book,
                                    "contract_date": days_ago(21)}}
        return CBOTFeed(s)

    def test_the_formula(self):
        par = self._feed().replacement_parity("CORN")
        self.assertAlmostEqual(par["basis"],
                               ((14600.0 / 54.3250) / 0.3937) - 465.0, places=8)
        self.assertAlmostEqual(par["basis"], 217.63, places=2)

    def test_the_local_price_is_the_only_input_to_it(self):
        """No quoted basis, however it moves, may touch the parity figure."""
        a = self._feed(market=190.0).replacement_parity("CORN")["basis"]
        b = self._feed(market=260.0).replacement_parity("CORN")["basis"]
        c = self._feed(market=None, book=None).replacement_parity("CORN")["basis"]
        self.assertAlmostEqual(a, b, places=10)
        self.assertAlmostEqual(a, c, places=10)

    def test_no_cost_stack_enters_it(self):
        feed = self._feed()
        before = feed.replacement_parity("CORN")["basis"]
        feed.state["ui"]["basis_expenses_egp_mt"] = 900.0
        self.assertAlmostEqual(feed.replacement_parity("CORN")["basis"],
                               before, places=10)

    def test_converting_back_returns_the_local_price(self):
        par = self._feed().replacement_parity("CORN")
        back = (par["board"] + par["basis"]) * par["factor"] * par["fx"]
        self.assertAlmostEqual(back, 14600.0, places=6)
        self.assertAlmostEqual(par["egp"], 14600.0, places=6)

    def test_a_quote_below_parity_means_a_cargo_lands_under_local(self):
        par = self._feed(market=190.0).replacement_parity("CORN")
        self.assertAlmostEqual(par["quoted"], 190.0)
        self.assertLess(par["gap"], 0)
        self.assertAlmostEqual(par["gap"], 190.0 - par["basis"], places=8)

    def test_a_quote_above_parity_means_local_wins(self):
        self.assertGreater(self._feed(market=260.0).replacement_parity("CORN")["gap"], 0)

    def test_a_typed_basis_is_preferred_as_the_comparison(self):
        """Someone typing one is saying what they have just been offered."""
        par = self._feed(market=190.0, manual=195.0).replacement_parity("CORN")
        self.assertEqual(par["quoted_source"], "manual")
        self.assertAlmostEqual(par["quoted"], 195.0)

    def test_the_comparison_falls_back_market_then_book(self):
        self.assertEqual(
            self._feed(market=190.0).replacement_parity("CORN")["quoted_source"], "market")
        self.assertEqual(
            self._feed(market=None).replacement_parity("CORN")["quoted_source"], "book")

    def test_the_comparison_can_be_pinned(self):
        par = self._feed(market=190.0, choice="book").replacement_parity("CORN")
        self.assertEqual(par["quoted_source"], "book")

    def test_local_can_never_be_the_comparison(self):
        """Comparing parity with itself would read zero forever."""
        par = self._feed(market=None, book=None, choice="local").replacement_parity("CORN")
        self.assertIsNone(par["quoted"])
        self.assertIsNone(par["gap"])

    def test_with_no_quote_the_parity_figure_still_stands(self):
        par = self._feed(market=None, book=None).replacement_parity("CORN")
        self.assertIsNotNone(par["basis"])
        self.assertIsNone(par["gap"])

    def test_missing_inputs_are_named(self):
        par = CBOTFeed(state()).replacement_parity("CORN")
        self.assertIsNone(par["basis"])
        self.assertIn("local price", par["note"])


class ManualBasisTests(unittest.TestCase):
    """A basis typed on the desk, held per board, used as the comparison."""

    def _feed(self):
        return CBOTFeed({
            "market_data": {"cbot_quotes": {"CORN": {"price": 465.0},
                                            "SBM": {"price": 345.9}},
                            "fx": {"price": 54.3250}},
            "cbot_history": [], "fx_history": [], "contracts": {},
            "local_prices": [{"date": days_ago(0), "commodity": "CORN",
                              "price_egp_mt": 14600.0, "transport_egp_mt": 323.13}],
            "market_basis": [],
            "ui": {"basis_local_use_transport": False}})

    def test_setting_and_reading_back(self):
        feed = self._feed()
        self.assertIsNone(feed.manual_basis("CORN"))
        feed.set_manual_basis("CORN", 195.0)
        self.assertAlmostEqual(feed.manual_basis("CORN"), 195.0)

    def test_it_is_held_per_board(self):
        feed = self._feed()
        feed.set_manual_basis("CORN", 195.0)
        self.assertIsNone(feed.manual_basis("SBM"))
        feed.set_manual_basis("SBM", 42.0)
        self.assertAlmostEqual(feed.manual_basis("CORN"), 195.0)

    def test_origin_suffixes_share_the_boards_value(self):
        feed = self._feed()
        feed.set_manual_basis("CORN", 195.0)
        self.assertAlmostEqual(feed.manual_basis("CORN-BRZ"), 195.0)

    def test_clearing_removes_it(self):
        feed = self._feed()
        feed.set_manual_basis("CORN", 195.0)
        feed.set_manual_basis("CORN", None)
        self.assertIsNone(feed.manual_basis("CORN"))

    def test_it_becomes_the_comparison_but_never_the_parity(self):
        feed = self._feed()
        before = feed.replacement_parity("CORN")["basis"]
        feed.set_manual_basis("CORN", 195.0)
        par = feed.replacement_parity("CORN")
        self.assertAlmostEqual(par["basis"], before, places=10)
        self.assertAlmostEqual(par["quoted"], 195.0)
        self.assertAlmostEqual(par["gap"], 195.0 - before, places=8)

    def test_a_corrupt_stored_value_does_not_crash_the_desk(self):
        feed = self._feed()
        feed.state["ui"]["replacement_manual_basis"] = "not a dict"
        self.assertIsNone(feed.manual_basis("CORN"))
