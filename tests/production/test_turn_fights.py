"""Fighting a turn at a time, with a weapon you chose.

Player fights used to resolve in one request: you picked a target and an
approach, and twelve rounds of dice happened without you. The loadout
was a set of passive bonuses.

Now a fight is a thing you are in. Each turn you pick what to swing,
ammunition and throwables come out of your pockets as you use them, and
you can walk away.

The interesting cases are all about a fight outliving the request that
started it: a refresh must not buy two swings, a fight must not be
cashed twice, and a stack of bricks must not become infinite.
"""

import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database.core.setup import create_tables
from game.combat.pvp import PVP_ENERGY_COST, PvpError
from game.combat.turns import (
    FISTS,
    MAXIMUM_TURNS,
    TurnError,
    Weapon,
    choose,
    decide,
    fists,
    take_turn,
)


def combatant(**changes):
    values = dict(strength=40, defence=20, speed=20, dexterity=20)
    values.update(changes)
    return SimpleNamespace(**values)


class TurnRuleTests(unittest.TestCase):
    def test_a_turn_always_resolves_both_sides(self):
        outcome = take_turn(
            1, combatant(), combatant(), fists(), 100, 100,
            rng=random.Random(1),
        )

        self.assertIn(outcome.attacker_event, ("hit", "miss"))
        self.assertIn(outcome.defender_event, ("hit", "miss"))

    def test_a_downed_defender_does_not_answer(self):
        outcome = take_turn(
            1, combatant(strength=500), combatant(defence=0),
            fists(), 100, 1, rng=random.Random(1),
        )

        self.assertEqual(outcome.defender_health, 0)
        self.assertEqual(outcome.defender_damage, 0)
        self.assertTrue(outcome.finished)
        self.assertTrue(outcome.victory)

    def test_the_fight_stops_at_the_turn_limit(self):
        outcome = take_turn(
            MAXIMUM_TURNS, combatant(strength=1), combatant(defence=400),
            fists(), 500, 500, rng=random.Random(1),
        )

        self.assertTrue(
            outcome.finished,
            "two players who cannot hurt each other fight for ever",
        )

    def test_a_stalemate_goes_to_the_defender(self):
        # Starting a fight you cannot finish should not pay.
        self.assertFalse(decide(100, 100))
        self.assertFalse(decide(50, 100))
        self.assertTrue(decide(100, 50))

    def test_firing_costs_a_round_even_on_a_miss(self):
        gun = Weapon("primary", "compact_9mm", "Compact 9mm", 22,
                     ammo_key="ammo_9mm", available=5)

        outcome = take_turn(
            1, combatant(strength=1), combatant(speed=400),
            gun, 100, 100, rng=random.Random(9),
        )

        self.assertEqual(outcome.ammo_spent, "ammo_9mm")

    def test_a_throwable_is_spent_whatever_happens(self):
        brick = Weapon("throwable", "brick", "Half Brick", 14, available=2)

        outcome = take_turn(
            1, combatant(), combatant(), brick, 100, 100,
            rng=random.Random(1),
        )

        self.assertEqual(outcome.throwable_spent, "brick")

    def test_fists_cost_nothing_and_never_run_out(self):
        outcome = take_turn(
            1, combatant(), combatant(), fists(), 100, 100,
            rng=random.Random(1),
        )

        self.assertIsNone(outcome.ammo_spent)
        self.assertIsNone(outcome.throwable_spent)
        self.assertIsNone(fists().available)

    def test_picking_something_you_do_not_have_is_refused(self):
        with self.assertRaises(TurnError):
            choose([fists()], "petrol_bomb")

    def test_picking_something_you_have_run_out_of_is_refused(self):
        empty = Weapon("throwable", "brick", "Half Brick", 14, available=0)

        with self.assertRaises(TurnError):
            choose([empty, fists()], "brick")


class FightThroughTheDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "turns.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.attacker_user, self.attacker = self.make(
            "att", strength=60, defence=40, speed=40, dexterity=40,
            energy=150, health=400, max_health=400,
        )
        self.defender_user, self.defender = self.make(
            "def", strength=12, defence=8, speed=8, dexterity=8,
            health=250, max_health=250,
        )

    def make(self, name, **columns):
        from database.repositories.players import create_player
        from database.repositories.users import create_user

        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET "
                + ", ".join(f"{key} = ?" for key in columns)
                + ", current_district = 'camden' WHERE user_id = ?",
                (*columns.values(), user_id),
            )
        player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return user_id, player_id

    def load(self, user_id):
        from database.repositories.players import get_player_by_user_id
        from game.player import Player

        return Player(*get_player_by_user_id(user_id))

    def give(self, key, count=1):
        from database.repositories.players import save_player
        from game.inventory import add_item

        player = self.load(self.attacker_user)
        for _ in range(count):
            add_item(player, key)
        save_player(player)

    def equip(self, key):
        from game.inventory import equip_item

        equip_item(self.attacker, key)

    def open_fight(self):
        from database.repositories.fights import start_fight

        attacker = self.load(self.attacker_user)
        defender = self.load(self.defender_user)
        return start_fight(
            attacker, self.defender, defender.health,
            defender.max_health, "aggressive",
        )

    def swing(self, fight, weapon, rng=None):
        from database.repositories.fights import take_fight_turn

        return take_fight_turn(
            fight.id,
            self.load(self.attacker_user),
            self.load(self.defender_user),
            weapon,
            rng=rng or random.Random(3),
        )

    def carried(self, key):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT quantity FROM player_inventory"
            " WHERE player_id = ? AND item_key = ?",
            (self.attacker, key),
        ).fetchone()
        connection.close()
        return row[0] if row else 0

    # ------------------------------------------------- the loadout

    def test_the_column_lists_every_weapon_slot_plus_fists(self):
        from database.repositories.fights import weapons_for

        self.give("compact_9mm")
        self.give("ammo_9mm", 6)
        self.give("machete")
        self.give("brick", 3)
        for key in ("compact_9mm", "machete", "brick"):
            self.equip(key)

        column = {weapon.key: weapon for weapon in weapons_for(self.attacker)}

        self.assertEqual(column["compact_9mm"].available, 6)
        self.assertEqual(column["machete"].available, None)
        self.assertEqual(column["brick"].available, 3)
        self.assertIn(FISTS, column)

    def test_fists_are_there_with_nothing_equipped(self):
        from database.repositories.fights import weapons_for

        self.assertEqual(
            [weapon.key for weapon in weapons_for(self.attacker)],
            [FISTS],
        )

    # --------------------------------------------------- the fight

    def test_starting_a_fight_charges_energy_once(self):
        before = self.load(self.attacker_user).energy

        fight = self.open_fight()
        self.swing(fight, FISTS)
        self.swing(fight, FISTS)

        self.assertEqual(
            self.load(self.attacker_user).energy,
            before - PVP_ENERGY_COST,
            "energy is charged per turn rather than per fight",
        )

    def test_only_one_fight_can_be_open(self):
        self.open_fight()

        with self.assertRaises(PvpError):
            self.open_fight()

    def test_walking_away_frees_you_to_start_another(self):
        from database.repositories.fights import flee, get_open_fight

        fight = self.open_fight()
        flee(fight.id, self.attacker)

        self.assertIsNone(get_open_fight(self.attacker))
        self.open_fight()

    def test_a_turn_cannot_be_taken_on_a_fight_that_ended(self):
        from database.repositories.fights import flee

        fight = self.open_fight()
        flee(fight.id, self.attacker)

        with self.assertRaises(PvpError):
            self.swing(fight, FISTS)

    def test_you_cannot_swing_in_somebody_elses_fight(self):
        from database.repositories.fights import take_fight_turn

        fight = self.open_fight()

        with self.assertRaises(PvpError):
            take_fight_turn(
                fight.id, self.load(self.defender_user),
                self.load(self.attacker_user), FISTS,
            )

    def test_the_turn_counter_climbs(self):
        fight = self.open_fight()

        for expected in (1, 2, 3):
            outcome, fight = self.swing(fight, FISTS)
            self.assertEqual(outcome.turn, expected)
            self.assertEqual(fight.turn, expected)

    # ------------------------------------------- spending what you use

    def test_a_round_leaves_the_inventory_when_it_is_fired(self):
        self.give("compact_9mm")
        self.give("ammo_9mm", 2)
        self.equip("compact_9mm")
        fight = self.open_fight()

        self.swing(fight, "compact_9mm")

        self.assertEqual(self.carried("ammo_9mm"), 1)

    def test_the_last_round_can_be_fired(self):
        """`quantity > 0` is a CHECK, so emptying a stack is the edge."""
        self.give("compact_9mm")
        self.give("ammo_9mm", 1)
        self.equip("compact_9mm")
        fight = self.open_fight()

        self.swing(fight, "compact_9mm")

        self.assertEqual(self.carried("ammo_9mm"), 0)

    def test_firing_with_nothing_left_is_refused(self):
        self.give("compact_9mm")
        self.give("ammo_9mm", 1)
        self.equip("compact_9mm")
        fight = self.open_fight()
        self.swing(fight, "compact_9mm")

        with self.assertRaises(TurnError):
            self.swing(fight, "compact_9mm")

    def test_a_thrown_weapon_is_gone(self):
        self.give("brick", 2)
        self.equip("brick")
        fight = self.open_fight()

        self.swing(fight, "brick")

        self.assertEqual(self.carried("brick"), 1)

    def test_throwing_the_last_one_clears_the_slot(self):
        from database.repositories.fights import weapons_for

        self.give("brick", 1)
        self.equip("brick")
        fight = self.open_fight()

        self.swing(fight, "brick")

        self.assertEqual(self.carried("brick"), 0)
        self.assertNotIn(
            "brick",
            [weapon.key for weapon in weapons_for(self.attacker)],
            "a thrown brick is still sitting in the slot",
        )

    def test_a_fight_ends_and_stops_accepting_turns(self):
        self.give("machete")
        self.equip("machete")
        fight = self.open_fight()

        for _ in range(MAXIMUM_TURNS + 5):
            outcome, fight = self.swing(fight, "machete")
            if outcome.finished:
                break

        self.assertTrue(outcome.finished)
        self.assertFalse(fight.open)

        with self.assertRaises(PvpError):
            self.swing(fight, "machete")


