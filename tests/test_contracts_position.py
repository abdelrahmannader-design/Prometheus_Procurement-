import datetime as dt

import openpyxl
import pytest

from prometheus_core.contracts_position import (SHEET, SUMMARY, write_summary_sheet, allocate, cbot_holidays, eta_from_text, first_notice_day,
                                                has_contract_number, label, month_code, position_rows,
                                                simulate_cover, trading_days, write_position_sheet)


def test_priced_tonnes_go_to_the_oldest_first_as_the_desk_report():
    # 2,000 MT, all used, 1,500 priced -> 1,500 sold long, 500 sold short (the YC report's first ADM row)
    a = allocate(2000, 2000, 2000, 0, 1500)
    assert a["sold_long"] == 1500 and a["sold_short"] == 500 and a["short_delivered"] == 500
    # 3,000 delivered unpriced, 998 at port, nothing used -> port short 998, warehouse short 2,002
    b = allocate(3000, 3000, 0, 998, 0)
    assert b["port_short"] == 998 and b["wh_short"] == 2002 and b["short_delivered"] == 3000
    # priced beyond what has arrived lands on the tonnes still on the way
    c = allocate(5000, 1000, 400, 100, 2000)
    assert (c["sold_long"], c["wh_long"], c["port_long"], c["long_way"], c["open_way"]) == (400, 500, 100, 1000, 3000)


def test_buckets_always_add_up_and_inputs_are_clamped():
    for args in [(2000, 2500, 3000, 900, 9000), (4000, 4000, 1686, 0, 0), (1000, 0, 50, 10, 300), (0, 0, 0, 0, 0)]:
        a = allocate(*args)
        whole = a["open_way"] + a["long_way"] + a["short_delivered"] + a["sold_long"] + a["wh_long"] + a["port_long"]
        assert whole == pytest.approx(max(args[0], 0))
        assert min(a.values()) >= 0


def test_labels_codes_and_contract_numbers():
    assert month_code("DEC-26") == "Z" and month_code("MAR") == "H"
    r = {"supplier": "ADM", "total": 2000, "origin": "ARG", "premium": 180.0, "futures": "DEC-26"}
    assert label(r) == "ADM ( 2 K mt ) ARG @ 180 Over Z"
    assert has_contract_number("460/20050000") and has_contract_number("SC33911-CH")
    assert not has_contract_number("4000MT COFCO - BRZ")


def _open(cid, name, sup="COFCO", qty=4000.0, prem=190.0, recv="2026-11-01", used=0.0, delivered=None):
    return {"contract_id": cid, "contract": name, "supplier": sup, "base": "CORN", "commodity": "CORN-BRZ",
            "qty_mt": qty, "delivered_mt": qty if delivered is None else delivered, "consumed_mt": used,
            "premium": prem, "futures": "DEC-26", "storage_start": recv}


def test_look_alikes_only_when_one_has_no_contract_number():
    rows = position_rows([_open("C1", "4000MT COFCO - BRZ"), _open("C2", "SC33911-CH"),
                          _open("C3", "460/20050000", "ADM", 2000, 180, "2026-10-26"),
                          _open("C4", "460/20050010", "ADM", 2000, 180, "2026-10-26")])
    by = {r["contract_id"]: r["remarks"] for r in rows}
    assert by["C1"] and by["C2"] and "SC33911-CH (C2)" in by["C1"][0]
    assert by["C3"] == [] and by["C4"] == []


def test_rows_sort_received_first_and_read_lots_and_final_cif():
    rows = position_rows([_open("C9", "SC-34179-CH.1", recv="", delivered=0.0), _open("C3", "460/20050000", "ADM", 2000, 180,
                                                                                       "2026-10-26", used=2000)],
                         lots={"C3": [{"mt": 508.02, "cbot": None}]}, final_cif={"C3": 246.64})
    assert [r["contract_id"] for r in rows] == ["C3", "C9"]
    assert rows[0]["priced"] == pytest.approx(508.02)
    assert rows[0]["fixed_cbot"] == pytest.approx(246.64 / 0.3937 - 180)
    rows = position_rows([_open("C5", "X-12345", used=0)], lots={"C5": [{"mt": 1000, "cbot": 440}, {"mt": 1000, "cbot": 450}]})
    assert rows[0]["fixed_cbot"] == pytest.approx(445)


