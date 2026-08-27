"""What progression is actually worth.

The crime ladder used to span 1.72x end to end. A player who had trained
for weeks, reached level 7 and unlocked Hackney earned £308 an hour
against £192 for someone shoplifting on their first afternoon -- at 28%
success and an hour in a cell, against 80% and ten minutes. Inside a
district it was worse: Camden's market stall carried triple the jail
risk of the shoplift and paid £3 an hour more.

Rewards are now set from a curve rather than chosen one at a time, so
the ladder is monotonic by construction and every district pays a real
premium for its harder job.

Like the casino paytables, these are recomputed on every run: edit a
reward without redoing the arithmetic and this fails. That is the point
-- a drift here quietly mints or destroys money and no player reports
getting richer.
"""

import unittest

from game.crime import CRIMES, CRIMES_BY_KEY

NERVE_PER_HOUR = 12

# The 2-nerve Camden shoplift, deliberately left where it was: this
# change lifts the middle and top of the ladder, it does not touch what
# a new player earns on their first afternoon.
STARTER_INCOME = 192.0
STARTER_NERVE = 2

# Chosen, not derived: (12/2) ** 0.68 = 3.38, so the hardest job in the
# game pays about three and a half times the safest one. Steep enough
# that reaching Hackney is felt, gentle enough that existing balances
# are not made worthless overnight.
CURVE_EXPONENT = 0.68

TOLERANCE = 0.06


def income_per_hour(crime):
    """What this crime returns an hour, spending nerve as fast as it comes."""
    runs = NERVE_PER_HOUR / crime.nerve_cost
    average = (crime.min_reward + crime.max_reward) / 2

    return average * (crime.success_chance / 100) * runs


def target_income(nerve_cost):
    return STARTER_INCOME * (nerve_cost / STARTER_NERVE) ** CURVE_EXPONENT


class EarningsCurveTests(unittest.TestCase):
    def test_every_crime_sits_on_the_curve(self):
        for crime in CRIMES:
            with self.subTest(crime=crime.key):
                actual = income_per_hour(crime)
                wanted = target_income(crime.nerve_cost)

                self.assertAlmostEqual(
                    actual / wanted,
                    1.0,
                    delta=TOLERANCE,
                    msg=(
                        f"{crime.key} pays £{actual:,.0f}/hour, the curve "
                        f"wants £{wanted:,.0f}. If this reward was changed "
                        f"on purpose, redo the curve rather than widening "
                        f"the tolerance."
                    ),
                )

    def test_the_starter_crime_is_untouched(self):
        starter = CRIMES_BY_KEY["camden_shoplift"]

        self.assertEqual(starter.min_reward, 20)
        self.assertEqual(starter.max_reward, 60)

    def test_harder_work_always_pays_better(self):
        ordered = sorted(CRIMES, key=lambda crime: crime.nerve_cost)
        incomes = [round(income_per_hour(crime)) for crime in ordered]

        self.assertEqual(
            incomes,
            sorted(incomes),
            "a crime costing more nerve earns less an hour than a "
            "cheaper one",
        )

    def test_the_ladder_is_worth_climbing(self):
        incomes = [income_per_hour(crime) for crime in CRIMES]
        spread = max(incomes) / min(incomes)

        self.assertGreater(
            spread,
            3.0,
            f"the whole ladder only spans {spread:.2f}x; progression "
            f"buys almost nothing",
        )
        self.assertLess(
            spread,
            4.0,
            f"the ladder spans {spread:.2f}x, which devalues every "
            f"balance already banked",
        )

    def test_every_district_pays_for_taking_the_risk(self):
        """The safe job and the risky one must not earn the same.

        Camden used to be the worst of these at 1.01x -- £3 an hour for
        triple the jail chance and double the sentence.
        """
        pairs = (
            ("camden_shoplift", "camden_market_stall"),
            ("brixton_phone_snatch", "brixton_warehouse"),
            ("soho_pickpocket", "soho_nightclub"),
            ("shoreditch_gallery_lift", "shoreditch_server_room"),
            ("hackney_lockup_raid", "hackney_canal_handover"),
        )

        for safe_key, risky_key in pairs:
            with self.subTest(district=safe_key.split("_")[0]):
                safe = income_per_hour(CRIMES_BY_KEY[safe_key])
                risky = income_per_hour(CRIMES_BY_KEY[risky_key])

                self.assertGreater(
                    risky / safe,
                    1.15,
                    f"{risky_key} carries the risk and pays "
                    f"{risky / safe:.2f}x, which is not worth it",
                )

    def test_no_crime_is_strictly_beaten_by_another(self):
        """Nothing may be cheaper, safer and better paid all at once.

        This is the invariant that matters, rather than success rate
        falling with nerve cost across the whole game. It does not: the
        Hackney lock-up raid costs 9 nerve at 45% while the Soho
        nightclub costs 8 at 38%. That is deliberate -- Hackney is
        gated behind level 7, so reaching it was the difficulty, and
        the content there can afford to be kinder.

        What must never happen is a crime nobody has a reason to pick.
        """
        for crime in CRIMES:
            for other in CRIMES:
                if other.key == crime.key:
                    continue

                beaten = (
                    other.nerve_cost <= crime.nerve_cost
                    and other.success_chance >= crime.success_chance
                    and income_per_hour(other) > income_per_hour(crime)
                )

                with self.subTest(crime=crime.key, beaten_by=other.key):
                    self.assertFalse(
                        beaten,
                        f"{crime.key} costs more, is riskier and pays "
                        f"less than {other.key}: nobody would run it",
                    )


if __name__ == "__main__":
    unittest.main()
