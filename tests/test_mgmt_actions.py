"""Pricing alerts, price exposure, changes since the last report, data to fix, the pasted
local price email, freight rate history and the daily commodity brief."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prometheus_core import mgmt_actions as A
from prometheus_core import mgmt_report as mr
from prometheus_core.freight_history import freight_rate_on, freight_segments
from prometheus_core.local_email import parse_email, to_local_rows
from test_mgmt_report import inputs


def model(**over):
    inp = inputs(**over)
    inp["contracts"][1].update(live=True)
    return mr.build(inp)


class PricingAlertTests(unittest.TestCase):
    def test_targets_trigger_against_the_live_cbot_and_headroom(self):
        inp = inputs(live_cbot={"CORN": {"price": 500.0, "time": "2026-10-04 12:00"}},
                     pricing_alerts={"C2": {"cbot_below": 505.0, "cbot_above": 600.0, "note": "fix below 505"}})
        m = mr.build(inp)
        a = m["alerts"][0]
        self.assertEqual(a["status"], "TRIGGERED")
        self.assertEqual(len(a["triggered"]), 1)
        self.assertIn("at or below your target 505.00", a["triggered"][0])
        self.assertTrue(a["cbot_live"])

    def test_not_hit_is_watching_and_a_priced_contract_no_longer_applies(self):
        m = mr.build(inputs(pricing_alerts={"C2": {"cbot_below": 100.0}, "C1": {"cbot_below": 999.0}}))
        st = {a["contract_id"]: a["status"] for a in m["alerts"]}
        self.assertEqual(st["C2"], "Watching")
        self.assertEqual(st["C1"], "Priced — target no longer applies")


class ExposureTests(unittest.TestCase):
    def test_cbot_step_effect_is_step_times_factor_times_fx_times_unpriced_mt(self):
        m = mr.build(inputs())
        rows = [r for r in m["exposure"]["cbot"] if r["base"] == "CORN"]
        self.assertEqual(len(rows), 1)
        c2 = next(c for c in m["contracts"] if c["id"] == "C2")
        fx = c2["current"]["fx"]
        self.assertAlmostEqual(rows[0]["unpriced_mt"], 1000.0)
        self.assertAlmostEqual(rows[0]["egp_per_step"], 10 * 0.3937 * fx * 1000.0)

    def test_fx_exposure_is_cif_times_mt_for_contracts_without_form4(self):
        m = mr.build(inputs())
        fx = m["exposure"]["fx_contracts"]
        self.assertEqual([r["contract_id"] for r in fx], ["C2"])
        self.assertAlmostEqual(fx[0]["egp_per_step"], fx[0]["cif"] * fx[0]["mt"])


class SinceLastTests(unittest.TestCase):
    def test_changes_against_the_previous_saved_report(self):
        m = mr.build(inputs())
        prev = dict(m["snapshot"], generated="2026-10-01 08:00")
        prev["kpis"] = dict(prev["kpis"], historical_saving_egp=(prev["kpis"]["historical_saving_egp"] or 0) - 1000.0)
        prev["fx"] = 50.0
        m2 = mr.build(inputs(report_history=[prev]))
        rows = {r["key"]: r for r in m2["since_last"]["rows"]}
        self.assertAlmostEqual(rows["historical_saving_egp"]["change"], 1000.0)
        self.assertAlmostEqual(rows["fx"]["change"], 52.0 - 50.0)
        self.assertEqual(m2["since_last"]["previous"]["generated"], "2026-10-01 08:00")

    def test_an_earlier_day_is_preferred_over_an_export_from_the_same_day(self):
        m = mr.build(inputs())
        older = dict(m["snapshot"], generated="2026-10-03 08:00", as_of="2026-10-03")
        same_day = dict(m["snapshot"], generated="2026-10-04 07:00", as_of="2026-10-04")
        m2 = mr.build(inputs(report_history=[older, same_day]))
        self.assertEqual(m2["since_last"]["previous"]["generated"], "2026-10-03 08:00")

    def test_no_history_means_no_rows(self):
        self.assertEqual(mr.build(inputs())["since_last"], {"previous": None, "rows": []})


class DataToFixTests(unittest.TestCase):
    def test_missing_clearance_storage_and_form4_are_listed_with_severity(self):
        inp = inputs()
        inp["contracts"][1].update(clr_missing=True, storage_start="", delivery_date="")
        m = mr.build(inp, )
        cats = {(x["category"], x["contract_id"]): x["severity"] for x in m["data_to_fix"]}
        self.assertEqual(cats[("Clearance not recorded", "C2")], "High")
        self.assertIn(("Form 4 pending", "C2"), cats)
        self.assertEqual([x["severity"] for x in m["data_to_fix"]],
                         sorted([x["severity"] for x in m["data_to_fix"]], key=A.SEVERITY.get))

    def test_old_fx_quote_and_zero_freight_route_are_flagged(self):
        m = mr.build(inputs(quote_status={"fx": {"price": 52, "market_date": "2026-09-20", "fetched_at": "2026-10-04"}},
                            freight_map=[{"commodity": "CORN", "place": "أكما", "destination": "الصف", "rate": 0}]))
        cats = [x["category"] for x in m["data_to_fix"]]
        self.assertIn("FX quote is old", cats)
        self.assertIn("Freight route rate is 0", cats)


class LocalEmailTests(unittest.TestCase):
    EMAIL = """Dear all,
