"""The two exports of the executive savings report: one model, two renderings
whose headline figures are sums of the contract rows beneath them."""

import datetime as dt
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core import exec_savings as xs
from prometheus_core.exec_report_html import render
from prometheus_core.timing_report import Series

try:
    import openpyxl
    from prometheus_core.exec_report_excel import SHEETS, build_workbook
except Exception:  # pragma: no cover - optional dependency
    openpyxl = None

D = dt.date
F = 0.3937


def draws(start, n, mt, cost, local):
    out = []
    for i in range(n):
        lp = local(i) if callable(local) else local
        out.append({"date": start + dt.timedelta(days=i), "mt": mt, "cost_egp_mt": cost,
                    "local_egp_mt": lp, "local_price_date": (start + dt.timedelta(days=i)).isoformat(),
                    "local_key": "X", "kind": "estimated", "is_stale": False, "stale": 0,
                    "saving_vs_local_egp": (lp - cost) * mt if lp is not None else None})
    return out


def row(i, contract, base, qty, cif, premium, landed, hist, fixing, open_=None, is_open=False,
        kind=xs.REALIZED, delivered=None, in_stock=0.0):
    consumed = hist.get("consumed_mt") or 0.0
    delivered = qty if delivered is None else delivered
    o = {"in_stock_mt": in_stock, "outstanding_mt": qty - delivered, "local_today": None,
         "local_key": base, "local_date": "2026-10-29", "landed_today": landed, "saving_egp_mt": None,
         "stock_saving_egp": 0.0, "outstanding_saving_egp": 0.0, "potential_priced_mt": 0.0,
         "open_value_usd": None}
    o.update(open_ or {})
    return {"id": f"C{i:03d}", "contract": contract, "supplier": "Supplier", "commodity": base,
            "base": base, "origin": "", "status": "Open" if is_open else "Closed", "is_open": is_open,
            "pricing_status": "PRICED", "qty_mt": qty, "delivery_date": "2026-09-01",
            "pricing_date": "2026-08-10", "futures_month": "DEC", "cif_usd_mt": cif, "premium": premium,
            "factor": F if premium else None, "fx": 50.0, "fx_basis": "fixed (Form 4)",
            "cif_basis": "fixed (priced)", "discharge_egp_mt": 200.0, "clearance_egp_mt": 200.0,
            "freight_egp_mt": 300.0, "landed_egp_mt": landed, "contract_value_usd": qty * cif,
            "saving_kind": kind, "fixing": fixing, "history": hist,
            "position": xs.position(qty, delivered, consumed, in_stock), "open": o,
            "assessment": "Test assessment."}


def model():
    cbot = Series([(D(2026, 9, 1) + dt.timedelta(days=i), 470.0 + i) for i in range(40)])
    corn_fix = xs.cbot_fixing({"cif_usd_mt": 285.0, "premium_cents": 207.0}, F, "CORN")
    landed_corn = 285.0 * 50 + 700
    h1 = xs.contract_history(draws(D(2026, 9, 1), 6, 500.0, landed_corn, lambda i: landed_corn + 300 + 10 * i),
                             fixing=corn_fix["value"], factor=F, fx=50.0, history=cbot, cost=landed_corn)
    h2 = xs.contract_history(draws(D(2026, 9, 3), 4, 290.0, 21000.0, 20500.0), cost=21000.0)
    landed_soy = 450.0 * 50 + 700
    h3 = xs.contract_history(draws(D(2026, 9, 20), 3, 10.0, landed_soy, 24000.0), cost=landed_soy)
    pot = xs.potential(1970.0, 25000.0, landed_soy)
    rows = [
        row(1, "Brz </script> cargo", "CORN", 3000.0, 285.0, 207.0, landed_corn, h1, corn_fix),
        row(2, "SBM flat", "SBM", 1160.0, 420.0, 0.0, 21000.0, h2,
            {"value": None, "label": "", "source": "", "flag": "flat price — no CBOT fixing",
             "unit": "", "usable": False}),
        row(3, "Soy open", "SOYBEAN", 2000.0, 450.0, 0.0, landed_soy, h3,
            {"value": None, "label": "", "source": "", "flag": "flat price — no CBOT fixing",
             "unit": "", "usable": False},
            open_={"local_today": 25000.0, "saving_egp_mt": pot["saving_egp_mt"],
                   "stock_saving_egp": pot["saving_egp_mt"] * 970.0,
                   "outstanding_saving_egp": pot["saving_egp_mt"] * 1000.0,
                   "potential_priced_mt": 1970.0, "open_value_usd": 1970.0 * 450.0},
            is_open=True, kind=xs.PROVISIONAL, delivered=1000.0, in_stock=970.0),
    ]
    coms = xs.commodity_rollup(rows)
    return {"title": "Executive Import Savings Dashboard", "generated": "2026-10-31 08:00",
            "as_of": "2026-10-31", "app": "Prometheus", "contracts": rows, "commodities": coms,
            "kpis": xs.kpis(rows, coms), "reconciliation": [
                {"base": "CORN", "mode": "daily rate from each delivery", "daily_rate": 500.0,
                 "consumed_mt": 3000.0, "import_mt": 3000.0, "local_purchase_mt": 0.0,
                 "unsourced_mt": 0.0, "stock_mt": 0.0, "counted_mt": 0.0}],
            "dropped": [], "look_alikes": [],
            "sources": {"local_latest": {"CORN": "2026-10-29"}, "cbot": {"CORN": ["2026-09-01", "2026-10-10", 40]},
                        "fx": ["2026-01-01", "2026-10-31"], "rates": {"CORN": 500.0}, "spikes": {"CORN": 0}},
            "version": "test"}


