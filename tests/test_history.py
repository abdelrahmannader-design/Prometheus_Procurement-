from __future__ import annotations

import unittest

from prometheus_core.history import approval_status, changed_terms, diff, fingerprint, hash_pin, snapshot


class HistoryTests(unittest.TestCase):
    def test_field_level_diff(self):
        before = snapshot({"contracts": {"C1": {"name": "A", "qty_mt": 1000, "ts": "x"}},
                           "local_purchases": [{"id": 1, "qty_mt": 50}],
                           "budgets": [{"commodity": "CORN", "year": 2026, "price_mt": 230}]})
        after = snapshot({"contracts": {"C1": {"name": "A", "qty_mt": 1200.0, "ts": "y"},
                                        "C2": {"name": "B"}},
                          "local_purchases": [],
                          "budgets": [{"commodity": "CORN", "year": 2026, "price_mt": 230.0}],
                          "local_prices": [{"date": "2026-09-27", "commodity": "corn", "price_egp_mt": 1}]})
        ch = {(c["entity"], c["key"], c["action"], c["field"]): c for c in diff(before, after)}
        self.assertIn(("contract", "C1", "EDITED", "qty_mt"), ch)
        self.assertEqual(ch[("contract", "C1", "EDITED", "qty_mt")]["new"], "1200.0")
        self.assertIn(("contract", "C2", "ADDED", ""), ch)
        self.assertIn(("local_purchase", "1", "DELETED", ""), ch)
        self.assertIn(("local_price", "2026-09-27|CORN", "ADDED", ""), ch)
        self.assertFalse(any(k[3] == "ts" for k in ch))            # ignored field
        self.assertFalse(any(k[0] == "budget" for k in ch))        # 230 == 230.0 is not a change

    def test_approval_fingerprint_and_status(self):
        rec = {"supplier": "A", "commodity": "CORN", "qty_mt": 1000, "premium_cents": 95, "note": "x"}
        a = {"entity": "contract", "status": "APPROVED", "fingerprint": fingerprint("contract", rec)}
        self.assertEqual(approval_status(a, dict(rec, note="changed note")), "APPROVED")   # not a key term
        self.assertEqual(approval_status(a, dict(rec, qty_mt=1000.0)), "APPROVED")
        self.assertEqual(approval_status(a, dict(rec, premium_cents=90)), "CHANGED")
        self.assertEqual(approval_status(a, None), "MISSING")
        self.assertEqual(approval_status(dict(a, status="REJECTED"), None), "REJECTED")
        self.assertEqual(changed_terms("contract", rec, dict(rec, qty_mt=900)), ["qty_mt"])

    def test_pin_hash(self):
        self.assertEqual(hash_pin("1234", "s"), hash_pin("1234", "s"))
        self.assertNotEqual(hash_pin("1234", "s"), hash_pin("1234", "t"))


if __name__ == "__main__":
    unittest.main()
