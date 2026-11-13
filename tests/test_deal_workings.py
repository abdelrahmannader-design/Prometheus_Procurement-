import re

from prometheus_core.decision import compute_decision
from prometheus_core.deal_workings import as_text, break_even_days, build_workings

CORN = {"type": "CBOT", "locked_factor": 0.3937}


def _inp(**kw):
    base = {"comm_meta": CORN, "fx": 50.0, "qty_mt": 2000, "local_egp_mt": 13500.0,
            "finance_days": 30, "interest_rate": 18, "cbot": 450.0, "premium_usd_mt": 90.0,
            "supplier_direct_egp_mt": 250.0, "supplier_indirect_egp_mt": 400.0,
            "canonical_landed_fees_egp_mt": None, "extra_landed_fees_egp_mt": 300.0}
    base.update(kw)
    return base


def _text(inp, out, **kw):
    return as_text(build_workings(inp, out, **kw))


def test_carry_lines_show_the_formula_with_the_engine_result():
    inp = _inp(); out = compute_decision(inp)
    cif = (450 + 90) * 0.3937
    assert abs(out["carry_usd_mt"] - cif * 0.18 * 30 / 360) < 1e-9
    t = _text(inp, out, fees=[("Direct intake", 250.0), ("Clearance", 200.0), ("Inland freight", 100.0)])
    assert f"(450.00 + 90.00) × 0.3937 = {cif:,.2f} USD/MT" in t
    assert f"{cif:,.2f} × 18.00% × 30 ÷ 360 = {out['carry_usd_mt']:,.2f} USD/MT" in t
    assert f"= {cif * 0.18 / 360:,.4f} USD/MT/day" in t
    assert f"Carry in EGP = {out['carry_usd_mt']:,.2f} × FX 50.0000 = {out['carry_usd_mt'] * 50:,.2f} EGP/MT" in t


def test_saving_line_matches_the_direct_saving():
    inp = _inp(); out = compute_decision(inp)
    t = _text(inp, out, fees=[("Direct intake", 250.0), ("Clearance", 200.0), ("Inland freight", 100.0)])
    assert f"{out['direct_saving_egp_mt']:+,.2f} EGP/MT" in t
    assert f"Landed cost = {out['own_after_egp_mt']:,.2f} + 550.00 = {out['direct_own_after_egp_mt']:,.2f}" in t
    assert "With indirect intake instead the saving is" in t


def test_contract_mode_uses_the_canonical_stack():
    inp = _inp(canonical_landed_fees_egp_mt=600.0, extra_landed_fees_egp_mt=0.0); out = compute_decision(inp)
    t = _text(inp, out, fees=[("Intake (DIRECT)", 250.0), ("Clearance", 250.0), ("Freight", 100.0)])
    assert f"= {out['saving_egp_mt']:+,.2f} EGP/MT" in t
    assert "indirect intake" not in t


def test_break_even_days_make_the_saving_zero():
    inp = _inp(); out = compute_decision(inp)
    be = break_even_days(out["import_usd_mt"], 50.0, 18, 550.0, 13500.0)
    at_be = compute_decision(_inp(finance_days=be))
    assert abs(at_be["direct_saving_egp_mt"]) < 1e-6
    t = _text(inp, out, fees=[("Direct intake", 250.0), ("Clearance", 200.0), ("Inland freight", 100.0)])
    assert f"= {be:,.0f} days" in t


def test_break_even_none_when_losing_at_zero_days():
    inp = _inp(local_egp_mt=9000.0); out = compute_decision(inp)
    lines = build_workings(inp, out, fees=[("Direct intake", 250.0)])
    assert "loses money even with 0 finance days" in as_text(lines)
    assert [k for k, t in lines if t.startswith("Saving =")] == ["x"]


def test_inventory_days_and_holding_carry():
    inp = _inp(); out = compute_decision(inp)
    t = _text(inp, out, fees=[], coverage={"cons_mt_day": 100.0, "start": "2026-11-01", "end": "2026-11-21",
                                           "avg_local": 13400.0, "local_carry_mt": 13400 * 0.18 * 10 / 360,
                                           "local_rate_pct": 18})
    assert "2,000 ÷ 100.00 = 20.00 days" in t
    assert "20.00 ÷ 2 = 10.00 days" in t
    cif = out["import_usd_mt"]
    assert f"{cif:,.2f} × 18.00% × 10.00 ÷ 360 = {cif * 0.18 * 10 / 360:,.2f} USD/MT" in t
    diff = (cif * 0.18 * 10 / 360 - out["carry_usd_mt"]) * 50
    assert f"by {diff:+,.2f} EGP/MT" in t
    assert f"= {13400 * 0.18 * 10 / 360:,.2f} EGP/MT" in t


