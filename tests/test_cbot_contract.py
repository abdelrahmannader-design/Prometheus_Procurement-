import datetime as dt
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.cbot_contract import (contract_windows, front_contract, is_final, last_trading_day,  # noqa: E402
                                           merge_history, needs_refresh)


def test_front_month_is_cmes_until_its_last_trading_day():
    assert last_trading_day(2026, 12) == dt.date(2026, 12, 14)          # Mon 14 Dec (15th is a Tuesday)
    assert last_trading_day(2026, 3) == dt.date(2026, 3, 13)            # 15 Mar 2026 is a Sunday → Fri 13th
    c = front_contract("CORN", dt.date(2026, 11, 20))                   # ZC=F was already March that day
    assert (c["symbol"], c["label"], c["futures"]) == ("ZCZ26.CBT", "Dec-26", "DEC-26")
    assert front_contract("CORN", dt.date(2026, 12, 14))["symbol"] == "ZCZ26.CBT"
    assert front_contract("CORN", dt.date(2026, 12, 15))["symbol"] == "ZCH27.CBT"
    assert front_contract("CORN", dt.date(2026, 9, 14))["symbol"] == "ZCU26.CBT"
    assert front_contract("SBM", dt.date(2026, 9, 20))["symbol"] == "ZMV26.CBT"
    assert front_contract("SOYBEAN", dt.date(2026, 11, 20))["symbol"] == "ZSF27.CBT"


def test_history_windows_follow_the_front_month():
    w = [(c["symbol"], a.isoformat(), b.isoformat()) for c, a, b in
         contract_windows("CORN", dt.date(2026, 9, 1), dt.date(2026, 12, 31))]
    assert w == [("ZCU26.CBT", "2026-09-01", "2026-09-14"), ("ZCZ26.CBT", "2026-09-15", "2026-12-14"),
                 ("ZCH27.CBT", "2026-12-15", "2026-12-31")]


def test_merge_replaces_automatic_closes_only():
    rows = [{"date": "2026-11-19", "commodity": "CORN", "price": 448.25, "source": "Yahoo-Finance"},
            {"date": "2026-11-20", "commodity": "CORN", "price": 448.75, "source": "Yahoo-Finance"},
            {"date": "2026-11-18", "commodity": "CORN", "price": 441.0, "source": "excel import"}]
    new = [{"date": d, "commodity": "CORN", "price": p, "source": "Yahoo ZCZ26.CBT (Dec-26)", "contract": "Dec-26",
            "final": True} for d, p in (("2026-11-18", 443.0), ("2026-11-19", 439.0), ("2026-11-20", 434.5),
                                        ("2026-11-23", 436.0))]
    rows, ch = merge_history(rows, new)
    by = {r["date"]: r for r in rows}
    assert by["2026-11-20"]["price"] == 434.5 and by["2026-11-20"]["contract"] == "Dec-26"
    assert by["2026-11-18"]["price"] == 441.0                           # typed / imported by hand: kept
    assert ("CORN", "2026-11-19", 448.25, 439.0) in ch and ("CORN", "2026-11-23", None, 436.0) in ch
    assert not any(c[1] == "2026-11-18" for c in ch)


def test_a_close_fetched_on_its_own_day_is_fetched_again():
    assert not is_final("2026-11-19", "2026-11-19 16:40:00") and is_final("2026-11-19", "2026-11-20 09:00:00")
    rows = [{"date": "2026-11-19", "commodity": "CORN", "price": 448.25, "source": "Yahoo-Finance"},
            {"date": "2026-11-20", "commodity": "CORN", "price": 434.5, "contract": "Dec-26", "final": True},
            {"date": "2026-11-21", "commodity": "CORN", "price": 436.0, "contract": "Dec-26", "final": False},
            {"date": "2026-10-01", "commodity": "CORN", "price": 500.0, "source": "Yahoo-Finance"}]
    assert needs_refresh(rows, "CORN", dt.date(2026, 11, 22)) == ["2026-11-19", "2026-11-21"]
