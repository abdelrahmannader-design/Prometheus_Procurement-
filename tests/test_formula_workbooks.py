"""Portfolio, Local Purchases and Stress workbooks are formula-based and
reconcile with the app's own calculations."""
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import unittest
import unittest.mock

TODAY = dt.date(2026, 9, 23)


def _state():
    cbot, fx, local = [], [], []
    for i in range(120):
        d = (TODAY - dt.timedelta(days=120 - i)).isoformat()
        cbot.append({"commodity": "CORN", "date": d, "price": 420 + (i % 10)})
        fx.append({"date": d, "rate": 50 + i * 0.01})
        if i % 5 == 0:
            local.append({"date": d, "commodity": "CORN", "price_egp_mt": 14000, "transport_egp_mt": 250})
    return {
        "contracts": {
            "C1": {"name": "Closed corn", "commodity": "CORN", "status": "Closed", "priced": True,
                   "qty_mt": 1000, "cif_usd_mt": 200.0, "premium_cents": 100, "delivery_fx": 50.0,
                   "discharge_egp_mt": 250, "clearance_egp_mt": 200, "freight_egp_mt": 300,
                   "delivery_date": (TODAY - dt.timedelta(days=30)).isoformat(),
                   "pricing_date": (TODAY - dt.timedelta(days=90)).isoformat()},
            "C2": {"name": "Open unpriced corn", "commodity": "CORN", "status": "Open",
                   "pricing_status": "UNPRICED", "qty_mt": 2000, "premium_cents": 110,
                   "discharge_egp_mt": 250, "clearance_egp_mt": 200, "freight_egp_mt": 300,
                   "delivery_date": (TODAY + dt.timedelta(days=40)).isoformat()},
        },
        "local_prices": local,
        "local_purchases": [{"id": 1, "date": (TODAY - dt.timedelta(days=10)).isoformat(),
                             "supplier": "Mill", "commodity": "CORN", "qty_mt": 500,
                             "price_egp_mt": 13800, "transport_egp_mt": 250}],
        "cbot_history": cbot, "fx_history": fx, "snapshots": [], "suppliers": {},
        "market_data": {"fx": {"price": 51.0}, "cbot_quotes": {"CORN": {"price": 430.0}}},
        "ui": {"marginal_threshold_egp_mt": 200},
    }


class FormulaWorkbookTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = pathlib.Path(__file__).resolve().parents[1] / "Prometheus_V10_9_10.py"
        spec = importlib.util.spec_from_file_location("prometheus_formula_workbooks", path)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def _app(self):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = _state()
        return app

    def test_portfolio_closed_rows_are_formulas_matching_savings_tab(self):
        app = self._app()
        wb, info = app._build_portfolio_workbook(today=TODAY)
        self.assertEqual(wb.sheetnames, ["Summary", "Assumptions", "Closed – Realized",
                                         "Open – Live MTM", "How Savings Work"])
        self.assertEqual((info["closed"], info["open"]), (1, 1))
        ws = wb["Closed – Realized"]
        self.assertTrue(str(ws["L5"].value).startswith("="))   # own-after
        self.assertTrue(str(ws["O5"].value).startswith("="))   # saving/MT
        self.assertTrue(str(ws["P5"].value).startswith("="))   # total
        row = app._sv_contract_saving_row("C1", app.state_obj["contracts"]["C1"], f_status="Closed")
        own_after = ws["G5"].value * ws["H5"].value + ws["I5"].value + ws["J5"].value + ws["K5"].value
        self.assertAlmostEqual(own_after, row["own_after"])
        self.assertAlmostEqual(ws["N5"].value - own_after, row["sav_mt"])

    def test_one_savings_engine_across_screens(self):
        app = self._app()
        # Freight in DETAILED mode (+14% VAT) used to be missed by Contract Detail.
        app.state_obj["contracts"]["C1"].update({"freight_mode": "DETAILED", "freight_base_egp_mt": 300})
        for cid, c in app.state_obj["contracts"].items():
            engine = app._contract_savings_economics(cid, c)
            detail = app._an_analyse_contract(cid, c, 90, 14, 50.0)
            self.assertAlmostEqual(detail["local_edge"], engine["sav_mt"], places=6)
            if app._contract_is_open(c):
                home = app._hd_cost_for_contract(cid, c, use_latest_fx=True, fx_mode="live")
                self.assertAlmostEqual(home["sav_mt"], engine["sav_mt"], places=6)
            else:
                row = app._sv_contract_saving_row(cid, c, f_status="Closed")
                self.assertAlmostEqual(row["sav_mt"], engine["sav_mt"], places=6)
                self.assertAlmostEqual(engine["freight"], 342.0)   # 300 × 1.14
                self.assertLessEqual(engine["local_date"], c["delivery_date"])

    def test_data_health_lists_real_gaps_and_autofix(self):
        app = self._app()
        app.state_obj["contracts"]["C3"] = {"name": "Closed not flagged", "commodity": "CORN", "status": "Closed",
                                             "qty_mt": 500, "cif_usd_mt": 205.0, "delivery_fx": 50.0,
                                             "freight_egp_mt": 300, "delivery_date": "2026-09-01"}
        app.state_obj["contracts"]["C4"] = {"name": "Open no premium", "commodity": "CORN", "status": "Open",
                                             "pricing_status": "UNPRICED", "qty_mt": 1000, "freight_egp_mt": 300}
        rows = app._data_health_checks(today=TODAY)
        problems = {(r["record"], r["problem"]) for r in rows}
        self.assertIn(("Closed not flagged", "Closed with a CIF but not marked as priced"), problems)
        self.assertIn(("Open no premium", "Open unpriced contract has no premium"), problems)
        self.assertFalse(any(r["record"] == "Closed corn" for r in rows))   # complete contract: no noise
        self.assertIsNone(app._sv_contract_saving_row("C3", app.state_obj["contracts"]["C3"]))
        with unittest.mock.patch.object(self.module, "save_state", lambda *_a, **_k: None):
            app.refresh_savings_tracker = lambda: None
            self.assertEqual(app._health_mark_priced(["C3"]), 1)
        self.assertIsNotNone(app._sv_contract_saving_row("C3", app.state_obj["contracts"]["C3"]))

    def test_portfolio_open_unpriced_shows_cif_of_the_moment(self):
        app = self._app()
        wb, _info = app._build_portfolio_workbook(today=TODAY)
        ws = wb["Open – Live MTM"]
        self.assertEqual(ws["F5"].value, "Unpriced")
        self.assertTrue(str(ws["K5"].value).startswith("=Assumptions!"))   # live CBOT
        self.assertIn("(K5+J5)*L5", ws["M5"].value)                       # CIF of the moment
        self.assertEqual(wb["Assumptions"]["B10"].value, 430.0)            # CORN live CBOT

    def test_local_purchase_refs_fill_from_history(self):
        app = self._app()
        rec = app.state_obj["local_purchases"][0]
        ev = app._lp_evaluate(rec)
        self.assertIsNotNone(ev["cbot"])
        self.assertIsNotNone(ev["fx"])
        self.assertEqual(ev["cbot_src"], "history on/before date")
        self.assertLessEqual(ev["cbot_date"], rec["date"])
        self.assertEqual(ev["premium"], 100)          # C1 premium, agreed before the purchase
        self.assertIsNotNone(ev["import_parity"])
        self.assertLessEqual(ev["market_date"], rec["date"])

    def test_local_purchases_workbook_is_local_only_and_formula_based(self):
        app = self._app()
        wb, n = app._build_local_purchases_workbook(today=TODAY)
        self.assertEqual(n, 1)
        self.assertEqual(wb.sheetnames, ["Local Purchases", "Summary", "Assumptions", "How It Is Judged"])
        ws = wb["Local Purchases"]
        self.assertTrue(ws["X5"].value.startswith("=IF(COUNT(P5,R5,T5,V5,W5)<5"))   # import parity
        self.assertTrue(ws["AB5"].value.startswith("=IF("))                           # overall verdict

    def test_stress_workbook_uses_editable_shock_cells(self):
        app = self._app()
        res = self.module.run_stress_test({
            "commodity": "CORN", "cbot": 430.0, "fx": 51.0, "premium_cents": 110.0,
            "qty_mt": 2000.0, "local_egp_mt": 14250.0, "fees_egp_mt": 750.0,
            "premium_locked": True, "cbot_shocks_custom": (-0.2, 0.2), "fx_shocks_custom": (0.1,)})
        hist, named = app._stress_named_scenarios(res)
        wb = app._build_stress_workbook(res, hist)
        self.assertEqual(wb.sheetnames, ["Stress Test", "Assumptions", "CBOT History Scenarios"])
        a = wb["Assumptions"]
        self.assertEqual([a.cell(row=13, column=c).value for c in (2, 3, 4)], [-20.0, 0.0, 20.0])
        ws = wb["Stress Test"]
        self.assertEqual(ws["B17"].value, "=Assumptions!B$13/100")
        # Best/adverse rows show every input, not just the saving.
        for cell in ("D6", "E6", "F6", "G6", "H6", "D7", "E7", "F7", "G7", "H7"):
            self.assertTrue(str(ws[cell].value).startswith("="), cell)
        self.assertIn("MIN(Assumptions!$B$13:$D$13)", ws["H6"].value)
        self.assertIn("MAX(Assumptions!$B$14:$C$14)", ws["I7"].value)
        self.assertTrue(named)
        self.assertEqual(named[0]["name"], "CBOT at 12-month low")


if __name__ == "__main__":
    unittest.main()
