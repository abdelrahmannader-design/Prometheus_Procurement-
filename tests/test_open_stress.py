"""Open-contracts stress test (prometheus_core.open_stress)."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from prometheus_core import open_stress as ost  # noqa: E402


def pos(**kw):
    p = {"id": "C1", "base": "CORN", "qty": 1000.0, "unpriced_mt": 1000.0, "cif_basis": "live",
         "cif": 250.0, "cbot": 450.0, "premium": 185.0, "factor": 0.3937, "fx": 50.0, "fx_secured": False,
         "disc": 200.0, "clr": 200.0, "freight": 400.0, "local": 14000.0, "local_transport": 300.0}
    p.update(kw)
    return p


class RevalueTests(unittest.TestCase):
    def test_base_matches_the_open_mtm_formula(self):
        r = ost.revalue(pos())
        self.assertAlmostEqual(r["own0"], 250 * 50 + 200 + 200 + 400)
        self.assertAlmostEqual(r["sav0"], 14000 - 13300)
        self.assertAlmostEqual(r["tot0"], 700 * 1000)
        x = ost.revalue(pos(), excl=True)
        self.assertAlmostEqual(x["own0"], 12900)
        self.assertAlmostEqual(x["sav0"], 13700 - 12900)

    def test_change_splits_exactly(self):
        r = ost.revalue(pos(), dc=0.10, dfx=0.05, dloc=-0.04)
        self.assertAlmostEqual(r["from_cbot"] + r["from_fx"] + r["from_local"], r["chg"], places=6)
        self.assertAlmostEqual(r["from_cbot"], -(450 * 0.10 * 0.3937) * 50 * 1000)
        self.assertAlmostEqual(r["from_local"], 13700 * -0.04 * 1000)

    def test_only_exposed_parts_move(self):
        fixed = ost.revalue(pos(cif_basis="saved"), dc=0.2)
        self.assertEqual(fixed["from_cbot"], 0)
        half = ost.revalue(pos(unpriced_mt=500.0), dc=0.2)
        self.assertAlmostEqual(half["from_cbot"], ost.revalue(pos(), dc=0.2)["from_cbot"] / 2)
        f4 = ost.revalue(pos(fx_secured=True), dfx=0.1)
        self.assertEqual(f4["from_fx"], 0)
        self.assertEqual(f4["fx_mt"], 0)

    def test_break_evens_zero_the_saving(self):
        p = pos()
        r = ost.revalue(p)
        at_cbot = ost.revalue(p, dc=r["be_cbot_move"])
        self.assertAlmostEqual(at_cbot["sav1"], 0, places=6)
        at_fx = ost.revalue(p, dfx=r["be_fx_move"])
        self.assertAlmostEqual(at_fx["sav1"], 0, places=6)
        at_loc = ost.revalue(p, dloc=r["be_local_move"])
        self.assertAlmostEqual(at_loc["sav1"], 0, places=6)
        self.assertIsNone(ost.revalue(pos(fx_secured=True))["be_fx"])

    def test_missing_inputs_are_left_out(self):
        r = ost.revalue(pos(cif=None))
        self.assertFalse(r["ok"])
        t = ost.scenario_total([pos(), pos(id="C2", local=None)])
        self.assertEqual((t["n"], t["na"]), (1, 1))

    def test_verdicts(self):
        self.assertEqual(ost.revalue(pos(), dc=0.5)["verdict"], "flips to loss")
        self.assertEqual(ost.revalue(pos(), dc=-0.1)["verdict"], "holds")


class RunTests(unittest.TestCase):
    def test_scenarios_and_grid(self):
        ps = [pos(), pos(id="C2", base="SBM", factor=1.1023, cbot=320.0, cif=455.0, local=27600.0, fx_secured=True)]
        res = ost.run(ps, cbot=[-0.05, 0.10], fx=[0.05], local=[-0.05], history={"CORN": 0.125, "SBM": 0.13})
        names = [s["name"] for s in res["scenarios"]]
        self.assertEqual(names, ["Base", "Best", "Adverse", "History"])
        base, adverse = res["scenarios"][0], res["scenarios"][2]
        self.assertAlmostEqual(base["chg"], 0)
        self.assertEqual((adverse["dc"], adverse["dfx"], adverse["dloc"]), (0.10, 0.05, -0.05))
        self.assertEqual(len(res["grid"]), 3 * 2 * 2)        # cbot (with 0) × fx (with 0) × local (with 0)
        self.assertAlmostEqual(res["grid"][(0.0, 0.0, 0.0)]["tot1"], base["tot0"])
        self.assertEqual(res["fx_exposed_mt"], 1000.0)
        hist = res["scenarios"][3]
        self.assertEqual(hist["dc_by_base"], {"CORN": 0.125, "SBM": 0.13})
        self.assertTrue(any("Adverse" in line for line in ost.summary(res)))


class CbotLevelTests(unittest.TestCase):
    def test_levels_and_book_break_even(self):
        ps = [pos(), pos(id="C2", qty=2000.0, unpriced_mt=2000.0, local=14200.0)]
        self.assertEqual(ost.spots(ps), {"CORN": 450.0})
        self.assertAlmostEqual(ost.cbot_levels(ps, 0.10)["CORN"], 495.0)
        self.assertEqual(ost.level_text(ps, 0.05), "CORN 472.50")
        be = ost.book_break_even(ps)
        self.assertAlmostEqual(ost.scenario_total(ps, be)["tot1"], 0, places=4)
        # a dearer FX or cheaper local brings the break-even CBOT down
        self.assertLess(ost.book_break_even(ps, dfx=0.03), be)
        self.assertLess(ost.book_break_even(ps, dloc=-0.03), be)
        self.assertIsNone(ost.book_break_even([pos(cif_basis="saved")]))

    def test_run_carries_levels_and_break_evens(self):
        res = ost.run([pos()], cbot=[0.05], fx=[0.03], local=[-0.03])
        self.assertEqual(res["spots"], {"CORN": 450.0})
        self.assertEqual(set(res["be_book"]), {(f, l) for f in (0.0, 0.03) for l in (-0.03, 0.0)})
        self.assertTrue(any(line.startswith("Break-even CBOT") for line in ost.summary(res)))


class PeriodTests(unittest.TestCase):
    SERIES = [("2026-06-01", 400.0), ("2026-08-10", 470.0), ("2026-09-15", 430.0),
              ("2026-10-20", 455.0), ("2026-11-06", 450.0)]

    def test_period_range_window(self):
        r = ost.period_range(self.SERIES, 3)
        self.assertEqual((r["from"], r["to"], r["points"]), ("2026-08-10", "2026-11-06", 4))
        self.assertEqual((r["low"], r["low_date"], r["high"], r["high_date"]), (430.0, "2026-09-15", 470.0, "2026-08-10"))
        self.assertAlmostEqual(r["avg"], (470 + 430 + 455 + 450) / 4)
        self.assertEqual(ost.period_range(self.SERIES, 0)["points"], 5)        # whole history
        self.assertIsNone(ost.period_range([], 3))
        self.assertEqual(ost.period_label(4), "in the last 4 months")

    def test_period_cases_in_run(self):
        pr = ost.period_range(self.SERIES, 3)
        res = ost.run([pos()], period={"label": ost.period_label(3), "by_base": {"CORN": pr}})
        ph = next(t for t in res["scenarios"] if t["name"] == "Period high")
        self.assertAlmostEqual(ph["dc_by_base"]["CORN"], 470 / 450 - 1)
        self.assertEqual((ph["dfx"], ph["dloc"]), (0.0, 0.0))
        bk = res["period"]["book"]
        self.assertGreater(bk["low"], bk["avg"])
        self.assertGreater(bk["avg"], bk["high"])
        self.assertAlmostEqual(bk["high"], ph["tot1"])
        self.assertTrue(any("above the period high" in line for line in ost.summary(res)))

    def test_no_period_no_extra_case(self):
        res = ost.run([pos()])
        self.assertNotIn("Period high", [t["name"] for t in res["scenarios"]])
        self.assertIsNone(res["period"])


if __name__ == "__main__":
    unittest.main()
