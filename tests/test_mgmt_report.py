"""Management savings report: traceable rows only, comparable CBOT only."""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core import mgmt_report as mr

D = dt.date


class CalendarTests(unittest.TestCase):
    def test_expiry_and_first_notice(self):
        self.assertEqual(mr.last_trade_day(2026, 12), D(2026, 12, 14))
        self.assertEqual(mr.first_notice_day(2026, 12), D(2026, 11, 30))
        self.assertEqual(mr.last_trade_day(2026, 3), D(2026, 3, 13))  # 14th is a Saturday

    def test_month_labels_as_recorded(self):
        self.assertEqual(mr.parse_futures_month("MAY-26"), (5, 2026))
        self.assertEqual(mr.parse_futures_month("Sep"), (9, None))
        self.assertEqual(mr.parse_futures_month("March"), (3, None))
        self.assertEqual(mr.parse_futures_month("Z26"), (12, 2026))
        self.assertIsNone(mr.parse_futures_month(""))

    def test_a_missing_year_is_inferred_and_said_so(self):
        cm = mr.resolve_contract_month("DEC", "CORN", "2026-01-12")
        self.assertEqual((cm["code"], cm["inferred"]), ("DEC-25", True))
        self.assertEqual(mr.resolve_contract_month("DEC", "CORN", "2026-10-20")["code"], "DEC-26")

    def test_a_month_corn_does_not_trade_is_rejected(self):
        self.assertIsNone(mr.resolve_contract_month("AUG", "CORN", "2026-06-01"))

    def test_only_days_on_the_contracts_own_month_are_comparable(self):
        cm = mr.resolve_contract_month("DEC-26", "CORN", None)
        self.assertEqual(mr.benchmark_status(D(2026, 10, 20), "CORN", cm), (mr.MATCHED, True))
        self.assertFalse(mr.benchmark_status(D(2026, 12, 5), "CORN", cm)[1])   # roll window
        self.assertIn("expired", mr.benchmark_status(D(2026, 12, 20), "CORN", cm)[0])
        self.assertIn("earlier month", mr.benchmark_status(D(2026, 8, 1), "CORN", cm)[0])


class FixingTests(unittest.TestCase):
    def base(self, **kw):
        return dict({"base": "CORN", "qty_mt": 3000, "cif_usd_mt": 285.0, "premium": 207.0,
                     "pricing_status": "PRICED"}, **kw)

    def test_the_user_example_is_implied_without_a_pricing_date(self):
        f = mr.fixing(self.base())
        self.assertTrue(f["fixed"])
        self.assertAlmostEqual(f["value"], 285 / 0.3937 - 207, places=6)
        self.assertEqual(f["type"], "Implied")
        self.assertFalse(f["pricing_date_known"])

    def test_an_unpriced_contract_is_not_fixed_but_shows_an_indicative(self):
        f = mr.fixing(self.base(pricing_status="UNPRICED"))
        self.assertFalse(f["fixed"])
        self.assertIsNone(f["value"])
        self.assertAlmostEqual(f["indicative"], 285 / 0.3937 - 207, places=6)

    def test_lots_give_the_tonne_weighted_recorded_fixing(self):
        lots = [{"qty_mt": 1000, "cbot": 530.0}, {"qty_mt": 1500, "cbot": 520.0}]
        f = mr.fixing(self.base(pricing_lots=lots, pricing_status="PARTIAL"))
        self.assertEqual(f["type"], "Recorded")
        self.assertAlmostEqual(f["value"], (530 * 1000 + 520 * 1500) / 2500)
        self.assertIn("2,500 of 3,000", f["status"])

    def test_a_final_cif_on_a_part_priced_contract_wins_over_the_lots(self):
        lots = [{"qty_mt": 1000, "cbot": 530.0}, {"qty_mt": 1500, "cbot": 520.0}]
        f = mr.fixing(self.base(pricing_lots=lots, pricing_status="PARTIAL", final_cif_over_lots=True))
        self.assertEqual(f["type"], "Implied")
        self.assertAlmostEqual(f["value"], 285 / 0.3937 - 207, places=6)
        self.assertIn("final CIF", f["status"])

    def test_flat_price_is_not_eligible(self):
        f = mr.fixing({"base": "SBM", "qty_mt": 500, "cif_usd_mt": 410, "premium": 0,
                       "premium_label": "FLAT", "pricing_status": "PRICED"})
        self.assertFalse(f["eligible"])

    def test_sbm_uses_its_own_factor_and_unit(self):
        f = mr.fixing({"base": "SBM", "qty_mt": 500, "cif_usd_mt": 409.39, "premium": 79,
                       "pricing_status": "PRICED"})
        self.assertAlmostEqual(f["value"], 409.39 / 1.1023 - 79, places=6)
        self.assertEqual(f["unit"], "$/short ton")

    def test_a_premium_in_the_wrong_units_is_caught(self):
        f = mr.fixing(self.base(cif_usd_mt=250.0, premium=600.0))
        self.assertFalse(f["fixed"])
        self.assertIn("units", f["status"])


