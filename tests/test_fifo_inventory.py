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


# ── physical counts reset the daily-rate walk ─────────────────────────────
def _count_lots():
    return [{"lot_id": "CONTRACT-A", "contract_id": "A", "commodity": "CORN-BRZ", "delivery_date": "2026-11-01",
             "original_mt": 2000.0, "cost_egp_mt": 14000.0},
            {"lot_id": "CONTRACT-B", "contract_id": "B", "commodity": "CORN-BRZ", "delivery_date": "2026-11-03",
             "original_mt": 2000.0, "cost_egp_mt": 14500.0}]


def _count(day, qty, comm="CORN-BRZ"):
    return {"date": day, "commodity": comm, "is_adjustment": True, "adjusted_qty": qty}


def _walk(counts, as_of="2026-11-06"):
    return build_daily_fifo_inventory(_count_lots(), events=[], consumption_rates={"CORN-BRZ": 500.0}, as_of=as_of,
                                      estimate_daily=True, record_draws=True, start_on_delivery=True,
                                      count_events=counts)["CORN"]


def test_count_above_the_model_gives_tonnes_back_to_the_newest_cargo():
    plain = _walk(None, as_of="2026-11-04")
    assert plain["remaining_mt"] == 2000.0                       # 4 days × 500 drawn from A
    row = _walk([_count("2026-11-04", 3000.0)], as_of="2026-11-04")
    assert row["remaining_mt"] == 3000.0
    left = {l["contract_id"]: l["remaining_mt"] for l in row["layers"]}
    assert left == {"A": 1000.0, "B": 2000.0}                    # FIFO: the newest cargo is what is left
    assert sum(d["mt"] for d in row["draws"] if d["lot_id"] == "CONTRACT-A") == 1000.0
    assert row["count_resets"] == [{"date": "2026-11-04", "counted_mt": 3000.0, "modelled_mt": 2000.0,
                                    "difference_mt": 1000.0}]
    after = _walk([_count("2026-11-04", 3000.0)], as_of="2026-11-06")    # the estimate carries on from the count
    assert after["remaining_mt"] == 2000.0


def test_count_below_the_model_draws_the_difference_from_the_oldest():
    row = _walk([_count("2026-11-04", 1500.0)], as_of="2026-11-04")
    assert row["remaining_mt"] == 1500.0
    assert {l["contract_id"]: l["remaining_mt"] for l in row["layers"]} == {"B": 1500.0}
    counted = [d for d in row["draws"] if d["kind"] == "count"]
    assert sum(d["mt"] for d in counted) == 500.0 and counted[0]["date"].isoformat() == "2026-11-04"


def test_count_beyond_every_receipt_is_an_unknown_cost_lot():
    row = _walk([_count("2026-11-04", 5000.0)], as_of="2026-11-04")
    assert row["remaining_mt"] == 5000.0
    phys = [l for l in row["layers"] if l.get("source") == "physical_adjustment_unallocated"]
    assert phys and phys[0]["remaining_mt"] == 1000.0
    assert any("exceeds identified receipts by 1,000 MT" in i for i in row["issues"])


def test_counts_of_the_corn_keys_on_one_day_are_added_up():
    row = _walk([_count("2026-11-04", 2500.0), _count("2026-11-04", 500.0, "CORN"),
                 _count("2026-11-04", 0.0, "CORN-ARG")], as_of="2026-11-04")
    assert row["remaining_mt"] == 3000.0
    assert _walk(None)["count_resets"] == []