def test_calendar_first_notice_and_trading_days():
    hol = cbot_holidays(2026)
    assert dt.date(2026, 11, 26) in hol and dt.date(2026, 12, 25) in hol and dt.date(2026, 4, 3) in hol  # Good Friday
    assert first_notice_day("DEC-26") == dt.date(2026, 11, 30)
    assert first_notice_day("MAR-27") == dt.date(2027, 2, 26)
    assert trading_days(dt.date(2026, 11, 17), dt.date(2026, 11, 30), hol) == 9      # Thanksgiving closed


def test_eta_from_shipment_text():
    as_of = dt.date(2026, 11, 17)
    assert eta_from_text("December delivery", as_of)[0] == dt.date(2026, 12, 15)
    assert eta_from_text("End December", as_of)[0] == dt.date(2026, 12, 25)
    assert eta_from_text("Early December Delivery", as_of)[0] == dt.date(2026, 12, 7)
    assert eta_from_text("January", as_of)[0] == dt.date(2027, 1, 15)
    late, note = eta_from_text("November delivery", as_of)
    assert late is None and "has passed" in note
    assert eta_from_text("", as_of)[0] is None


def test_cover_simulation():
    rows, covered = simulate_cover(4000, 500, [(dt.date(2026, 11, 20), 2000), (None, 5000)], dt.date(2026, 11, 18), 30)
    assert rows[2]["arrivals"] == 2000 and rows[0]["closing"] == 3500
    assert covered == dt.date(2026, 11, 29)            # 6,000 MT / 500 a day from 18 Nov
    rows, covered = simulate_cover(100, 500, [], dt.date(2026, 11, 18), 5)
    assert covered == dt.date(2026, 11, 17) and rows[0]["use"] == 100
    _, covered = simulate_cover(10**6, 500, [], dt.date(2026, 11, 18), 5)
    assert covered is None


def test_v2_sheet(tmp_path):
    rows = position_rows([_open("C3", "460/20050000", "ADM", 2000, 180, "2026-10-26", used=2000),
                          _open("C7", "460/20050340", "ADM", 3000, 190, "2026-11-10"),
                          _open("C9", "SC-34179-CH.1", recv="", delivered=0.0, qty=5000, prem=197)],
                         receipts={"C9": {"shipment": "December delivery"}},
                         lots={"C3": [{"mt": 1500, "cbot": 447.18}]})
    for r in rows:
        r.update(discharge=235.0, clearance=200.0, freight=344.0, local=14300.0, local_date="2026-11-10")
    rows[0]["fx_contract"] = 55.2974                      # Form 4 recorded on 460/20050000
    rows[1]["port"] = 998
    wb = openpyxl.Workbook()
    out = write_position_sheet(wb, rows, as_of=dt.date(2026, 11, 17), fx=53.5, cbot=441, rate=500)
    ws, c, lay = wb[SHEET], out["cache"], out["layout"]
    assert wb.sheetnames[0] == SHEET and ws["A2"].value == "Date : 17 November 2026"
    y = lay["yc"]
    assert c[f"L{y}"] == 1500 and c[f"M{y}"] == 500 and c[f"I{y + 1}"] == 998 and c[f"K{y + 1}"] == 2002
    assert out["unpriced_mt"] == 8500 and out["used_unpriced_mt"] == 500 and out["stock_mt"] == 3000
    # to-do: the contract with used-unpriced tonnes first, then stock, then on the way
    t0, tl = out["todo_rows"]
    assert [ws.cell(r, 2).value for r in range(t0, tl + 1)] == ["460/20050000", "460/20050340", "SC-34179-CH.1"]
    assert c[f"C{t0}"] == "500 MT already used" and c[f"D{t0}"] == 500
    cif = (441 + 180) * 0.3937
    assert c[f"J{t0}"] == pytest.approx(cif) and c[f"K{t0}"] == pytest.approx(cif * 55.2974 + 435)  # Form 4 FX
    assert c[f"M{t0}"] == pytest.approx(14300 - (cif * 55.2974 + 435))                          # no freight
    assert c[f"I{t0}"] == pytest.approx(180 + 235 / 55.2974 / 0.3937)
    cif2 = (441 + 190) * 0.3937
    assert c[f"K{t0 + 1}"] == pytest.approx(cif2 * 53.5 + 435)                                  # FX now
    assert c[f"O{t0}"] == pytest.approx(500 * 0.3937 * 55.2974)
    assert c["H6"] == pytest.approx(c[f"O{out['todo_total']}"])
    assert c[f"P{t0}"] == 9 and out["min_days_to_fnd"] == 9
    assert ws[f"P{t0}"].value.startswith("=IF(ISNUMBER(V") and "NETWORKDAYS" in ws[f"P{t0}"].value
    # cover: 3,000 MT in stock, 5,000 MT on 15 Dec, 500 a day from 18 Nov -> covered to 23 Nov
    assert out["cover_until"] == dt.date(2026, 11, 23)
    assert ws["A6"].value == "=(E%d+F%d)" % (out["total_row"], out["total_row"])
    assert c["A6"] == 8500
    assert len(ws._charts) == 1
    # the one-screen summary reads the detail sheet
    sc = write_summary_sheet(wb, out, as_of=dt.date(2026, 11, 17))
    sm = wb[SUMMARY]
    assert wb.sheetnames[0] == SUMMARY
    assert sm["A5"].value == f"='{SHEET}'!A6" and sc["A5"] == 8500
    assert sc["A6"] == "of which 500 MT already used" and sc["B5"] == 9
    assert sm["A10"].value == "460/20050000  ·  ADM · 2,000 MT @ 180" and sc["C10"] == 500
    assert sm["H10"].value == f"='{SHEET}'!P{t0}" and sc["H10"] == 9
    assert sc["D10"] == 55.2974 and sc["D11"] == "pending" and sc["F10"] == 14300
    assert sc["E10"] == pytest.approx(cif * 55.2974 + 435) and sc["G10"] == pytest.approx(14300 - sc["E10"])
    assert sm["E9"].value == "Own after excl. freight" and sm["F9"].value == "Local now excl. transport (10/11)"
    assert sc["C13"] == 8500                                          # total to price


