import unittest

from types import SimpleNamespace
from unittest.mock import Mock

from game.combat import (
    COMBAT_ENERGY_COST,
    OPPONENTS_BY_KEY,
    CombatError,
    fight_opponent,
    get_combat_block,
    get_district_opponents,
)
from game.combat.npc import OUTGROWN_PAYOUT_FLOOR, payout_share


class HighRolls:
    def randint(self, start, end):
        return start


class LowDamage:
    def randint(self, start, end):
        return end


def player(**changes):
    values = dict(
        current_district="camden",
        hospital_until=None,
        jail_until=None,
        travel_destination=None,
        shift_until=None,
        health=100,
        energy=100,
        money=0,
        xp=0,
        level=1,
        strength=50,
        defence=50,
        speed=50,
        dexterity=50,
    )
    values.update(changes)
    return SimpleNamespace(**values)


class CombatTests(unittest.TestCase):

    def test_districts_offer_different_opponents(self):
        assert [o.key for o in get_district_opponents("camden")] == [
            "market_runner",
            "canal_yard_enforcer",
        ]
        assert [o.key for o in get_district_opponents("soho")] == [
            "soho_door_enforcer",
        ]

    def test_equipment_bonuses_drive_a_winning_fight(self):
        fighter = player()
        result = fight_opponent(
            fighter,
            Mock(strength_bonus=15, defence_bonus=12),
            OPPONENTS_BY_KEY["canal_yard_enforcer"],
            rng=HighRolls(),
        )
        assert result.victory is True
        assert fighter.energy == (
            100 - OPPONENTS_BY_KEY["canal_yard_enforcer"].energy_cost
        )
        # Not the full £70 purse: this fixture is a developed fighter at
        # five times starting stats, and the enforcer is a Camden
        # standard, so most of the purse has been outgrown. A genuinely
        # new player still takes the lot -- see the tests below.
        assert fighter.money == 15
        assert fighter.xp == 35
        assert result.rounds

    def test_a_new_player_is_never_scaled_down(self):
        # Starting stats are 10 across the board, beneath every Camden
        # opponent but the market runner. Fighting above your weight
        # always pays the whole purse.
        #
        # This reads the rule rather than a fight, deliberately: a new
        # player loses to the enforcer, which is the point of it.
        new_player = player(
            strength=10, defence=10, speed=10, dexterity=10
        )

        assert payout_share(
            new_player, OPPONENTS_BY_KEY["canal_yard_enforcer"]
        ) == 1
        assert payout_share(
            new_player, OPPONENTS_BY_KEY["soho_door_enforcer"]
        ) == 1

    def test_the_scale_never_falls_to_nothing(self):
        # An opponent you have hugely outgrown still pays something, so
        # a district never becomes literally worthless to visit.
        titan = player(
            strength=10_000, defence=10_000,
            speed=10_000, dexterity=10_000,
        )

        assert payout_share(
            titan, OPPONENTS_BY_KEY["market_runner"]
        ) == OUTGROWN_PAYOUT_FLOOR

    def test_equipping_your_best_gear_never_cuts_your_income(self):
        """Gear is what you brought, not who you are.

        The payout scale reads trained stats alone. If it counted the
        loadout, arming yourself would shrink your own purse and the
        optimal play would be to fight barehanded -- which is the
        opposite of what buying a weapon is for.
        """
        barehanded = player()
        armed = player()

        for fighter, equipment in (
            (barehanded, Mock(strength_bonus=0, defence_bonus=0)),
            (armed, Mock(strength_bonus=40, defence_bonus=40)),
        ):
            fight_opponent(
                fighter,
                equipment,
                OPPONENTS_BY_KEY["canal_yard_enforcer"],
                rng=HighRolls(),
            )

        assert armed.money == barehanded.money

    def test_hard_defeat_sends_player_to_hospital(self):
        fighter = player(
            current_district="soho",
            health=8,
            strength=1,
            defence=0,
            speed=1,
            dexterity=1,
        )
        result = fight_opponent(
            fighter,
            Mock(strength_bonus=0, defence_bonus=0),
            OPPONENTS_BY_KEY["soho_door_enforcer"],
            rng=LowDamage(),
        )
        assert result.victory is False
        assert fighter.health == 0
        assert fighter.hospital_until is not None

    def test_combat_restrictions(self):
        opponent = OPPONENTS_BY_KEY["canal_yard_enforcer"]
        cases = (
            ({"current_district": "soho"}, "Camden"),
            ({"hospital_until": "2099-01-01 00:00:00"}, "Hospital"),
            ({"jail_until": "2099-01-01 00:00:00"}, "Jail"),
            ({"travel_destination": "soho"}, "travelling"),
            ({"shift_until": "2099-01-01 00:00:00"}, "working"),
            ({"energy": 0}, "energy"),
        )
        for changes, reason in cases:
            assert reason in get_combat_block(player(**changes), opponent)

    def test_the_page_can_ask_about_a_player_with_no_opponent(self):
        """The fight page renders by asking "can this player fight?"

        `get_combat_block` took `opponent=None` and every guard handled
        it except the energy one, which read `opponent.energy_cost`
        anyway. So the page 500'd for any healthy, free player and
        worked only for players in hospital, in jail, travelling or on a
        shift -- it was up for exactly the people who could not use it.
        """
        assert get_combat_block(player()) is None

    def test_with_no_opponent_it_prices_the_cheapest_fight_available(self):
        from game.combat.npc import cheapest_fight_cost

        cheapest = cheapest_fight_cost("camden")

        assert get_combat_block(player(energy=cheapest)) is None
        assert "energy" in get_combat_block(player(energy=cheapest - 1))

    def test_a_district_with_nobody_to_fight_blocks_nothing(self):
        # No opponents is not a reason to tell a player they are unable
        # to fight; there is simply nobody here.
        broke = player(current_district="brixton", energy=0)

        assert get_combat_block(broke) is None

    def test_blocked_fight_does_not_spend_energy(self):
        fighter = player(energy=0)
        try:
            fight_opponent(
                fighter,
                Mock(strength_bonus=0, defence_bonus=0),
                OPPONENTS_BY_KEY["canal_yard_enforcer"],
            )
        except CombatError:
            pass
        else:
            raise AssertionError("Blocked fight should raise CombatError")
        assert fighter.energy == 0


if __name__ == "__main__":
    unittest.main()
