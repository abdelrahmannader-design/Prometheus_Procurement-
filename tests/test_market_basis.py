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


class ReplacementRouteTests(unittest.TestCase):
    """Replacement as the cheaper of buying a cargo or buying local."""

    def _feed(self, local=14300.0, traded=190.0, costs=500.0, **over):
        s = state(local_prices=[{"date": days_ago(0), "commodity": "CORN",
                                 "price_egp_mt": local, "transport_egp_mt": 323.13}])
        s["ui"].update({"basis_expenses_egp_mt": costs, "basis_source": "local",
                        "basis_local_use_transport": False})
        s["market_data"] = {"cbot_quotes": {"CORN": {"price": 460.25}},
                            "fx": {"price": 54.0580}}
        if traded is not None:
            s["market_basis"] = [{"commodity": "CORN", "basis": traded,
                                  "date": days_ago(1)}]
        s.update(over)
        return CBOTFeed(s)

    def test_import_leg_carries_the_cost_stack(self):
        r = self._feed().replacement_routes("CORN")
        self.assertAlmostEqual(
            r["import"]["value"], (460.25 + 190.0) * 0.3937 * 54.0580 + 500.0,
            places=4)

    def test_local_leg_is_the_price_with_nothing_added(self):
        r = self._feed().replacement_routes("CORN")
        self.assertAlmostEqual(r["local"]["value"], 14300.0)

    def test_replacement_is_the_cheaper_route(self):
        r = self._feed().replacement_routes("CORN")
        self.assertEqual(r["binding"], "local")
        self.assertAlmostEqual(r["value"], 14300.0)
        self.assertAlmostEqual(r["edge"], r["import"]["value"] - 14300.0, places=6)

    def test_the_binding_route_flips_with_the_basis(self):
        """A wider basis makes the cargo dearer and hands it to local."""
        cheap = self._feed(traded=150.0).replacement_routes("CORN")
        dear = self._feed(traded=260.0).replacement_routes("CORN")
        self.assertEqual(cheap["binding"], "import")
        self.assertEqual(dear["binding"], "local")

    def test_the_import_leg_never_uses_a_local_derived_basis(self):
        """Otherwise the board cancels and the two legs collapse into one."""
        feed = self._feed()
        # The displayed basis is local-derived...
        self.assertEqual(feed.basis_reference("CORN")["source"], "local")
        # ...while the import leg prices off the quoted one regardless.
        leg = feed.replacement_routes("CORN")["import"]
        self.assertEqual(leg["source"], "market")
        self.assertAlmostEqual(leg["basis"], 190.0)
        self.assertNotAlmostEqual(leg["basis"],
                                  feed.basis_reference("CORN")["value"], places=2)

    def test_a_book_average_is_flagged_as_not_a_quote(self):
        feed = self._feed(traded=None, contracts={
            "a": {"status": "Open", "commodity": "CORN", "qty_mt": 1000,
                  "premium_cents": 185.5, "contract_date": days_ago(5)}})
        leg = feed.replacement_routes("CORN")["import"]
        self.assertEqual(leg["source"], "book")
        self.assertTrue(leg["fallback"])

    def test_a_quoted_basis_is_not_flagged(self):
        self.assertFalse(self._feed().replacement_routes("CORN")["import"]["fallback"])

    def test_a_missing_leg_does_not_sink_the_other(self):
        feed = self._feed(traded=None)          # no basis at all
        r = feed.replacement_routes("CORN")
        self.assertIsNone(r["import"]["value"])
        self.assertEqual(r["binding"], "local")
        self.assertAlmostEqual(r["value"], 14300.0)
        self.assertIsNone(r["edge"])

    def test_no_data_at_all_reports_rather_than_guessing(self):
        r = CBOTFeed(state()).replacement_routes("CORN")
        self.assertIsNone(r["value"])
        self.assertIsNone(r["binding"])


class ReplacementBasisChoiceTests(unittest.TestCase):
    """Pricing the import leg at each basis the app holds."""

    def _feed(self, choice=None, market=190.0, book=185.45, local=14300.0):
        s = state(local_prices=[{"date": days_ago(0), "commodity": "CORN",
                                 "price_egp_mt": local, "transport_egp_mt": 323.13}])
        s["ui"].update({"basis_expenses_egp_mt": 500.0, "basis_source": "local",
                        "basis_local_use_transport": False})
        if choice:
            s["ui"]["replacement_basis"] = choice
        s["market_data"] = {"cbot_quotes": {"CORN": {"price": 459.0}},
                            "fx": {"price": 54.1500}}
        if market is not None:
            s["market_basis"] = [{"commodity": "CORN", "basis": market,
                                  "date": days_ago(1)}]
        if book is not None:
            s["contracts"] = {"a": {"status": "Open", "commodity": "CORN",
                                    "qty_mt": 16000, "premium_cents": book,
                                    "contract_date": days_ago(21)}}
        return CBOTFeed(s)

    def test_all_three_bases_are_offered(self):
        sources = [c["source"] for c in self._feed().basis_candidates("CORN")]
        self.assertEqual(sorted(sources), ["book", "local", "market"])

    def test_variants_price_the_leg_at_each_and_sort_cheapest_first(self):
        rows = self._feed().replacement_variants("CORN")
        values = [r["value"] for r in rows]
        self.assertEqual(values, sorted(values))
        by = {r["source"]: r for r in rows}
        self.assertAlmostEqual(by["book"]["value"],
                               (459.0 + 185.45) * 0.3937 * 54.15 + 500, places=4)
        self.assertAlmostEqual(by["market"]["value"],
                               (459.0 + 190.0) * 0.3937 * 54.15 + 500, places=4)

    def test_the_local_variant_returns_local_plus_costs(self):
        """The identity, visible beside the others rather than hidden."""
        by = {r["source"]: r for r in self._feed().replacement_variants("CORN")}
        self.assertAlmostEqual(by["local"]["value"], 14300.0 + 500.0, places=4)
        self.assertTrue(by["local"]["circular"])

    def test_auto_prefers_a_quote_over_the_book(self):
        leg = self._feed().replacement_routes("CORN")["import"]
        self.assertEqual(leg["source"], "market")
        self.assertFalse(leg["fallback"])

    def test_auto_falls_back_to_the_book_when_no_quote_exists(self):
        leg = self._feed(market=None).replacement_routes("CORN")["import"]
        self.assertEqual(leg["source"], "book")
        self.assertTrue(leg["fallback"])

    def test_pinning_the_book_ignores_an_available_quote(self):
        leg = self._feed(choice="book").replacement_routes("CORN")["import"]
        self.assertEqual(leg["source"], "book")
        self.assertAlmostEqual(leg["basis"], 185.45)

    def test_pinning_local_is_allowed_and_marked_circular(self):
        routes = self._feed(choice="local").replacement_routes("CORN")
        self.assertTrue(routes["import"]["circular"])
        self.assertAlmostEqual(routes["import"]["value"], 14800.0, places=4)
        self.assertEqual(routes["binding"], "local")

    def test_pinning_a_basis_that_does_not_exist_prices_nothing(self):
        """Better an empty leg than a silent substitution."""
        leg = self._feed(choice="market", market=None).replacement_routes("CORN")["import"]
        self.assertIsNone(leg["value"])
        self.assertIn("traded basis", leg["note"])

    def test_the_choice_changes_which_route_binds(self):
        quote = self._feed(choice="market").replacement_routes("CORN")
        book = self._feed(choice="book").replacement_routes("CORN")
        self.assertEqual(quote["binding"], "local")
        self.assertEqual(book["binding"], "import")
