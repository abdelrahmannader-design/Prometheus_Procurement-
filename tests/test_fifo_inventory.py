from __future__ import annotations

import datetime as dt
import unittest

from prometheus_core import (
    build_daily_fifo_inventory,
    effective_freight_egp_mt,
    calculate_inventory_scenario,
    inventory_market_layer_metrics,
)


class FifoInventoryTests(unittest.TestCase):
    def test_closed_and_open_delivered_both_count_future_is_inbound(self):
        lots = [
            {"contract_id":"A","contract_ref":"A","commodity":"CORN-BRZ","delivery_date":"2026-09-01","original_mt":500,"cost_egp_mt":13000,"status":"Closed"},
            {"contract_id":"B","contract_ref":"B","commodity":"CORN-ARG","delivery_date":"2026-09-02","original_mt":400,"cost_egp_mt":14000,"status":"Open"},
            {"contract_id":"C","contract_ref":"C","commodity":"CORN-BRZ","delivery_date":"2026-09-10","original_mt":300,"cost_egp_mt":15000,"status":"Open"},
        ]
        rows = build_daily_fifo_inventory(lots, as_of="2026-09-08", estimate_daily=False)
        corn = rows["CORN"]
        self.assertEqual(corn["remaining_mt"], 900)
        self.assertEqual(corn["inbound_mt"], 300)
        self.assertEqual(corn["oldest"]["contract_id"], "A")
        self.assertEqual(corn["newest"]["contract_id"], "B")

    def test_physical_baseline_reconciles_oldest_first_then_actual_consumption(self):
        lots = [
            {"contract_id":"A","commodity":"CORN-BRZ","delivery_date":"2026-06-01","original_mt":500,"cost_egp_mt":13000},
            {"contract_id":"B","commodity":"CORN-ARG","delivery_date":"2026-06-15","original_mt":500,"cost_egp_mt":14000},
            {"contract_id":"C","commodity":"CORN-BRZ","delivery_date":"2026-07-03","original_mt":300,"cost_egp_mt":15000},
        ]
        events = [
            {"date":"2026-06-30","commodity":"CORN-BRZ","is_adjustment":True,"adjusted_qty":600},
            {"date":"2026-06-30","commodity":"CORN","is_adjustment":True,"adjusted_qty":300},
            {"date":"2026-07-02","commodity":"CORN","consumed_mt":200,"received_mt":0},
        ]
        corn = build_daily_fifo_inventory(lots, events, as_of="2026-07-05", estimate_daily=False)["CORN"]
        # 1000 historical receipts -> 900 physical baseline consumes 100 from A;
        # then 200 actual consumption consumes another 200 from A; C arrives later.
        self.assertAlmostEqual(corn["remaining_mt"], 1000)
        by_id = {r.get("contract_id"): r for r in corn["layers"]}
        self.assertAlmostEqual(by_id["A"]["remaining_mt"], 200)
        self.assertAlmostEqual(by_id["B"]["remaining_mt"], 500)
        self.assertAlmostEqual(by_id["C"]["remaining_mt"], 300)
        self.assertEqual(corn["oldest"]["contract_id"], "A")
        self.assertEqual(corn["newest"]["contract_id"], "C")

    def test_daily_estimate_depletes_fifo_without_mutating_events(self):
        lots = [{"contract_id":"A","commodity":"SBM","delivery_date":"2026-06-30","original_mt":500,"cost_egp_mt":20000}]
        events = [{"date":"2026-06-30","commodity":"SBM","is_adjustment":True,"adjusted_qty":500}]
        original = [dict(events[0])]
        row = build_daily_fifo_inventory(lots, events, {"SBM":100}, as_of="2026-07-03", estimate_daily=True)["SBM"]
        self.assertEqual(row["status"], "ESTIMATED")
        self.assertEqual(row["estimate_days"], 3)
        self.assertEqual(row["remaining_mt"], 200)
        self.assertEqual(events, original)

    def test_weighted_average_uses_remaining_quantity(self):
        lots = [
            {"contract_id":"A","commodity":"SOYBEAN","delivery_date":"2026-01-01","original_mt":100,"cost_egp_mt":10000},
            {"contract_id":"B","commodity":"SOYBEAN","delivery_date":"2026-01-02","original_mt":300,"cost_egp_mt":14000},
        ]
        events = [{"date":"2026-01-03","commodity":"SOYBEAN","consumed_mt":50}]
        row = build_daily_fifo_inventory(lots, events, as_of="2026-01-03", estimate_daily=False)["SOYBEAN"]
        expected = (50*10000 + 300*14000) / 350
        self.assertAlmostEqual(row["weighted_avg_cost_egp_mt"], expected)