def inputs(**over):
    """Two corn contracts; one day has no cargo, one has no local price."""
    contracts = [
        {"id": "C1", "contract": "A-1", "supplier": "S", "commodity": "CORN-BRZ", "base": "CORN",
         "origin": "BRAZIL", "status": "Closed", "is_open": False, "pricing_status": "PRICED",
         "qty_mt": 1000.0, "delivery_date": "2026-10-01", "storage_start": "2026-10-01",
         "futures_month": "DEC", "cif_usd_mt": 285.0, "premium": 207.0, "cif_final": True,
         "fx": 50.0, "landed_egp_mt": 15000.0, "source_id": "contracts.C1",
         "freight_egp_mt": 400.0, "discharge_egp_mt": 200.0, "clearance_egp_mt": 150.0, "form4_fx": 50.0},
        {"id": "C2", "contract": "B-2", "supplier": "S", "commodity": "CORN-BRZ", "base": "CORN",
         "origin": "BRAZIL", "status": "Open", "is_open": True, "pricing_status": "UNPRICED",
         "qty_mt": 1000.0, "delivery_date": "2026-10-03", "storage_start": "2026-10-03",
         "futures_month": "DEC", "cif_usd_mt": 250.0, "premium": 180.0, "cif_final": False,
         "fx": 50.0, "landed_egp_mt": 14000.0, "landed_today": 14100.0, "local_today": 15000.0,
         "local_today_price": 14676.87, "local_today_transport": 323.13,
         "local_today_date": "2026-10-04", "source_id": "contracts.C2",
         "freight_egp_mt": 400.0, "discharge_egp_mt": 200.0, "clearance_egp_mt": 150.0},
    ]
    local = {"price": 15500.0, "date": "2026-10-01", "key": "CORN-BRZ"}
    draws = [
        {"date": D(2026, 9, 30), "lot_id": "", "mt": 500.0, "kind": "estimated", "base": "CORN"},
        {"date": D(2026, 10, 1), "lot_id": "CONTRACT-C1", "mt": 500.0, "kind": "estimated", "base": "CORN", "local": local},
        {"date": D(2026, 10, 2), "lot_id": "CONTRACT-C1", "mt": 500.0, "kind": "estimated", "base": "CORN", "local": {}},
        {"date": D(2026, 10, 3), "lot_id": "CONTRACT-C2", "mt": 500.0, "kind": "estimated", "base": "CORN",
         "local": dict(local, date="2026-10-01")},
    ]
    cbot = [(D(2026, 9, 28) + dt.timedelta(days=i), 520.0) for i in range(10)]
    inp = {"as_of": "2026-10-04", "contracts": contracts, "draws": draws, "cbot": {"CORN": cbot},
           "latest_fx": {"rate": 52.0, "date": "2026-10-04", "source": "fx_history"},
           "local_obs": [{"key": "CORN-BRZ", "base": "CORN", "date": "2026-10-01", "price": 15176.87,
                          "transport": 323.13, "delivered": 15500.0, "source": "manual",
                          "source_id": "local_prices[7]", "status": "Observed"}],
           "stock_by_contract": {"C1": 0.0, "C2": 500.0}}
    inp.update(over)
    return inp


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.m = mr.build(inputs())

    def test_unsourced_consumption_is_excluded_not_valued(self):
        self.assertTrue(all(a["contract_id"] in ("C1", "C2") for a in self.m["allocations"]))
        cats = [e["category"] for e in self.m["excluded"]]
        self.assertIn("Unsourced consumption", cats)
        audit = self.m["audit"][0]
        self.assertAlmostEqual(audit["consumed_mt"], 2000)
        self.assertAlmostEqual(audit["allocated_mt"] + audit["excluded_mt"], 2000)

    def test_a_day_without_a_local_price_is_excluded_not_zero(self):
        days = [s["date"] for s in self.m["savings"]]
        self.assertNotIn("2026-10-02", days)
        self.assertIn("No usable local price", [e["category"] for e in self.m["excluded"]])

    def test_daily_saving_is_local_less_landed_times_tonnes(self):
        s = next(r for r in self.m["savings"] if r["date"] == "2026-10-01")
        self.assertAlmostEqual(s["saving"], (15500 - 15000) * 500)
        later = next(r for r in self.m["savings"] if r["date"] == "2026-10-03")
        self.assertEqual(later["local_status"], "Last price in force (2 d)")
        self.assertEqual(later["cif_basis"], mr.PROVISIONAL)

    def test_the_last_local_price_stays_in_force_however_old(self):
        """No new local price means no change: a 40-day-old price is still the price."""
        inp = inputs()
        inp["draws"][1]["local"] = {"price": 15500.0, "date": "2026-08-22", "key": "CORN-BRZ"}
        inp["local_obs"].append({"key": "CORN-BRZ", "date": "2026-08-22", "source_id": "local_prices[3]"})
        row = next(s for s in mr.build(inp)["savings"] if s["date"] == "2026-10-01")
        self.assertEqual(row["local_status"], "STALE — 40 days old (last price in force)")
        self.assertTrue(row["local_stale"])
        self.assertAlmostEqual(row["saving"], (15500 - 15000) * 500)

    def test_cbot_only_for_fixed_contracts_and_month_matched_days(self):
        rows = self.m["cbot"]
        self.assertEqual({r["contract_id"] for r in rows}, {"C1"})
        r = rows[0]
        fix = 285 / 0.3937 - 207
        self.assertTrue(r["assessable"])
        self.assertAlmostEqual(r["diff"], 520 - fix)
        self.assertAlmostEqual(r["usd"], (520 - fix) * 0.3937 * 500)
        self.assertEqual(r["result"], "Advantage")

    def test_unpriced_contract_is_valued_at_latest_cbot_plus_premium_and_latest_fx(self):
        o = next(r for r in self.m["open"] if r["contract_id"] == "C2")
        self.assertEqual(o["class"], "Indicative (unpriced)")
        cif = (520.0 + 180.0) * 0.3937                       # latest CBOT + premium
        self.assertAlmostEqual(o["cif"], cif)
        self.assertEqual(o["fx_basis"], "Latest market FX — provisional (Form 4 pending)")
        self.assertAlmostEqual(o["cost_excl"], cif * 52.0 + 200 + 150)
        self.assertAlmostEqual(o["cost_incl"], cif * 52.0 + 200 + 150 + 400)
        self.assertAlmostEqual(o["potential"], (15000 - o["cost_incl"]) * 500)
        self.assertAlmostEqual(o["potential_excl"], (14676.87 - o["cost_excl"]) * 500)
        self.assertIn("on DEC-26 (front month)", o["cbot_note"])   # 7 Oct: DEC is the front month
        inp = inputs()
        inp["contracts"][1]["futures_month"] = "MAR-27"
        o2 = next(r for r in mr.build(inp)["open"] if r["contract_id"] == "C2")
        self.assertIn("Indicative proxy", o2["cbot_note"])          # MAR-27 is not stored
        self.assertEqual(self.m["kpis"]["open_fixed_potential_egp"], 0)

    def test_a_recorded_form4_wins_over_the_latest_fx(self):
        inp = inputs()
        inp["contracts"][1]["form4_fx"] = 51.0
        o = next(r for r in mr.build(inp)["open"] if r["contract_id"] == "C2")
        self.assertEqual((o["fx"], o["fx_basis"]), (51.0, "Form 4"))

    def test_both_transport_scenarios_use_each_sides_own_transport(self):
        s = next(r for r in self.m["savings"] if r["date"] == "2026-10-01")
        self.assertAlmostEqual(s["cost_excl"], 15000 - 400)          # CIF incl. ocean freight kept
        self.assertAlmostEqual(s["local_excl"], 15176.87)
        self.assertAlmostEqual(s["saving_excl"], (15176.87 - 14600) * 500)
        self.assertAlmostEqual(s["saving"] - s["saving_excl"], (323.13 - 400) * 500)

    def test_an_unreceived_contract_gets_a_current_market_valuation_only(self):
        inp = inputs()
        inp["contracts"][1].update(storage_start="", delivery_date="2026-10-03", is_open=True)
        inp["draws"] = [d for d in inp["draws"] if d.get("lot_id") != "CONTRACT-C2"]
        inp["stock_by_contract"] = {"C1": 0.0}
        m = mr.build(inp)
        c2 = next(c for c in m["contracts"] if c["id"] == "C2")
        self.assertEqual((c2["storage_status"], c2["received"], c2["consumed_mt"]), ("Not recorded", False, 0))
        o = next(r for r in m["open"] if r["contract_id"] == "C2")
        self.assertTrue(o["class"].startswith("Current market valuation"))
        self.assertAlmostEqual(o["unconsumed_mt"], 1000.0)
        self.assertNotIn("C2", {r["contract_id"] for r in m["savings"]})

    def test_consumption_without_storage_start_is_flagged_not_reclassified(self):
        inp = inputs()
        inp["contracts"][0]["storage_start"] = ""
        m = mr.build(inp)
        c1 = next(c for c in m["contracts"] if c["id"] == "C1")
        self.assertTrue(any("reconcile" in f for f in c1["flags"]))
        self.assertIn("C1", {r["contract_id"] for r in m["savings"]})

    def test_pricing_classes(self):
        self.assertEqual(next(c for c in self.m["contracts"] if c["id"] == "C1")["pricing_class"], "Fixed")
        self.assertEqual(next(c for c in self.m["contracts"] if c["id"] == "C2")["pricing_class"], "Unpriced")

    def test_the_report_passes_its_own_validation(self):
        failed = [v for v in self.m["validation"] if not v["passed"]]
        self.assertEqual(failed, [])
        self.assertTrue(self.m["management_ready"])

    def test_a_contract_over_allocated_fails_validation(self):
        inp = inputs()
        inp["contracts"][0]["qty_mt"] = 400.0
        m = mr.build(inp)
        self.assertFalse(m["management_ready"])


