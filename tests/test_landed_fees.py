"""Manual-mode landed fees: clearance + inland freight.

Contract mode has always added clearance and effective freight on top of
intake.  Manual mode stopped at intake, so an import that had not yet paid
for clearance or the run to the yard was compared against a local price that
includes transport.  These tests pin the arithmetic and the ex-yard rule.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.decision import compute_decision

CORN = {"type": "CBOT", "unit": "cents/bu", "conversion_type": "bu_per_mt",
        "conversion_value": 39.37, "locked_factor": 0.3937,
        "premium_mode": "CBOT_UNIT"}

BASE = {
    "comm_meta": CORN,
    "fx": 52.6910,
    "qty_mt": 2000.0,
    "local_egp_mt": 14300.0,
    "finance_days": 30,
    "interest_rate": 20,
    "supplier_direct_egp_mt": 235.0,
    "supplier_indirect_egp_mt": 365.0,
    "cbot": 482.75,
    "premium_usd_mt": 175.0,
    "hedge_pct": 0,
}


def run(**over):
    inp = dict(BASE)
    inp.update(over)
    return compute_decision(inp)


class LandedFeeTests(unittest.TestCase):
    def test_absent_fees_reproduce_the_original_numbers(self):
        """A calculation saved before the fields existed must not move."""
        out = run()
        self.assertAlmostEqual(out["import_usd_mt"], 258.96, places=2)
        self.assertAlmostEqual(out["carry_usd_mt"], 4.32, places=2)
        self.assertAlmostEqual(out["own_after_egp_mt"], 13872.07, places=2)
        self.assertAlmostEqual(out["direct_own_after_egp_mt"], 14107.07, places=2)
        self.assertAlmostEqual(out["indirect_own_after_egp_mt"], 14237.07, places=2)
        self.assertEqual(out["extra_landed_fees_egp_mt"], 0.0)

    def test_fees_land_on_both_intake_scenarios(self):
        out = run(extra_landed_fees_egp_mt=443.13)
        self.assertAlmostEqual(out["direct_own_after_egp_mt"], 14550.20, places=2)
        self.assertAlmostEqual(out["indirect_own_after_egp_mt"], 14680.20, places=2)

    def test_fees_flip_a_marginal_deal_negative(self):
        """The case that prompted this: +193 saving was freight-blind."""
        self.assertGreater(run()["direct_saving_egp_mt"], 0)
        out = run(extra_landed_fees_egp_mt=443.13)
        self.assertLess(out["direct_saving_egp_mt"], 0)
        self.assertAlmostEqual(out["direct_saving_egp_mt"], -250.20, places=2)

    def test_own_after_itself_is_untouched(self):
        """Fees belong to the landed lines, not to the bare CIF+carry line."""
        a, b = run(), run(extra_landed_fees_egp_mt=443.13)
        self.assertAlmostEqual(a["own_after_egp_mt"], b["own_after_egp_mt"])
        self.assertAlmostEqual(a["saving_egp_mt"], b["saving_egp_mt"])

    def test_break_even_fx_accounts_for_the_fees(self):
        out = run(extra_landed_fees_egp_mt=443.13)
        expected = (14300.0 - 235.0 - 443.13) / out["own_after_usd_mt"]
        self.assertAlmostEqual(out["break_even_fx_direct"], expected, places=6)
        self.assertLess(out["break_even_fx_direct"], run()["break_even_fx_direct"])

    def test_hedged_own_after_accounts_for_the_fees(self):
        out = run(extra_landed_fees_egp_mt=443.13, hedge_pct=50, hedge_fx=54.0)
        plain = run(hedge_pct=50, hedge_fx=54.0)
        self.assertAlmostEqual(
            out["hedged_direct_own_after_egp_mt"]
            - plain["hedged_direct_own_after_egp_mt"], 443.13, places=6)

    def test_contract_mode_is_not_double_charged(self):
        """canonical_landed_fees already carries clearance and freight."""
        out = run(canonical_landed_fees_egp_mt=678.13,
                  extra_landed_fees_egp_mt=443.13)
        self.assertAlmostEqual(out["direct_own_after_egp_mt"],
                               13872.07 + 678.13, places=2)
        self.assertEqual(out["direct_own_after_egp_mt"],
                         out["indirect_own_after_egp_mt"])


if __name__ == "__main__":
    unittest.main()