class FreightVatTests(unittest.TestCase):
    def test_detailed_adds_vat_once(self):
        self.assertAlmostEqual(effective_freight_egp_mt(400, "DETAILED", 14), 456)

    def test_all_in_does_not_add_vat_again(self):
        self.assertAlmostEqual(effective_freight_egp_mt(456, "ALL_IN", 14, 456), 456)

    def test_legacy_is_unchanged(self):
        self.assertAlmostEqual(effective_freight_egp_mt(425.53, "LEGACY", 14), 425.53)


class InventoryVsMarketTests(unittest.TestCase):
    def test_positive_edges_mean_owned_inventory_is_cheaper(self):
        r = inventory_market_layer_metrics(
            remaining_mt=1000, fifo_cost_egp_mt=14000,
            cbot=500, premium=200, conversion_factor=0.3937, fx=50,
            freight_egp_mt=456, discharge_egp_mt=200, clearance_egp_mt=200,
            local_egp_mt=15000)
        expected_cif = (500 + 200) * 0.3937
        expected_replacement = expected_cif * 50 + 456 + 200 + 200
        self.assertAlmostEqual(r["replacement_cif_usd_mt"], expected_cif)
        self.assertAlmostEqual(r["replacement_cost_egp_mt"], expected_replacement)
        self.assertEqual(r["inventory_vs_local_egp_mt"], 1000)
        self.assertEqual(r["inventory_vs_local_egp"], 1_000_000)
        self.assertAlmostEqual(r["inventory_vs_replacement_egp_mt"], expected_replacement - 14000)
        self.assertEqual(r["decision"], "Ahead of local + CBOT")

    def test_missing_premium_does_not_invent_cbot_replacement(self):
        r = inventory_market_layer_metrics(
            remaining_mt=500, fifo_cost_egp_mt=14500, cbot=520, premium=None,
            conversion_factor=0.3937, fx=50, freight_egp_mt=456,
            discharge_egp_mt=200, clearance_egp_mt=200, local_egp_mt=15000)
        self.assertIsNone(r["replacement_cost_egp_mt"])
        self.assertEqual(r["inventory_vs_local_egp_mt"], 500)
        self.assertEqual(r["decision"], "Ahead of local")


class ScenarioTests(unittest.TestCase):
    def test_explicit_consumption_wins_over_horizon(self):
        r = calculate_inventory_scenario(
            current_remaining_mt=1000,
            avg_inventory_cost_egp_mt=13000,
            local_base_egp_mt=14000,
            local_transport_egp_mt=500,
            cbot=500,
            premium=200,
            conversion_factor=0.3937,
            fx=50,
            freight_input_egp_mt=400,
            freight_mode="DETAILED",
            freight_vat_pct=14,
            other_fees_egp_mt=400,
            purchase_qty_mt=500,
            consumption_qty_mt=200,
            horizon_days=30,
            daily_consumption_mt=100,
        )
        self.assertEqual(r["projected_consumption_mt"], 200)
        self.assertEqual(r["projected_inventory_mt"], 1300)
        self.assertAlmostEqual(r["effective_freight_egp_mt"], 456)

    def test_scenario_horizon_used_when_explicit_consumption_zero(self):
        r = calculate_inventory_scenario(
            current_remaining_mt=1000, avg_inventory_cost_egp_mt=13000,
            local_base_egp_mt=14000, local_transport_egp_mt=0,
            cbot=500, premium=200, conversion_factor=0.3937, fx=50,
            freight_input_egp_mt=456, freight_mode="ALL_IN", freight_vat_pct=14,
            purchase_qty_mt=0, consumption_qty_mt=0, horizon_days=3,
            daily_consumption_mt=100,
        )
        self.assertEqual(r["projected_consumption_mt"], 300)
        self.assertEqual(r["projected_inventory_mt"], 700)
        self.assertAlmostEqual(r["effective_freight_egp_mt"], 456)


if __name__ == "__main__":
    unittest.main()