if __name__ == "__main__":
    unittest.main()


class EquivalentPremiumTests(unittest.TestCase):
    def test_local_price_as_a_cif_premium_over_the_days_cbot(self):
        c = {"base": "CORN", "premium": 150.0, "discharge_egp_mt": 300.0, "clearance_egp_mt": 200.0,
             "fix": {"eligible": True}}
        day = dt.date(2026, 10, 28)
        out = mr.equivalent_premium(c, 15000.0, day, lambda b, d: (400.0, d), lambda d: (50.0, d))
        self.assertAlmostEqual(out["eq_premium"], (15000 - 500) / 50 / 0.3937 - 400)
        self.assertAlmostEqual(out["eq_premium_gross"], 15000 / 50 / 0.3937 - 400)
        self.assertAlmostEqual(out["premium_gap"], out["eq_premium"] - 150)
        self.assertEqual(out["premium_unit"], "¢/bu")

    def test_missing_cbot_or_fx_is_not_assessed_and_flat_contracts_get_no_premium(self):
        flat = {"base": "SBM", "premium": 0.0, "fix": {"eligible": False}}
        out = mr.equivalent_premium(flat, 27000.0, dt.date(2026, 10, 28), lambda b, d: (None, None), lambda d: (55.0, d))
        self.assertIsNone(out["eq_premium"]); self.assertIsNone(out["contract_premium"]); self.assertIsNone(out["premium_gap"])
        sfm = mr.equivalent_premium({"base": "SFM", "fix": {"eligible": False}}, 20000.0, dt.date(2026, 10, 28),
                                    lambda b, d: (1.0, d), lambda d: (50.0, d))
        self.assertIsNone(sfm["premium_factor"]); self.assertIsNone(sfm["eq_premium"])


