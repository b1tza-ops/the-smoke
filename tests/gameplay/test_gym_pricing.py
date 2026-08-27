"""What the gym ladder costs, against what it gives you.

The last three gyms held 94% of the ladder's entire price. The Lock was
£2,500,000 -- about 1,284 three-hour days of the best crime in London,
which is three and a half years of daily play for one membership.

The cause was two curves that did not match. Price multiplied by roughly
2.5 at every rung while the training rate rose 10-15%, so value for
money collapsed: £250 per point of multiplier at the bottom against
£833,333 at the top, a 3,300x degradation.

A price nobody can reach is not a money sink. It absorbs nothing,
because no balance ever arrives. The top three are repriced so the
ladder keeps climbing at a rate that tracks what it buys, and the
eleven gyms below them are untouched -- they were never the problem.

These tests hold the relationship rather than the prices, so a
deliberate retune does not have to fight them.
"""

import unittest

from game.crime import CRIMES
from game.gym import GYMS

NERVE_PER_HOUR = 12
PLAYING_HOURS_PER_DAY = 3


def best_daily_income():
    """What the best crime in London returns in a session."""
    best = max(
        (crime.min_reward + crime.max_reward) / 2
        * (crime.success_chance / 100)
        * (NERVE_PER_HOUR / crime.nerve_cost)
        for crime in CRIMES
    )

    return best * PLAYING_HOURS_PER_DAY


def training_advantage(gym):
    """The best training rate this gym offers, over the free one.

    Measured on the highest multiplier rather than the average,
    deliberately. Three gyms train only three of the four stats but
    train those harder -- Powerhouse beats Marsh Athletic on strength,
    defence and speed and does no dexterity at all. Averaging calls
    those bad; they are specialist, and someone buys them on purpose.
    """
    return max((
        gym.strength_multiplier,
        gym.defence_multiplier,
        gym.speed_multiplier,
        gym.dexterity_multiplier,
    )) - 1


def paid_gyms():
    return [gym for gym in GYMS if gym.membership_cost > 0]


class GymPricingTests(unittest.TestCase):
    def test_the_dearest_gym_is_reachable_in_a_season(self):
        dearest = max(gym.membership_cost for gym in GYMS)
        days = dearest / best_daily_income()

        self.assertLess(
            days,
            260,
            f"the top gym takes {days:,.0f} days of the best crime in "
            f"London; nobody arrives, so it drains nothing",
        )
        self.assertGreater(
            days,
            60,
            f"the top gym takes only {days:,.0f} days, which is not "
            f"much of a long-term goal",
        )

    def test_value_for_money_never_collapses(self):
        """The bug, stated as a rule.

        A dearer gym is allowed to be worse value -- that is what makes
        it a luxury. It is not allowed to be *orders of magnitude*
        worse, which is what turns the top of the ladder into a wall.
        """
        rates = [
            gym.membership_cost / training_advantage(gym)
            for gym in paid_gyms()
        ]

        self.assertLess(
            max(rates) / min(rates),
            1_000,
            f"the worst-value gym is {max(rates) / min(rates):,.0f}x "
            f"the best; it was 3,333x when the top gym was £2.5m",
        )

    def test_no_single_step_more_than_triples_the_price(self):
        ordered = sorted(paid_gyms(), key=lambda gym: gym.membership_cost)

        for cheaper, dearer in zip(ordered, ordered[1:]):
            with self.subTest(step=f"{cheaper.name} -> {dearer.name}"):
                self.assertLessEqual(
                    dearer.membership_cost / cheaper.membership_cost,
                    3.0,
                    "one step up the ladder costs more than three times "
                    "the last, which is how the top ran away",
                )

    def test_the_top_of_the_ladder_is_not_the_whole_ladder(self):
        ordered = sorted(GYMS, key=lambda gym: gym.membership_cost)
        total = sum(gym.membership_cost for gym in ordered)
        top_three = sum(gym.membership_cost for gym in ordered[-3:])

        self.assertLess(
            top_three / total,
            0.85,
            f"the last three gyms are {top_three / total:.0%} of "
            f"everything the ladder costs; it was 94%",
        )

    def test_every_gym_is_the_best_buy_for_something(self):
        """Paying more must buy the best rate for *some* stat.

        Not for every stat: the gyms peak on different ones. West End
        Fight Lab costs twice Soho Fitness Rooms and has a lower top
        multiplier, but trains strength at 1.85 against Soho's 1.7 --
        which is the whole reason a strength build walks past Soho.

        What must never happen is a gym with no reason to buy it.
        """
        stats = (
            "strength_multiplier",
            "defence_multiplier",
            "speed_multiplier",
            "dexterity_multiplier",
        )
        ordered = sorted(paid_gyms(), key=lambda gym: gym.membership_cost)

        for position, gym in enumerate(ordered):
            cheaper = ordered[:position]
            if not cheaper:
                continue

            best_at = [
                stat for stat in stats
                if all(
                    getattr(gym, stat) > getattr(other, stat)
                    for other in cheaper
                )
            ]

            with self.subTest(gym=gym.key):
                self.assertTrue(
                    best_at,
                    f"{gym.name} costs £{gym.membership_cost:,} and "
                    f"trains nothing better than something cheaper",
                )

    def test_the_cheap_end_was_left_alone(self):
        """A new player's first two gyms must not have moved."""
        by_key = {gym.key: gym for gym in GYMS}

        self.assertEqual(by_key["camden_community"].membership_cost, 0)
        self.assertEqual(by_key["camden_average_joes"].membership_cost, 100)
        self.assertEqual(by_key["camden_ironworks"].membership_cost, 250)


if __name__ == "__main__":
    unittest.main()
