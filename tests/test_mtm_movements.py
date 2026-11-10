"""Every daily Open-MTM movement since storage: the Home comparison for every day, and the workbook."""
import os
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from prometheus_core import mtm_history, mtm_movements as mv  # noqa: E402


def rec(day, cid, ref, cbot, local, qty=1000.0, fx=50.0, prem=100.0, conv=0.4, fees=500.0, mode="LIVE", base="CORN"):
    cif = (cbot + prem) * conv
    own = cif * fx + fees
    sav = local - own
    return {"date": day, "contract_id": cid, "contract_ref": ref, "commodity": base, "base_commodity": base,
            "supplier": "S", "qty_mt": qty, "cbot_price": cbot, "cbot_unit": "c/bu", "premium_quote": prem,
            "cbot_conversion": conv, "cif_usd_mt": cif, "fx": fx, "fx_source": "market", "discharge_egp_mt": fees,
            "clearance_egp_mt": 0.0, "freight_egp_mt": 0.0, "own_after_egp_mt": own, "local_egp_mt": local,
            "local_price_date": day, "saving_egp_mt": sav, "total_saving_egp": sav * qty, "mode": mode, "stale_quotes": []}


def ledger():
    return [
        rec("2026-11-02", "C1", "A-1", 440.0, 12000.0),
        rec("2026-11-02", "C2", "B-2", 450.0, 12100.0, qty=500.0),
        rec("2026-11-03", "C1", "A-1", 445.0, 11900.0, fx=50.5, mode="RECONSTRUCTED"),
        rec("2026-11-03", "C2", "B-2", 445.0, 12100.0, qty=500.0),
        rec("2026-11-04", "C1", "A-1", 441.0, 11900.0, fx=50.5),          # C2 exited, C3 new
        rec("2026-11-04", "C3", "C-3", 441.0, 12500.0, qty=2000.0),
    ]


class DayBlockTests(unittest.TestCase):
    def test_home_semantics_for_every_day(self):
        blocks = mv.day_blocks(ledger())
        self.assertEqual([b["date"] for b in blocks], ["2026-11-02", "2026-11-03", "2026-11-04"])
        self.assertEqual(blocks[0]["prior_date"], "")
        self.assertIsNone(blocks[0]["book"]["d_total"])
        for b in blocks[1:]:
            rows = b["rows"]
            # the rows' changes add up to the change in the open book (new and exited included)
            self.assertAlmostEqual(sum(r["d_total"] for r in rows), b["book"]["d_total"], places=4)
            for r in rows:
                if r["from_cbot"] is not None:
                    self.assertAlmostEqual(sum(r[k] for k in mv.PARTS), r["d_sav"], places=6)
        last = {r["ref"]: r for r in blocks[2]["rows"]}
        self.assertEqual(last["B-2"]["flag"], "exited")
        self.assertAlmostEqual(last["B-2"]["d_total"], -ledger()[3]["total_saving_egp"])
        self.assertEqual(last["C-3"]["flag"], "new")
        self.assertAlmostEqual(last["C-3"]["d_sav"], last["C-3"]["sav"])
        self.assertEqual(last["A-1"]["flag"], "")
        self.assertAlmostEqual(last["A-1"]["d_cbot"], -4.0)
        # CBOT −4 c/bu × 0.4 × FX 50.5 → +80.8 EGP/MT
        self.assertAlmostEqual(last["A-1"]["from_cbot"], 80.8, places=6)

    def test_book_and_headline(self):
        b = mv.day_blocks(ledger())[1]["book"]
        q, t = 1500.0, ledger()[2]["total_saving_egp"] + ledger()[3]["total_saving_egp"]
        self.assertAlmostEqual(b["total"], t)
        self.assertAlmostEqual(b["sav"], t / q)
        self.assertEqual(b["mode"], "Mixed")
        self.assertIn("2026-11-02 → 2026-11-03 · Open MTM edge EGP", b["text"])
        self.assertIn("CORN 440.00→445.00", b["text"])
        self.assertIn("Why (EGP/MT, tonne-weighted): CBOT", b["text"])
        nxt = mv.day_blocks(ledger())[2]["book"]
        self.assertIn("2026-11-03 was rebuilt from stored closes", nxt["text"])

    def test_scope_limits_contracts(self):
        blocks = mv.day_blocks(ledger(), ids={"C1"})
        self.assertTrue(all(len(b["rows"]) == 1 for b in blocks))

    def test_missing_price_is_noted(self):
        h = ledger()
        h[2] = dict(h[2], saving_egp_mt=None, total_saving_egp=None, local_egp_mt=None)
        row = next(r for r in mv.day_blocks(h)[1]["rows"] if r["ref"] == "A-1")
        self.assertIn("no saving on 2026-11-03", row["note"])