class UnfixedConsumptionTests(unittest.TestCase):
    def test_consumed_unpriced_days_are_listed_apart_from_the_cbot_totals(self):
        m = mr.build(inputs())
        un = [r for r in m["cbot_unfixed"] if r["contract_id"] == "C2"]
        if not un:
            self.skipTest("fixture has no consumption on the unpriced contract")
        self.assertTrue(all(r["contract_id"] not in {x["contract_id"] for x in m["cbot"]} for r in un))
        for r in un:
            if r["ind_diff"] is not None:
                self.assertAlmostEqual(r["ind_diff"], r["cbot"] - r["latest_cbot"])
                self.assertAlmostEqual(r["ind_usd"], r["ind_diff"] * r["factor"] * r["mt"])
        self.assertAlmostEqual(m["kpis"]["cbot_net_usd"], sum(r["usd"] for r in m["cbot"] if r["assessable"]))


class BreakEvenTests(unittest.TestCase):
    def test_break_even_cbot_and_headroom_for_an_unpriced_contract(self):
        c = {"base": "CORN", "pricing_class": "Unpriced"}
        f = {"fixed": False, "value": None}
        out = mr.break_even(c, 197.0, f, 449.5, 56.0, 235.0, 200.0, 485.0, 15200.0, 15597.0)
        be_x = (15200 - 435) / 56 / 0.3937 - 197
        be_i = (15597 - 435 - 485) / 56 / 0.3937 - 197
        self.assertAlmostEqual(out["be_cbot_excl"], be_x)
        self.assertAlmostEqual(out["be_cbot_incl"], be_i)
        self.assertAlmostEqual(out["headroom_excl"], be_x - 449.5)
        self.assertAlmostEqual(out["local_eq_premium"], (15200 - 435) / 56 / 0.3937 - 449.5)
        self.assertAlmostEqual(out["premium_gap_now"], out["headroom_excl"])
        self.assertEqual(out["ref_cbot_basis"], "latest stored CBOT")

    def test_fixed_contracts_measure_headroom_from_their_fixing_and_flat_ones_get_none(self):
        out = mr.break_even({"base": "CORN", "pricing_class": "Fixed"}, 190.0, {"fixed": True, "value": 430.0},
                            449.5, 56.0, 235.0, 200.0, 485.0, 15200.0, 15597.0)
        self.assertEqual(out["ref_cbot"], 430.0)
        flat = mr.break_even({"base": "SBM", "pricing_class": "Flat-priced"}, 0.0, {"fixed": False}, 330.0, 56.0, 0, 0, 370.0, 27000.0, 27370.0)
        self.assertIsNone(flat["be_cbot_excl"])

    def test_an_open_contract_without_dates_reads_its_futures_month_against_today(self):
        cm = mr.resolve_contract_month("DEC", "CORN", "2026-11-02")
        self.assertEqual(cm["code"], "DEC-26")