class ModelTests(unittest.TestCase):
    def test_the_fixture_splits_every_tonne_once(self):
        for r in model()["contracts"]:
            self.assertAlmostEqual(r["position"]["unreconciled_mt"], 0.0)

    def test_combined_is_historical_plus_potential_and_cbot_is_apart(self):
        k = model()["kpis"]
        self.assertAlmostEqual(k["combined_benefit_egp"], k["historical_saving_egp"] + k["potential_saving_egp"])
        self.assertNotEqual(k["cbot_adv_usd"], 0)


@unittest.skipIf(openpyxl is None, "openpyxl not installed")
class WorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = model()
        cls.path = os.path.join(tempfile.mkdtemp(), "exec.xlsx")
        build_workbook(cls.m, cls.path)
        cls.wb = openpyxl.load_workbook(cls.path, data_only=True)
        cls.raw = openpyxl.load_workbook(cls.path)

    def test_seven_named_sheets_within_excels_limit(self):
        self.assertEqual(len(SHEETS), 7)
        self.assertEqual([w.title for w in self.wb.worksheets], list(SHEETS))
        self.assertTrue(all(len(s) <= 31 for s in SHEETS))

    def test_every_formula_has_a_stored_result(self):
        with zipfile.ZipFile(self.path) as z:
            for name in z.namelist():
                if name.startswith("xl/worksheets/sheet"):
                    self.assertNotRegex(z.read(name).decode(), r"</f><v\s*/>", name)

    def test_summary_cards_show_the_model_figures_as_formulas(self):
        k, ws, raw = self.m["kpis"], self.wb[SHEETS[0]], self.raw[SHEETS[0]]
        for ref, key in (("B6", "historical_saving_egp"), ("E6", "potential_saving_egp"),
                         ("H6", "combined_benefit_egp"), ("B10", "open_outstanding_mt"),
                         ("E10", "open_full_value_usd"), ("H10", "weighted_saving_egp_mt")):
            self.assertTrue(str(raw[ref].value).startswith("="), ref)
            self.assertAlmostEqual(ws[ref].value, k[key], places=4, msg=ref)
        self.assertAlmostEqual(ws["B14"].value, k["cbot_adv_usd"], places=4)

    def test_the_daily_sheet_carries_every_consumption_day(self):
        ws = self.wb[SHEETS[4]]
        days = sum(len(r["history"]["daily"]) for r in self.m["contracts"])
        dates = [c.value for c in ws["A"][4:] if isinstance(c.value, (dt.date, dt.datetime, str)) and
                 re.match(r"\d{4}-\d\d-\d\d", str(c.value))]
        self.assertEqual(len(dates), days)

    def test_open_sheet_keeps_stock_and_outstanding_apart(self):
        ws = self.wb[SHEETS[3]]
        r = next(i for i in range(6, 20) if ws.cell(i, 4).value == "C003")
        self.assertAlmostEqual(ws.cell(r, 9).value, 970.0)      # delivered, in stock
        self.assertAlmostEqual(ws.cell(r, 10).value, 1000.0)    # not yet delivered


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
        self.assertEqual(back["kpis"]["historical_saving_egp"], self.m["kpis"]["historical_saving_egp"])
        self.assertEqual(back["contracts"][0]["contract"], "Brz </script> cargo")

    def test_a_contract_name_cannot_close_the_script(self):
        self.assertEqual(self.doc.count("</script>"), 2)

    def test_print_and_filter_hooks_exist(self):
        for hook in ("@media print", 'id="chips"', 'id="fStatus"', 'id="tHist"', 'id="tOpen"', 'id="tCbot"'):
            self.assertIn(hook, self.doc)


if __name__ == "__main__":
    unittest.main()