class ExtendTests(unittest.TestCase):
    def lookups(self):
        closes = {"2026-10-29": 430.0, "2026-10-30": 435.0, "2026-11-02": 440.0}
        cbot_on = lambda base, day: (closes.get(day), day if day in closes else None)
        fx_on = lambda day: (50.0, day)
        local_on = lambda c, day: (11800.0, "2026-10-28")
        return cbot_on, fx_on, local_on, sorted(closes)

    def test_days_from_storage_start_to_first_record(self):
        contracts = {"C1": {"storage_start": "2026-10-29", "created_ts": "2026-11-02 09:00"},
                     "C2": {"storage_start": "2026-11-05"}}           # stored after its first record: nothing
        cbot_on, fx_on, local_on, trading = self.lookups()
        ext = mv.extend_to_storage(ledger(), contracts, trading, cbot_on, fx_on, local_on)
        self.assertEqual([(r["contract_id"], r["date"]) for r in ext], [("C1", "2026-10-29"), ("C1", "2026-10-30")])
        r = ext[0]
        self.assertEqual(r["mode"], "RECONSTRUCTED")
        self.assertEqual(r["capture_reason"], "before_first_record")
        self.assertAlmostEqual(r["cif_usd_mt"], (430.0 + 100.0) * 0.4)        # floating CIF follows that day's close
        self.assertAlmostEqual(r["saving_egp_mt"], 11800.0 - ((430.0 + 100.0) * 0.4 * 50.0 + 500.0), places=3)
        self.assertIn("storage start 2026-10-29", r["reconstructed_from"])
        self.assertEqual(mv.extend_to_storage(ledger(), contracts, trading, cbot_on, fx_on, local_on, ids={"C2"}), [])

    def test_rebuild_row_matches_reconstruct_day(self):
        cbot_on, fx_on, local_on, _t = self.lookups()
        h = ledger()
        contracts = {"C1": {"created_ts": "2026-10-01"}, "C2": {"created_ts": "2026-10-01"}}
        day = mtm_history.reconstruct_day("2026-10-30", h[2:], contracts, cbot_on, fx_on, local_on)
        one = mtm_history.rebuild_row("2026-10-30", h[2], contracts["C1"], cbot_on, fx_on, local_on)
        self.assertEqual([r["contract_id"] for r in day], ["C1", "C2"])
        self.assertEqual(day[0], one)