class StorageWindowBenchmarkTests(unittest.TestCase):
    def test_second_benchmark_averages_cbot_from_storage_date_to_last_consumption(self):
        inp = inputs()
        m = mr.build(inp)
        rows = [r for r in m["cbot"] if r.get("win_cbot") is not None]
        self.assertTrue(rows)
        for cid in {r["contract_id"] for r in rows}:
            rs = [r for r in rows if r["contract_id"] == cid]
            c = next(x for x in inp["contracts"] if x["id"] == cid)
            start = dt.date.fromisoformat(str(c.get("storage_start") or min(r["date"] for r in rs))[:10])
            end = max(dt.date.fromisoformat(r["date"]) for r in rs)
            pts = [p for d, p in inp["cbot"][rs[0]["base"]] if start <= d <= end]
            if pts:
                self.assertAlmostEqual(rs[0]["win_cbot"], sum(pts) / len(pts), places=6)
            self.assertEqual(len({r["win_cbot"] for r in rs}), 1)
            for r in rs:
                self.assertAlmostEqual(r["win_usd"], (r["win_cbot"] - r["fix"]) * r["factor"] * r["mt"], places=6)
                self.assertEqual(r["win_start"], start.isoformat())
        self.assertAlmostEqual(m["kpis"]["cbot_win_net_usd"], sum(r["win_usd"] for r in rows), places=6)

    def test_the_consumption_day_benchmark_is_unchanged(self):
        m = mr.build(inputs())
        self.assertEqual(mr.MATCHED, "Consumption-day CBOT")
        self.assertAlmostEqual(m["kpis"]["cbot_net_usd"], sum(r["usd"] for r in m["cbot"] if r["assessable"]))


class RouteFreightTests(unittest.TestCase):
    def test_no_route_freight_leaves_the_including_transport_comparison_out(self):
        inp = inputs()
        c = inp["contracts"][0]
        c.update(landed_excl_egp_mt=c["landed_egp_mt"] - (c.get("freight_egp_mt") or 0), freight_egp_mt=None,
                 freight_note="No freight table route", loading_place="دمياط", destination="النوبارية")
        m = mr.build(inp)
        rows = [r for r in m["savings"] if r["contract_id"] == c["id"]]
        self.assertTrue(rows)
        self.assertTrue(all(r["saving"] is None and r["cost"] is None for r in rows))
        self.assertTrue(all(r["saving_excl"] is not None for r in rows))
        ex = [e for e in m["excluded"] if e["category"] == "Inland freight not recorded"]
        self.assertEqual([e["contract_id"] for e in ex], [c["id"]])
        self.assertAlmostEqual(ex[0]["mt"], sum(r["mt"] for r in rows))
        self.assertAlmostEqual(m["kpis"]["historical_mt"], sum(r["mt"] for r in m["savings"] if r["saving"] is not None))
        self.assertTrue(m["management_ready"], [v for v in m["validation"] if not v["passed"]])

    def test_route_freight_is_added_to_the_landed_cost_without_freight(self):
        inp = inputs()
        c = inp["contracts"][0]
        base = c["landed_egp_mt"] - (c.get("freight_egp_mt") or 0)
        c.update(landed_excl_egp_mt=base, freight_egp_mt=343.98)
        m = mr.build(inp)
        r = next(x for x in m["savings"] if x["contract_id"] == c["id"])
        self.assertAlmostEqual(r["cost"], base + 343.98)
        self.assertAlmostEqual(r["cost_excl"], base)


