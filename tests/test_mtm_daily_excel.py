import openpyxl
import pytest

from prometheus_core.mtm_daily_excel import HEADERS, write_daily_mtm


def _row(ref, tag, ct, cp, st, sp, tt, tp, qt, qp, parts=(None, None, None, None), why=False, it=True, ip=True):
    return {"ref": ref, "commodity": "CORN", "tag": tag, "cbot_today": ct, "cbot_prior": cp, "sav_today": st,
            "sav_prior": sp, "from_cbot": parts[0], "from_fx": parts[1], "from_local": parts[2], "other": parts[3],
            "total_today": tt, "total_prior": tp, "qty_today": qt, "qty_prior": qp, "why_complete": why,
            "in_today": it, "in_prior": ip}


def test_same_columns_deltas_and_total_row(tmp_path):
    rows = [_row("460/20050340 1000MT", "weaker", 448.75, 444.25, 35, 331, 35113, 331000, 1000, 1000,
                 (-96, 0, -200, 0), True),
            _row("460/20050340 2000", "weaker", 448.75, 444.25, -241, 56, -482615, 112000, 2000, 2000,
                 (-97, 0, -200, 0), True),
            _row("NEW-1  [new]", "new", 448.75, None, 100, None, 300000, None, 3000, None, ip=False),
            _row("OLD-1  [exited open book]", "new", None, 444.25, None, 50, None, 100000, None, 2000, it=False)]
    p = tmp_path / "d.xlsx"
    out = write_daily_mtm(p, rows, today="2026-11-19", prior="2026-11-18", summary="summary line")
    ws = openpyxl.load_workbook(p).active
    assert [ws.cell(5, c).value for c in range(1, 16)] == HEADERS
    c = out["cache"]
    assert c["E6"] == pytest.approx(4.5) and c["H6"] == -296 and c["O6"] == 35113 - 331000
    assert c["H8"] == 100 and c["O8"] == 300000                 # new: counts in full
    assert c["H9"] == -50 and c["O9"] == -100000 and c["E9"] == ""   # exited: loses its prior value
    t = out["total_row"]
    assert ws.cell(t, 1).value == "TOTAL OPEN BOOK  (3 today / 3 prior)"
    assert c[f"M{t}"] == 35113 - 482615 + 300000 and c[f"N{t}"] == 331000 + 112000 + 100000
    assert c[f"F{t}"] == pytest.approx((35113 - 482615 + 300000) / 6000)
    assert c[f"G{t}"] == pytest.approx((331000 + 112000 + 100000) / 5000)
    assert c[f"I{t}"] == pytest.approx((-96 * 1000 - 97 * 2000) / 3000)      # tonne-weighted, why rows only
    assert ws[f"I{t}"].value.startswith("=IF($S$") and ws["A3"].value == "summary line"


def test_without_a_prior_day_the_one_sided_rows_have_no_delta(tmp_path):
    rows = [_row("A", "new", 448.75, None, 100, None, 300000, None, 3000, None, ip=False)]
    out = write_daily_mtm(tmp_path / "d.xlsx", rows, today="2026-11-19", prior="")
    assert out["cache"]["H6"] == "" and out["cache"]["O6"] == ""