def test_no_consumption_rate_is_explained():
    inp = _inp(finance_days=0); out = compute_decision(inp)
    t = _text(inp, out)
    assert "No finance carry" in t
    assert "No consumption rate is set" in t


def test_fraction_rate_is_flagged():
    inp = _inp(interest_rate=0.18); out = compute_decision(inp)
    assert "read as 0.18% (not 18.00%)" in _text(inp, out)


def test_flat_price_and_bushel_conversions():
    flat = _inp(comm_meta={"type": "NONCBOT"}, import_usd_mt=410.0)
    assert "CIF price entered = 410.00 USD/MT" in _text(flat, compute_decision(flat))
    bu = _inp(comm_meta={"type": "CBOT", "conversion_type": "bu_per_mt", "conversion_value": 36.7437,
                         "premium_mode": "CBOT_UNIT"}, cbot=1000.0, premium_usd_mt=50.0)
    out = compute_decision(bu)
    assert f"(1,000.00 + 50.00) ÷ 100 × 36.7437 = {out['import_usd_mt']:,.2f} USD/MT" in _text(bu, out)


def test_lines_never_start_with_an_equals_sign_and_headings_are_numbered():
    inp = _inp(); out = compute_decision(inp)
    lines = build_workings(inp, out, fees=[("Direct intake", 250.0)], coverage={"cons_mt_day": 120})
    assert all(not txt.startswith("=") for _, txt in lines)
    heads = [txt for k, txt in lines if k == "h"]
    assert [h[0] for h in heads] == ["1", "2", "3", "4", "5"]
    assert re.search(r"Each extra day financed costs [\d,.]+ EGP/MT", as_text(lines))


from prometheus_core.deal_workings import fifo_stock_days


def test_fifo_days_for_a_cargo_already_in_stock():
    # landed 12 days ago, 1,000 of 4,000 MT used, nothing ahead, 500 MT/day
    f = fifo_stock_days(qty=4000, rate=500, today="2026-11-13", start="2026-11-01", ahead_mt=0, own_remaining=3000)
    assert f["last_use"] == "2026-11-19" and f["first_use"] == "2026-11-11"
    assert f["wait_days"] == 10 and f["use_days"] == 8 and f["avg_days"] == 14


def test_fifo_days_for_a_future_cargo_wait_for_the_stock_still_ahead_on_arrival():
    # 6,000 MT in stock today, cargo lands in 4 days -> 4,000 MT still ahead -> waits 8 days
    f = fifo_stock_days(qty=2000, rate=500, today="2026-11-13", start="2026-11-17", ahead_mt=6000)
    assert f["wait_days"] == 8 and f["use_days"] == 4 and f["avg_days"] == 10
    assert f["first_use"] == "2026-11-25" and f["arrival_known"]
    late = fifo_stock_days(qty=2000, rate=500, today="2026-11-13", start="2026-12-30", ahead_mt=6000)
    assert late["wait_days"] == 0 and late["avg_days"] == 2


def test_fifo_days_never_start_before_the_cargo_landed():
    # landed today and 500 MT already used: the plain sum would put the first tonne a day before landing
    f = fifo_stock_days(qty=4000, rate=500, today="2026-11-13", start="2026-11-13", ahead_mt=0, own_remaining=3500)
    assert f["wait_days"] == 0 and f["last_days"] == 7 and f["first_use"] == "2026-11-13"


def test_workings_use_fifo_days_for_the_stock_carry():
    inp = _inp(); out = compute_decision(inp)
    fifo = fifo_stock_days(qty=2000, rate=100, today="2026-11-13", ahead_mt=1000)
    t = _text(inp, out, coverage={"cons_mt_day": 100.0, "fifo": fifo})
    assert "treated as arriving today" in t
    assert "Waits 10.00 days, then used over 20.00 days" in t
    assert "= 10.00 + 20.00 ÷ 2 = 20.00 days" in t
    cif = out["import_usd_mt"]
    assert f"Carry for 20.00 stock days = {cif:,.2f} × 18.00% × 20.00 ÷ 360" in t
    assert "rate × 0" not in t