from prometheus_core.contracts_position import INV_SHEET, consumed_status, pricing_status, write_inventory_sheet


def test_consumed_and_pricing_status():
    assert consumed_status(3000, 0, 0) == "Not arrived"
    assert consumed_status(2000, 2000, 0) == "Not consumed yet"
    assert consumed_status(4000, 4000, 1686) == "Partly consumed"
    assert consumed_status(2000, 2000, 2000) == "Fully consumed"
    assert pricing_status(2000, 0) == "Unpriced" and pricing_status(2000, 2032.09) == "Fully priced"
    assert pricing_status(2000, 508.02) == "Partly priced · 25%"


def test_inventory_sheet_lots_and_totals():
    base = {"supplier": "ADM", "origin": "ARG", "futures": "DEC-26", "vessel": "", "shipment": ""}
    rows = [dict(base, contract="460/20050000", total=2000, received=2000, used=1200, premium=180, fx_contract=55.2974,
                 fixed_cbot=446.5, receiving_date="2026-10-26",
                 lots=[{"date": dt.date(2026, 11, 10), "mt": 508.02, "cbot": 441.25},
                       {"date": dt.date(2026, 11, 11), "mt": 1000, "cbot": None}]),
            dict(base, contract="460/20050610 3000", total=3000, received=0, used=0, premium=198, fx_contract=None,
                 fixed_cbot=None, receiving_date="", shipment="December delivery", lots=[])]
    wb = openpyxl.Workbook()
    out = write_inventory_sheet(wb, rows, as_of=dt.date(2026, 11, 17), fx_now=53.68)
    ws, c = wb[INV_SHEET], out["cache"]
    assert ws["L7"].value == "=SUM(L8:L9)" and c["L7"] == pytest.approx(1508.02)
    assert c["E7"] == "Partly consumed" and c["M7"] == "Partly priced · 75%"
    # 1,508 priced: 1,200 consumed long, 308 in inventory long, 492 in inventory short
    assert c["J7"] == 1200 and c["K7"] == 0 and c["H7"] == pytest.approx(308.02) and c["I7"] == pytest.approx(491.98)
    assert c["M8"] == "priced 10 Nov 2026" and ws["W8"].value == "lot"
    assert c["Q8"] == pytest.approx((441.25 + 180) * 0.3937)            # lot CIF from its own CBOT
    assert c["P9"] == 446.5 and c["Q9"] == pytest.approx((446.5 + 180) * 0.3937)   # no CBOT: implied
    assert c["Q7"] == pytest.approx((508.02 * c["Q8"] + 1000 * c["Q9"]) / 1508.02)
    assert ws["D10"].value == "pending" and c["E10"] == "Not arrived" and c["G10"] == 3000
    tr = out["total_row"]
    assert ws[f"C{tr}"].value.startswith('=SUMIF($W$7:$W$10,"contract"') and c[f"C{tr}"] == 5000
    assert c[f"L{tr}"] == pytest.approx(1508.02)                    # lot lines are not counted twice