class ExclTransportTests(unittest.TestCase):
    def ledger(self):
        h = ledger()
        for r in h:
            r["freight_egp_mt"] = 300.0                      # route freight inside our price
            r["own_after_egp_mt"] += 300.0
            r["saving_egp_mt"] -= 300.0
            r["total_saving_egp"] = r["saving_egp_mt"] * r["qty_mt"]
        return h

    def test_both_sides_lose_their_own_transport(self):
        h = self.ledger()
        ex = mv.excl_transport(h, {}, lambda c, r: 400.0)
        r0, x0 = h[0], ex[0]
        self.assertAlmostEqual(x0["local_egp_mt"], r0["local_egp_mt"] - 400.0)
        self.assertAlmostEqual(x0["own_after_egp_mt"], r0["own_after_egp_mt"] - 300.0)
        self.assertAlmostEqual(x0["saving_egp_mt"], r0["saving_egp_mt"] - 100.0, places=3)
        self.assertAlmostEqual(x0["total_saving_egp"], x0["saving_egp_mt"] * r0["qty_mt"], places=1)
        self.assertEqual((x0["local_transport_egp_mt"], x0["freight_egp_mt"]), (400.0, 300.0))
        self.assertAlmostEqual(x0["saving_incl_egp_mt"], r0["saving_egp_mt"])
        self.assertNotIn("basis", h[0])                          # the ledger itself is not changed

    def test_unknown_local_transport_leaves_no_saving(self):
        ex = mv.excl_transport(self.ledger(), {}, lambda c, r: None)
        self.assertIsNone(ex[0]["saving_egp_mt"])
        self.assertIn("no transport found on the local quote", ex[0]["stale_quotes"])

    def test_workbook_labels(self):
        import openpyxl
        ex = mv.excl_transport(self.ledger(), {}, lambda c, r: 400.0)
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "x.xlsx")
            res = mv.write_movements_excel(ex, {"C1": {"status": "Open"}, "C3": {"status": "Open"}}, fp, basis="excl")
            self.assertEqual(res["basis"], "excl")
            wb = openpyxl.load_workbook(fp, data_only=True)
            dm = wb["Daily Movement"]
            heads = [c.value for c in dm[4]]
            for h in ("Sav/MT Today (excl tr.)", "Local Today (excl tr.)", "Our price Today (excl tr.)", "Our freight",
                      "Local transport"):
                self.assertIn(h, heads)
            th = [c.value for c in wb["Contract Trail"][4]]
            for h in ("Our price incl tr.", "Our price excl tr.", "Local incl tr.", "Local transport", "Local excl tr."):
                self.assertIn(h, th)
            self.assertIn("EXCL TRANSPORT", dm["A2"].value)
            row = next(r for r in dm.iter_rows(min_row=5, values_only=True) if r[2] == "Contract")
            self.assertEqual((row[heads.index("Our freight")], row[heads.index("Local transport")]), (300.0, 400.0))
            bb = wb["Book by Day"]
            self.assertIn("Open MTM edge excl transport", bb.cell(6, bb.max_column).value)


class ChainTests(unittest.TestCase):
    def test_chain_matches_records_both_bases(self):
        h = mv.excl_transport(ExclTransportTests().ledger(), {}, lambda c, r: 400.0)
        for basis, recs in (("excl", h), ("incl", [mv.incl_view(r) for r in h])):
            rows = sorted(recs, key=lambda r: (r["contract_id"], r["date"]))
            ys = mv.chain([mv.row_inputs(r) for r in rows], basis == "excl")
            for r, y in zip(rows, ys):
                self.assertAlmostEqual(y["sav"], r["saving_egp_mt"], places=3)
                self.assertAlmostEqual(y["total"], r["total_saving_egp"], places=0)


