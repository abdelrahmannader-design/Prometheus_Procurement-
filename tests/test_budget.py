from __future__ import annotations

import datetime as dt
import unittest

from prometheus_core.budget import budget_vs_actual, budget_year_label, budget_year_of, budget_year_range


class BudgetYearTests(unittest.TestCase):
    def test_calendar_and_fiscal_years(self):
        self.assertEqual(budget_year_of(dt.date(2026, 6, 30), 1), 2026)
        self.assertEqual(budget_year_of(dt.date(2026, 6, 30), 7), 2025)
        self.assertEqual(budget_year_of(dt.date(2026, 7, 1), 7), 2026)
        self.assertIsNone(budget_year_of(None))
        self.assertEqual(budget_year_label(2026, 1), "2026")
        self.assertEqual(budget_year_label(2026, 7), "FY 2026/27")
        self.assertEqual(budget_year_range(2026, 7), (dt.date(2026, 7, 1), dt.date(2027, 6, 30)))
        self.assertEqual(budget_year_range(2026, 1), (dt.date(2026, 1, 1), dt.date(2026, 12, 31)))


class BudgetVsActualTests(unittest.TestCase):
    LINES = [{"kind": "ACTUAL", "qty_mt": 3000, "cost_egp_mt": 19000},
             {"kind": "COMMITTED", "qty_mt": 2000, "cost_egp_mt": 21000},
             {"kind": "ACTUAL", "qty_mt": 100, "cost_egp_mt": None}]

    def test_bought_forecast_and_headroom(self):
        r = budget_vs_actual({"price_egp_mt": 20000, "qty_mt": 10000}, self.LINES, 22000,
                             dt.date(2026, 7, 2), 1, 2026)
        self.assertEqual(r["bought_qty"], 5000)
        self.assertAlmostEqual(r["bought_avg"], 19800)
        self.assertAlmostEqual(r["vs_budget_mt"], 200)          # under budget so far
        self.assertAlmostEqual(r["vs_budget_total"], 1_000_000)
        self.assertEqual(r["no_cost_qty"], 100)                  # listed, not averaged
        self.assertEqual(r["remaining_qty"], 5000)
        self.assertAlmostEqual(r["headroom_price"], 20200)       # (200M − 99M) / 5,000
        self.assertAlmostEqual(r["forecast_avg"], 20900)         # (99M + 5,000 × 22,000) / 10,000
        self.assertAlmostEqual(r["forecast_vs_budget_total"], -9_000_000)
        self.assertEqual(r["status"], "OVER")                    # forecast −4.5 %
        self.assertAlmostEqual(r["pct_year_elapsed"], 183 / 365 * 100, places=3)

    def test_no_budget_qty_uses_bought_only(self):
        r = budget_vs_actual({"price_egp_mt": 20000}, self.LINES, None)
        self.assertIsNone(r["forecast_avg"])
        self.assertIsNone(r["headroom_price"])
        self.assertEqual(r["status"], "ON_BUDGET")               # +1 % is within ±2 %

    def test_currency_neutral_keys(self):
        usd = budget_vs_actual({"price_mt": 230.0, "qty_mt": 1000},
                               [{"kind": "ACTUAL", "qty_mt": 400, "cost_mt": 220.0}], 240.0)
        self.assertAlmostEqual(usd["vs_budget_mt"], 10.0)
        self.assertAlmostEqual(usd["headroom_price"], (230000 - 88000) / 600)
        self.assertAlmostEqual(usd["forecast_avg"], (88000 + 600 * 240) / 1000)

    def test_statuses(self):
        self.assertEqual(budget_vs_actual(None, self.LINES)["status"], "NO_BUDGET")
        self.assertEqual(budget_vs_actual({"price_egp_mt": 20000}, [])["status"], "NOTHING_BOUGHT")
        self.assertEqual(budget_vs_actual({"price_egp_mt": 25000}, self.LINES)["status"], "UNDER")
        full = budget_vs_actual({"price_egp_mt": 20000, "qty_mt": 4000}, self.LINES, None)
        self.assertEqual(full["remaining_qty"], 0)                # bought more than budgeted
        self.assertAlmostEqual(full["forecast_avg"], 19800)


if __name__ == "__main__":
    unittest.main()
