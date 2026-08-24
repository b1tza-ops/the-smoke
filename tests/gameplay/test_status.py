import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from game.player.status import (
    MAX_WANTED_LEVEL,
    add_wanted,
    decay_wanted_level,
    get_active_restriction,
    send_to_hospital,
    send_to_jail,
    update_player_status,
)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026,
            8,
            22,
            12,
            25,
            tzinfo=timezone.utc,
        )

    def make_player(
        self,
        wanted_level=0,
        last_wanted_update="2026-08-22 12:00:00",
        jail_until=None,
        hospital_until=None,
    ):
        return SimpleNamespace(
            wanted_level=wanted_level,
            last_wanted_update=last_wanted_update,
            jail_until=jail_until,
            hospital_until=hospital_until,
        )

    def test_wanted_level_decays_for_completed_ticks(self):
        wanted_level, last_update = decay_wanted_level(
            current_level=5,
            last_update="2026-08-22 12:00:00",
            now=self.now,
        )

        self.assertEqual(wanted_level, 3)
        self.assertEqual(
            last_update,
            "2026-08-22 12:20:00",
        )

    def test_wanted_level_never_falls_below_zero(self):
        wanted_level, last_update = decay_wanted_level(
            current_level=1,
            last_update="2026-08-22 12:00:00",
            now=self.now,
        )

        self.assertEqual(wanted_level, 0)
        self.assertEqual(
            last_update,
            "2026-08-22 12:25:00",
        )

    def test_expired_restrictions_clear_automatically(self):
        player = self.make_player(
            jail_until="2026-08-22 12:20:00",
            hospital_until="2026-08-22 12:24:00",
        )

        result = update_player_status(
            player,
            now=self.now,
        )

        self.assertIsNone(player.jail_until)
        self.assertIsNone(player.hospital_until)
        self.assertTrue(result.released_from_jail)
        self.assertTrue(result.discharged_from_hospital)

    def test_active_hospital_restriction_is_returned(self):
        player = self.make_player(
            hospital_until="2026-08-22 12:30:00",
        )

        restriction = get_active_restriction(
            player,
            now=self.now,
        )

        self.assertEqual(restriction.kind, "hospital")
        self.assertEqual(restriction.remaining_seconds, 300)

    def test_jail_time_can_be_extended(self):
        player = self.make_player(
            jail_until="2026-08-22 12:30:00",
        )

        jail_until = send_to_jail(
            player,
            duration_seconds=120,
            now=self.now,
        )

        self.assertEqual(
            jail_until,
            "2026-08-22 12:32:00",
        )

    def test_hospital_time_starts_from_now(self):
        player = self.make_player()

        hospital_until = send_to_hospital(
            player,
            duration_seconds=300,
            now=self.now,
        )

        self.assertEqual(
            hospital_until,
            "2026-08-22 12:30:00",
        )

    def test_discharge_from_hospital_fully_heals(self):
        player = SimpleNamespace(
            wanted_level=0,
            last_wanted_update="2026-08-22 12:00:00",
            jail_until=None,
            hospital_until="2026-08-22 12:10:00",
            health=40,
            max_health=100,
            last_health_update="2026-08-22 12:05:00",
        )

        status_update = update_player_status(player, now=self.now)

        self.assertTrue(status_update.discharged_from_hospital)
        self.assertEqual(player.health, 100)
        self.assertEqual(
            player.last_health_update,
            "2026-08-22 12:25:00",
        )

    def test_still_hospitalised_players_are_not_healed(self):
        player = SimpleNamespace(
            wanted_level=0,
            last_wanted_update="2026-08-22 12:00:00",
            jail_until=None,
            hospital_until="2026-08-22 13:00:00",
            health=40,
            max_health=100,
            last_health_update="2026-08-22 12:05:00",
        )

        status_update = update_player_status(player, now=self.now)

        self.assertFalse(status_update.discharged_from_hospital)
        self.assertEqual(player.health, 40)

    def test_wanted_level_is_capped(self):
        player = self.make_player(wanted_level=98)

        new_level = add_wanted(
            player,
            amount=10,
            now=self.now,
        )

        self.assertEqual(new_level, MAX_WANTED_LEVEL)

    def test_negative_values_are_rejected(self):
        player = self.make_player()

        with self.assertRaises(ValueError):
            add_wanted(player, -1, now=self.now)

        with self.assertRaises(ValueError):
            send_to_jail(player, 0, now=self.now)

        with self.assertRaises(ValueError):
            send_to_hospital(player, -10, now=self.now)


if __name__ == "__main__":
    unittest.main()