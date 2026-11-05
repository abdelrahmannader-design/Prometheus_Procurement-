"""Realised savings on the shared engine: consumption-day local, route freight."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prometheus_core import realised as rl  # noqa: E402

APP = ROOT / "Prometheus_V10_9_10.py"
needs_app = unittest.skipUnless(APP.exists(), "the desktop app file is not in this checkout")


def _day(cid, date, mt, cost, local, *, cost_x=None, local_x=None, freight=300.0,
         local_date=None, age=0):
    sav = None if cost is None or local is None else (local - cost) * mt
    cost_x = cost_x if cost_x is not None else (None if cost is None else cost - freight)
    local_x = local_x if local_x is not None else (None if local is None else local - 250)
    sav_x = None if cost_x is None or local_x is None else (local_x - cost_x) * mt
    return {"contract_id": cid, "date": date, "mt": mt, "cost": cost, "local": local,
            "cost_excl": cost_x, "local_excl": local_x, "saving": sav, "saving_excl": sav_x,
            "freight": freight if cost is not None else None, "cif_used": 200.0, "fx_used": 50.0,
            "discharge": 250.0, "clearance": 200.0, "freight_basis": "Freight table: A → B",
            "local_date": local_date or date, "local_age": age}


def _model():
    # C1: closed, 300 MT consumed over two months, 200 MT still in stock.
    # cost = 200 × 50 + 250 + 200 + 300 = 10,750 every day.
    return {
        "contracts": [{"id": "C1", "status": "Closed", "available_mt": 200.0},
                      {"id": "C2", "status": "Closed", "available_mt": 500.0},
                      {"id": "C3", "status": "Closed", "available_mt": 0.0}],
        "savings": [
            _day("C1", "2026-08-30", 100, 10750, 11250),
            _day("C1", "2026-09-02", 100, 10750, 11000, local_date="2026-08-26", age=7),
            _day("C1", "2026-09-03", 100, 10750, None, local_x=None),
            # C3: local known but no route freight → excl. only
            _day("C3", "2026-09-04", 50, None, 11000, cost_x=10450, local_x=10750),
        ],
    }


class AggregateTests(unittest.TestCase):
    def test_contract_record(self):
        a = rl.aggregate(_model())["C1"]
        self.assertEqual(a["consumed_mt"], 300)
        self.assertEqual(a["compared_mt"], 200)
        self.assertEqual(a["no_local_mt"], 100)
        self.assertEqual(a["in_stock_mt"], 200)
        self.assertAlmostEqual(a["saving"], 500 * 100 + 250 * 100)
        self.assertAlmostEqual(a["saving_excl"], (11250 - 250 - 10450) * 100 + (11000 - 250 - 10450) * 100)
        self.assertAlmostEqual(a["cost"], 10750)
        self.assertAlmostEqual(a["local"], 11125)
        self.assertAlmostEqual(a["saving_mt"], 375)
        self.assertEqual((a["first_day"], a["last_day"]), ("2026-08-30", "2026-09-03"))
        self.assertEqual((a["local_from"], a["local_to"]), ("2026-08-26", "2026-08-30"))
        self.assertEqual(a["local_age_max"], 7)
        self.assertTrue(a["stale"])
        self.assertEqual(rl.age_label(a), "2026-08-26 → 2026-08-30 · 7d ⚠")

    def test_in_stock_only_and_missing_freight(self):
        agg = rl.aggregate(_model())
        c2 = agg["C2"]
        self.assertEqual((c2["consumed_mt"], c2["in_stock_mt"]), (0, 500))
        self.assertIsNone(c2["saving"])
        c3 = agg["C3"]
        self.assertIsNone(c3["saving"])
        self.assertEqual(c3["no_cost_mt"], 50)
        self.assertAlmostEqual(c3["saving_excl"], 300 * 50)

    def test_month_split_and_slice(self):
        days = rl.aggregate(_model())["C1"]["days"]
        self.assertEqual(rl.split_by_month(days), {"2026-08": 50000.0, "2026-09": 25000.0})
        mt, s, _sx = rl.slice_days(days, lambda d: d[:7] == "2026-09")
        self.assertEqual((mt, s), (100, 25000.0))


def _state():
    return {
        "contracts": {
            "C1": {"name": "Closed corn", "commodity": "CORN", "status": "Closed", "priced": True,
                   "qty_mt": 500, "cif_usd_mt": 200.0, "delivery_fx": 50.0,
                   "discharge_egp_mt": 250, "clearance_egp_mt": 200, "freight_egp_mt": 300,
                   "delivery_date": "2026-08-20", "closed_date": "2026-08-20"},
            "C2": {"name": "Closed in stock", "commodity": "CORN", "status": "Closed", "priced": True,
                   "qty_mt": 500, "cif_usd_mt": 200.0, "delivery_fx": 50.0,
                   "discharge_egp_mt": 250, "clearance_egp_mt": 200, "freight_egp_mt": 300,
                   "delivery_date": "2026-09-01", "closed_date": "2026-09-01"},
        },
        "local_prices": [{"date": "2026-08-15", "commodity": "CORN", "price_egp_mt": 12000,
                          "transport_egp_mt": 250}],
        "fx_history": [], "cbot_history": [], "snapshots": [], "suppliers": {},
        "market_data": {"fx": {"price": 51.0}}, "ui": {},
    }


@needs_app
class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prometheus_realised_app", ROOT / "Prometheus_V10_9_10.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def _app(self, model=None):
        app = self.module.App.__new__(self.module.App)
        app.state_obj = _state()
        app.builds = 0

        def build():
            app.builds += 1
            if model == "boom":
                raise RuntimeError("engine down")
            return model or _model()
        app._xr_build_model = build
        return app

    def test_closed_row_uses_consumption_days(self):
        app = self._app()
        c = app.state_obj["contracts"]["C1"]
        row = app._sv_contract_saving_row("C1", c)
        self.assertEqual(row["method"], "consumption")
        self.assertEqual(row["qty"], 200)                       # tonnes compared
        self.assertEqual(row["consumed_mt"], 300)
        self.assertEqual(row["in_stock_mt"], 200)
        self.assertAlmostEqual(row["total_sav"], 75000)
        self.assertAlmostEqual(row["own_after"], 10750)
        self.assertAlmostEqual(row["local"], 11125)
        self.assertAlmostEqual(row["freight"], 300)
        self.assertIn("in stock", row["status"])
        self.assertIn("⚠ old quote", row["status"])
        # the delivery-date result stays on the row: 12,250 − 10,750 on all 500 MT
        self.assertAlmostEqual(row["old_total_sav"], 1500 * 500)
        # the cost build-up still adds up for the Excel formula
        self.assertAlmostEqual(row["cif_usd"] * row["delivery_fx"] + row["discharge"]
                               + row["clearance"] + row["freight"], row["own_after"])

    def test_in_stock_contract_is_not_realised(self):
        app = self._app()
        row = app._sv_contract_saving_row("C2", app.state_obj["contracts"]["C2"])
        self.assertIsNone(row["total_sav"])
        self.assertEqual(row["tag"], "stock")
        self.assertIn("not yet realised", row["status"])

    def test_totals_months_and_cache(self):
        app = self._app()
        rows, tot = app._sv_collect_savings_rows()
        self.assertAlmostEqual(tot["grand_sav"], 75000)
        self.assertEqual(tot["grand_qty"], 200)
        self.assertEqual(tot["counted"], 1)
        self.assertEqual(tot["consumed_mt"], 300)
        self.assertEqual(tot["in_stock_mt"], 700)
        self.assertEqual(tot["month_tots"], {"2026-08": 50000.0, "2026-09": 25000.0})
        self.assertEqual(tot["basis"], "consumption-day local, route freight")
        app._sv_collect_savings_rows()
        self.assertEqual(app.builds, 1)                         # cached
        app.state_obj["local_prices"].append({"date": "2026-09-01", "commodity": "CORN",
                                              "price_egp_mt": 11800})
        app._sv_collect_savings_rows()
        self.assertEqual(app.builds, 2)                         # data changed → rebuilt

    def test_monthly_report_by_consumption_month(self):
        app = self._app()
        d = app._monthly_report_data(2026, 9, today=self.module.dt.date(2026, 9, 30))
        self.assertAlmostEqual(d["month_total"], 25000)
        self.assertEqual(d["month_qty"], 100)
        self.assertAlmostEqual(d["prev_total"], 50000)
        self.assertAlmostEqual(d["ytd_total"], 75000)
        self.assertEqual(d["basis"], "consumption-day local, route freight")
        self.assertTrue(any("consumed in September 2026" in line for line in d["summary"]))

    def test_setup_switch_back_to_delivery_date(self):
        app = self._app()
        app.state_obj["ui"]["realised_method"] = "delivery"
        rows, tot = app._sv_collect_savings_rows()
        self.assertEqual(app.builds, 0)
        self.assertAlmostEqual(tot["grand_sav"], 1500 * 500 + 1500 * 500)
        self.assertEqual(tot["grand_qty"], 1000)
        self.assertIsNone(tot["grand_sav_excl"])

    def test_engine_failure_falls_back_to_delivery_date(self):
        app = self._app(model="boom")
        rows, tot = app._sv_collect_savings_rows()
        self.assertEqual(tot["basis"], "delivery-date local (engine unavailable)")
        self.assertTrue(all(r["method"].startswith("delivery") for r in rows))
        self.assertAlmostEqual(tot["grand_sav"], 1500 * 1000)

    def test_home_metrics(self):
        app = self._app()
        app._home_contract_matches_filter = lambda c, sel: True
        app._home_commodity_options = lambda: ["CORN"]
        app._home_coverage_for_commodity = lambda comm, q: {"status": "", "days": None}
        m = app._home_exec_metrics("ALL")
        self.assertAlmostEqual(m["realized_saving"], 75000)
        self.assertAlmostEqual(m["realized_per_mt"], 375)
        self.assertEqual(m["closed_qty"], 300)                  # consumed, not contract qty
        self.assertEqual(m["closed_stock_mt"], 700)
        self.assertEqual(m["method"], "consumption")
        self.assertAlmostEqual(m["old_realized_saving"], 1500 * 1000)


@needs_app
class RealEngineTests(unittest.TestCase):
    """The real engine on a small book: no route freight → excl. only, clearly labelled."""

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prometheus_realised_real", ROOT / "Prometheus_V10_9_10.py")
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_no_route_freight(self):
        app = self.module.App.__new__(self.module.App)
        st = _state()
        del st["contracts"]["C2"]
        c = st["contracts"]["C1"]
        c["storage_start"] = c["delivery_date"]
        st["consumption"] = {"CORN": 50}
        st["consumption_log"] = [{"date": c["delivery_date"], "commodity": "CORN", "received_mt": 500,
                                  "consumed_mt": 0, "contract_id": "C1"}]
        app.state_obj = st
        row = app._sv_contract_saving_row("C1", c)
        self.assertEqual(row["method"], "consumption")
        self.assertEqual(row["consumed_mt"], 500)
        self.assertIsNone(row["total_sav"])
        self.assertIn("No route freight", row["status"])
        self.assertIsNotNone(row["total_sav_excl"])
        _rows, tot = app._sv_collect_savings_rows()
        self.assertAlmostEqual(tot["grand_sav_excl"], row["total_sav_excl"])
        self.assertEqual(tot["grand_qty_excl"], 500)


if __name__ == "__main__":
    unittest.main()