class CostBuildUpTests(unittest.TestCase):
    def test_open_cost_is_cif_times_fx_plus_discharge_clearance_and_freight_with_sources(self):
        inp = inputs()
        c = inp["contracts"][1]
        c.update(disc_basis="Contract entry", clr_basis="Not recorded — 0 used", clearance_egp_mt=0.0, clr_missing=True,
                 freight_basis="Freight table: X → Y, 425.53 + 14% VAT")
        m = mr.build(inp)
        o = next(x for x in m["open"] if x["contract_id"] == "C2")
        self.assertAlmostEqual(o["cif_egp"], o["cif"] * o["fx"])
        self.assertAlmostEqual(o["cost_excl"], o["cif_egp"] + o["discharge"] + o["clearance"])
        self.assertAlmostEqual(o["cost_incl"], o["cost_excl"] + o["freight"])
        self.assertEqual((o["disc_basis"], o["clr_basis"]), ("Contract entry", "Not recorded — 0 used"))
        self.assertTrue(o["clr_missing"])
        self.assertTrue(o["freight_basis"].startswith("Freight table"))

    def test_sources_default_when_the_app_does_not_send_them(self):
        inp = inputs()
        inp["contracts"][1].update(freight_egp_mt=None, disc_missing=True)
        o = next(x for x in mr.build(inp)["open"] if x["contract_id"] == "C2")
        self.assertEqual(o["disc_basis"], "Not recorded — 0 used")
        self.assertEqual(o["clr_basis"], "Contract entry")
        self.assertIn("add the freight manually", o["freight_basis"])
        self.assertIsNone(o["cost_incl"])

    def test_each_savings_row_carries_its_cost_parts(self):
        m = mr.build(inputs())
        for r in m["savings"]:
            self.assertAlmostEqual(r["cif_egp"] + r["discharge"] + r["clearance"], r["cost_excl"], places=6)
            if r["cost"] is not None:
                self.assertAlmostEqual(r["cost_excl"] + r["freight"], r["cost"], places=6)


class LocalEquivalentCbotTests(unittest.TestCase):
    def test_local_equivalent_cbot_is_local_as_cif_minus_contract_premium(self):
        c = {"base": "CORN", "premium": 150.0, "discharge_egp_mt": 300.0, "clearance_egp_mt": 200.0,
             "fix": {"eligible": True, "fixed": True, "value": 420.0}}
        out = mr.equivalent_premium(c, 15000.0, dt.date(2026, 10, 28), lambda b, d: (400.0, d), lambda d: (50.0, d))
        self.assertAlmostEqual(out["eq_cbot"], (15000 - 500) / 50 / 0.3937 - 150)
        self.assertAlmostEqual(out["eq_cbot"] - out["day_cbot"], out["premium_gap"])  # the same gap, read on the CBOT side
        self.assertAlmostEqual(out["eq_cbot_diff"], out["eq_cbot"] - 420.0)

    def test_needs_a_contract_premium_and_reports_no_difference_until_fixed(self):
        c = {"base": "CORN", "premium": 150.0, "fix": {"eligible": True, "fixed": False, "value": None}}
        out = mr.equivalent_premium(c, 15000.0, dt.date(2026, 10, 28), lambda b, d: (None, None), lambda d: (50.0, d))
        self.assertIsNotNone(out["eq_cbot"])  # does not need that day's CBOT
        self.assertIsNone(out["eq_cbot_diff"])
        flat = {"base": "SBM", "premium": 0.0, "fix": {"eligible": False}}
        self.assertIsNone(mr.equivalent_premium(flat, 25000.0, dt.date(2026, 10, 28), lambda b, d: (300.0, d), lambda d: (50.0, d))["eq_cbot"])
