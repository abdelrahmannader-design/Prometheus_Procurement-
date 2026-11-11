"""The one-screen-wide CBOT fixed vs consumption workbook."""
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prometheus_core import cbot_overview as ov  # noqa: E402

FACTOR = 0.3937


def cbot_row(cid, day, cbot, cif=245.66, mt=500.0, fx=53.58, prem=175.0, base="CORN"):
    fix = cif / FACTOR - prem
    diff = cbot - fix
    return {"date": day, "contract_id": cid, "contract": "REF-" + cid, "supplier": "COFCO", "commodity": base + "-BRZ",
            "base": base, "mt": mt, "cif": cif, "premium": prem, "unit": "¢/bu", "factor": FACTOR, "fix": fix,
            "fix_type": "Implied", "futures": "DEC-26", "cbot": cbot, "diff": diff, "usd_mt": diff * FACTOR,
            "usd": diff * FACTOR * mt, "egp": diff * FACTOR * mt * fx, "fx": fx, "assessable": True,
            "win_cbot": 460.4, "win_start": "2026-10-20", "win_end": "2026-10-26"}


def sav_row(cid, day, cif=245.66, fx=53.58, local_excl=14900.0, base="CORN"):
    return {"contract_id": cid, "date": day, "base": base, "cif_used": cif, "fx_used": fx, "cif_egp": cif * fx,
            "discharge": 225.0, "clearance": 200.0, "freight": 343.98, "cost_excl": cif * fx + 425.0,
            "local_excl": local_excl, "supplier": "COFCO", "commodity": base + "-BRZ"}


def model():
    cb = [cbot_row("C1", "2026-10-23", 456.0), cbot_row("C1", "2026-10-24", 455.0),
          cbot_row("C2", "2026-09-29", 440.0, cif=250.0), cbot_row("C2", "2026-09-30", 441.0, cif=250.0),
          cbot_row("C2", "2026-10-01", 500.0, cif=260.0),                 # a second lot: other terms
          cbot_row("S1", "2026-10-01", 300.0, base="SBM")]
    un = [{"date": "2026-11-01", "contract_id": "C3", "contract": "REF-C3", "base": "CORN", "mt": 500.0, "premium": 180.0,
           "factor": FACTOR, "futures": "DEC-26", "cbot": 450.0, "latest_cbot": 446.25, "latest_cbot_date": "2026-11-11",
           "latest_cbot_live": True, "fx": 55.0}]
    sv = [sav_row(r["contract_id"], r["date"], cif=r["cif"]) for r in cb] + [sav_row("C3", "2026-11-01", cif=246.5, fx=55.0)]
    return {"as_of": "2026-11-11", "options": {"neutral_cbot": 1.0}, "cbot": cb, "cbot_unfixed": un, "savings": sv,
            "contracts": [{"id": "C1", "qty_mt": 2000.0, "is_open": False}, {"id": "C2", "qty_mt": 2000.0},
                          {"id": "C3", "qty_mt": 2000.0, "is_open": True}]}


def trail():
    days = [{"date": d, "cbot": c, "market_fx": x, "local_excl": 14300.0}
            for d, c, x in (("2026-10-28", 451.75, 56.09), ("2026-10-29", 451.5, 56.08), ("2026-10-30", 447.75, 56.0),
                            ("2026-11-02", 449.75, 55.99), ("2026-11-03", 446.0, 55.53))]
    return {"contract_id": "C9", "contract": "OPEN-9", "supplier": "ADM", "mt": 5000.0, "pricing": "Unpriced",
            "entered": "2026-11-02", "storage_start": "", "day0": "2026-11-02", "premium": 197.0, "factor": FACTOR,
            "fixed_cif": None, "fixed_fx": None, "discharge": 235.0, "clearance": 200.0, "other_fee": 0.0, "days": days}


