from __future__ import annotations

import datetime as dt
import unittest

from prometheus_core.importer import match_sheet, parse_date, parse_sheet, plan_import


class ParseTests(unittest.TestCase):
    def test_dates(self):
        self.assertEqual(parse_date("2026-09-20"), "2026-09-20")
        self.assertEqual(parse_date("20/09/2026"), "2026-09-20")
        self.assertEqual(parse_date(dt.datetime(2026, 9, 20, 0, 0)), "2026-09-20")
        self.assertEqual(parse_date(46285), "2026-09-20")          # Excel serial
        self.assertIsNone(parse_date("2026-13-01"))

    def test_sheet_names(self):
        self.assertEqual(match_sheet("local purchases"), "Local Purchases")
        self.assertEqual(match_sheet("FX_History"), "FX History")
        self.assertIsNone(match_sheet("Sheet1"))

    def test_header_below_title_and_help_rows(self):
        rows = [["Budgets — title"], ["help", "help"],
                ["commodity *", "year *", "currency", "basis", "price_mt *", "qty_mt", "note"],
                ["corn", 2026, "usd", "cif", "232.5", "140,000", ""],
                [None, None, None],
                ["SBM", "twenty", "USD", "CIF", -5, None, None]]
        p = parse_sheet("Budgets", rows)
        self.assertEqual(p["missing_cols"], [])
        self.assertEqual(len(p["records"]), 1)
        r = p["records"][0]
        self.assertEqual((r["commodity"], r["year"], r["currency"], r["basis"], r["price_mt"], r["qty_mt"]),
                         ("CORN", 2026, "USD", "CIF", 232.5, 140000.0))
        self.assertEqual(p["errors"][0]["row"], 6)
        self.assertTrue(any("year" in e for e in p["errors"][0]["errors"]))
        self.assertTrue(any("price_mt must be > 0" in e for e in p["errors"][0]["errors"]))

    def test_missing_required_column(self):
        p = parse_sheet("FX History", [["date", "value"], ["2026-01-01", 50]])
        self.assertEqual(p["records"], [])


class PlanTests(unittest.TestCase):
    STATE = {
        "contracts": {"C1": {"name": "Corn Nov", "supplier": "A", "commodity": "CORN", "qty_mt": 30000}},
        "local_prices": [{"date": "2026-09-20", "commodity": "CORN", "price_egp_mt": 14600, "transport_egp_mt": 150}],
        "budgets": [{"commodity": "CORN", "year": 2026, "price_egp_mt": 20000}],
        "fx_history": [{"date": "2026-09-20", "rate": 48.25}],
        "cbot_history": [{"date": "2026-09-20", "commodity": "CORN", "price": 428.25}],
        "local_purchases": [],
    }

    def test_contract_match_by_id_or_name(self):
        recs = [{"contract_id": "C1", "name": "x", "supplier": "y", "commodity": "CORN", "qty_mt": 30000, "_row": 4},
                {"name": "corn nov", "supplier": "a", "commodity": "CORN", "qty_mt": 25000, "_row": 5},
                {"name": "New", "supplier": "B", "commodity": "SBM", "qty_mt": 5000, "_row": 6}]
        plan = plan_import("Contracts", recs, self.STATE)
        self.assertEqual(plan[0]["action"], "DUPLICATE")         # same contract as the next row
        self.assertEqual((plan[1]["action"], plan[1]["target"], plan[1]["changes"]), ("UPDATE", "C1", ["qty_mt"]))
        self.assertEqual(plan[2]["action"], "NEW")

    def test_same_update_new(self):
        lp = plan_import("Local Prices", [{"date": "2026-09-20", "commodity": "CORN", "price_egp_mt": 14600,
                                           "transport_egp_mt": 150}], self.STATE)
        self.assertEqual(lp[0]["action"], "SAME")
        fx = plan_import("FX History", [{"date": "2026-09-20", "rate": 48.3}, {"date": "2026-09-21", "rate": 48.4}],
                         self.STATE)
        self.assertEqual([p["action"] for p in fx], ["UPDATE", "NEW"])
        cb = plan_import("CBOT History", [{"date": "2026-09-20", "commodity": "CORN", "close": 428.25}], self.STATE)
        self.assertEqual(cb[0]["action"], "SAME")                # 'price' key of saved history is read

    def test_old_egp_budget_is_updated_to_usd(self):
        b = plan_import("Budgets", [{"commodity": "CORN", "year": 2026, "price_mt": 20000}], self.STATE)
        self.assertEqual(b[0]["action"], "UPDATE")               # EGP delivered → USD CIF default
        self.assertIn("currency", b[0]["changes"])


if __name__ == "__main__":
    unittest.main()
