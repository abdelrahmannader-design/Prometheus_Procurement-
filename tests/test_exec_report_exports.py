"""The management report's two exports: one model, the same figures in both."""

import datetime as dt
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core import mgmt_report as mr
from prometheus_core.exec_report_html import render
from tests.test_mgmt_report import inputs

try:
    import openpyxl
    from prometheus_core.exec_report_excel import SHEETS, build_workbook
except Exception:  # pragma: no cover - optional dependency
    openpyxl = None


def model():
    inp = inputs()
    inp["contracts"][0]["contract"] = "A-1 </script> cargo"
    inp["local_purchases"] = [{"lot_id": "LOCAL-1-0", "ref": "LOCAL #1 · Titan", "supplier": "Titan",
                               "commodity": "CORN", "qty_mt": 500.0, "cost_egp_mt": 15200.0,
                               "source_id": "local_purchases id 1"}]
    inp["draws"].append({"date": dt.date(2026, 10, 4), "lot_id": "LOCAL-1-0", "mt": 500.0, "kind": "estimated",
                         "base": "CORN", "local": {"price": 15500.0, "date": "2026-10-01", "key": "CORN"}})
    return mr.build(inp)


@unittest.skipIf(openpyxl is None, "openpyxl not installed")
class WorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = model()
        cls.path = os.path.join(tempfile.mkdtemp(), "mgmt.xlsx")
        build_workbook(cls.m, cls.path)
        cls.wb = openpyxl.load_workbook(cls.path, data_only=True)
        cls.raw = openpyxl.load_workbook(cls.path)

    def test_the_eleven_sheets_within_excels_name_limit(self):
        self.assertEqual(sorted(w.title for w in self.wb.worksheets), sorted(SHEETS))
        titles = [w.title for w in self.wb.worksheets]
        self.assertEqual(titles.index("Local Purchases"), titles.index("Daily Consumption Allocation") + 1)
        self.assertTrue(all(len(s) <= 31 for s in SHEETS))
        for name in ("Contract Master", "Local Market Price History", "Daily Consumption Allocation",
                     "Savings vs Local", "CBOT Fixed vs Consumption", "Contract CBOT Performance",
                     "Open Contracts vs Local Today", "Excluded & Missing Data"):
            self.assertIn(name, SHEETS)

    def test_data_sheets_are_excel_tables(self):
        for name in list(SHEETS[1:10]) + ["Local Purchases"]:
            self.assertTrue(self.raw[name].tables, name)

    def test_every_formula_has_a_stored_result(self):
        with zipfile.ZipFile(self.path) as z:
            for name in z.namelist():
                if name.startswith("xl/worksheets/sheet"):
                    self.assertNotRegex(z.read(name).decode(), r"</f><v\s*/>", name)

    def test_summary_cards_equal_the_model_and_are_formulas(self):
        k, ws, raw = self.m["kpis"], self.wb[SHEETS[0]], self.raw[SHEETS[0]]
        for ref, key in (("B6", "historical_saving_egp"), ("E6", "open_fixed_potential_egp"),
                         ("H6", "open_outstanding_mt"), ("B10", "cbot_advantage_usd"),
                         ("E10", "cbot_missed_usd"), ("H10", "cbot_net_usd")):
            self.assertTrue(str(raw[ref].value).startswith("="), ref)
            self.assertAlmostEqual(ws[ref].value, k[key], places=4, msg=ref)

    def test_no_unsourced_row_in_the_allocation_table(self):
        ws = self.wb["Daily Consumption Allocation"]
        ids = [ws.cell(r, 2).value for r in range(5, ws.max_row + 1) if ws.cell(r, 2).value]
        self.assertTrue(ids)
        self.assertTrue(all(i in ("C1", "C2") for i in ids))
        ex = self.wb["Excluded & Missing Data"]
        cats = [ex.cell(r, 1).value for r in range(5, ex.max_row + 1)]
        self.assertIn("Unsourced consumption", cats)

    def test_local_purchases_are_on_their_own_sheet_only(self):
        al = self.wb["Daily Consumption Allocation"]
        self.assertNotIn("LOCAL-1-0", [al.cell(r, 2).value for r in range(5, al.max_row + 1)])
        lq = self.wb["Local Purchases"]
        self.assertEqual(lq.cell(5, 2).value, "LOCAL-1-0")
        self.assertAlmostEqual(lq.cell(5, 11).value, (15500 - 15200) * 500)
        sv = self.wb["Savings vs Local"]
        self.assertNotIn("LOCAL-1-0", [sv.cell(r, 2).value for r in range(5, sv.max_row + 1)])
        audit = self.wb["Validation & Sources"]
        vals = [[audit.cell(r, c).value for c in range(1, 6)] for r in range(1, audit.max_row + 1)]
        corn = next(v for v in vals if v[0] == "CORN" and isinstance(v[1], (int, float)))
        self.assertAlmostEqual(corn[4], 0.0)          # consumed = allocated + excluded
        self.assertAlmostEqual(corn[2], 2000.0)       # 1,500 imports + 500 local purchase

    def test_implied_fixing_is_a_formula_on_the_master(self):
        raw, ws = self.raw["Contract Master"], self.wb["Contract Master"]
        r = next(r for r in range(5, raw.max_row + 1) if raw.cell(r, 1).value == "C1")
        self.assertEqual(raw.cell(r, 19).value, f"=N{r}/R{r}-O{r}")
        self.assertAlmostEqual(ws.cell(r, 19).value, 285 / 0.3937 - 207, places=6)
        r2 = next(r for r in range(5, raw.max_row + 1) if raw.cell(r, 1).value == "C2")
        self.assertEqual(ws.cell(r2, 19).value, "Not fixed")

    def test_monthly_trend_sums_back_to_the_headline(self):
        ws = self.wb["Monthly Trend"]
        total = sum(ws.cell(r, 2).value or 0 for r in range(5, ws.max_row + 1) if ws.cell(r, 1).value)
        self.assertAlmostEqual(total, self.m["kpis"]["historical_saving_egp"], places=4)
        cbot = sum(ws.cell(r, 5).value or 0 for r in range(5, ws.max_row + 1) if ws.cell(r, 1).value)
        self.assertAlmostEqual(cbot, self.m["kpis"]["cbot_net_usd"], places=4)

    def test_transport_premium_storage_and_stale_columns(self):
        def heads(name):
            ws = self.raw[name]
            return [ws.cell(4, c).value for c in range(1, ws.max_column + 1)]
        sv = heads("Savings vs Local")
        for h in ("Import Inland Transport EGP/MT", "Savings Excl. Transport EGP/MT", "Local Price Age Status", "Storage Start Date"):
            self.assertIn(h, sv)
        op = heads("Open Contracts vs Local Today")
        for h in ("Storage Start Date", "Premium", "Futures Month", "Fixed CBOT", "Latest CBOT", "FX Basis", "Form 4 Status",
                  "Imported Cost Excl. Transport EGP/MT", "Imported Cost Incl. Transport EGP/MT", "Local Price Age Status",
                  "Total Potential Excl. Transport EGP", "Total Potential Incl. Transport EGP", "Totals Bucket"):
            self.assertIn(h, op)
        ws = self.wb["Open Contracts vs Local Today"]
        col = {h: i + 1 for i, h in enumerate(op)}
        conf = sum(ws.cell(r, col["Total Potential Incl. Transport EGP"]).value for r in range(5, ws.max_row + 1)
                   if ws.cell(r, col["Totals Bucket"]).value == "Confirmed")
        self.assertAlmostEqual(conf, self.m["kpis"]["open_fixed_potential_egp"], places=4)
        cs = heads("Contract Savings Summary")
        for h in ("Premium", "Futures Month", "Final CIF", "Pricing Status"):
            self.assertTrue(any(h in (x or "") for x in cs), h)
        self.assertTrue(any("Fixing Type" in (x or "") for x in cs))

    def test_validation_banner_and_checksum(self):
        ws = self.wb["Validation & Sources"]
        self.assertIn("MANAGEMENT-READY", ws["A3"].value)
        self.assertIn(self.m["checksum"], ws["A2"].value)


class HtmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = model()
        cls.doc = render(cls.m)

    def test_nothing_is_fetched(self):
        self.assertIsNone(re.search(r"""(src|href)\s*=\s*["']?https?:""", self.doc))
        self.assertNotIn("@import", self.doc)

    def test_the_model_is_embedded_intact(self):
        blob = re.search(r'<script id="data" type="application/json">(.*?)</script>', self.doc, re.S).group(1)
        back = json.loads(blob.replace("<\\/", "</"))
        self.assertEqual(back["kpis"], json.loads(json.dumps(self.m["kpis"])))
        self.assertEqual(back["checksum"], self.m["checksum"])
        self.assertEqual(back["contracts"][0]["contract"], "A-1 </script> cargo")

    def test_a_contract_name_cannot_close_the_script(self):
        self.assertEqual(self.doc.count("</script>"), 2)

    def test_dashboard_controls_exist(self):
        for hook in ('data-p="savings"', 'id="svT"', 'data-p="trends"', 'id="trMonth"', 'id="trLocal"', 'id="trCbot"', 'id="trSupplier"', 'id="trSource"', 'id="bMgmt"', 'id="bTheme"', 'id="bXlsx"', "window.print()", 'id="fFrom"', 'id="fDQ"',
                     'data-p="cbot"', 'data-p="open"', 'data-p="quality"', "@media print",
                     'prefers-color-scheme:dark', 'id="txSeg"', 'data-tx="side" class="on"', 'id="fAge"',
                     'id="oBucket"', 'id="oRes"', "STALE", "N/A — Missing Source Data"):
            self.assertIn(hook, self.doc)


if __name__ == "__main__":
    unittest.main()
