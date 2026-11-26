import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.pricing_radar import (first_notice_day, month_choices, normalise_month, radar,  # noqa: E402
                                           resolve_month, trading_days_left)

TODAY = dt.date(2026, 11, 23)


def _c(name, qty, month="DEC", lots=(), status="Open", comm="CORN-BRZ", deliv="2026-11-17"):
    return {"name": name, "commodity": comm, "status": status, "qty_mt": qty, "futures_month": month,
            "delivery_date": deliv, "pricing_lots": [{"qty_mt": q} for q in lots]}


def test_calendar():
    assert first_notice_day(2026, 12) == dt.date(2026, 11, 30)
    assert first_notice_day(2027, 3) == dt.date(2027, 2, 26)
    assert trading_days_left(TODAY, dt.date(2026, 11, 30)) == 4           # 23, 24, 25, 27 (26 Nov is Thanksgiving)
    assert resolve_month("DEC", "CORN", "2026-11-17") == (2026, 12)
    assert resolve_month("Dec 2027", "CORN", None) == (2027, 12) and resolve_month("Z26", "CORN", None) == (2026, 12)
    assert resolve_month("DEC", "CORN", "2026-12-20") == (2027, 12)       # Dec-26 stopped trading on 14 Dec
    assert resolve_month("APR", "CORN", TODAY) is None                     # not a corn month
    assert normalise_month("dec", "CORN", "2026-11-17") == "DEC-26" and normalise_month("", "CORN") == ""
    assert month_choices("CORN", TODAY, 4) == ["DEC-26", "MAR-27", "MAY-27", "JUL-27"]


def test_radar_rows_months_and_alerts():
    contracts = {"A": _c("SC-34179-CH.1", 5000), "B": _c("SC33911-CH", 4000, lots=(508.02, 1016.05)),
                 "C": _c("OLD", 2000, status="Closed"), "D": _c("NO-MONTH", 1000, month=""),
                 "E": _c("MAR-ONE", 2000, month="MAR-27"), "F": _c("DONE", 1000, lots=(1000,)),
                 "G": _c("SBM-1", 900, comm="SBM", month="")}
    quotes = {"ZCZ26.CBT": 434.5, "ZCH27.CBT": 448.75}
    out = radar(contracts, TODAY, quotes)
    rows = {r["contract"]: r for r in out["rows"]}
    assert set(rows) == {"SC-34179-CH.1", "SC33911-CH", "NO-MONTH", "MAR-ONE", "SBM-1"}
    a = rows["SC-34179-CH.1"]
    assert (a["futures"], a["fnd"], a["days_left"], a["level"]) == ("DEC-26", dt.date(2026, 11, 30), 4, "amber")
    assert a["lots"] == 10 and a["per_day"] == 3 and a["next_futures"] == "MAR-27" and a["spread"] == 14.25
    assert round(rows["SC33911-CH"]["unpriced"], 2) == 2475.93
    assert rows["MAR-ONE"]["level"] == "ok" and rows["NO-MONTH"]["level"] == "no month"
    dec = next(g for g in out["months"] if g["futures"] == "DEC-26")
    assert round(dec["unpriced"], 2) == 7475.93 and dec["contracts"] == 2 and dec["lots"] == 15 and dec["per_day"] == 4
    lvl, title, action = out["alerts"][0]
    assert lvl == "High" and title.startswith("7,476 MT CORN unpriced on DEC-26 (2 contracts) — 4 trading days")
    assert not any("MAR-27" in t for _l, t, _a in out["alerts"])        # MAR-27 is weeks away
    assert "≈ 4 lot(s) of 508 MT a day" in action and "MAR-27 is +14.25 vs DEC-26" in action
    assert any("NO-MONTH" in t for _l, t, _a in out["alerts"])


def test_levels_close_to_and_after_the_deadline():
    c = {"A": _c("X", 2000)}
    assert radar(c, dt.date(2026, 11, 27))["rows"][0]["level"] == "red"     # 1 trading day left
    late = radar(c, dt.date(2026, 11, 30))
    assert late["rows"][0]["level"] == "passed" and late["alerts"][0][0] == "High"
    assert "has passed" in late["alerts"][0][1]
    watch = radar(c, dt.date(2026, 11, 13))
    assert watch["rows"][0]["level"] == "watch" and watch["alerts"][0][0] == "Medium"   # 10 trading days left
    assert radar(c, dt.date(2026, 11, 9))["rows"][0]["level"] == "ok"       # 14 trading days left


def test_quote_for_contract_uses_own_month():
    from prometheus_core.pricing_radar import quote_for_contract
    rows = [{"symbol": "ZCZ26.CBT", "price": 433.0, "as_of": "t1"},
            {"symbol": "ZCH27.CBT", "price": 449.25, "as_of": "t2", "source": "curve"}]
    front = {"symbol": "ZCZ26.CBT", "price": 433.0, "as_of": "t0", "source": "YAHOO"}
    today = "2026-11-25"
    q = quote_for_contract({"commodity": "CORN-BRZ", "futures_month": "March", "delivery_date": "2026-11-17"},
                           rows, front, today)
    assert q["price"] == 449.25 and q["futures"] == "MAR-27" and q["matched"]
    q = quote_for_contract({"commodity": "CORN-BRZ", "futures_month": "DEC", "delivery_date": "2026-11-01"},
                           rows, front, today)
    assert q["price"] == 433.0 and q["futures"] == "DEC-26" and q["matched"] and q["as_of"] == "t0"
    q = quote_for_contract({"commodity": "CORN", "futures_month": "MAY-27"}, rows, front, today)
    assert q["price"] == 433.0 and not q["matched"] and "MAY-27" in q["note"]
    q = quote_for_contract({"commodity": "CORN"}, rows, front, today)
    assert q["price"] == 433.0 and not q["matched"]


def test_open_premium_and_blended_cif():
    from prometheus_core.pricing_radar import blended_cif, open_premium
    assert open_premium({"premium_cents": 190}) == 190
    assert open_premium({"premium_cents": 190, "open_premium_cents": 173.75}) == 173.75
    lots = [{"qty_mt": 1000, "cbot": 440.0, "premium_cents": 190.0},
            {"qty_mt": 1000, "cbot": 436.0, "premium_cents": 190.0}]
    r = blended_cif(lots, 4000, 449.25, 173.75, 0.3937)
    want = (1000 * 630 + 1000 * 626 + 2000 * (449.25 + 173.75)) / 4000 * 0.3937
    assert abs(r["cif"] - want) < 1e-9 and r["priced_mt"] == 2000 and r["unpriced_mt"] == 2000
    assert abs(r["priced_cbot"] - 438.0) < 1e-9 and "2,000 MT open (449.25+173.75)" in r["formula"]
    full = blended_cif(lots, 2000, None, None, 0.3937)          # fully priced: no live quote needed
    assert abs(full["cif"] - 628 * 0.3937) < 1e-9 and full["unpriced_mt"] == 0
    capped = blended_cif(lots, 1500, None, None, 0.3937)        # lots above the contract qty are scaled
    assert abs(capped["cif"] - 628 * 0.3937) < 1e-9 and capped["priced_mt"] == 1500
    nocbot = blended_cif([{"qty_mt": 500, "premium_cents": 190.0}], 1000, 433.0, 173.75, 0.3937)
    assert abs(nocbot["cif"] - (500 * 623 + 500 * 606.75) / 1000 * 0.3937) < 1e-9
    assert blended_cif([], 1000, 433, 190, 0.3937) is None
    assert blended_cif(lots, 4000, None, 173.75, 0.3937) is None
