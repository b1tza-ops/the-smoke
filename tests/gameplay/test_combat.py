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


def test_districts_offer_different_opponents():
    assert [o.key for o in get_district_opponents("camden")] == [
        "market_runner",
        "canal_yard_enforcer",
    ]
    assert [o.key for o in get_district_opponents("soho")] == [
        "soho_door_enforcer",
    ]


def test_equipment_bonuses_drive_a_winning_fight():
    fighter = player()
    result = fight_opponent(
        fighter,
        Mock(strength_bonus=15, defence_bonus=12),
        OPPONENTS_BY_KEY["canal_yard_enforcer"],
        rng=HighRolls(),
    )
    assert result.victory is True
    assert fighter.energy == 100 - COMBAT_ENERGY_COST
    assert fighter.money >= 70
    assert fighter.xp == 35
    assert result.rounds


def test_hard_defeat_sends_player_to_hospital():
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


def test_combat_restrictions():
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


def test_blocked_fight_does_not_spend_energy():
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
