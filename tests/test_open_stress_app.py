"""The app's open-contracts stress test: history over a chosen period."""
import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
APP = ROOT / "Prometheus_V10_9_10.py"


@unittest.skipUnless(APP.exists(), "the desktop app file is not in this checkout")
class PeriodHistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("prometheus_open_stress_app", APP)
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def _app(self):
        today = dt.date.today()
        hist = []
        for i in range(400):                      # a year+ of daily closes, high 60 days ago
            d = today - dt.timedelta(days=i)
            px = 450.0 + (40.0 if i == 60 else 0.0) + (i % 7)
            hist.append({"date": d.isoformat(), "commodity": "CORN", "close": px})
        hist.append({"date": (today - dt.timedelta(days=300)).isoformat(), "commodity": "CORN", "close": 600.0})
        app = self.module.App.__new__(self.module.App)
        app.state_obj = {"cbot_history": hist, "fx_history": [], "ui": {}}
        return app

    def test_period_window_and_history_case(self):
        app = self._app()
        pos = [{"base": "CORN", "cbot": 450.0}]
        h3, notes3, p3 = app._os_history(pos, horizon=20, months=3)
        self.assertEqual(p3["months"], 3)
        self.assertEqual(p3["label"], "in the last 3 months")
        self.assertAlmostEqual(p3["by_base"]["CORN"]["high"], 490.0 + (60 % 7))
        self.assertNotIn("series", p3["by_base"]["CORN"])
        self.assertIn("CORN", h3)
        hall, _n, pall = app._os_history(pos, horizon=20, months=0)
        self.assertEqual(pall["by_base"]["CORN"]["high"], 600.0)      # the old spike only counts in "all history"
        self.assertEqual(pall["label"], "over the whole history")

    def test_periods_offered(self):
        self.assertEqual([m for _l, m in self.module.App.OS_PERIODS], [0, 12, 6, 4, 3])


if __name__ == "__main__":
    unittest.main()
