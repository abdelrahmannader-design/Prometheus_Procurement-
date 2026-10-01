from __future__ import annotations

import datetime as dt
import unittest

from prometheus_core.usda_crop import (
    forecast_summary, parse_forecasts, parse_progress, parse_state_condition, parse_stocks,
    pick_latest_class, progress_signal, progress_summary, stocks_signal, yield_signal,
)


def _prog(year, week, pct, stage="HARVESTED", cls="ALL CLASSES", week_ending=None):
    return {"year": str(year), "reference_period_desc": f"WEEK #{week:02d}", "unit_desc": f"PCT {stage}",
            "Value": str(pct), "agg_level_desc": "NATIONAL", "class_desc": cls,
            "week_ending": week_ending or f"{year}-09-{min(28, week - 10):02d}"}


class ProgressTests(unittest.TestCase):
    def test_summary_vs_last_year_and_5yr_average(self):
        rows = [_prog(2026, 38, 10), _prog(2026, 39, 18, week_ending="2026-09-27")]
        for y, p in zip(range(2021, 2026), (20, 25, 30, 28, 27)):
            rows += [_prog(y, 37, p - 8), _prog(y, 39, p)]
        s = progress_summary(parse_progress({"data": rows}), 2026)
        h = next(x for x in s if x["stage"] == "HARVESTED")
        self.assertEqual(h["pct"], 18)
        self.assertEqual(h["prev_week"], 10)
        self.assertEqual(h["last_year"], 27)
        self.assertAlmostEqual(h["avg5"], 26.0)
        sig = progress_signal(s, dt.date(2026, 9, 29))
        self.assertEqual(sig["direction"], 1)                      # 8 pts behind → up risk
        self.assertIn("Harvested 18% vs 26% 5-yr average", sig["reading"])

    def test_missing_week_before_first_report_is_zero(self):
        rows = [_prog(2026, 39, 5, week_ending="2026-09-27"), _prog(2025, 40, 12)]
        s = progress_summary(parse_progress(rows), 2026)
        self.assertEqual(s[0]["last_year"], 0.0)

    def test_wheat_classes_and_out_of_season(self):
        rows = [_prog(2026, 39, 30, "PLANTED", "WINTER", "2026-09-27"), _prog(2026, 36, 100, "HARVESTED", "SPRING")]
        s = progress_summary(parse_progress(rows), 2026)
        self.assertEqual({x["stage"] for x in s}, {"WINTER · PLANTED", "SPRING · HARVESTED"})
        self.assertIsNone(progress_signal(s, dt.date(2026, 12, 1)))  # nothing reported in 3 weeks


def _fc(year, period, value, stat="YIELD", prefix="CORN, GRAIN"):
    unit = "BU / ACRE" if stat == "YIELD" else "BU"
    return {"year": year, "reference_period_desc": period, "Value": value, "agg_level_desc": "NATIONAL",
            "short_desc": f"{prefix} - {stat}, MEASURED IN {unit}"}


class ForecastTests(unittest.TestCase):
    def test_latest_forecast_vs_previous(self):
        rows = [_fc(2026, "YEAR - AUG FORECAST", "180.7"), _fc(2026, "YEAR - SEP FORECAST", "178.5"),
                _fc(2025, "YEAR", "186.5"), _fc(2025, "YEAR - NOV FORECAST", "185.0"),
                {"year": 2026, "reference_period_desc": "YEAR - SEP FORECAST", "Value": "220",
                 "short_desc": "CORN, GRAIN, IRRIGATED - YIELD, MEASURED IN BU / ACRE"}]
        y = forecast_summary(parse_forecasts(rows, "CORN", "YIELD"), 2026)
        self.assertEqual((y["value"], y["prev_value"], y["last_year"]), (178.5, 180.7, 186.5))
        prod = forecast_summary(parse_forecasts([_fc(2026, "YEAR - SEP FORECAST", "15,800,000,000", "PRODUCTION")],
                                                "CORN", "PRODUCTION"), 2026)
        sig = yield_signal(y, prod)
        self.assertEqual(sig["direction"], 1)                      # cut 1.2 % → up risk
        self.assertIn("15.80 bn bu", sig["reading"])

    def test_annual_copy_of_latest_forecast_is_ignored(self):
        rows = [_fc(2026, "YEAR - AUG FORECAST", "180.7"), _fc(2026, "YEAR - SEP FORECAST", "178.5"),
                _fc(2026, "YEAR", "178.5")]
        y = forecast_summary(parse_forecasts(rows, "CORN", "YIELD"), 2026)
        self.assertEqual((y["period"], y["prev_value"]), ("Sep forecast", 180.7))
        final = forecast_summary(parse_forecasts(rows[:2] + [_fc(2026, "YEAR", "177.9")], "CORN", "YIELD"), 2026)
        self.assertEqual((final["period"], final["value"], final["prev_value"]), ("final", 177.9, 178.5))

    def test_single_forecast_gives_no_signal(self):
        y = forecast_summary(parse_forecasts([_fc(2026, "YEAR - AUG FORECAST", "180")], "CORN", "YIELD"), 2026)
        self.assertIsNone(yield_signal(y))


class StocksTests(unittest.TestCase):
    def test_total_stocks_year_on_year(self):
        def row(y, q, v, sd="SOYBEANS - STOCKS, MEASURED IN BU"):
            return {"year": y, "reference_period_desc": q, "Value": v, "short_desc": sd, "agg_level_desc": "NATIONAL"}
        rows = [row(2025, "FIRST OF SEP", "342,000,000"), row(2026, "FIRST OF JUN", "970,000,000"),
                row(2026, "FIRST OF SEP", "300,000,000"),
                row(2026, "FIRST OF SEP", "100,000,000", "SOYBEANS, ON FARM, STORAGE - STOCKS, MEASURED IN BU")]
        st = parse_stocks(rows, "SOYBEANS")
        self.assertEqual(len(st), 3)                               # on-farm split ignored
        sig = stocks_signal(st)
        self.assertEqual(sig["direction"], 1)                      # −12 % vs a year ago
        self.assertEqual(sig["as_of"], "1 Sep 2026")


class StateTests(unittest.TestCase):
    def test_states_latest_week_and_change(self):
        def row(st, wk, cat, v, cls="ALL CLASSES"):
            return {"state_alpha": st, "state_name": st, "week_ending": wk, "unit_desc": f"PCT {cat}",
                    "Value": v, "class_desc": cls}
        rows = []
        for wk, (ex, good) in (("2026-09-20", (20, 45)), ("2026-09-27", (18, 44))):
            rows += [row("IA", wk, "EXCELLENT", ex), row("IA", wk, "GOOD", good), row("IA", wk, "POOR", 5),
                     row("IA", wk, "VERY POOR", 2), row("IA", wk, "FAIR", 100 - ex - good - 7)]
        rows += [row("CA", "2026-09-27", "EXCELLENT", 50), row("CA", "2026-09-27", "GOOD", 50)]
        st = parse_state_condition(rows, "CORN")
        self.assertEqual([s["state"] for s in st], ["IA"])         # only key producing states
        self.assertEqual((st[0]["ge"], st[0]["change"], st[0]["poor"]), (62, -3, 7))

    def test_pick_latest_wheat_class(self):
        rows = [{"class_desc": "WINTER", "week_ending": "2026-05-31"},
                {"class_desc": "SPRING, (EXCL DURUM)", "week_ending": "2026-08-30"}]
        self.assertEqual(pick_latest_class(rows), [rows[1]])


if __name__ == "__main__":
    unittest.main()
