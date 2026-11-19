import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from prometheus_core.contract_pick import describe, open_totals, pick_contracts  # noqa: E402

C = {
    "C0175": {"name": "SC-34179-CH.1", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 5000, "storage_start": "2026-11-17"},
    "C0176": {"name": "460/20050610 2000", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 2000, "storage_start": "2026-11-15"},
    "C0180": {"name": "460/20050610 3000", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 3000, "storage_start": ""},
    "C0177": {"name": "460/20050340 2000", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 2000, "storage_start": "2026-11-10"},
    "C0179": {"name": "460/20050340 1000MT", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 1000, "storage_start": "2026-11-11"},
    "C0181": {"name": "460/20050010-COPY", "commodity": "CORN-BRZ", "status": "Open", "qty_mt": 2000, "storage_start": "2026-10-26"},
    "C0165": {"name": "460/20050000", "commodity": "CORN-BRZ", "status": "Closed", "qty_mt": 2000, "storage_start": "2026-10-26"},
    "C9": {"name": "SBM-1", "commodity": "SBM", "status": "Open", "qty_mt": 900, "storage_start": "2026-11-01"},
}


def test_pasted_names_match_and_total():
    p = pick_contracts(C, "CORN", "SC-34179-CH.1,\n460/20050610 2000, 460/20050340 1000MT,460/20050340 2000 ,"
                                  "460/20050010, 460/20050000, NOT-THERE")
    assert p["ids"] == {"C0175", "C0176", "C0179", "C0177", "C0181", "C0165"}
    assert p["unmatched"] == ["NOT-THERE"]
    assert ("460/20050010", "C0181", "460/20050010-COPY", "suffix") in p["matched"]
    t = open_totals(C, "CORN", p["ids"])
    assert (t["open_n"], t["open_mt"], t["received_mt"], t["closed_mt"]) == (5, 12000, 12000, 2000)
    assert t["left_out"] == [("460/20050610 3000", 3000.0)]
    text = describe(p, t)
    assert "open 5 contract(s) 12,000 MT" in text and "not found: NOT-THERE" in text
    assert "open but not in your list: 460/20050610 3000 (3,000 MT)" in text
    p2 = pick_contracts(C, "CORN", ", ".join(c["name"] for c in C.values() if c["commodity"].startswith("CORN")))
    assert open_totals(C, "CORN", p2["ids"])["open_mt"] == 15000 and not p2["unmatched"]


def test_a_number_shared_by_two_contracts_is_not_guessed():
    p = pick_contracts(C, "CORN", "460/20050340, 460/20050610")
    assert p["ids"] == set() and [a[0] for a in p["ambiguous"]] == ["460/20050340", "460/20050610"]
    assert pick_contracts(C, "CORN", "  ")["ids"] is None
    assert open_totals(C, "CORN")["open_mt"] == 15000                   # every CORN contract
