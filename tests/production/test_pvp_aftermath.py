"""What a winner does with the person on the floor.

PvP used to decide this for you: winning always mugged the loser for a
slice of their cash *and* always put them in hospital for a quarter of
an hour. There was no decision in it, and no way to beat somebody
without robbing them.

Torn's attack screen asks instead -- leave, mug, or hospitalise -- and
the three are exclusive. Taking their money and taking them out of the
game for fifteen minutes are different prizes, and having to pick one
is the whole mechanic.

These hold the rules, the once-only settlement, and the window that
stops a win being banked and cashed later.
"""

import random
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database.core.setup import create_tables
from game.combat.pvp import (
    AFTERMATH_CHOICES,
    AFTERMATH_WINDOW_SECONDS,
    MUG_CASH_CAP,
    PvpError,
    apply_aftermath,
    mug_takings,
)


class MugArithmeticTests(unittest.TestCase):
    def test_it_takes_a_share_of_what_they_carry(self):
        self.assertEqual(mug_takings(1_000, 10), 100)

    def test_it_is_capped_however_rich_they_are(self):
        self.assertEqual(mug_takings(10_000_000, 10), MUG_CASH_CAP)

    def test_nothing_comes_off_somebody_with_nothing(self):
        self.assertEqual(mug_takings(0, 10), 0)
        self.assertEqual(mug_takings(-50, 10), 0)

    def test_it_never_takes_more_than_they_have(self):
        self.assertEqual(mug_takings(30, 10), 3)
        self.assertLessEqual(mug_takings(7, 10), 7)

    def test_a_repeat_target_is_worth_less(self):
        self.assertLess(
            mug_takings(1_000, 10, reward_multiplier=0.5),
            mug_takings(1_000, 10, reward_multiplier=1.0),
        )

    def test_an_unrated_repeat_is_worth_nothing(self):
        self.assertEqual(mug_takings(1_000, 10, reward_multiplier=0), 0)


class AftermathRuleTests(unittest.TestCase):
    def fighters(self, money=1_000):
        attacker = SimpleNamespace(money=0)
        defender = SimpleNamespace(
            money=money, health=0, hospital_until=None
        )
        return attacker, defender

    def test_leaving_costs_them_nothing_at_all(self):
        attacker, defender = self.fighters()

        result = apply_aftermath(attacker, defender, "leave")

        self.assertEqual(result.cash_stolen, 0)
        self.assertIsNone(result.hospital_until)
        self.assertEqual(defender.money, 1_000)
        self.assertIsNone(defender.hospital_until)

    def test_mugging_takes_money_and_not_liberty(self):
        attacker, defender = self.fighters()

        result = apply_aftermath(
            attacker, defender, "mug", rng=random.Random(7)
        )

        self.assertGreater(result.cash_stolen, 0)
        self.assertEqual(attacker.money, result.cash_stolen)
        self.assertEqual(defender.money, 1_000 - result.cash_stolen)
        self.assertIsNone(
            defender.hospital_until,
            "mugging also hospitalised them; the choice is exclusive",
        )

    def test_hospitalising_takes_liberty_and_not_money(self):
        attacker, defender = self.fighters()

        result = apply_aftermath(attacker, defender, "hospitalise")

        self.assertEqual(result.cash_stolen, 0)
        self.assertIsNotNone(result.hospital_until)
        self.assertIsNotNone(defender.hospital_until)
        self.assertEqual(
            defender.money,
            1_000,
            "hospitalising also robbed them; the choice is exclusive",
        )

    def test_an_unknown_choice_is_refused_rather_than_guessed(self):
        # Defaulting to anything here would take something nobody asked
        # to take.
        attacker, defender = self.fighters()

        for bad in ("", "rob", "MUG", None):
            with self.subTest(choice=bad):
                with self.assertRaises(PvpError):
                    apply_aftermath(attacker, defender, bad)

        self.assertEqual(defender.money, 1_000)

    def test_the_three_choices_are_the_whole_menu(self):
        self.assertEqual(
            set(AFTERMATH_CHOICES),
            {"leave", "mug", "hospitalise"},
        )


class FightNoLongerDecidesTests(unittest.TestCase):
    """Winning must leave the decision open, not make it."""

    def test_a_won_fight_takes_no_money_by_itself(self):
        from unittest.mock import Mock

        from game.combat.pvp import fight_player

        def fighter(identifier, **changes):
            values = dict(
                id=identifier,
                current_district="camden",
                hospital_until=None, jail_until=None,
                travel_destination=None, shift_until=None,
                health=100, max_health=100, energy=100, money=5_000,
                xp=0, level=5, strength=10, defence=10,
                speed=10, dexterity=10,
            )
            values.update(changes)
            return SimpleNamespace(**values)

        attacker = fighter(1, strength=400, defence=400, speed=400,
                           dexterity=400, health=1_000, max_health=1_000)
        defender = fighter(2)
        before = defender.money

        result = fight_player(
            attacker, defender,
            Mock(strength_bonus=0, defence_bonus=0),
            Mock(strength_bonus=0, defence_bonus=0),
            "aggressive",
            rng=random.Random(3),
        )

        self.assertTrue(result.victory)
        self.assertEqual(result.cash_stolen, 0)
        self.assertEqual(defender.money, before)
        self.assertIsNone(
            defender.hospital_until,
            "the fight hospitalised them before anybody chose to",
        )
        self.assertGreater(result.xp_reward, 0, "winning still earns XP")


class SettlingThroughTheDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "pvp.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.winner_user = create_user("winner", "w@example.com", "hash")
        create_player(self.winner_user, "Winner")
        self.loser_user = create_user("loser", "l@example.com", "hash")
        create_player(self.loser_user, "Loser")

        self.winner = self.player_id(self.winner_user)
        self.loser = self.player_id(self.loser_user)
        self.set(self.loser, money=4_000)

    def player_id(self, user_id):
        connection = sqlite3.connect(self.database_path)
        found = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return found

    def set(self, player_id, **columns):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET "
                + ", ".join(f"{key} = ?" for key in columns)
                + " WHERE id = ?",
                (*columns.values(), player_id),
            )
        connection.close()

    def read(self, player_id, column):
        connection = sqlite3.connect(self.database_path)
        value = connection.execute(
            f"SELECT {column} FROM players WHERE id = ?", (player_id,)
        ).fetchone()[0]
        connection.close()
        return value

    def record_win(self, created_at=None):
        """A won fight sitting there waiting to be settled."""
        created_at = created_at or datetime.now(timezone.utc).isoformat()
        connection = sqlite3.connect(self.database_path)
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO player_pvp_attacks (
                    attacker_id, defender_id, approach, outcome,
                    cash_stolen, xp_reward, reward_multiplier,
                    rounds_json, created_at
                )
                VALUES (?, ?, 'aggressive', 'victory', 0, 40, 1.0, '[]', ?)
                """,
                (self.winner, self.loser, created_at),
            )
            attack_id = cursor.lastrowid
        connection.close()
        return attack_id

    def settle(self, attack_id, choice):
        from database.repositories.pvp import settle_aftermath

        return settle_aftermath(
            attack_id, self.winner, choice, rng=random.Random(5)
        )

    def test_mugging_moves_money_between_the_two(self):
        attack_id = self.record_win()

        before = self.read(self.winner, "money")

        result = self.settle(attack_id, "mug")

        self.assertGreater(result.cash_stolen, 0)
        self.assertEqual(
            self.read(self.winner, "money"), before + result.cash_stolen
        )
        self.assertEqual(
            self.read(self.loser, "money"), 4_000 - result.cash_stolen
        )

    def test_hospitalising_puts_them_away_and_leaves_the_cash(self):
        attack_id = self.record_win()

        self.settle(attack_id, "hospitalise")

        self.assertIsNotNone(self.read(self.loser, "hospital_until"))
        self.assertEqual(self.read(self.loser, "money"), 4_000)

    def test_leaving_changes_nothing(self):
        attack_id = self.record_win()

        self.settle(attack_id, "leave")

        self.assertEqual(self.read(self.loser, "money"), 4_000)
        self.assertIsNone(self.read(self.loser, "hospital_until"))

    def test_a_fight_can_only_be_settled_once(self):
        """The one that matters: no mugging the same win twice."""
        attack_id = self.record_win()

        first = self.settle(attack_id, "mug")

        with self.assertRaises(PvpError):
            self.settle(attack_id, "mug")

        self.assertEqual(
            self.read(self.loser, "money"), 4_000 - first.cash_stolen
        )

    def test_you_cannot_settle_somebody_elses_fight(self):
        from database.repositories.pvp import settle_aftermath

        attack_id = self.record_win()

        with self.assertRaises(PvpError):
            settle_aftermath(attack_id, self.loser, "mug")

        self.assertEqual(self.read(self.loser, "money"), 4_000)

    def test_a_win_cannot_be_banked_and_cashed_later(self):
        stale = datetime.now(timezone.utc) - timedelta(
            seconds=AFTERMATH_WINDOW_SECONDS + 60
        )
        attack_id = self.record_win(created_at=stale.isoformat())

        with self.assertRaises(PvpError):
            self.settle(attack_id, "mug")

        self.assertEqual(self.read(self.loser, "money"), 4_000)

    def test_an_expired_fight_stops_being_pending(self):
        from database.repositories.pvp import get_pending_aftermath

        stale = datetime.now(timezone.utc) - timedelta(
            seconds=AFTERMATH_WINDOW_SECONDS + 60
        )
        self.record_win(created_at=stale.isoformat())

        self.assertIsNone(get_pending_aftermath(self.winner))

    def test_a_fresh_win_is_offered(self):
        from database.repositories.pvp import get_pending_aftermath

        attack_id = self.record_win()

        pending = get_pending_aftermath(self.winner)

        self.assertIsNotNone(pending)
        self.assertEqual(pending.attack_id, attack_id)
        self.assertEqual(pending.defender_name, "Loser")

    def test_mugging_somebody_who_spent_it_takes_nothing(self):
        attack_id = self.record_win()
        self.set(self.loser, money=0)

        result = self.settle(attack_id, "mug")

        self.assertEqual(result.cash_stolen, 0)
        self.assertEqual(self.read(self.loser, "money"), 0)


if __name__ == "__main__":
    unittest.main()
