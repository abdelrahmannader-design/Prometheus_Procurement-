import openpyxl
import pytest

from prometheus_core.open_mtm_excel import HEADINGS, LEAD, figures, write_open_mtm


def _row(ref, qty, cif, fx, frt, disc, clr, local, tr, tag="go", marks=""):
    return {"ref": ref, "supplier": "ADM", "commodity": "CORN-BRZ", "origin": "BRAZIL", "status": "Open", "qty": qty,
            "cif": cif, "cif_display": f"{cif:.2f}" if cif else "?", "cif_formula": "(449+198)×0.3937 | DEC",
            "fx": fx, "freight": frt, "disc": disc, "clr": clr, "local": local, "local_transport": tr,
            "decision": "Strong import edge", "tag": tag, "marks": marks}


def test_figures_follow_the_app():
    f = figures(_row("A", 3000, 254.72, 53.516, 344, 320.87, 200, 14400, 400))
    assert f["own"] == pytest.approx(254.72 * 53.516 + 320.87 + 200 + 344)
    assert f["own_x"] == pytest.approx(f["own"] - 344) and f["local_x"] == 14000
    assert f["sav_x"] == pytest.approx(14000 - f["own_x"]) and f["tot_x"] == pytest.approx(f["sav_x"] * 3000)


@pytest.mark.parametrize("view", ["incl", "excl", "both"])
def test_layout_groups_and_total(tmp_path, view):
    corn = [_row("460/20050610 3000", 3000, 254.72, 53.516, 344, 320.87, 200, 14400, 400, "wait"),
            _row("460/20050010", 2000, 246.64, 55.78, 485, 320.87, 200, 15500, 400, "go", " *"),
            _row("NO-CIF", 1000, None, 53.5, 344, 235, 200, 14400, 400, "missing")]
    sbm = [_row("SCN-8800", 500, 454.26, 53.576, 377, 0, 0, 25871, 371)]
    p = tmp_path / "o.xlsx"
    out = write_open_mtm(p, [("CORN", corn), ("SBM", sbm)], view=view, today="2026-11-19")
    ws = openpyxl.load_workbook(p).active
    heads = [ws.cell(4, c).value for c in range(1, 15)]
    assert heads == LEAD + list(HEADINGS[view]) + ["Decision"]
    c = out["cache"]
    xv = view == "excl"
    figs = [figures(x) for x in corn]
    k_own, k_sav = ("own_x", "sav_x") if xv else ("own", "sav")
    assert c["K6"] == pytest.approx(figs[0][k_own]) and c["M6"] == pytest.approx(figs[0][k_sav])
    assert c["K8"] == ""                                              # no CIF, no Own After
    assert ws["L7"].number_format.endswith('" *"')                    # the stale-local mark stays numeric
    g_qty = 6000
    assert c["F5"] == g_qty and c["K5"] == pytest.approx(sum((f[k_own] or 0) * f["qty"] for f in figs) / g_qty)
    edge = sum((f[k_sav] or 0) * f["qty"] for f in figs)
    assert c["N5"] == f"EGP {edge:+,.0f} total" and c["M5"] == pytest.approx(edge / g_qty)
    t = out["total_row"]
    allf = figs + [figures(sbm[0])]
    tot_edge = sum((f[k_sav] or 0) * f["qty"] for f in allf)
    assert ws.cell(t, 1).value == "TOTAL  (4 open)" and c[f"F{t}"] == 6500
    assert c[f"N{t}"] == pytest.approx(tot_edge) and c[f"M{t}"] == pytest.approx(tot_edge / 6500)
    if view == "both":
        assert ws.cell(4, 15).value == "Own After excl." and c[f"R{t}"] == pytest.approx(sum(f["tot_x"] or 0 for f in allf))
