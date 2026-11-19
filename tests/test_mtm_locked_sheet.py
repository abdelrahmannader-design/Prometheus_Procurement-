import datetime as dt
import os
import pathlib
import sys
import tempfile

import openpyxl

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.mtm_locked_sheet import SHEET, shift_formula, write_mtm_sheet  # noqa: E402
from prometheus_core.xlsx_cache import store_formula_results  # noqa: E402


def test_shift_formula_moves_the_table_and_its_absolute_references():
    assert shift_formula("=SUM(O6:O12)", -3) == "=SUM(Q3:Q9)"
    assert shift_formula('=IF($S$13>0,SUMPRODUCT(K6:K12,$S$6:$S$12)/$S$13,"")', -3) == \
        '=IF($U$10>0,SUMPRODUCT(M3:M9,$U$3:$U$9)/$U$10,"")'
    assert shift_formula("=A6&B6", 10) == "=A16&D16"                    # column A stays, B moves to D
    assert shift_formula("='Receiving date'!D8", 5) == "='Receiving date'!D8"   # other sheets untouched
    assert shift_formula('="EGP "&TEXT(SUMPRODUCT(M6:M7,F6:F7),"+#,##0")', 8) == \
        '="EGP "&TEXT(SUMPRODUCT(O14:O15,H14:H15),"+#,##0")'


def _daily_row(cid, ref, sav_t, sav_p, qty):
    return {"contract_id": cid, "ref": ref, "commodity": "CORN", "tag": "weaker" if sav_t < sav_p else "improved",
            "cbot_today": 449.0, "cbot_prior": 444.25, "sav_today": sav_t, "sav_prior": sav_p, "from_cbot": -100.0,
            "from_fx": 0.0, "from_local": sav_t - sav_p + 100.0, "other": 0.0, "total_today": sav_t * qty,
            "total_prior": sav_p * qty, "qty_today": qty, "qty_prior": qty, "in_today": True, "in_prior": True,
            "why_complete": True}


def _open_row(cid, ref, local, fx, qty, tag="go"):
    return {"contract_id": cid, "ref": ref, "supplier": "ADM", "commodity": "CORN-BRZ", "origin": "BRAZIL",
            "status": "Open", "qty": qty, "cif": 246.64, "cif_display": "246.64", "cif_formula": "Saved contract CIF",
            "fx": fx, "freight": 485.1, "disc": 320.87, "clr": 200.0, "local": local, "local_transport": 396.88,
            "decision": "Strong import edge", "tag": tag, "marks": ""}


def test_sheet_has_the_three_tables_with_the_receiving_period():
    wb = openpyxl.Workbook()
    rd = wb.active
    rd.title = "Receiving date"
    rd["D5"], rd["Q5"] = dt.datetime(2026, 10, 26), dt.datetime(2026, 10, 30)
    rd["D6"], rd["Q6"] = "Not received", "—"
    cache = {}
    daily = {"today": "2026-11-19", "prior": "2026-11-18", "commodity": "CORN",
             "rows": [_daily_row("C1", "460/20050010", -366.67, -166.67, 2000.0),
                      _daily_row("C2", "460/20050610 3000", -163.97, 143.66, 3000.0)]}
    locked = {"today": "2026-11-19", "commodity": "CORN", "fx_mode": "locked", "view": "excl",
              "groups": [("CORN", [_open_row("C1", "460/20050010", 15496.88, 55.78, 2000.0),
                                   _open_row("C2", "460/20050610 3000", 14396.88, 53.516, 3000.0, "wait")])]}
    live = dict(locked, fx_mode="live",
                groups=[("CORN", [_open_row("C1", "460/20050010", 14396.88, 55.78, 1500.0, "wait"),
                                  _open_row("C2", "460/20050610 3000", 14396.88, 53.768, 3000.0, "wait")])])
    out = write_mtm_sheet(wb, cache, daily=daily, locked=locked, live=live, recv_rows={"C1": 5, "C2": 6},
                          recv_values={("C1", "date"): dt.date(2026, 10, 26), ("C1", "end"): dt.date(2026, 10, 30),
                                       ("C2", "date"): "Not received", ("C2", "end"): "—"})
    assert wb.sheetnames[0] == SHEET
    ws, c = wb[SHEET], out["cache"]
    assert [s["title"] for s in out["sections"]] == ["Changes From Prior :-", "Savings In The Date Of Receiving Commodity",
                                                       "LIVE V LIVE"]
    # daily: heading row 2, rows 3-4, total row 5 with its weighted parts moved with the columns
    assert [ws.cell(2, k).value for k in (1, 2, 3, 4, 5)] == ["Ref", "Receiving date", "Receiving end", "Commodity",
                                                             "CBOT Today"]
    assert ws["B3"].value == "='Receiving date'!D5" and ws["C3"].value == "='Receiving date'!Q5"
    assert ws["B4"].value == "='Receiving date'!D6" and c["B4"] == "Not received"
    assert ws["A5"].value.startswith("TOTAL OPEN BOOK") and ws["O5"].value == "=SUM(O3:O4)"
    assert ws["K5"].value == '=IF($U$5>0,SUMPRODUCT(K3:K4,$U$3:$U$4)/$U$5,"")'
    assert c["O5"] == -366.67 * 2000 + -163.97 * 3000
    # locked: title, heading, group band, two contracts, no TOTAL row
    top = out["sections"][1]["top"]
    assert ws.cell(top - 1, 1).value == "Savings In The Date Of Receiving Commodity"
    assert ws.cell(top, 2).value == "Receiving date" and ws.cell(top, 4).value == "Supplier"
    g = top + 1
    assert ws.cell(g, 1).value == "▸  CORN  (2 contracts)" and ws.cell(g, 8).value == f"=SUM(H{g + 1}:H{g + 2})"
    assert ws.cell(g + 1, 2).value == "='Receiving date'!D5"
    m = ws.cell(g + 1, 13).value                                          # Own After excl. = CIF × FX + R + S
    assert m == f'=IF(AND(ISNUMBER(I{g + 1}),ISNUMBER(K{g + 1}),K{g + 1}<>0),I{g + 1}*K{g + 1}+R{g + 1}+S{g + 1},"")'
    assert abs(c[f"M{g + 1}"] - (246.64 * 55.78 + 320.87 + 200.0)) < 1e-6
    assert abs(c[f"O{g + 1}"] - (15496.88 - 396.88 - (246.64 * 55.78 + 320.87 + 200.0))) < 1e-6
    assert ws.cell(g + 3, 1).value is None                                # the TOTAL row is left out
    live_top = out["sections"][2]["top"]
    assert ws.cell(live_top - 1, 1).value == "LIVE V LIVE" and ws.cell(live_top + 2, 11).value == 55.78
    # the cached results hold once saved
    with tempfile.TemporaryDirectory() as tmp:
        fp = os.path.join(tmp, "m.xlsx")
        wb.save(fp)
        store_formula_results(fp, cache)
        v = openpyxl.load_workbook(fp, data_only=True)[SHEET]
        assert v["B3"].value.date() == dt.date(2026, 10, 26) and v["C3"].value.date() == dt.date(2026, 10, 30)
        assert v["O5"].value == c["O5"]


def test_empty_tables_say_so():
    wb = openpyxl.Workbook()
    out = write_mtm_sheet(wb, {}, daily={"rows": [], "today": "2026-11-19"}, locked={"groups": []},
                          live={"groups": []})
    ws = wb[SHEET]
    assert [s["rows"] for s in out["sections"]] == [0, 0, 0]
    assert ws["A2"].value.startswith("No rows: refresh Home first")
