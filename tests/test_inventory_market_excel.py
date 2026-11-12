"""Inventory vs Market workbook: an overview and one cost ladder per lot."""
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prometheus_core import inventory_market_excel as ix  # noqa: E402


def imp(ref="460/2005", mt=1000.0, fx=53.97, cif=251.1806, intake=245.63, local=14696.88, basis="fixed"):
    fifo = cif * fx + 301.74 + 42.2436 + intake + 200.0
    repl_cif = (448.0 + 190.0) * 0.3937
    repl = repl_cif * 53.564 + 301.74 + 42.2436 + intake + 200.0
    return {"source_type": "IMPORT_CONTRACT", "ref": ref, "supplier": "ADM", "commodity": "CORN-BRZ", "origin": "BRAZIL",
            "status": "Open", "pricing_status": "UNPRICED", "remaining_mt": mt, "fifo_cost": fifo, "fifo_cost_basis": basis,
            "fifo_cost_formula": "how it was built", "fifo_cif_usd": cif, "fifo_fx": fx, "fifo_freight_mode": "DETAILED",
            "fifo_freight_base": 301.74, "fifo_freight_vat_pct": 14.0, "fifo_freight_vat": 42.2436,
            "fifo_freight_incl_vat": 343.9836, "fifo_intake_mode": "DIRECT", "fifo_selected_intake": intake,
            "fifo_clearance": 200.0, "live_cbot": 448.0, "premium": 190.0, "conversion_factor": 0.3937,
            "replacement_cif": repl_cif, "fx_today": 53.564, "replacement_freight_base": 301.74,
            "replacement_freight_vat_pct": 14.0, "replacement_freight_vat": 42.2436, "freight_today": 343.9836,
            "replacement_intake_mode": "DIRECT", "replacement_selected_intake": intake, "replacement_clearance": 200.0,
            "replacement_cost": repl, "formula": "(448.00+190.00)×0.3937 | DEC", "local": local, "local_date": "2026-11-10",
            "edge_local_mt": local - fifo, "edge_local_total": (local - fifo) * mt, "edge_repl_mt": repl - fifo,
            "edge_repl_total": (repl - fifo) * mt, "decision": "Ahead local; CBOT cheaper", "issues": ["a warning"]}


def loc():
    return {"source_type": "LOCAL_PURCHASE", "ref": "Local Purchase", "supplier": "Titan", "commodity": "CORN",
            "origin": "Local", "status": "Local Purchase", "pricing_status": "LOCAL ACTUAL", "remaining_mt": 500.0,
            "fifo_cost": 14650.0, "local_purchase_base": 14250.0, "local_purchase_transport": 400.0, "live_cbot": 448.0,
            "premium": 190.0, "conversion_factor": 0.3937, "replacement_cif": 251.1806, "fx_today": 53.564,
            "replacement_total_expenses": 789.6136, "replacement_cost": 251.1806 * 53.564 + 789.6136,
            "formula": "portfolio premium", "local": 14696.88, "local_date": "2026-11-10", "issues": []}


class WordsTests(unittest.TestCase):
    def test_words_say_which_side_is_cheaper(self):
        self.assertEqual(ix.vs_local_words(351.0), "Our stock is cheaper than local")
        self.assertEqual(ix.vs_local_words(-1.0), "Local is cheaper than our stock")
        self.assertEqual(ix.vs_import_words(-102.0), "Importing today is cheaper than our stock")
        self.assertEqual(ix.short_words(5.0, -5.0), "Cheaper than local · importing today is cheaper")
        self.assertEqual(ix.short_words(None, None), "")


