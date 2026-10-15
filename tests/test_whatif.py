"""The what-if table, pinned to the YC offers mail of 14 Oct 2026.

If any of these fail, the app and the import manager's circulated figures
have diverged, which is the one outcome this module exists to prevent.
"""

import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prometheus_core.whatif import (MAIL_REFERENCE, carry_cost, days_until,
                                    local_premium_equivalent,
                                    offer_comparison, scenario_ladder,
                                    whatif_scenario)

M = MAIL_REFERENCE


def mail_scenario(**over):
    args = dict(local_price_egp_mt=M["local_price_egp_mt"],
                fx_egp_usd=M["fx_egp_usd"], conversion=M["conversion"],
                cbot=M["cbot"], interest_rate_pct=M["interest_rate_pct"],
                carry_days=M["carry_days"],
                local_expenses_egp_mt=M["local_expenses_egp_mt"],
                year_basis=M["year_basis"])
    args.update(over)
    return whatif_scenario(**args)


class MailReproductionTests(unittest.TestCase):
    def test_every_printed_line_matches_the_mail(self):
        row = mail_scenario()
        for field, expected in M["expected"].items():
            with self.subTest(line=field):
                # The mail rounds each line as it prints it; agreement to
                # that rounding is agreement.
                places = 2 if expected < 100 else 0
                self.assertAlmostEqual(row[field], expected, delta=0.6,
                                       msg=f"{field}: {row[field]} vs {expected}")
                del places

    def test_the_headline_premium_is_195(self):
        self.assertAlmostEqual(mail_scenario()["premium"], 195.06, places=2)

    def test_no_carry_gives_the_flat_equivalent_premium(self):
        """The mail's 'Equal to Premium' line is the same chain, zero days."""
        row = mail_scenario(carry_days=0)
        self.assertAlmostEqual(row["carry_cost_egp_mt"], 0.0)
        self.assertAlmostEqual(row["price_with_carry_egp_mt"], 14350.0)
        self.assertAlmostEqual(row["premium"], 183.76, places=2)

    def test_the_mails_186_needs_450_of_expenses_not_500(self):
        """Documents a real inconsistency inside the mail itself."""
        self.assertAlmostEqual(
            mail_scenario(carry_days=0, local_expenses_egp_mt=450)["premium"],
            186.15, places=2)

    def test_raw_premium_omits_the_deduction(self):
        row = mail_scenario()
        self.assertAlmostEqual(row["premium_raw"] - row["premium"],
                               (500 / 53.0) / 0.3937, places=8)
        self.assertAlmostEqual(row["premium_raw"], 219.02, places=2)


class CarryTests(unittest.TestCase):
    def test_carry_follows_the_mails_three_steps(self):
        c = carry_cost(14350, 20, 30, 365)
        self.assertAlmostEqual(c["interest_amount_per_annum"], 2870.0)
        self.assertAlmostEqual(c["interest_per_day"], 7.863, places=3)
        self.assertAlmostEqual(c["carry_cost_egp_mt"], 235.89, places=2)

    def test_year_basis_is_not_assumed(self):
        """365 for the local facility, 360 money-market — mixing them is an error."""
        self.assertNotAlmostEqual(carry_cost(14350, 20, 30, 365)["carry_cost_egp_mt"],
                                  carry_cost(14350, 20, 30, 360)["carry_cost_egp_mt"])

    def test_zero_days_costs_nothing(self):
        self.assertEqual(carry_cost(14350, 20, 0)["carry_cost_egp_mt"], 0.0)


class PremiumEquivalentTests(unittest.TestCase):
    def test_14300_raw_on_the_mails_inputs(self):
        row = local_premium_equivalent(14300, 53.0, 0.3937, 480.0, 0.0)
        self.assertAlmostEqual(row["premium"], 205.32, places=2)

    def test_missing_inputs_are_named_not_zeroed(self):
        row = local_premium_equivalent(14300, None, 0.3937, 480.0)
        self.assertIsNone(row["premium"])
        self.assertIn("FX", row["note"])


class OfferComparisonTests(unittest.TestCase):
    TODAY = dt.date(2026, 10, 14)

    def _rows(self, expenses=500.0):
        return offer_comparison(
            M["offers"], M["local_price_egp_mt"], M["fx_egp_usd"],
            M["conversion"], M["cbot"],
            interest_rate_pct=M["interest_rate_pct"],
            local_expenses_egp_mt=expenses, year_basis=M["year_basis"],
            today=self.TODAY)

    def test_each_offer_is_carried_to_its_own_eta(self):
        rows = self._rows()
        self.assertEqual([r["carry_days"] for r in rows], [21, 32, 52])

    def test_a_flat_thirty_days_would_misprice_two_of_the_three(self):
        """The reason ETA matters: only ADM sits near day 30."""
        rows = self._rows()
        self.assertNotEqual(rows[0]["carry_days"], 30)
        self.assertNotEqual(rows[2]["carry_days"], 30)

    def test_verdicts_differ_by_supplier(self):
        """On the mail's own FX and board, the three offers do not agree.

        Nagi's single 30-day figure says import, full stop. Carried to each
        arrival date instead, El-Magd's December slot loses to local — the
        extra three weeks of carry cost less than its 15-cent wider basis.
        """
        rows = {r["supplier"]: r for r in self._rows()}
        self.assertEqual(rows["Cofco"]["verdict"], "import cheaper")
        self.assertEqual(rows["ADM"]["verdict"], "import cheaper")
        self.assertEqual(rows["El-Magd"]["verdict"], "local cheaper")
        # ADM's mid-November slot is the clear one; Cofco is nearly level.
        self.assertAlmostEqual(rows["ADM"]["gap"], 5.81, places=2)
        self.assertAlmostEqual(rows["Cofco"]["gap"], 1.67, places=2)
        self.assertAlmostEqual(rows["El-Magd"]["gap"], -1.65, places=2)

    def test_gap_sign_means_what_the_verdict_says(self):
        for row in self._rows():
            if row["verdict"] == "import cheaper":
                self.assertGreater(row["gap"], 0)
            elif row["verdict"] == "local cheaper":
                self.assertLess(row["gap"], 0)

    def test_days_until_floors_at_zero_for_a_past_date(self):
        self.assertEqual(days_until("2026-01-01", self.TODAY), 0)
        self.assertIsNone(days_until("", self.TODAY))
        self.assertIsNone(days_until("not a date", self.TODAY))


class LadderTests(unittest.TestCase):
    def test_premium_rises_with_every_extra_day_held(self):
        rows = scenario_ladder(
            [0, 15, 30, 60], local_price_egp_mt=M["local_price_egp_mt"],
            fx_egp_usd=M["fx_egp_usd"], conversion=M["conversion"],
            cbot=M["cbot"], interest_rate_pct=M["interest_rate_pct"],
            local_expenses_egp_mt=M["local_expenses_egp_mt"],
            year_basis=M["year_basis"])
        premiums = [r["premium"] for r in rows]
        self.assertEqual(premiums, sorted(premiums))
        self.assertAlmostEqual(premiums[2], 195.06, places=2)


if __name__ == "__main__":
    unittest.main()