class ThroughTheAttackScreenTests(FightThroughTheDatabaseTests):
    """The page, not just the repository."""

    def setUp(self):
        super().setUp()
        from web.application import app

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.attacker_user

        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE users SET created_at = '2026-01-01 00:00:00'"
                " WHERE id = ?",
                (self.defender_user,),
            )
        connection.close()

    def start(self):
        return self.client.post(
            "/pvp",
            data={"target_id": self.defender, "approach": "aggressive"},
        )

    def test_the_staging_screen_gives_way_to_the_fight(self):
        """The START FIGHT form posts to the URL that staged it.

        That URL still carries ?target_id, so without suppressing the
        staging screen it renders on top of the fight it just began --
        two START FIGHT buttons for one fight.
        """
        page = self.client.post(
            f"/pvp?target_id={self.defender}",
            data={"target_id": self.defender, "approach": "aggressive"},
        ).get_data(as_text=True)

        self.assertNotIn("START FIGHT", page)
        self.assertIn('name="weapon"', page)

    def test_the_weapons_are_buttons_once_the_fight_is_on(self):
        self.give("machete")
        self.equip("machete")

        page = self.start().get_data(as_text=True)

        self.assertIn('name="weapon" value="machete"', page)
        self.assertIn('name="weapon" value="fists"', page)

    def test_a_turn_reports_why_it_was_refused(self):
        """Errors are raised mid-fight, when the browse page is hidden."""
        self.start()

        page = self.client.post(
            "/pvp", data={"action": "turn", "weapon": "petrol_bomb"}
        ).get_data(as_text=True)

        self.assertIn("not carrying that", page)

    def test_walking_away_ends_the_fight(self):
        from database.repositories.fights import get_open_fight

        self.start()
        fight = get_open_fight(self.attacker)

        self.client.post(
            "/pvp", data={"action": "flee", "fight_id": fight.id}
        )

        self.assertIsNone(get_open_fight(self.attacker))

    def test_it_all_works_without_javascript(self):
        # The test client runs none, which is the point.
        self.give("machete")
        self.equip("machete")
        self.start()

        for _ in range(MAXIMUM_TURNS + 2):
            page = self.client.post(
                "/pvp", data={"action": "turn", "weapon": "machete"}
            ).get_data(as_text=True)
            if "MUG" in page or "LEAVE" in page:
                break

        self.assertIn("LEAVE", page)
        self.assertIn("MUG", page)


if __name__ == "__main__":
    unittest.main()
