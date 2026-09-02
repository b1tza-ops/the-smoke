"""Three places to keep money, and only one of them can be taken.

The bank in this game is free, unlimited, instant and on every page. A
safe that merely protected cash would be a capacity-limited worse bank,
so nobody would use it and a burglar would find nothing worth taking --
dead content twice over.

So the safe is the one that pays, and the one that can be robbed:

  Bank     untouchable, earns nothing
  Safe     earns interest, another player can break in
  Pockets  earns nothing, taken when you lose a fight

Most of what follows is about the protections. A mechanic where players
take money from each other is where griefing lives, and the limits are
the feature as much as the theft is.
"""

import random
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.crime.burglary import (
    BURGLARY_NERVE_COST,
    BURGLARY_TAKE_CAP,
    BURGLARY_WORTH_ROBBING,
    HOME_SECURITY,
    BurglaryError,
    odds_against,
    takings,
)
from game.housing.safe import (
    MAXIMUM_INTEREST_DAYS,
    SafeError,
    capacity_for,
    interest_earned,
)


class SafeArithmeticTests(unittest.TestCase):
    def test_a_bigger_home_holds_more(self):
        self.assertGreater(
            capacity_for("penthouse"), capacity_for("council_flat")
        )

    def test_interest_is_paid_on_what_is_kept(self):
        self.assertEqual(
            interest_earned(100_000, timedelta(days=1)), 250
        )

    def test_nothing_in_the_safe_earns_nothing(self):
        self.assertEqual(interest_earned(0, timedelta(days=30)), 0)

    def test_a_balance_too_small_to_earn_a_pound_earns_nothing(self):
        # The honest answer rather than a rounding gift.
        self.assertEqual(interest_earned(50, timedelta(days=1)), 0)

    def test_time_never_runs_backwards_into_a_payout(self):
        self.assertEqual(
            interest_earned(10_000, timedelta(days=-10)), 0
        )

    def test_a_long_absence_stops_earning(self):
        capped = interest_earned(10_000, timedelta(days=365))

        self.assertEqual(
            capped,
            interest_earned(10_000, timedelta(days=MAXIMUM_INTEREST_DAYS)),
        )

    def test_interest_never_covers_the_rent(self):
        """The safe softens the sink; it must not cancel it.

        Otherwise the top of the housing ladder pays for itself and rent
        stops being a sink at exactly the tier it was built to bite.
        """
        from game.housing import RESIDENCES
        from game.housing.service import daily_upkeep

        for home in RESIDENCES:
            rent = daily_upkeep(home)
            if not rent:
                continue
            earned = interest_earned(
                capacity_for(home.key), timedelta(days=1)
            )
            with self.subTest(home=home.key):
                self.assertLess(earned, rent)


class BurglaryArithmeticTests(unittest.TestCase):
    def test_every_home_has_a_security_rating(self):
        from game.housing import RESIDENCES

        self.assertEqual(
            set(HOME_SECURITY), {home.key for home in RESIDENCES}
        )

    def test_a_better_home_is_harder_to_get_into(self):
        self.assertLess(
            odds_against({}, "penthouse").chance,
            odds_against({}, "tent").chance,
        )

    def test_the_right_kit_helps(self):
        self.assertGreater(
            odds_against({"lockpick": 1}, "council_flat").chance,
            odds_against({}, "council_flat").chance,
        )

    def test_the_wrong_kit_does_not(self):
        # A burner phone is for a phone snatch, not a front door.
        self.assertEqual(
            odds_against({"burner_phone": 1}, "council_flat").chance,
            odds_against({}, "council_flat").chance,
        )

    def test_a_break_in_never_takes_the_lot(self):
        for balance in (500, 5_000, 50_000, 100_000):
            with self.subTest(balance=balance):
                self.assertLess(takings(balance), balance)

    def test_the_haul_is_capped(self):
        self.assertEqual(takings(10_000_000), BURGLARY_TAKE_CAP)

    def test_a_nearly_empty_safe_is_not_worth_robbing(self):
        self.assertEqual(takings(BURGLARY_WORTH_ROBBING - 1), 0)


class BurglaryThroughTheDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "safe.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.thief_user, self.thief = self.make(
            "thief", money=0, nerve=100, residence_key="council_flat"
        )
        self.victim_user, self.victim = self.make(
            "victim", money=50_000, nerve=100, residence_key="hostel"
        )

    def make(self, name, established=True, **columns):
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
            if established:
                connection.execute(
                    "UPDATE users SET created_at = '2026-01-01' "
                    "WHERE id = ?",
                    (user_id,),
                )
        player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return user_id, player_id

    def read(self, player_id, column, table="players"):
        key = "player_id" if table != "players" else "id"
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            f"SELECT {column} FROM {table} WHERE {key} = ?", (player_id,)
        ).fetchone()
        connection.close()
        return row[0] if row else None

    def stock_the_safe(self, amount=500):
        from database.repositories.safe import deposit

        return deposit(self.victim_user, amount)

    def raid(self, seed=1, victim=None):
        from database.repositories.safe import burgle

        return burgle(
            self.thief_user,
            victim if victim is not None else self.victim,
            rng=random.Random(seed),
        )

    # ------------------------------------------------------- the safe

    def test_money_moves_pocket_to_safe_and_back(self):
        from database.repositories.safe import safe_for, withdraw

        self.stock_the_safe(400)

        self.assertEqual(safe_for(self.victim_user).balance, 400)
        self.assertEqual(self.read(self.victim, "money"), 49_600)

        withdraw(self.victim_user, 150)

        self.assertEqual(safe_for(self.victim_user).balance, 250)
        self.assertEqual(self.read(self.victim, "money"), 49_750)

    def test_the_safe_will_not_hold_more_than_the_home_does(self):
        with self.assertRaises(SafeError):
            self.stock_the_safe(capacity_for("hostel") + 1)

    def test_you_cannot_put_in_what_you_are_not_carrying(self):
        self.make("pauper", money=10, residence_key="penthouse")

        from database.repositories.safe import deposit

        with self.assertRaises(SafeError):
            deposit(
                [u for u, _ in [(self.victim_user, 0)]][0], 10_000_000
            )

    def test_you_cannot_take_out_what_is_not_there(self):
        from database.repositories.safe import withdraw

        self.stock_the_safe(100)

        with self.assertRaises(SafeError):
            withdraw(self.victim_user, 500)

    def test_nothing_moves_on_a_nonsense_amount(self):
        from database.repositories.safe import deposit, withdraw

        for amount in (0, -1, -999999):
            with self.subTest(amount=amount):
                with self.assertRaises(SafeError):
                    deposit(self.victim_user, amount)
                with self.assertRaises(SafeError):
                    withdraw(self.victim_user, amount)

        self.assertEqual(self.read(self.victim, "money"), 50_000)

    def test_interest_lands_when_the_safe_is_next_touched(self):
        from database.repositories.safe import safe_for

        self.stock_the_safe(500)
        old = (
            datetime.now(timezone.utc) - timedelta(days=20)
        ).strftime("%Y-%m-%d %H:%M:%S")
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE player_safe SET settled_at = ? WHERE player_id = ?",
                (old, self.victim),
            )
        connection.close()

        state = safe_for(self.victim_user)

        self.assertEqual(state.interest_earned, 25)
        self.assertEqual(state.balance, 525)

    def test_interest_is_not_paid_twice_for_the_same_time(self):
        from database.repositories.safe import safe_for

        self.stock_the_safe(500)
        old = (
            datetime.now(timezone.utc) - timedelta(days=20)
        ).strftime("%Y-%m-%d %H:%M:%S")
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE player_safe SET settled_at = ? WHERE player_id = ?",
                (old, self.victim),
            )
        connection.close()

        first = safe_for(self.victim_user).balance
        second = safe_for(self.victim_user).balance

        self.assertEqual(first, second)

    # --------------------------------------------------- breaking in

    def test_a_successful_break_in_moves_exactly_what_it_says(self):
        self.stock_the_safe(500)

        for seed in range(30):
            result = self.raid(seed=seed)
            if result.succeeded:
                break
        else:
            self.fail("thirty attempts and never got in")

        self.assertEqual(self.read(self.thief, "money"), result.taken)
        self.assertEqual(
            self.read(self.victim, "balance", table="player_safe"),
            500 - result.taken,
        )

    def test_the_nerve_goes_whether_or_not_it_works(self):
        self.stock_the_safe(500)
        before = self.read(self.thief, "nerve")

        self.raid()

        self.assertEqual(
            self.read(self.thief, "nerve"), before - BURGLARY_NERVE_COST
        )

    def test_the_victim_is_told_either_way(self):
        self.stock_the_safe(500)

        self.raid()

        connection = sqlite3.connect(self.database_path)
        notice = connection.execute(
            "SELECT message FROM pvp_notifications WHERE player_id = ?",
            (self.victim,),
        ).fetchone()
        connection.close()

        self.assertIsNotNone(
            notice, "somebody was robbed and never found out"
        )

    # ---------------------------------------------- the protections

    def test_you_cannot_burgle_yourself(self):
        with self.assertRaises(BurglaryError):
            self.raid(victim=self.thief)

    def test_a_new_player_is_left_alone(self):
        _, fresh = self.make(
            "fresh", established=False, money=9_000,
            residence_key="council_flat",
        )
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "INSERT INTO player_safe (player_id, balance, settled_at)"
                " VALUES (?, 5000, ?)",
                (fresh, datetime.now(timezone.utc).isoformat()),
            )
        connection.close()

        with self.assertRaises(BurglaryError):
            self.raid(victim=fresh)

    def test_somebody_with_nothing_at_home_is_left_alone(self):
        """Where griefing the poor would otherwise live."""
        with self.assertRaises(BurglaryError):
            self.raid()

    def test_the_same_house_cannot_be_done_twice_in_a_row(self):
        self.stock_the_safe(500)

        self.raid()

        with self.assertRaises(BurglaryError):
            self.raid()

    def test_a_failed_attempt_still_starts_the_cooldown(self):
        """Otherwise a burglar just retries until the dice agree."""
        self.stock_the_safe(500)

        for seed in range(40):
            result = self.raid(seed=seed)
            if not result.succeeded:
                break
            # Clear the cooldown and refill the safe, or the successes
            # drain it below the floor and the raid is refused for the
            # wrong reason.
            connection = sqlite3.connect(self.database_path)
            with connection:
                connection.execute("DELETE FROM player_burglaries")
                connection.execute(
                    "UPDATE player_safe SET balance = 500"
                    " WHERE player_id = ?",
                    (self.victim,),
                )
            connection.close()
        else:
            self.fail("forty attempts and never failed")

        with self.assertRaises(BurglaryError):
            self.raid()

    def test_a_burglar_in_a_cell_stays_there(self):
        self.stock_the_safe(500)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET jail_until = '2099-01-01 00:00:00'"
                " WHERE id = ?",
                (self.thief,),
            )
        connection.close()

        with self.assertRaises(BurglaryError):
            self.raid()

    def test_a_burglar_without_the_nerve_cannot_try(self):
        self.stock_the_safe(500)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET nerve = 0 WHERE id = ?",
                (self.thief,),
            )
        connection.close()

        with self.assertRaises(BurglaryError):
            self.raid()


if __name__ == "__main__":
    unittest.main()
