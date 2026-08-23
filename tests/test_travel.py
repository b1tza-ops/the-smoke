from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from game.travel import (
    AlreadyTravellingError,
    DistrictLockedError,
    InsufficientTravelFundsError,
    SameDistrictError,
    TravelRestrictedError,
    get_active_travel,
    start_travel,
    update_travel,
)


class TravelTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(
            2026,
            8,
            23,
            12,
            0,
            tzinfo=timezone.utc,
        )

    def make_player(self, **overrides):
        player_data = {
            "level": 2,
            "money": 100,
            "current_district": "camden",
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
        }

        player_data.update(overrides)

        return SimpleNamespace(**player_data)

    def test_start_travel_deducts_cash_and_records_journey(self):
        player = self.make_player()

        result = start_travel(
            player,
            "brixton",
            now=self.now,
        )

        self.assertEqual(result.origin_key, "camden")
        self.assertEqual(
            result.destination_key,
            "brixton",
        )
        self.assertEqual(result.cost, 35)
        self.assertEqual(
            result.arrives_at,
            "2026-08-23 12:10:00",
        )

        self.assertEqual(player.money, 65)
        self.assertEqual(
            player.current_district,
            "camden",
        )
        self.assertEqual(
            player.travel_destination,
            "brixton",
        )
        self.assertEqual(
            player.travel_until,
            "2026-08-23 12:10:00",
        )

    def test_arrival_updates_district_and_clears_journey(self):
        player = self.make_player(
            travel_destination="brixton",
            travel_until="2026-08-23 12:10:00",
        )

        arrival_time = datetime(
            2026,
            8,
            23,
            12,
            10,
            tzinfo=timezone.utc,
        )

        arrived = update_travel(
            player,
            now=arrival_time,
        )

        self.assertTrue(arrived)
        self.assertEqual(
            player.current_district,
            "brixton",
        )
        self.assertIsNone(
            player.travel_destination
        )
        self.assertIsNone(player.travel_until)

        self.assertFalse(
            update_travel(
                player,
                now=arrival_time,
            )
        )

    def test_active_travel_reports_remaining_time(self):
        player = self.make_player(
            travel_destination="brixton",
            travel_until="2026-08-23 12:10:00",
        )

        status = get_active_travel(
            player,
            now=self.now,
        )

        self.assertIsNotNone(status)
        self.assertEqual(
            status.destination_key,
            "brixton",
        )
        self.assertEqual(
            status.remaining_seconds,
            600,
        )

    def test_insufficient_cash_does_not_start_travel(self):
        player = self.make_player(money=20)

        with self.assertRaises(
            InsufficientTravelFundsError
        ):
            start_travel(
                player,
                "brixton",
                now=self.now,
            )

        self.assertEqual(player.money, 20)
        self.assertIsNone(
            player.travel_destination
        )
        self.assertIsNone(player.travel_until)

    def test_locked_district_rejects_low_level_player(self):
        player = self.make_player(level=1)

        with self.assertRaises(
            DistrictLockedError
        ):
            start_travel(
                player,
                "soho",
                now=self.now,
            )

        self.assertEqual(player.money, 100)
        self.assertIsNone(
            player.travel_destination
        )

    def test_player_cannot_travel_to_current_district(self):
        player = self.make_player()

        with self.assertRaises(
            SameDistrictError
        ):
            start_travel(
                player,
                "camden",
                now=self.now,
            )

        self.assertEqual(player.money, 100)

    def test_player_cannot_start_second_journey(self):
        player = self.make_player(
            travel_destination="brixton",
            travel_until="2026-08-23 12:10:00",
        )

        with self.assertRaises(
            AlreadyTravellingError
        ):
            start_travel(
                player,
                "soho",
                now=self.now,
            )

        self.assertEqual(player.money, 100)
        self.assertEqual(
            player.travel_destination,
            "brixton",
        )

    def test_jail_prevents_travel(self):
        player = self.make_player(
            jail_until="2026-08-23 12:05:00",
        )

        with self.assertRaises(
            TravelRestrictedError
        ):
            start_travel(
                player,
                "brixton",
                now=self.now,
            )

        self.assertEqual(player.money, 100)
        self.assertIsNone(
            player.travel_destination
        )


if __name__ == "__main__":
    unittest.main()