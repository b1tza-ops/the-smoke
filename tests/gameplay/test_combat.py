from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from game.combat import (
    COMBAT_ENERGY_COST,
    CombatError,
    fight_camden_opponent,
    get_combat_block,
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


def test_equipment_bonuses_drive_a_winning_fight():
    fighter = player()
    equipment = Mock(strength_bonus=15, defence_bonus=12)

    result = fight_camden_opponent(
        fighter,
        equipment,
        rng=HighRolls(),
    )

    assert result.victory is True
    assert fighter.energy == 100 - COMBAT_ENERGY_COST
    assert fighter.money >= 70
    assert fighter.xp == 35
    assert result.rounds


def test_defeat_sends_player_to_hospital():
    fighter = player(
        health=8,
        strength=1,
        defence=0,
        speed=1,
        dexterity=1,
    )
    equipment = Mock(strength_bonus=0, defence_bonus=0)

    result = fight_camden_opponent(
        fighter,
        equipment,
        rng=LowDamage(),
    )

    assert result.victory is False
    assert fighter.health == 0
    assert fighter.hospital_until is not None


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"current_district": "soho"}, "Camden"),
        ({"hospital_until": "2099-01-01 00:00:00"}, "Hospital"),
        ({"jail_until": "2099-01-01 00:00:00"}, "Jail"),
        ({"travel_destination": "soho"}, "travelling"),
        ({"shift_until": "2099-01-01 00:00:00"}, "working"),
        ({"energy": 0}, "energy"),
    ],
)
def test_combat_restrictions(changes, reason):
    assert reason in get_combat_block(player(**changes))


def test_blocked_fight_does_not_spend_energy():
    fighter = player(energy=0)
    with pytest.raises(CombatError):
        fight_camden_opponent(
            fighter,
            Mock(strength_bonus=0, defence_bonus=0),
        )
    assert fighter.energy == 0