YC 4/11/2026 2/11/2026
(YC ARG) 15300 LE to 15400 LE / Ton 15200 LE to 15300 LE / Ton
(YC UKR) 14600 LE to 14700 LE / Ton
Subject to availability and quality 14500 LE to 14600 LE / Ton
SBM Hi pro 46% 27500 LE to 27700 LE/ Ton N/A
Soybeans 29000 LE to 29500 LE/ Ton 29000 LE to 29500 LE/ Ton
The prices *Without* transportation"""

    def test_both_dates_and_every_row_are_read(self):
        e = parse_email(self.EMAIL)
        got = {(x["date"], x["key"]): (x["low"], x["high"]) for x in e}
        self.assertEqual(got[("2026-11-04", "ARG")], (15300, 15400))
        self.assertEqual(got[("2026-11-02", "ARG")], (15200, 15300))
        self.assertEqual(got[("2026-11-02", "UKR")], (14500, 14600))
        self.assertEqual(got[("2026-11-04", "SBM")], (27500, 27700))
        self.assertNotIn(("2026-11-02", "SBM"), got)   # N/A in the email

    def test_brazil_takes_argentina_transport_carried_and_unchanged_prices_skipped(self):
        stored = [{"date": "2026-11-01", "commodity": "CORN-ARG", "price_egp_mt": 15200, "transport_egp_mt": 396.88},
                  {"date": "2026-11-01", "commodity": "CORN-BRZ", "price_egp_mt": 15200, "transport_egp_mt": 396.88},
                  {"date": "2026-11-02", "commodity": "SOYBEAN", "price_egp_mt": 29500, "transport_egp_mt": 323.13},
                  {"date": "2026-11-02", "commodity": "CORN-ARG", "price_egp_mt": 15000, "transport_egp_mt": 396.88}]
        rows = to_local_rows(parse_email(self.EMAIL), stored, point="high")
        by = {(r["date"], r["commodity"]): r for r in rows}
        self.assertEqual(by[("2026-11-04", "CORN-BRZ")]["price_egp_mt"], 15400)
        self.assertEqual(by[("2026-11-04", "CORN-BRZ")]["transport_egp_mt"], 396.88)
        self.assertNotIn(("2026-11-02", "SOYBEAN"), by)            # already stored at the same price
        self.assertTrue(by[("2026-11-02", "CORN-ARG")]["_update"])  # stored 15,000 → 15,300
        self.assertNotIn(("2026-11-04", "SBM"), by)                 # the app has no SBM series here
        mid = to_local_rows(parse_email(self.EMAIL), stored, point="mid")
        self.assertEqual(next(r for r in mid if r["commodity"] == "CORN-ARG" and r["date"] == "2026-11-04")["price_egp_mt"], 15350)

    def test_text_without_a_price_table_gives_nothing(self):
        self.assertEqual(parse_email("Hello, no prices today."), [])


class FreightHistoryTests(unittest.TestCase):
    def test_old_records_keep_the_previous_rate_before_the_effective_date(self):
        rec = {"rate": 425.53, "old_rate": 379.94, "effective": "2026-03-10"}
        self.assertEqual(freight_segments(rec), [("", 379.94), ("2026-03-10", 425.53)])
        self.assertEqual(freight_rate_on(rec, "2026-02-01")[:1], (379.94,))
        self.assertEqual(freight_rate_on(rec, "2026-02-01")[2], "previous rate")
        self.assertEqual(freight_rate_on(rec, "2026-03-10")[::2], (425.53, "current rate"))

    def test_every_change_stays_in_force_for_its_own_dates(self):
        rec = {"history": [{"effective": "", "rate": 300}, {"effective": "2026-03-10", "rate": 340},
                           {"effective": "2026-12-01", "rate": 380}]}
        self.assertEqual(freight_rate_on(rec, "2026-01-15")[0], 300)
        self.assertEqual(freight_rate_on(rec, "2026-06-01")[0], 340)
        self.assertEqual(freight_rate_on(rec, "2026-12-02")[0], 380)
        self.assertEqual(freight_rate_on(rec, "2026-06-01")[2], "rate from 2026-03-10")


class DailyBriefTests(unittest.TestCase):
    def test_brief_builds_and_writes_excel_and_pdf(self):
        from prometheus_core import daily_brief as D
        m = mr.build(inputs(live_cbot={"CORN": {"price": 515.0, "time": "2026-10-04 12:00"}},
                            fx_series=[("2026-10-01", 51.5, "x"), ("2026-10-04", 52.0, "x")]))
        b = D.build(m)
        corn = next(x for x in b["market"] if x["base"] == "CORN")
        self.assertEqual((corn["value"], corn["basis"]), (515.0, "live quote"))
        fxr = next(x for x in b["market"] if x["base"] == "FX")
        self.assertAlmostEqual(fxr["d1"], 0.5)
        p = next(x for x in b["parity"] if x["code"] == "CORN-BRZ")
        self.assertAlmostEqual(p["cif"], (515.0 + p["premium"]) * 0.3937)
        self.assertAlmostEqual(p["import_excl"], p["cif"] * 52.0 + p["discharge"] + p["clearance"])
        self.assertAlmostEqual(p["edge_excl"], p["local_excl"] - p["import_excl"])
        with tempfile.TemporaryDirectory() as d:
            try:
                import openpyxl  # noqa: F401
                D.write_excel(b, os.path.join(d, "b.xlsx"))
                self.assertGreater(os.path.getsize(os.path.join(d, "b.xlsx")), 3000)
            except ImportError:
                pass
            try:
                import reportlab  # noqa: F401
                D.write_pdf(b, os.path.join(d, "b.pdf"))
                with open(os.path.join(d, "b.pdf"), "rb") as fh:
                    self.assertEqual(fh.read(4), b"%PDF")
            except ImportError:
                pass


if __name__ == "__main__":
    unittest.main()


class BriefPositionAndStockTests(unittest.TestCase):
    def test_open_position_uses_the_app_rows_when_given(self):
        from prometheus_core import daily_brief as D
        m = mr.build(inputs())
        app_rows = [{"contract_id": "C2", "contract": "B-2", "supplier": "S", "commodity": "CORN-BRZ", "base": "CORN",
                     "origin": "BRAZIL", "status": "Open", "qty": 1000.0, "cif": 250.0, "cif_formula": "(440.50+180.00)×0.3937 | DEC",
                     "fx": 55.4, "freight": 485.0, "own_after": 14500.0, "local": 15397.0, "local_date": "2026-10-04",
                     "local_flag": "", "sav_mt": 897.0, "total_sav": 897000.0, "decision": "Strong import edge", "threshold": 200.0}]
        op = D.build(m, app_position=app_rows)["open_position"]
        self.assertEqual(op["source"], "app")
        g = op["groups"][0]
        self.assertEqual((g["base"], g["qty"], g["total_sav"]), ("CORN", 1000.0, 897000.0))
        r = g["rows"][0]
        self.assertAlmostEqual(r["sav_to_consume"], 897.0 * r["to_consume_mt"])

    def test_model_fallback_and_fifo_stock_against_cbot_and_local(self):
        from prometheus_core import daily_brief as D
        m = mr.build(inputs(live_cbot={"CORN": {"price": 515.0, "time": "2026-10-04 12:00"}}, rates={"CORN-BRZ": 250.0}))
        b = D.build(m)
        self.assertEqual(b["open_position"]["source"], "report model")
        self.assertIn("C2", [r["contract_id"] for g in b["open_position"]["groups"] for r in g["rows"]])
        lots = b["fifo"]["lots"]
        self.assertTrue(lots)
        o = next(x for x in m["open"] if x["contract_id"] == lots[0]["contract_id"])
        self.assertAlmostEqual(lots[0]["stock_mt"], o["available_mt"])
        if lots[0]["vs_local_incl"] is not None:
            self.assertAlmostEqual(lots[0]["vs_local_incl"], o["saving_mt"] * o["available_mt"])
        self.assertEqual(lots[0]["use_from"], "2026-10-04")   # FIFO from today at the configured rate
        self.assertEqual(lots[0]["use_to"], "2026-10-06")     # 500 MT at 250 MT/day


class DigestTests(unittest.TestCase):
    def test_group_averages_skip_missing_rows_and_email_summary_has_both_bodies(self):
        from prometheus_core import daily_brief as D
        m = mr.build(inputs())
        base = {"supplier": "S", "commodity": "SBM", "base": "SBM", "origin": "USA", "status": "Open", "cif_formula": "",
                "fx": 55.0, "freight": 377.0, "local_date": "", "local_flag": "", "decision": "", "threshold": 200.0, "cif": 450.0}
        rows = [dict(base, contract_id="X1", contract="X1", qty=500.0, own_after=25000.0, local=27000.0, sav_mt=2000.0, total_sav=1e6),
                dict(base, contract_id="X2", contract="X2", qty=500.0, own_after=None, local=27000.0, sav_mt=None, total_sav=None)]
        b = D.build(m, app_position=rows)
        g = b["open_position"]["groups"][0]
        self.assertEqual((g["own_after"], g["sav_mt"], g["missing"]), (25000.0, 2000.0, 1))
        text, html = D.email_summary(b)
        self.assertIn("Daily Commodity Brief", text)
        self.assertIn("1 contract(s) missing data", text)
        self.assertIn("<table", html)
