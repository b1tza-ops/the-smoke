import unittest
from datetime import datetime, timedelta, timezone

from game.player.regeneration import regenerate_resource


class RegenerationTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(
            2026, 8, 21, 20, 0, 0,
            tzinfo=timezone.utc
        )

    def test_energy_regenerates_completed_ticks(self):
        energy, timestamp = regenerate_resource(
            current_value=20,
            maximum_value=100,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.start + timedelta(minutes=35)
        )

        self.assertEqual(energy, 35)
        self.assertEqual(timestamp, "2026-08-21 20:30:00")

    def test_nerve_regenerates_completed_ticks(self):
        nerve, timestamp = regenerate_resource(
            current_value=5,
            maximum_value=20,
            last_update="2026-08-21 20:00:00",
            points_per_tick=1,
            tick_seconds=300,
            now=self.start + timedelta(minutes=35)
        )

        self.assertEqual(nerve, 12)
        self.assertEqual(timestamp, "2026-08-21 20:35:00")

    def test_resource_never_exceeds_maximum(self):
        energy, timestamp = regenerate_resource(
            current_value=95,
            maximum_value=100,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.start + timedelta(hours=2)
        )

        self.assertEqual(energy, 100)
        self.assertEqual(timestamp, "2026-08-21 22:00:00")

    def test_repeated_loading_does_not_duplicate_regeneration(self):
        now = self.start + timedelta(minutes=35)

        energy, timestamp = regenerate_resource(
            current_value=0,
            maximum_value=100,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=now
        )

        energy_again, timestamp_again = regenerate_resource(
            current_value=energy,
            maximum_value=100,
            last_update=timestamp,
            points_per_tick=5,
            tick_seconds=600,
            now=now
        )

        self.assertEqual(energy, 15)
        self.assertEqual(energy_again, 15)
        self.assertEqual(timestamp_again, timestamp)


if __name__ == "__main__":
    unittest.main()