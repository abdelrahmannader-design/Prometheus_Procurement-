import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.stock_report import apply, plan, read_report  # noqa: E402

EMAIL = """Dear Mr. Mohamed,
Following is the situation of our main raw materials is as follows:
Raw Material\t23/11/2026
\tNobaria\tSaaf\tTotal
\tCurrent Stock (Ton)\tActual Daily Consumption (Ton)\tDays of Supply/Daily consumption\tAverage Daily forecast Consumption (Ton)\tDays of Supply/Daily max forecast
Yellow Corn (BRZ)\t7294\t396\t18\t455\t16\t1763\t93\t19\t109\t16\t9057\t490\t18
Soybean Meal 46%\t1243\t208\t6\t183\t7\t352\t50\t7\t57\t6\t1595\t258\t6
DDGS\t1344\t11\t118\t13\t101\t141\t6\t24\t8\t17\t1485\t17\t86
Sunflower Meal\t789\t100\t8\t42\t19\t98\t4\t26\t6\t16\t886\t104\t8
Soybean (FFS)\t907\t9\t102\t12\t78\t68\t2\t38\t2\t30\t975\t11\t91
Gluten Meal\t24\t1\t31\t2\t11\t2\t0.00\t#DIV/0!\t0.00\t#DIV/0!\t26\t1\t33
"""


def test_reads_the_email_table_tab_separated_or_one_cell_per_line():
    r = read_report(EMAIL)
    assert r["date"] == "2026-11-23" and not r["notes"]
    assert [x["key"] for x in r["rows"]] == ["CORN-BRZ", "SBM", "DDGS", "SFM", "SOYBEAN", "GLUTEN"]
    corn = r["rows"][0]
    assert corn["sites"]["Nobaria"] == {"stock": 7294, "actual": 396, "days": 18, "forecast": 455, "days_forecast": 16}
    assert corn["sites"]["Saaf"]["stock"] == 1763 and corn["total"]["stock"] == 9057 and corn["total"]["actual"] == 490
    assert r["rows"][5]["sites"]["Saaf"]["days"] is None                  # #DIV/0!
    one_per_line = EMAIL.replace("\t", "\n")
    assert [x["total"]["stock"] for x in read_report(one_per_line)["rows"]] == [9057, 1595, 1485, 886, 975, 26]


def test_plan_and_apply_counts_and_rates():
    state = {"consumption": {"CORN-BRZ": 500.0, "SBM": 290.0, "DDGS": 15.0, "SFM": 86.0, "SOYBEAN": 10.0},
             "consumption_log": [{"date": "2026-09-09", "commodity": "CORN", "is_adjustment": True, "adjusted_qty": 0},
                                 {"date": "2026-09-09", "commodity": "CORN-ARG", "is_adjustment": True, "adjusted_qty": 0},
                                 {"date": "2026-11-23", "commodity": "SBM", "is_adjustment": True, "adjusted_qty": 1},
                                 {"date": "2026-11-01", "commodity": "SBM", "consumed_mt": 300}],
             "contracts": {}}
    p = plan(read_report(EMAIL), state)
    lines = {l["key"]: l for l in p["lines"]}
    assert lines["CORN-BRZ"]["counts"] == [("CORN-BRZ", 9057.0), ("CORN", 0.0), ("CORN-ARG", 0.0)]
    assert lines["CORN-BRZ"]["rate"] == 500.0 and round(lines["CORN-BRZ"]["days"], 1) == 18.5
    assert lines["SBM"]["alert"][0] == "High" and lines["SFM"]["alert"][0] == "Medium"
    assert not lines["GLUTEN"]["tracked"] and lines["GLUTEN"]["counts"] == []
    res = apply(state, p, set_counts=True, set_rates=True, stamp="2026-11-23 16:00:00")
    assert res == {"counts": 7, "rates": 5}
    sbm = [e for e in state["consumption_log"] if e.get("commodity") == "SBM" and e.get("is_adjustment")]
    assert len(sbm) == 1 and sbm[0]["adjusted_qty"] == 1595.0              # replaced, not added twice
    assert "Nobaria 1,243 + Saaf 352 MT" in sbm[0]["note"]
    assert state["consumption"]["CORN-BRZ"] == 490.0 and state["consumption"]["SBM"] == 258.0
    assert state["stock_reports"][-1]["date"] == "2026-11-23" and len(state["stock_reports"][-1]["lines"]) == 6
