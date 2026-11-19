import datetime as dt
import os
import pathlib
import sys
import tempfile

import openpyxl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.receiving_end_import import apply_updates, plan_updates, read_end_dates  # noqa: E402


def _book(path):
    wb = openpyxl.Workbook()
    rd = wb.active
    rd.title = "Receiving date"
    for c, h in enumerate(["Contract", "Vessel", "Shipment", "Receiving date"], 1):
        rd.cell(4, c, h)
    rd.cell(4, 17, "Receiving end")
    rows = [("SC-34179-CH.1", dt.datetime(2026, 11, 17), dt.datetime(2026, 11, 19)),
            ("460/20050610 2000", dt.datetime(2026, 11, 15), "Still receiving"),
            ("460/20050340 2000", dt.datetime(2026, 11, 10), dt.datetime(2026, 11, 16)),
            ("460/20050000", dt.datetime(2026, 10, 26), None),
            ("TRADE#SC-33039.1", dt.datetime(2026, 10, 1), None),
            ("460/20050010", dt.datetime(2026, 10, 26), dt.datetime(2026, 10, 30))]
    for i, (n, s, e) in enumerate(rows, 5):
        rd.cell(i, 1, n); rd.cell(i, 4, s); rd.cell(i, 17, e)
    fx = wb.create_sheet("Fixed consumption")
    fx["A4"] = ("460/20050000  ·  ADM  ·  CORN-BRZ  ·  2,000 MT  ·  DEC-26  ·  Recorded CBOT fixing  ·  "
                "received 2026-10-26 (end2026-10-28)  ·  consumed (FIFO) 2026-10-31 to 2026-11-03 → last lot priced")
    fx["A32"] = "TRADE#SC-33039.1  ·  COFCO  ·  received 2026-10-01 (end 2026-10-03) → last lot priced 2026-10-16"
    fx["A60"] = "TRADE#SC-33039.2  ·  COFCO  ·  received 2026-09-29 (end 2026-10-02) → last lot priced 2026-10-19"
    fx["A90"] = "SC-34179-CH.1  ·  COFCO  ·  received 2026-11-17 to 2026-11-25 → still open"   # the tab wins
    wb.save(path)


def test_read_and_match_the_typed_end_dates():
    with tempfile.TemporaryDirectory() as tmp:
        fp = os.path.join(tmp, "b.xlsx")
        _book(fp)
        found = read_end_dates(fp)
    got = {f["contract"]: f["end"] for f in found}
    assert got == {"SC-34179-CH.1": "2026-11-19", "460/20050340 2000": "2026-11-16", "460/20050000": "2026-10-28",
                   "TRADE#SC-33039.1": "2026-10-03", "TRADE#SC-33039.2": "2026-10-02", "460/20050010": "2026-10-30"}
    contracts = {
        "C0175": {"name": "SC-34179-CH.1", "storage_start": ""},
        "C0177": {"name": "460/20050340", "storage_start": "2026-11-10"},
        "C0179": {"name": "460/20050340 1000MT", "storage_start": "2026-11-10"},
        "C0165": {"name": "460/20050000", "storage_start": "2026-10-26", "receiving_end": "2026-10-28"},
        "C0152": {"name": "TRADE#SC-33039", "storage_start": "2026-10-01"},
        "C0181": {"name": "460/20050010-COPY", "storage_start": "2026-10-26"},
        "C0153": {"name": "TRADE#SC-33039", "storage_start": "2026-09-29", "receiving_end": "2026-09-30"}}
    plan = {p["contract"]: p for p in plan_updates(contracts, found)}
    assert (plan["SC-34179-CH.1"]["cid"], plan["SC-34179-CH.1"]["action"]) == ("C0175", "set")
    assert (plan["460/20050340 2000"]["cid"], plan["460/20050340 2000"]["action"]) == ("C0177", "set")
    assert plan["460/20050000"]["action"] == "same"
    assert (plan["TRADE#SC-33039.1"]["cid"], plan["TRADE#SC-33039.1"]["action"]) == ("C0152", "set")
    assert (plan["TRADE#SC-33039.2"]["cid"], plan["TRADE#SC-33039.2"]["action"]) == ("C0153", "replace")
    assert (plan["460/20050010"]["cid"], plan["460/20050010"]["action"]) == ("C0181", "set")   # '-COPY' in the app
    assert apply_updates(contracts, list(plan.values()), stamp="t") == 5
    assert contracts["C0177"]["receiving_end"] == "2026-11-16" and contracts["C0153"]["receiving_end"] == "2026-10-02"
    assert "receiving_end" not in contracts["C0179"]


def test_nothing_is_matched_on_a_guess():
    contracts = {"A": {"name": "X-1", "storage_start": "2026-10-01"}, "B": {"name": "X-1", "storage_start": "2026-10-01"},
                 "C": {"name": "Y", "storage_start": "2026-10-05"}}
    plan = plan_updates(contracts, [
        {"contract": "X-1", "start": "2026-10-01", "end": "2026-10-03"},      # two contracts, same date
        {"contract": "Y.1", "start": "2026-10-06", "end": "2026-10-08"},      # suffix but another date
        {"contract": "Y", "start": "2026-10-05", "end": "2026-10-01"},        # end before the receiving date
        {"contract": "YY", "start": "2026-10-05", "end": "2026-10-07"}])      # 'Y' + 'Y' is not a suffix
    assert [p["action"] for p in plan] == ["skip"] * 4
    assert "2 contracts match" in plan[0]["note"] and "no contract" in plan[1]["note"]
    assert "before the app's receiving date" in plan[2]["note"]
    assert apply_updates(contracts, plan) == 0