class WorkbookTests(unittest.TestCase):
    def test_overview_and_ladders(self):
        import openpyxl
        rows = [imp(), imp("SC339", 3500.0, fx=56.137, intake=235.0), loc()]
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "inv.xlsx")
            res = ix.write_workbook(rows, fp, as_of="2026-11-12", commodity="CORN", status="All")
            self.assertEqual((res["lots"], res["mt"]), (3, 5000.0))
            wf, wv = openpyxl.load_workbook(fp), openpyxl.load_workbook(fp, data_only=True)
            self.assertEqual(wf.sheetnames, list(ix.SHEETS))
            ws, wd = wf[ix.SHEETS[0]], wv[ix.SHEETS[0]]
            self.assertLessEqual(ws.max_column, 10)                      # nothing to scroll sideways
            # no label may be read as a formula
            for row in ws.iter_rows(min_col=1, max_col=1):
                self.assertFalse(str(row[0].value or "").startswith("="), row[0].coordinate)
            # the overview: one line per lot, each figure read from the lot's card
            self.assertEqual([wd.cell(r, 1).value for r in (7, 8, 9)], ["460/2005", "SC339", "Local Purchase"])
            r0 = rows[0]
            self.assertAlmostEqual(wd["C7"].value, r0["fifo_cost"], places=4)
            self.assertAlmostEqual(wd["E7"].value, r0["edge_local_mt"], places=4)
            self.assertAlmostEqual(wd["F7"].value, r0["edge_local_total"], places=2)
            self.assertAlmostEqual(wd["G7"].value, r0["replacement_cost"], places=4)
            self.assertAlmostEqual(wd["H7"].value, r0["edge_repl_mt"], places=4)
            self.assertAlmostEqual(wd["I7"].value, r0["edge_repl_total"], places=2)
            self.assertEqual(wd["J7"].value, "Cheaper than local · importing today is cheaper")
            self.assertTrue(str(ws["C7"].value).startswith("=IF(ISNUMBER(C"))
            # totals add the lots up
            self.assertEqual(wd["B10"].value, 5000.0)
            self.assertAlmostEqual(wd["F10"].value, sum((r["local"] - r["fifo_cost"]) * r["remaining_mt"] for r in rows), places=2)
            self.assertAlmostEqual(wd["C10"].value, sum(r["fifo_cost"] * r["remaining_mt"] for r in rows) / 5000.0, places=4)
            # the first card: our cost and today's import cost side by side, step by step
            labels = {str(ws.cell(r, 1).value): r for r in range(13, 30)}
            cif, fx, egp, cost = (labels[k] for k in ("→ CIF USD/MT", "× FX EGP/USD", "→ CIF EGP/MT", "→ COST EGP/MT"))
            self.assertEqual(wd.cell(cif, 3).value, 251.1806)                         # ours: the contract CIF, an input
            self.assertEqual(ws.cell(cif, 7).value, f'=IF(AND(ISNUMBER(G{cif - 3}),ISNUMBER(G{cif - 2}),ISNUMBER(G{cif - 1})),'
                                                    f'(G{cif - 3}+G{cif - 2})*G{cif - 1},"")')
            self.assertAlmostEqual(wd.cell(egp, 3).value, 251.1806 * 53.97, places=4)
            self.assertAlmostEqual(wd.cell(fx, 8).value, 53.564 - 53.97)              # today − ours on each step
            self.assertTrue(str(ws.cell(cost, 3).value).startswith("=N(C"))
            self.assertAlmostEqual(wd.cell(cost, 3).value, r0["fifo_cost"], places=4)
            self.assertEqual(wd.cell(cost, 10).value, "Importing today is cheaper than our stock")
            loc_row = cost + 2
            self.assertEqual(wd.cell(loc_row, 10).value, "Our stock is cheaper than local")
            self.assertEqual(wd.cell(cost + 1, 3).value, wd.cell(cost, 3).value)      # the app's recorded figure agrees
            # a local purchase: price + transport on our side, an import at today's prices on the other
            lp = next(r for r in range(30, ws.max_row) if ws.cell(r, 1).value == "Local purchase price")
            self.assertEqual((wd.cell(lp, 3).value, wd.cell(lp + 1, 3).value), (14250.0, 400.0))
            self.assertEqual(wd.cell(lp + 2, 3).value, 14650.0)
            # the original wide table is kept, with its check formulas' results stored
            w2 = wv[ix.SHEETS[1]]
            self.assertEqual(w2.max_column, 52)
            self.assertAlmostEqual(w2["U6"].value, r0["fifo_cost"], places=4)
            self.assertAlmostEqual(w2["AO6"].value, r0["replacement_cost"], places=4)

    def test_unpriced_lot_shows_its_cbot_steps(self):
        import openpyxl
        r = imp(cif=(448.0 + 190.0) * 0.3937, basis="live")
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "inv.xlsx")
            ix.write_workbook([r], fp)
            ws = openpyxl.load_workbook(fp)[ix.SHEETS[0]]
            row = next(x for x in range(10, 20) if ws.cell(x, 1).value == "CBOT")
            self.assertEqual((ws.cell(row, 3).value, ws.cell(row + 1, 3).value), (448.0, 190.0))
            self.assertTrue(str(ws.cell(row + 3, 3).value).startswith("=IF(AND(ISNUMBER(C"))

    def test_steps_that_do_not_add_up_are_flagged(self):
        import openpyxl
        r = imp()
        r["fifo_cost"] += 25.0
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "inv.xlsx")
            ix.write_workbook([r], fp)
            ws = openpyxl.load_workbook(fp)[ix.SHEETS[0]]
            self.assertTrue(any("do not add up" in str(c.value) for row in ws.iter_rows(min_col=10, max_col=10) for c in row))

    def test_no_stock(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(ix.write_workbook([], os.path.join(tmp, "inv.xlsx"))["lots"], 0)


if __name__ == "__main__":
    unittest.main()