class WorkbookTests(unittest.TestCase):
    def test_workbook(self):
        import openpyxl
        contracts = {"C1": {"status": "Open", "storage_start": "2026-10-30"}, "C2": {"status": "Closed"},
                     "C3": {"status": "Open"}}
        closes = {"2026-10-30": 435.0}
        ext = mv.extend_to_storage(ledger(), contracts, sorted(closes), lambda b, d: (closes.get(d), d),
                                   lambda d: (50.0, d), lambda c, d: (11900.0, d))
        with tempfile.TemporaryDirectory() as tmp:
            fp = os.path.join(tmp, "moves.xlsx")
            res = mv.write_movements_excel(ledger() + ext, contracts, fp, as_of="2026-11-04", extension=ext,
                                           ledger_start="2026-11-02")
            self.assertEqual(res["days"], 4)
            self.assertEqual(res["open_sheets"], 2)
            self.assertEqual(res["rebuilt_before_entry"], 1)
            wb = openpyxl.load_workbook(fp)
            self.assertEqual(wb.sheetnames[:4], ["Summary", "Book by Day", "Daily Movement", "Contract Trail"])
            self.assertIn("A-1", wb.sheetnames)
            self.assertNotIn("B-2", wb.sheetnames)                       # closed: in the tables, no own sheet
            ws = wb["A-1"]
            self.assertEqual(ws["D5"].value.date().isoformat(), "2026-10-30")
            heads = [c.value for c in ws[4]]
            col = lambda h: heads.index(h) + 1
            # every derived column is a formula; only the inputs are values
            for h in ("CIF $/MT", "Our price incl tr.", "Our price excl tr.", "Local excl tr.", "Sav/MT (incl tr.)",
                      "Total EGP (incl tr.)", "Δ Sav/MT", "from CBOT", "from FX", "from Local", "Other", "Δ Total"):
                self.assertTrue(str(ws.cell(6, col(h)).value).startswith("="), h)
            self.assertEqual(ws.cell(6, col("CIF $/MT")).value, '=IF(ISNUMBER(L6),L6,IF(AND(ISNUMBER(H6),ISNUMBER(J6),'
                                                                 'ISNUMBER(K6)),(H6+J6)*K6,""))')
            vals = openpyxl.load_workbook(fp, data_only=True)
            v = vals["A-1"]
            for r in range(6, 9):                                         # parts add up to Δ Sav/MT (stored results)
                parts = sum(v.cell(r, col(h)).value for h in ("from CBOT", "from FX", "from Local", "Other"))
                self.assertAlmostEqual(parts, v.cell(r, col("Δ Sav/MT")).value, places=4)
            # the formula chain reproduces the app's own saving per tonne
            want = {r["date"]: r["saving_egp_mt"] for r in ledger() if r["contract_id"] == "C1"}
            for r in range(6, 9):
                self.assertAlmostEqual(v.cell(r, col("Sav/MT (incl tr.)")).value,
                                       want[v.cell(r, col("Date")).value.date().isoformat()], places=3)
            wf = openpyxl.load_workbook(fp)
            self.assertTrue(str(wf["Book by Day"]["I5"].value).startswith("=SUMIFS("))
            self.assertTrue(str(wf["Summary"]["T11"].value).startswith("=SUMIFS("))
            bb = vals["Book by Day"]
            self.assertEqual(bb["A5"].value.date().isoformat(), "2026-10-30")
            self.assertEqual(bb.cell(5, 5).value, 1)
            dm = vals["Daily Movement"]
            self.assertEqual(dm["A5"].value.date().isoformat(), "2026-11-04")   # newest first
            # the TOTAL row of each day equals the book of that day
            for blk in mv.day_blocks(ledger() + ext):
                tot = next(r for r in dm.iter_rows(min_row=5, values_only=True)
                           if r[2] == "TOTAL" and r[0].date().isoformat() == blk["date"])
                self.assertAlmostEqual(tot[21], blk["book"]["total"], places=2)
            kinds = [dm.cell(r, 3).value for r in range(5, dm.max_row + 1) if dm.cell(r, 3).value]
            self.assertEqual(kinds.count("TOTAL"), 4)

    def test_sheet_names_are_valid_and_unique(self):
        used = set()
        a = mv.sheet_name("460/2005:[x]*?", used)
        b = mv.sheet_name("460/2005:[x]*?", used)
        self.assertNotRegex(a, r"[\[\]\*\?/\\:]")
        self.assertNotEqual(a.lower(), b.lower())
        self.assertLessEqual(len(b), 31)


if __name__ == "__main__":
    unittest.main()
