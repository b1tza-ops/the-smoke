import unittest
from datetime import datetime, timedelta, timezone

from types import SimpleNamespace

from game.player.regeneration import (
    player_regeneration_forecast,
    regenerate_resource,
    regeneration_forecast,
)


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


class RegenerationForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026, 8, 21, 20, 5, 0,
            tzinfo=timezone.utc
        )

    def test_counts_down_to_the_next_tick_and_to_full(self):
        forecast = regeneration_forecast(
            current_value=100,
            maximum_value=150,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now,
        )

        self.assertFalse(forecast["is_full"])
        self.assertEqual(forecast["ticks_needed"], 10)
        self.assertEqual(forecast["seconds_to_next_tick"], 300)
        # Five minutes to the next tick, then nine more full ticks.
        self.assertEqual(forecast["seconds_to_full"], 300 + 9 * 600)

    def test_a_partial_tick_counts_towards_the_next_one(self):
        # `regenerate_resource` leaves `last_update` on the last
        # completed boundary, so this is five minutes into a tick.
        forecast = regeneration_forecast(
            current_value=145,
            maximum_value=150,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now + timedelta(minutes=20),
        )

        self.assertEqual(forecast["seconds_to_next_tick"], 300)
        self.assertEqual(forecast["seconds_to_full"], 300)

    def test_a_full_resource_forecasts_nothing(self):
        forecast = regeneration_forecast(
            current_value=150,
            maximum_value=150,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now,
        )

        self.assertTrue(forecast["is_full"])
        self.assertEqual(forecast["seconds_to_next_tick"], 0)
        self.assertEqual(forecast["seconds_to_full"], 0)

    def test_a_final_partial_tick_still_counts_as_one(self):
        forecast = regeneration_forecast(
            current_value=148,
            maximum_value=150,
            last_update="2026-08-21 20:00:00",
            points_per_tick=5,
            tick_seconds=600,
            now=self.now,
        )

        self.assertEqual(forecast["ticks_needed"], 1)
        self.assertEqual(forecast["seconds_to_full"], 300)


class PlayerForecastTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026, 8, 21, 20, 5, 0,
            tzinfo=timezone.utc
        )

    def make_player(self, **overrides):
        values = {
            "health": 60,
            "max_health": 100,
            "last_health_update": "2026-08-21 20:00:00",
            "energy": 100,
            "max_energy": 150,
            "last_energy_update": "2026-08-21 20:00:00",
            "nerve": 20,
            "max_nerve": 20,
            "last_nerve_update": "2026-08-21 20:00:00",
            "happiness": 0,
            "max_happiness": 100,
            "last_happiness_update": "2026-08-21 20:00:00",
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_each_regenerating_meter_has_a_forecast(self):
        player = self.make_player()

        for resource in ("health", "energy", "nerve", "happiness"):
            with self.subTest(resource=resource):
                self.assertIsNotNone(
                    player_regeneration_forecast(
                        player,
                        resource,
                        now=self.now,
                    )
                )

    def test_the_energy_forecast_uses_the_energy_rate(self):
        forecast = player_regeneration_forecast(
            self.make_player(),
            "energy",
            now=self.now,
        )

        self.assertEqual(forecast["points_per_tick"], 5)
        self.assertEqual(forecast["tick_seconds"], 600)
        self.assertEqual(forecast["seconds_to_next_tick"], 300)

    def test_a_full_meter_reports_itself_full(self):
        forecast = player_regeneration_forecast(
            self.make_player(),
            "nerve",
            now=self.now,
        )

        self.assertTrue(forecast["is_full"])

    def test_experience_has_no_forecast(self):
        self.assertIsNone(
            player_regeneration_forecast(
                self.make_player(),
                "xp",
                now=self.now,
            )
        )

    def test_a_player_missing_a_timestamp_has_no_forecast(self):
        # Some code paths build a partial player; the HUD must not blow
        # up on one.
        player = self.make_player(last_energy_update=None)

        self.assertIsNone(
            player_regeneration_forecast(player, "energy", now=self.now)
        )

    def test_health_has_no_forecast_while_hospitalised(self):
        player = self.make_player(
            hospital_until="2026-08-21 21:00:00",
        )

        self.assertIsNone(
            player_regeneration_forecast(player, "health", now=self.now)
        )
        # Only health is frozen; the rest keep ticking.
        self.assertIsNotNone(
            player_regeneration_forecast(player, "energy", now=self.now)
        )

    def test_health_forecasts_again_after_discharge(self):
        player = self.make_player(
            hospital_until="2026-08-21 20:01:00",
        )

        self.assertIsNotNone(
            player_regeneration_forecast(player, "health", now=self.now)
        )


if __name__ == "__main__":
    unittest.main()