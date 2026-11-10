"""The management report limited to a period (mgmt_report.build with inp["period"])."""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core import mgmt_report as mr  # noqa: E402
from tests.test_mgmt_report import inputs  # noqa: E402

D = dt.date


def with_old_contract():
    """inputs() plus C3: delivered before the period, no storage start, consumed on 1 Oct only."""
    inp = inputs()
    inp["contracts"] = inp["contracts"] + [{
        "id": "C3", "contract": "C-3", "supplier": "S", "commodity": "CORN-BRZ", "base": "CORN",
        "origin": "BRAZIL", "status": "Closed", "is_open": False, "pricing_status": "PRICED",
        "qty_mt": 500.0, "delivery_date": "2026-09-25", "futures_month": "DEC", "cif_usd_mt": 280.0,
        "premium": 200.0, "cif_final": True, "fx": 50.0, "landed_egp_mt": 14800.0, "source_id": "contracts.C3",
        "freight_egp_mt": 400.0, "discharge_egp_mt": 200.0, "clearance_egp_mt": 150.0, "form4_fx": 50.0}]
    inp["draws"] = inp["draws"] + [{"date": D(2026, 10, 1), "lot_id": "CONTRACT-C3", "mt": 500.0, "kind": "estimated",
                                    "base": "CORN", "local": {"price": 15500.0, "date": "2026-10-01", "key": "CORN-BRZ"}}]
    inp["stock_by_contract"] = dict(inp["stock_by_contract"], C3=0.0)
    return inp


PERIOD = {"from": "2026-10-02", "to": "2026-10-04"}


class PeriodBuildTests(unittest.TestCase):
    def setUp(self):
        self.full = mr.build(with_old_contract())
        self.per = mr.build(dict(with_old_contract(), period=PERIOD))

    def test_only_rows_inside_the_period(self):
        for key in ("allocations", "savings", "cbot"):
            self.assertTrue(all("2026-10-02" <= r["date"] <= "2026-10-04" for r in self.per[key]), key)
        inside = [r for r in self.full["savings"] if "2026-10-02" <= r["date"] <= "2026-10-04"]
        self.assertEqual(len(self.per["savings"]), len(inside))
        self.assertAlmostEqual(self.per["kpis"]["historical_saving_egp"], sum(r["saving"] or 0 for r in inside))
        self.assertTrue(all(not e.get("date") or "2026-10-02" <= e["date"] <= "2026-10-04" for e in self.per["excluded"]))

    def test_open_book_and_delivery_status_use_the_whole_history(self):
        self.assertEqual(sorted(o["contract_id"] for o in self.per["open"]),
                         sorted(o["contract_id"] for o in self.full["open"]))
        self.assertNotIn("C3", [o["contract_id"] for o in self.per["open"]])     # consumed before the period
        for key in ("open_fixed_potential_egp", "open_indicative_potential_egp", "open_contracts"):
            self.assertEqual(self.per["kpis"][key], self.full["kpis"][key])
        c3p = next(c for c in self.per["contracts"] if c["id"] == "C3")
        c3f = next(c for c in self.full["contracts"] if c["id"] == "C3")
        self.assertEqual(c3p["consumed_mt"], 0.0)                 # nothing consumed inside the period
        self.assertEqual(c3p["delivery_status"], c3f["delivery_status"])
        self.assertEqual(c3p["unreconciled_mt"], c3f["unreconciled_mt"])

    def test_validation_and_labels(self):
        self.assertEqual([v["check"] for v in self.per["validation"] if not v["passed"]],
                         [v["check"] for v in self.full["validation"] if not v["passed"]])
        self.assertEqual(self.per["period"]["from"], "2026-10-02")
        self.assertEqual(self.per["period"]["days"], 3)
        self.assertIn("Period Overview", self.per["title"])
        self.assertNotIn("period", self.full)

    def test_summary_reconciles(self):
        ps = self.per["period_summary"]
        t = ps["totals"]
        self.assertAlmostEqual(t["consumed_mt"], t["import_mt"] + t["local_purchase_mt"] + t["excluded_mt"])
        self.assertEqual(t["consumed_mt"], 1000.0)                 # C1 on 2 Oct + C2 on 3 Oct (30 Sep and 1 Oct are outside)
        self.assertAlmostEqual(sum(m["saving_incl"] for m in ps["by_month"]), t["saving_incl"] or 0)
        self.assertEqual(ps["market"]["cbot"]["CORN"]["first_date"], "2026-10-02")
        self.assertEqual(ps["market"]["cbot"]["CORN"]["last_date"], "2026-10-04")
        self.assertTrue(all("2026-10-02" <= o["date"] <= "2026-10-04" for o in self.per["local_obs"]))
        acts = {a["contract_id"]: a for a in ps["activity"]}
        self.assertIn("C2", acts)
        self.assertIn("Stored 2026-10-03", acts["C2"]["events"])

    def test_period_window_helpers(self):
        self.assertEqual(mr.period_window({"from": "2026-10-04", "to": "2026-10-02"}), (D(2026, 10, 2), D(2026, 10, 4)))
        self.assertIsNone(mr.period_window({"from": "", "to": "2026-10-02"}))
        self.assertIsNone(mr.period_window(None))


class PeriodExportTests(unittest.TestCase):
    def setUp(self):
        self.per = mr.build(dict(with_old_contract(), period=PERIOD))

    def test_html_has_the_period_tab(self):
        from prometheus_core import exec_report_html as h
        html = h.render(self.per)
        self.assertIn('id="tabPeriod"', html)
        self.assertIn('"period_summary"', html)
        self.assertIn("2026-10-02", html)

    def test_workbook_opens_on_the_period_sheet(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not installed")
        from prometheus_core.exec_report_excel import build_workbook
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.xlsx")
            build_workbook(self.per, path)
            wb = openpyxl.load_workbook(path, data_only=True)
            self.assertEqual(wb.sheetnames[0], "Period Overview")
            self.assertEqual(wb.active.title, "Period Overview")
            ws = wb["Period Overview"]
            self.assertIn("2026-10-02", ws["A1"].value)
            self.assertIn("PERIOD 2026-10-02", wb["Management Summary"]["A2"].value)


if __name__ == "__main__":
    unittest.main()
