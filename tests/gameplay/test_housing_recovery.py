"""What a home is actually for.

The residence ladder shipped with recovery, storage, safe and garage
figures on every rung and not one of them was read by anything. A
player could pay £85,000 for a penthouse and get a different photograph.

These hold the half that is now wired up: where you live, and what you
have had fitted, shortens the energy and nerve ticks. Storage, safe
capacity and garage space are still only numbers on a page -- that is
recorded in the guide rather than pretended about here.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.housing import install_facility, move_house
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.users import create_user
from game.housing import get_residence
from game.housing.service import faster_tick, recovery_bonus
from game.player import Player
from game.player.regeneration import (
    ENERGY_TICK_SECONDS,
    NERVE_TICK_SECONDS,
)


class RecoveryBonusTests(unittest.TestCase):
    def test_a_bonus_shortens_the_tick(self):
        # 40% faster means the same points arrive in 100/140 of the time.
        self.assertEqual(faster_tick(600, 40), 429)
        self.assertEqual(faster_tick(600, 100), 300)

    def test_no_bonus_leaves_the_tick_alone(self):
        self.assertEqual(faster_tick(600, 0), 600)
        self.assertEqual(faster_tick(600, -10), 600)

    def test_a_tick_never_collapses_to_nothing(self):
        self.assertEqual(faster_tick(1, 100_000), 1)

    def test_the_ladder_gets_steadily_faster(self):
        from game.housing import RESIDENCES

        ticks = [
            faster_tick(
                ENERGY_TICK_SECONDS,
                recovery_bonus(home, (), "energy"),
            )
            for home in RESIDENCES
        ]

        self.assertEqual(
            ticks,
            sorted(ticks, reverse=True),
            "a dearer home must never refill energy more slowly",
        )

    def test_fittings_stack_on_top_of_the_home(self):
        penthouse = get_residence("penthouse")

        self.assertEqual(
            recovery_bonus(penthouse, (), "energy"),
            40,
        )
        self.assertEqual(
            recovery_bonus(penthouse, ("hot_tub",), "energy"),
            45,
        )
        # The sauna is nerve, so it must not touch energy.
        self.assertEqual(
            recovery_bonus(penthouse, ("sauna",), "energy"),
            40,
        )
        self.assertEqual(
            recovery_bonus(penthouse, ("sauna",), "nerve"),
            40,
        )


class RecoveryThroughTheLoaderTests(unittest.TestCase):
    """The bonus has to survive the round trip, not just the arithmetic."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "recovery.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

    def make_player(self, name, money=200_000):
        user_id = create_user(name, f"{name}@example.com", "hash")
        create_player(user_id, name)
        self.set(user_id, money=money)
        return user_id

    def set(self, user_id, **columns):
        assignments = ", ".join(f"{key} = ?" for key in columns)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                f"UPDATE players SET {assignments} WHERE user_id = ?",
                (*columns.values(), user_id),
            )
        connection.close()

    def drain_and_wind_back(self, user_id, hours):
        moved = datetime.now(timezone.utc) - timedelta(hours=hours)
        stamp = moved.strftime("%Y-%m-%d %H:%M:%S")
        self.set(
            user_id,
            energy=0,
            nerve=0,
            last_energy_update=stamp,
            last_nerve_update=stamp,
        )

    def energy_after(self, user_id, hours):
        self.drain_and_wind_back(user_id, hours)
        return Player(*get_player_by_user_id(user_id)).energy

    def test_a_penthouse_refills_faster_than_a_tent(self):
        rough = self.make_player("sleeper")
        rich = self.make_player("owner")
        move_house(rich, "penthouse")

        # One hour of the same wall clock for both.
        in_a_tent = self.energy_after(rough, 1)
        in_a_penthouse = self.energy_after(rich, 1)

        self.assertGreater(
            in_a_penthouse,
            in_a_tent,
            "the penthouse is 40% faster and recovered no more energy",
        )
        # 3600s at 600s a tick is 6 ticks; at 429s it is 8.
        self.assertEqual(in_a_tent, 30)
        self.assertEqual(in_a_penthouse, 40)

    def test_a_hot_tub_adds_to_the_house_it_is_in(self):
        plain = self.make_player("dry")
        soaked = self.make_player("wet")
        for user_id in (plain, soaked):
            move_house(user_id, "council_house")
        install_facility(soaked, "hot_tub")

        self.assertGreater(
            self.energy_after(soaked, 1),
            self.energy_after(plain, 1),
            "the hot tub is fitted and changed nothing",
        )

    def test_a_sauna_speeds_nerve_and_leaves_energy_alone(self):
        user_id = self.make_player("steamed")
        move_house(user_id, "council_house")

        without = self.energy_after(user_id, 1)
        install_facility(user_id, "sauna")
        with_sauna = self.energy_after(user_id, 1)

        self.assertEqual(
            with_sauna,
            without,
            "the sauna is a nerve fitting and moved energy",
        )

    def test_moving_house_changes_the_rate_immediately(self):
        user_id = self.make_player("mover")

        before = self.energy_after(user_id, 1)
        move_house(user_id, "penthouse")
        after = self.energy_after(user_id, 1)

        self.assertGreater(after, before)

    def test_a_full_bar_is_still_a_full_bar(self):
        # The bonus must not push a player past their maximum.
        user_id = self.make_player("rested")
        move_house(user_id, "penthouse")
        self.drain_and_wind_back(user_id, 48)

        player = Player(*get_player_by_user_id(user_id))

        self.assertEqual(player.energy, player.max_energy)
        self.assertEqual(player.nerve, player.max_nerve)


if __name__ == "__main__":
    unittest.main()
