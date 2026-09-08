"""Tests for the FIFO Inventory & Scenario Lab pure-calculation core
(prometheus_core.py). Run via: python -m unittest discover -s tests

This file covers the core-engine cases from the FIFO upgrade's test list:
FIFO depletion across multiple contracts, partial consumption, fully
consumed contracts dropping out of current inventory, weighted-average
inventory cost, inventory-vs-local-market edge, freight with 14% VAT,
all-in freight without double VAT, scenario calculations, purity (no
mutation of inputs -- the state-level "scenario reset must not modify
app_state.json" behavior is additionally verified end-to-end once the
Scenario Lab UI exists), commodity isolation, and the FIFO reconciliation
identity that the dashboard/drill-down totals rely on.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import prometheus_core as core


class TestFifoAllocateInventory(unittest.TestCase):
    def test_multi_contract_depletion_matches_spec_example(self):
        # Contract A = 5,000 MT @ delivered first, Contract B = 4,000 MT
        # delivered later. Consumption = 6,000 MT.
        # Expected: A fully consumed (0 remaining), B has 3,000 remaining.
        layers = [
            {"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 5000},
            {"contract_id": "B", "delivery_date": "2026-02-01", "qty_mt": 4000},
        ]
        result = core.fifo_allocate_inventory(layers, total_consumed=6000)
        lots_by_id = {lot["contract_id"]: lot for lot in result["lots"]}
        self.assertEqual(lots_by_id["A"]["remaining_mt"], 0)
        self.assertEqual(lots_by_id["A"]["consumed_mt"], 5000)
        self.assertEqual(lots_by_id["B"]["remaining_mt"], 3000)
        self.assertEqual(lots_by_id["B"]["consumed_mt"], 1000)
        self.assertEqual(result["unattributed_consumed_mt"], 0)
        self.assertEqual(result["skipped"], [])

    def test_oldest_first_regardless_of_input_order(self):
        # Same as above but layers passed in newest-first -- allocation
        # order must still be oldest delivery_date first.
        layers = [
            {"contract_id": "B", "delivery_date": "2026-02-01", "qty_mt": 4000},
            {"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 5000},
        ]
        result = core.fifo_allocate_inventory(layers, total_consumed=6000)
        self.assertEqual([lot["contract_id"] for lot in result["lots"]], ["A", "B"])

    def test_partial_consumption_of_a_single_contract(self):
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 5000}]
        result = core.fifo_allocate_inventory(layers, total_consumed=1200)
        lot = result["lots"][0]
        self.assertEqual(lot["consumed_mt"], 1200)
        self.assertEqual(lot["remaining_mt"], 3800)

    def test_fully_consumed_contract_has_zero_remaining_but_stays_listed(self):
        # A fully consumed lot must show remaining_mt == 0 (so it drops out
        # of *current* inventory math) while still appearing in the lots
        # list (so historical/realised reporting can still see it).
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 5000}]
        result = core.fifo_allocate_inventory(layers, total_consumed=5000)
        lot = result["lots"][0]
        self.assertEqual(lot["remaining_mt"], 0)
        self.assertEqual(lot["consumed_mt"], 5000)
        # And it's excluded from weighted-average current-inventory cost:
        avg = core.weighted_avg_cost([{"remaining_mt": lot["remaining_mt"],
                                        "cost_egp_mt": 13000}])
        self.assertIsNone(avg)

    def test_unattributed_consumption_when_exceeding_all_layers(self):
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 1000}]
        result = core.fifo_allocate_inventory(layers, total_consumed=1500)
        self.assertEqual(result["lots"][0]["remaining_mt"], 0)
        self.assertEqual(result["unattributed_consumed_mt"], 500)

    def test_layers_missing_data_are_skipped_not_dropped_silently(self):
        layers = [
            {"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 1000},
            {"contract_id": "BAD", "delivery_date": "", "qty_mt": 2000},
            {"contract_id": "BAD2", "delivery_date": "2026-01-05", "qty_mt": None},
        ]
        result = core.fifo_allocate_inventory(layers, total_consumed=0)
        self.assertEqual(len(result["lots"]), 1)
        self.assertIn("BAD", result["skipped"])
        self.assertIn("BAD2", result["skipped"])

    def test_negative_total_consumed_is_clamped_to_zero(self):
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 1000}]
        result = core.fifo_allocate_inventory(layers, total_consumed=-50)
        self.assertEqual(result["lots"][0]["remaining_mt"], 1000)

    def test_does_not_mutate_input_layers(self):
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 1000}]
        before = copy.deepcopy(layers)
        core.fifo_allocate_inventory(layers, total_consumed=400)
        self.assertEqual(layers, before)

    def test_commodity_isolation_via_separate_calls(self):
        # The engine takes pre-filtered layers for one commodity at a time;
        # two independent commodities must never influence each other.
        corn_layers = [{"contract_id": "C1", "delivery_date": "2026-01-01", "qty_mt": 1000}]
        soy_layers = [{"contract_id": "S1", "delivery_date": "2026-01-01", "qty_mt": 2000}]
        corn = core.fifo_allocate_inventory(corn_layers, total_consumed=1000)
        soy = core.fifo_allocate_inventory(soy_layers, total_consumed=100)
        self.assertEqual(corn["lots"][0]["remaining_mt"], 0)
        self.assertEqual(soy["lots"][0]["remaining_mt"], 1900)

    def test_reconciliation_identity_sums_to_total_inbound_minus_consumed(self):
        # This is the identity the dashboard-vs-drill-down reconciliation
        # (requirement #10/#12) depends on: total remaining + total
        # consumed-within-layers + unattributed == total inbound.
        layers = [
            {"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 5000},
            {"contract_id": "B", "delivery_date": "2026-02-01", "qty_mt": 4000},
            {"contract_id": "C", "delivery_date": "2026-03-01", "qty_mt": 2500},
        ]
        total_inbound = sum(l["qty_mt"] for l in layers)
        for consumed in (0, 3000, 5000, 6000, 11500, 20000):
            result = core.fifo_allocate_inventory(layers, total_consumed=consumed)
            total_remaining = sum(lot["remaining_mt"] for lot in result["lots"])
            total_consumed_in_lots = sum(lot["consumed_mt"] for lot in result["lots"])
            # remaining + consumed always reconstitutes total inbound MT,
            # regardless of over-consumption (unattributed is on top of
            # this, not part of it).
            self.assertAlmostEqual(total_remaining + total_consumed_in_lots, total_inbound)
            self.assertAlmostEqual(
                total_consumed_in_lots + result["unattributed_consumed_mt"],
                consumed)


class TestWeightedAvgCost(unittest.TestCase):
    def test_quantity_weighted_not_simple_average(self):
        # Two lots with very different quantities -- a simple arithmetic
        # mean of the two costs would be wrong (13,500); the correct
        # quantity-weighted figure is (3000*13000 + 1000*16000)/4000.
        lots = [
            {"remaining_mt": 3000, "cost_egp_mt": 13000},
            {"remaining_mt": 1000, "cost_egp_mt": 16000},
        ]
        avg = core.weighted_avg_cost(lots)
        self.assertAlmostEqual(avg, (3000 * 13000 + 1000 * 16000) / 4000)
        self.assertNotAlmostEqual(avg, 14500)  # the wrong, unweighted average

    def test_excludes_zero_and_negative_remaining(self):
        lots = [
            {"remaining_mt": 0, "cost_egp_mt": 99999},
            {"remaining_mt": -5, "cost_egp_mt": 99999},
            {"remaining_mt": 100, "cost_egp_mt": 14000},
        ]
        self.assertEqual(core.weighted_avg_cost(lots), 14000)

    def test_excludes_missing_cost_rather_than_treating_as_zero(self):
        lots = [
            {"remaining_mt": 100, "cost_egp_mt": None},
            {"remaining_mt": 200, "cost_egp_mt": 14000},
        ]
        self.assertEqual(core.weighted_avg_cost(lots), 14000)

    def test_returns_none_when_no_lot_qualifies(self):
        self.assertIsNone(core.weighted_avg_cost([]))
        self.assertIsNone(core.weighted_avg_cost([{"remaining_mt": 0, "cost_egp_mt": 100}]))


class TestContractLandedCost(unittest.TestCase):
    def test_matches_existing_own_after_formula(self):
        # own_after = cif * fx + discharge + clearance + freight
        cost = core.contract_landed_cost_egp_mt(
            cif_usd_mt=283.17, fx=50.45, discharge_egp_mt=100,
            clearance_egp_mt=50, freight_egp_mt=456)
        self.assertAlmostEqual(cost, 283.17 * 50.45 + 100 + 50 + 456)

    def test_none_when_cif_or_fx_missing(self):
        self.assertIsNone(core.contract_landed_cost_egp_mt(None, 50.0))
        self.assertIsNone(core.contract_landed_cost_egp_mt(283.0, None))

    def test_defaults_missing_fees_to_zero(self):
        cost = core.contract_landed_cost_egp_mt(cif_usd_mt=100, fx=50)
        self.assertEqual(cost, 5000)


class TestInventoryEdge(unittest.TestCase):
    def test_positive_edge_when_inventory_cheaper_than_local(self):
        edge = core.inventory_edge(local_price_egp_mt=15000,
                                    weighted_avg_cost_egp_mt=14000,
                                    remaining_mt=3000)
        self.assertAlmostEqual(edge["edge_per_mt"], 1000)
        self.assertAlmostEqual(edge["edge_total"], 3_000_000)

    def test_negative_edge_when_local_is_cheaper(self):
        edge = core.inventory_edge(local_price_egp_mt=13000,
                                    weighted_avg_cost_egp_mt=14000,
                                    remaining_mt=3000)
        self.assertAlmostEqual(edge["edge_per_mt"], -1000)
        self.assertAlmostEqual(edge["edge_total"], -3_000_000)

    def test_none_when_local_or_cost_missing(self):
        edge = core.inventory_edge(None, 14000, 3000)
        self.assertIsNone(edge["edge_per_mt"])
        self.assertIsNone(edge["edge_total"])


class TestReplacementCif(unittest.TestCase):
    def test_corn_formula(self):
        # (CBOT + premium) x 0.3937
        val = core.replacement_cif_usd_mt("CORN", cbot=450.0, premium=80.0)
        self.assertAlmostEqual(val, (450.0 + 80.0) * 0.3937)

    def test_soybean_and_wheat_share_factor(self):
        soy = core.replacement_cif_usd_mt("SOYBEAN", cbot=1050.0, premium=60.0)
        wheat = core.replacement_cif_usd_mt("WHEAT", cbot=600.0, premium=40.0)
        self.assertAlmostEqual(soy, (1050.0 + 60.0) * 0.36745)
        self.assertAlmostEqual(wheat, (600.0 + 40.0) * 0.36745)

    def test_sbm_formula(self):
        val = core.replacement_cif_usd_mt("SBM", cbot=310.0, premium=15.0)
        self.assertAlmostEqual(val, (310.0 + 15.0) * 1.1023)

    def test_never_invents_a_missing_premium(self):
        self.assertIsNone(core.replacement_cif_usd_mt("CORN", cbot=450.0, premium=None))
        self.assertIsNone(core.replacement_cif_usd_mt("CORN", cbot=None, premium=80.0))


class TestScenarioPurchaseCost(unittest.TestCase):
    def test_combines_replacement_cif_and_landed_cost(self):
        cost = core.scenario_purchase_cost_egp_mt(
            "CORN", cbot=450.0, premium=80.0, fx=50.0,
            freight_egp_mt=456.0, discharge_egp_mt=100.0, clearance_egp_mt=50.0)
        expected_cif = (450.0 + 80.0) * 0.3937
        expected = expected_cif * 50.0 + 100.0 + 50.0 + 456.0
        self.assertAlmostEqual(cost, expected)

    def test_none_when_inputs_incomplete(self):
        self.assertIsNone(core.scenario_purchase_cost_egp_mt(
            "CORN", cbot=None, premium=80.0, fx=50.0))


class TestFreightVat(unittest.TestCase):
    def test_default_14_percent(self):
        # Base freight = 400 EGP/MT, VAT = 56, final = 456.
        self.assertAlmostEqual(core.freight_incl_vat(400), 456.0)

    def test_custom_vat_pct(self):
        self.assertAlmostEqual(core.freight_incl_vat(400, vat_pct=10), 440.0)

    def test_all_in_mode_means_this_function_is_simply_not_called(self):
        # "All-In" freight entry: the UI writes the user's number straight
        # into freight_egp_mt without ever calling freight_incl_vat, and
        # contract_landed_cost_egp_mt() adds freight_egp_mt raw -- so a
        # 456 all-in entry must land in the landed-cost formula as exactly
        # 456, never as 456 * 1.14 (519.84). This test locks that in by
        # checking landed cost is identical whether freight_egp_mt came
        # from freight_incl_vat(400) or was typed in directly as 456.
        detailed_freight = core.freight_incl_vat(400)  # -> 456
        all_in_freight = 456.0
        self.assertAlmostEqual(detailed_freight, all_in_freight)
        cost_detailed = core.contract_landed_cost_egp_mt(
            cif_usd_mt=100, fx=50, freight_egp_mt=detailed_freight)
        cost_all_in = core.contract_landed_cost_egp_mt(
            cif_usd_mt=100, fx=50, freight_egp_mt=all_in_freight)
        self.assertAlmostEqual(cost_detailed, cost_all_in)
        self.assertNotAlmostEqual(cost_all_in, 100 * 50 + 456.0 * 1.14)

    def test_none_when_base_missing(self):
        self.assertIsNone(core.freight_incl_vat(None))


class TestPurityForScenarioReset(unittest.TestCase):
    """Every core function must be side-effect-free: a Scenario Lab that
    only ever calls these functions with different arguments can never
    accidentally mutate saved contracts/history, which is what backs the
    "scenario reset must not modify app_state.json" requirement at the
    engine level. (An end-to-end check against the real state_obj is
    added once the Scenario Lab UI exists.)"""

    def test_dict_and_list_arguments_are_never_mutated(self):
        layers = [{"contract_id": "A", "delivery_date": "2026-01-01", "qty_mt": 1000}]
        lots = [{"remaining_mt": 100, "cost_egp_mt": 14000}]
        layers_before, lots_before = copy.deepcopy(layers), copy.deepcopy(lots)
        core.fifo_allocate_inventory(layers, total_consumed=500)
        core.weighted_avg_cost(lots)
        self.assertEqual(layers, layers_before)
        self.assertEqual(lots, lots_before)


if __name__ == "__main__":
    unittest.main()