def test_recently_closed_group_has_its_own_subtotal():
    base = {"supplier": "COFCO", "origin": "BRZ", "futures": "DEC-26", "vessel": "", "shipment": "", "premium": 175,
            "fx_contract": 53.58, "fixed_cbot": 449.0, "receiving_date": "2026-10-20", "total": 2000,
            "received": 2000, "used": 2000}
    rows = [dict(base, contract="OPEN-1", lots=[], fixed_cbot=None),
            dict(base, contract="SC-33609-CH.2", closed="2026-11-05",
                 lots=[{"date": "2026-10-28", "mt": 1016.04, "cbot": 451.75}, {"date": "2026-10-30", "mt": 1016.05,
                                                                              "cbot": 447.75}]),
            dict(base, contract="OLD", closed="2026-10-01", lots=[])]
    wb = openpyxl.Workbook()
    out = write_inventory_sheet(wb, rows, as_of=dt.date(2026, 11, 17))
    ws, c = wb[INV_SHEET], out["cache"]
    tr = out["total_row"]
    assert ws[f"A{tr}"].value == "Total Feed (open contracts)" and c[f"C{tr}"] == 2000 and c[f"L{tr}"] == 0
    names = [ws.cell(r, 2).value for r in range(tr, ws.max_row + 1)]
    assert any(n and n.startswith("SC-33609-CH.2") and "closed 5 Nov" in n for n in names)
    assert not any(n and n.startswith("OLD") for n in names)               # closed too long ago
    cr = next(r for r in range(tr, ws.max_row + 1) if (ws.cell(r, 2).value or "").startswith("SC-33609-CH.2"))
    assert c[f"L{cr}"] == pytest.approx(2032.09) and c[f"M{cr}"] == "Fully priced" and c[f"J{cr}"] == 2000
    sub = cr + 3
    assert ws[f"A{sub}"].value == "Total recently closed" and '"closed"' in ws[f"C{sub}"].value
    assert out["closed_totals"]["priced"] == pytest.approx(2032.09)


from prometheus_core.contracts_position import closed_rows


def test_closed_rows_keep_only_recent_closures_with_a_date():
    contracts = [
        {"id": "C1", "contract": "SC-33609-CH.2", "base": "CORN", "status": "Closed", "commodity": "CORN-BRZ",
         "supplier": "COFCO", "qty_mt": 2000, "delivered_mt": 2000, "consumed_mt": 2000, "premium": 175,
         "contract_month": {"code": "DEC-26"}, "fx": 53.58, "fx_basis": "Form 4", "storage_start": "2026-10-20"},
        {"id": "C2", "contract": "OLD", "base": "CORN", "status": "Closed", "qty_mt": 2000},
        {"id": "C3", "contract": "NO-DATE", "base": "CORN", "status": "Closed", "qty_mt": 2000},
        {"id": "C4", "contract": "OPEN", "base": "CORN", "status": "Open", "qty_mt": 2000}]
    rows = closed_rows(contracts, "CORN", {"C1": "2026-11-05", "C2": "2026-10-01", "C3": ""},
                       {"C1": [{"date": "2026-10-28", "mt": 1016.04, "cbot": 451.75},
                               {"date": "2026-10-30", "mt": 1016.05, "cbot": 447.75}]}, dt.date(2026, 11, 18), 15)
    assert [r["contract"] for r in rows] == ["SC-33609-CH.2"]
    r = rows[0]
    assert r["closed"] == "2026-11-05" and r["fx_contract"] == 53.58 and r["origin"] == "BRZ"
    assert r["futures"] == "DEC-26" and r["fixed_cbot"] == pytest.approx((451.75 * 1016.04 + 447.75 * 1016.05) / 2032.09)