class BlockTests(unittest.TestCase):
    def test_terms_once_per_block_newest_first(self):
        blocks = ov.fixed_blocks(model(), "CORN")
        self.assertEqual([(b["contract_id"], len(b["days"])) for b in blocks], [("C1", 2), ("C2", 1), ("C2", 2)])
        self.assertAlmostEqual(blocks[0]["cif"], 245.66)
        self.assertEqual(set(blocks[0]["days"][0]), {"date", "mt", "cbot", "local_excl"})   # only what changes by day
        self.assertEqual([b["contract_id"] for b in ov.unfixed_blocks(model(), "CORN")], ["C3"])
        self.assertEqual(ov.fixed_blocks(model(), "SBM")[0]["contract_id"], "S1")

    def test_lead_days(self):
        t = ["2026-10-27", "2026-10-28", "2026-10-29", "2026-10-30", "2026-11-02", "2026-11-03"]
        self.assertEqual(ov.lead_days(t, "2026-11-02", 3), ["2026-10-28", "2026-10-29", "2026-10-30"])
        self.assertEqual(ov.lead_days(t, "2026-11-02", 0), [])


class WorkbookTests(unittest.TestCase):
    def test_workbook(self):
        import openpyxl
        m = model()
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "ov.xlsx")
            res = ov.write_overview(m, fp, "CORN", [trail()], lead=3)
            self.assertEqual((res["fixed_contracts"], res["fixed_days"], res["unfixed_contracts"], res["open_contracts"]),
                             (3, 5, 1, 1))
            want = sum(r["usd"] for r in m["cbot"] if r["base"] == "CORN")
            self.assertAlmostEqual(res["fixed_usd"], want, places=6)
            wf, wv = openpyxl.load_workbook(fp), openpyxl.load_workbook(fp, data_only=True)
            self.assertEqual(wf.sheetnames, list(ov.SHEETS))
            for ws in wf.worksheets:                              # nothing to scroll sideways
                self.assertLessEqual(ws.max_column, 16, ws.title)
            fx, fv = wf["Fixed consumption"], wv["Fixed consumption"]
            # block 1: bar on row 4, terms on row 6, days from row 8
            self.assertIn("REF-C1", fx["A4"].value)
            self.assertEqual(fx["A6"].value, "=D6/C6-B6")                       # implied fixed CBOT
            self.assertEqual(fx["I6"].value, '=IF(ISNUMBER(F6),F6+G6+H6,"")')    # landed excl. transport
            self.assertAlmostEqual(fv["A6"].value, 245.66 / FACTOR - 175.0)
            self.assertEqual(fx["D8"].value, '=IF(AND(ISNUMBER(C8),ISNUMBER($A$6)),C8-$A$6,"")')
            r0 = m["cbot"][0]
            self.assertAlmostEqual(fv["D8"].value, r0["diff"]); self.assertAlmostEqual(fv["F8"].value, r0["usd"])
            self.assertAlmostEqual(fv["G8"].value, r0["egp"]); self.assertEqual(fv["K8"].value, "Advantage")
            self.assertAlmostEqual(fv["I8"].value, 14900.0 - (245.66 * 53.58 + 425.0))
            self.assertEqual(fx["F10"].value, "=SUM(F8:F9)")
            self.assertAlmostEqual(fv["F10"].value, m["cbot"][0]["usd"] + m["cbot"][1]["usd"])
            # summary reads the blocks and adds up to the engine's total
            sx, sv_ = wf["Summary"], wv["Summary"]
            self.assertEqual(sx["J10"].value, "='Fixed consumption'!F10")
            tot = next(r for r in range(10, 20) if str(sv_.cell(r, 1).value).startswith("Total — fixed"))
            self.assertAlmostEqual(sv_.cell(tot, 10).value, want, places=6)
            self.assertEqual(sv_.cell(tot, 4).value, 2500.0)
            # open contract: day 0 after three lead days; changes are formulas
            ox, ow = wf["Open contracts"], wv["Open contracts"]
            self.assertEqual(ox["I6"].value, "=A11")
            self.assertEqual(ow["I6"].value.date().isoformat(), "2026-11-02")
            self.assertEqual([ow.cell(r, 2).value for r in range(8, 13)], [-5, -4, -3, 0, 1])
            self.assertAlmostEqual(ow["E12"].value, 446.0 - 449.75)
            self.assertAlmostEqual(ow["H12"].value, 55.53 - 55.99)
            cif = (446.0 + 197.0) * FACTOR
            self.assertAlmostEqual(ow["I12"].value, cif)
            self.assertAlmostEqual(ow["J12"].value, cif * 55.53 + 435.0)
            self.assertAlmostEqual(ow["L12"].value, 14300.0 - (cif * 55.53 + 435.0))
            self.assertTrue(str(ox["J12"].value).startswith("=IF(ISNUMBER(I12)"))

    def test_receiving_date_side_by_side(self):
        import openpyxl
        m = model()
        win = [{"date": d, "cbot": c, "local_excl": 14800.0} for d, c in
               (("2026-10-20", 467.75), ("2026-10-21", 459.0), ("2026-10-22", 464.25), ("2026-10-23", 999.0),
                ("2026-10-24", 999.0), ("2026-10-25", 456.0), ("2026-10-26", 455.0), ("2026-10-27", 448.75))]
        rc = {"C1": {"date": "2026-10-20", "vessel": "ELENI M II", "shipment": "2nd half October", "closed": "2026-10-28",
                     "window": win, "cbot": 467.75, "local_excl": 14800.0, "contract": "REF-C1", "mt": 2000.0},
              "C3": {"date": "2026-10-30", "vessel": "MEGAN HOPE", "cbot": 455.0, "local_excl": 15100.0, "contract": "REF-C3",
                     "window": [{"date": "2026-10-30", "cbot": 455.0, "local_excl": 15100.0},
                                {"date": "2026-10-31", "cbot": 447.75, "local_excl": 15200.0}]},
              "C9": {"date": "2026-11-02", "vessel": "PHILIPPAKOS", "contract": "OPEN-9", "mt": 5000.0},
              "C8": {"date": "", "vessel": "ALPHA TEAM", "contract": "REF-C8", "mt": 5000.0}}
        t = dict(trail(), vessel="PHILIPPAKOS", received="2026-11-02")
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "ov.xlsx")
            res = ov.write_overview(m, fp, "CORN", [t], receipts=rc, only={"C1", "C3", "C9", "C8"})
            self.assertEqual((res["fixed_contracts"], res["unfixed_contracts"], res["open_contracts"], res["received_rows"]),
                             (1, 1, 1, 3))                                  # C2 is left out by ``only``
            wf, wv = openpyxl.load_workbook(fp), openpyxl.load_workbook(fp, data_only=True)
            fx, fv = wf["Fixed consumption"], wv["Fixed consumption"]
            self.assertIn("vessel ELENI M II", fx["A4"].value)
            self.assertIn("received 2026-10-20 → closed 2026-10-28", fx["A4"].value)
            # every day from the receiving date to the last pricing day; MT only on the consumption days
            days = [fv.cell(r, 1).value.date().isoformat() for r in range(8, 16)]
            self.assertEqual(days, [w["date"] for w in win])
            self.assertEqual([fv.cell(r, 2).value for r in range(8, 16)], [None, None, None, 500, 500, None, None, None])
            self.assertEqual(fv["C11"].value, 456.0)                       # a consumption day keeps the engine's CBOT
            self.assertEqual(fx["A8"].number_format, ov.RECV_FMT)          # the receiving date is marked
            self.assertIsNone(fv["F8"].value)                              # no tonnes that day: no saving
            self.assertAlmostEqual(fv["D8"].value, 467.75 - (245.66 / FACTOR - 175.0))
            self.assertEqual(fv["B16"].value, 1000.0)                      # total = the consumed tonnes
            self.assertEqual(fx["C17"].value, '=IF(COUNT(C8:C15)>0,AVERAGE(C8:C15),"")')
            cbs = [467.75, 459.0, 464.25, 456.0, 455.0, 456.0, 455.0, 448.75]
            self.assertAlmostEqual(fv["C17"].value, sum(cbs) / 8)
            # the receiving sheet: the whole contract on its receiving date
            rx, rv = wf["Receiving date"], wv["Receiving date"]
            rows = {rv.cell(r, 1).value: r for r in range(5, 20) if rv.cell(r, 1).value}
            r1 = rows["REF-C1"]
            self.assertEqual(rv.cell(r1, 2).value, "ELENI M II")
            self.assertEqual(rx.cell(r1, 10).value, "='Fixed consumption'!C8")
            diff = 467.75 - (245.66 / FACTOR - 175.0)
            self.assertAlmostEqual(rv.cell(r1, 11).value, diff)
            self.assertAlmostEqual(rv.cell(r1, 13).value, diff * FACTOR * 2000.0)
            self.assertAlmostEqual(rv.cell(r1, 14).value, diff * FACTOR * 2000.0 * 53.58)
            self.assertEqual(rv.cell(r1, 16).value, "Advantage")
            r3, r9 = rows["REF-C3"], rows["OPEN-9"]
            self.assertAlmostEqual(rv.cell(r3, 11).value, 455.0 - 446.25)   # not fixed: against the latest CBOT
            self.assertEqual(rv.cell(r3, 16).value, "Indicative")
            self.assertAlmostEqual(rv.cell(r9, 11).value, 449.75 - 446.0)   # open, not consumed: day 0 against now
            self.assertEqual(rv.cell(rows["REF-C8"], 4).value, "Not received")
            # the summary reads the receiving sheet, next to the consumption figures
            sx, sv_ = wf["Summary"], wv["Summary"]
            self.assertEqual(sx["O10"].value, f"='Receiving date'!M{r1}")
            self.assertAlmostEqual(sv_["O10"].value, diff * FACTOR * 2000.0)
            self.assertAlmostEqual(sv_["J10"].value, m["cbot"][0]["usd"] + m["cbot"][1]["usd"])
            # not fixed: the window days carry the CIF used on the consumption day
            uv = wv["Not fixed consumption"]
            self.assertEqual([uv.cell(r, 1).value.date().isoformat() for r in range(8, 11)],
                             ["2026-10-30", "2026-10-31", "2026-11-01"])
            self.assertEqual({uv.cell(r, 8).value for r in range(8, 11)}, {246.5})

    def test_merge_window(self):
        days = [{"date": ov._d("2026-10-23"), "mt": 500.0, "cbot": 456.0, "local_excl": 1.0, "cif_used": 9.0}]
        rv = {"date": "2026-10-22", "window": [{"date": "2026-10-22", "cbot": 464.25}, {"date": "2026-10-23", "cbot": 0.0},
                                               {"date": "2026-10-24", "cbot": 455.0}]}
        out = ov.merge_window(days, rv, carry=("cif_used",))
        self.assertEqual([(d["date"].isoformat(), d["mt"], d["cbot"], d["cif_used"]) for d in out],
                         [("2026-10-22", None, 464.25, 9.0), ("2026-10-23", 500.0, 456.0, 9.0), ("2026-10-24", None, 455.0, 9.0)])
        self.assertEqual(ov.merge_window(days, None), days)

    def test_form4_fx_and_fixed_cif_hold_the_price(self):
        import openpyxl
        t = dict(trail(), fixed_fx=55.0, fixed_cif=250.0)
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "ov.xlsx")
            ov.write_overview(model(), fp, "CORN", [t])
            ow = openpyxl.load_workbook(fp, data_only=True)["Open contracts"]
            self.assertEqual({round(ow.cell(r, 10).value, 4) for r in range(8, 13)}, {round(250.0 * 55.0 + 435.0, 4)})


if __name__ == "__main__":
    unittest.main()
