from __future__ import annotations

import datetime as dt
import math
import unittest

from prometheus_core.market_signals import (
    combine_signals, cot_signal, crop_condition_signal, curve_signal, deferred_contract,
    parse_cot_rows, parse_nass_condition, report_calendar, seasonal_signal, seasonality,
    trend_signal, wasde_signal,
)


def _cot_payload(n=156, last_long=None):
    rows = []
    for i in range(n):
        d = dt.date(2023, 10, 3) + dt.timedelta(weeks=i)
        rows.append({"report_date_as_yyyy_mm_dd": f"{d.isoformat()}T00:00:00.000",
                     "m_money_positions_long_all": str(200000 + i * 100),
                     "m_money_positions_short_all": "150000", "open_interest_all": "1500000"})
    if last_long is not None:
        rows[-1]["m_money_positions_long_all"] = str(last_long)
    return list(reversed(rows))  # the API returns newest first


class CotTests(unittest.TestCase):
    def test_parse_sorts_oldest_first_and_reads_socrata_fields(self):
        rows = parse_cot_rows(_cot_payload(5))
        self.assertEqual(len(rows), 5)
        self.assertLess(rows[0]["date"], rows[-1]["date"])
        self.assertEqual(rows[0]["long"], 200000.0)

    def test_record_fund_short_is_up_risk(self):
        s = cot_signal(parse_cot_rows(_cot_payload(last_long=20000)))
        self.assertEqual(s["direction"], 1)
        self.assertIn("1st percentile", s["reading"])

    def test_record_fund_long_is_down_risk(self):
        s = cot_signal(parse_cot_rows(_cot_payload(last_long=900000)))
        self.assertEqual(s["direction"], -1)

    def test_empty_is_none(self):
        self.assertIsNone(cot_signal(parse_cot_rows([])))


class NassTests(unittest.TestCase):
    def test_parse_and_signal(self):
        payload = {"data": [
            {"week_ending": "2026-09-13", "unit_desc": "PCT EXCELLENT", "Value": "20"},
            {"week_ending": "2026-09-13", "unit_desc": "PCT GOOD", "Value": "46"},
            {"week_ending": "2026-09-20", "unit_desc": "PCT EXCELLENT", "Value": "18"},
            {"week_ending": "2026-09-20", "unit_desc": "PCT GOOD", "Value": "44"},
            {"week_ending": "2026-09-20", "unit_desc": "PCT POOR", "Value": "9"},
        ]}
        weeks = parse_nass_condition(payload)
        self.assertEqual([w["ge"] for w in weeks], [66.0, 62.0])
        ly = [{"week_ending": "2025-08-31", "ge": 60}, {"week_ending": "2025-09-21", "ge": 70}]
        s = crop_condition_signal(weeks, ly)
        self.assertIn("-8 pts vs last year", s["reading"])  # matched to the same week, not by index
        self.assertEqual(s["direction"], 1)


class WasdeCurveTrendTests(unittest.TestCase):
    def test_wasde_cut_is_up_risk(self):
        self.assertEqual(wasde_signal(1900, 2100, 290, 300)["direction"], 1)
        self.assertEqual(wasde_signal(2300, 2100)["direction"], -1)
        self.assertEqual(wasde_signal(2110, 2100)["direction"], 0)
        self.assertIsNone(wasde_signal(None, 2100))

    def test_curve(self):
        self.assertEqual(curve_signal(430, 420)["direction"], 1)    # inverted
        self.assertEqual(curve_signal(400, 440)["direction"], -1)   # wide carry
        self.assertEqual(curve_signal(400, 410)["direction"], 0)

    def test_deferred_contract_symbol(self):
        self.assertEqual(deferred_contract("CORN", dt.date(2026, 9, 27)), ("ZCH27.CBT", "Mar 2027"))
        self.assertEqual(deferred_contract("SOYBEAN", dt.date(2026, 9, 27))[0], "ZSH27.CBT")
        self.assertEqual(deferred_contract("SBM", dt.date(2026, 11, 2))[0], "ZMK27.CBT")
        self.assertEqual(deferred_contract("XXX", dt.date(2026, 9, 27)), (None, ""))

    def test_trend(self):
        up = [(f"d{i:03d}", 100 + i) for i in range(120)]
        self.assertEqual(trend_signal(up)["direction"], 1)
        self.assertEqual(trend_signal(list(reversed([(d, v) for d, v in up])))["direction"], -1)
        self.assertIsNone(trend_signal(up[:30]))


class SeasonalityTests(unittest.TestCase):
    def test_monthly_pattern(self):
        series = []
        d = dt.date(2022, 12, 1)
        while d <= dt.date(2026, 9, 30):
            series.append((d.isoformat(), 400 + 40 * math.sin(d.timetuple().tm_yday / 58.0)))
            d += dt.timedelta(days=1)
        season = seasonality(series)
        self.assertGreaterEqual(season["years"], 4)
        jan = season["table"][0]
        self.assertEqual(jan["name"], "Jan")
        self.assertEqual(jan["years"], 4)
        self.assertGreater(jan["avg_pct"], 1.5)  # sine rises through January
        s = seasonal_signal(season, dt.date(2026, 12, 5))  # next month = Jan
        self.assertEqual(s["direction"], 1)
        self.assertIsNone(seasonal_signal(seasonality(series[:40]), dt.date(2026, 1, 5)))


class CombineTests(unittest.TestCase):
    def test_bias_and_shocks(self):
        up = combine_signals([wasde_signal(1900, 2100), curve_signal(430, 420), None])
        self.assertEqual(up["bias"], "UP")
        self.assertEqual(up["suggested_cbot_shocks"], "-5, 5, 10, 15")
        down = combine_signals([wasde_signal(2300, 2100)])
        self.assertEqual(down["bias"], "DOWN")
        self.assertEqual(combine_signals([])["bias"], "BALANCED")


class CalendarTests(unittest.TestCase):
    def test_fixed_rule_dates(self):
        ev = report_calendar(dt.date(2026, 1, 1), dt.date(2026, 12, 31))
        names = {(e["name"], e["date"]) for e in ev}
        self.assertIn(("Prospective Plantings + Grain Stocks", dt.date(2026, 3, 31)), names)
        self.assertIn(("Acreage + Grain Stocks", dt.date(2026, 6, 30)), names)
        self.assertIn(("Grain Stocks", dt.date(2026, 9, 30)), names)
        # Crop Progress moves to Tuesday after Memorial Day and Labor Day
        self.assertIn(("Crop Progress", dt.date(2026, 5, 26)), names)
        self.assertIn(("Crop Progress", dt.date(2026, 9, 8)), names)
        self.assertNotIn(("Crop Progress", dt.date(2026, 12, 7)), names)
        wasde = [e for e in ev if e["name"] == "WASDE"]
        self.assertEqual(len(wasde), 12)
        self.assertTrue(all(e["estimated"] and e["date"].weekday() < 5 for e in wasde))

    def test_sorted_and_in_range(self):
        ev = report_calendar(dt.date(2026, 9, 27), dt.date(2026, 10, 20))
        self.assertTrue(all(dt.date(2026, 9, 27) <= e["date"] <= dt.date(2026, 10, 20) for e in ev))
        self.assertEqual(ev, sorted(ev, key=lambda e: (e["date"], {"High": 0, "Medium": 1, "Low": 2}[e["impact"]])))


if __name__ == "__main__":
    unittest.main()
