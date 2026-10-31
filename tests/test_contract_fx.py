"""A contract's cost FX: Form 4 once entered, except for SBM."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.contract_fx import cost_fx, uses_form4


class CostFxTests(unittest.TestCase):
    def test_form4_wins_over_delivery_once_entered(self):
        c = {"commodity": "CORN-BRZ", "form4_fx": 49.5, "delivery_fx": 50.33}
        self.assertEqual(cost_fx(c, 56.0), (49.5, "Form 4"))

    def test_every_commodity_but_sbm_uses_form4(self):
        for commodity in ("CORN", "CORN-ARG", "SOYBEAN", "SFM", "DDGS", "WHEAT"):
            self.assertTrue(uses_form4({"commodity": commodity, "form4_fx": 49.5}),
                            commodity)

    def test_sbm_keeps_its_delivery_fx(self):
        c = {"commodity": "SBM", "form4_fx": 49.5, "delivery_fx": 50.33}
        self.assertFalse(uses_form4(c))
        self.assertEqual(cost_fx(c, 56.0), (50.33, "delivery"))

    def test_without_form4_it_is_the_delivery_fx(self):
        self.assertEqual(cost_fx({"commodity": "CORN", "delivery_fx": 50.33}, 56.0),
                         (50.33, "delivery"))

    def test_with_neither_it_falls_back_to_what_the_caller_gives(self):
        self.assertEqual(cost_fx({"commodity": "CORN"}, 56.0), (56.0, "market today"))
        self.assertEqual(cost_fx({"commodity": "CORN"}), (None, ""))

    def test_a_blank_or_zero_form4_is_not_a_rate(self):
        for empty in ("", None, 0, "0", "abc"):
            c = {"commodity": "CORN", "form4_fx": empty, "delivery_fx": 50.33}
            self.assertEqual(cost_fx(c), (50.33, "delivery"), repr(empty))

    def test_a_typed_value_with_a_thousands_comma_still_reads(self):
        self.assertEqual(cost_fx({"commodity": "CORN", "form4_fx": "49.50"}), (49.5, "Form 4"))

    def test_a_missing_commodity_is_treated_as_corn(self):
        self.assertTrue(uses_form4({"form4_fx": 49.5}))


if __name__ == "__main__":
    unittest.main()
