from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from game.world.districts import TRAVEL_ROUTES, get_travel_route
from game.world.transport import (
    DEFAULT_TRANSPORT_KEY,
    NO_UNDERGROUND,
    TRANSPORT_MODES,
    available_modes,
    get_transport_mode,
    serves,
)
from game.world.travel import (
    InsufficientTravelFundsError,
    TransportUnavailableError,
    UnknownTransportError,
    get_active_travel,
    start_travel,
    update_travel,
)


class TransportModeTests(unittest.TestCase):
    def test_the_three_ways_across_london(self):
        self.assertEqual(
            [mode.key for mode in TRANSPORT_MODES],
            ["walk", "bus", "underground"],
        )

    def test_walking_is_always_free(self):
        walk = get_transport_mode("walk")

        for route in TRAVEL_ROUTES:
            with self.subTest(route=route.district_a):
                self.assertEqual(walk.fare(route), 0)

    def test_the_bus_is_the_fare_and_time_on_the_route(self):
        bus = get_transport_mode("bus")

        for route in TRAVEL_ROUTES:
            with self.subTest(route=route.district_a):
                self.assertEqual(bus.fare(route), route.cost)
                self.assertEqual(
                    bus.duration_seconds(route),
                    route.duration_seconds,
                )

    def test_money_buys_time_back(self):
        """Each step up costs more and takes less. That is the point."""
        route = get_travel_route("camden", "soho")
        walk, bus, tube = TRANSPORT_MODES

        self.assertLess(walk.fare(route), bus.fare(route))
        self.assertLess(bus.fare(route), tube.fare(route))
        self.assertGreater(
            walk.duration_seconds(route),
            bus.duration_seconds(route),
        )
        self.assertGreater(
            bus.duration_seconds(route),
            tube.duration_seconds(route),
        )

    def test_no_journey_is_ever_instant(self):
        for route in TRAVEL_ROUTES:
            for mode in TRANSPORT_MODES:
                with self.subTest(route=route.district_a, mode=mode.key):
                    self.assertGreaterEqual(
                        mode.duration_seconds(route),
                        60,
                    )

    def test_the_underground_does_not_reach_hackney(self):
        self.assertIn("hackney", NO_UNDERGROUND)

        modes = available_modes("brixton", "hackney")
        self.assertEqual(
            [mode.key for mode in modes],
            ["walk", "bus"],
        )

        # Either end of the route is enough to rule it out.
        self.assertFalse(
            serves(get_transport_mode("underground"), "hackney", "soho")
        )

    def test_everywhere_else_has_all_three(self):
        for route in TRAVEL_ROUTES:
            pair = {route.district_a, route.district_b}

            if pair & NO_UNDERGROUND:
                continue

            with self.subTest(route=route.district_a):
                self.assertEqual(
                    len(available_modes(*pair)),
                    3,
                )

    def test_an_unknown_mode_resolves_to_nothing(self):
        self.assertIsNone(get_transport_mode("hovercraft"))


class TravellingByModeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)

    def make_player(self, **overrides):
        values = {
            "level": 10,
            "money": 500,
            "current_district": "camden",
            "travel_destination": None,
            "travel_until": None,
            "travel_mode": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_walking_costs_nothing_and_takes_three_times_as_long(self):
        player = self.make_player()

        result = start_travel(player, "soho", "walk", now=self.now)

        self.assertEqual(result.cost, 0)
        self.assertEqual(player.money, 500)
        # Camden to Soho is five minutes on the bus.
        self.assertEqual(result.arrives_at, "2026-08-26 09:15:00")
        self.assertEqual(player.travel_mode, "walk")

    def test_the_underground_halves_it_for_double(self):
        player = self.make_player()

        result = start_travel(
            player,
            "soho",
            "underground",
            now=self.now,
        )

        self.assertEqual(result.cost, 40)
        self.assertEqual(player.money, 460)
        self.assertEqual(result.arrives_at, "2026-08-26 09:02:30")

    def test_the_bus_is_the_default(self):
        player = self.make_player()

        result = start_travel(player, "soho", now=self.now)

        self.assertEqual(result.mode_key, DEFAULT_TRANSPORT_KEY)
        self.assertEqual(result.cost, 20)
        self.assertEqual(result.arrives_at, "2026-08-26 09:05:00")

    def test_a_broke_player_can_still_walk(self):
        player = self.make_player(money=0)

        with self.assertRaises(InsufficientTravelFundsError):
            start_travel(player, "soho", "bus", now=self.now)

        result = start_travel(player, "soho", "walk", now=self.now)

        self.assertEqual(result.cost, 0)
        self.assertEqual(player.travel_destination, "soho")

    def test_the_tube_is_refused_to_hackney(self):
        player = self.make_player()

        with self.assertRaises(TransportUnavailableError):
            start_travel(player, "hackney", "underground", now=self.now)

        self.assertIsNone(player.travel_destination)
        self.assertEqual(player.money, 500)

    def test_an_unknown_mode_is_refused(self):
        player = self.make_player()

        with self.assertRaises(UnknownTransportError):
            start_travel(player, "soho", "hovercraft", now=self.now)

        self.assertIsNone(player.travel_destination)

    def test_the_journey_remembers_how_it_is_being_made(self):
        player = self.make_player()
        start_travel(player, "soho", "underground", now=self.now)

        active = get_active_travel(player, now=self.now)

        self.assertEqual(active.mode_key, "underground")
        self.assertEqual(active.mode_name, "Underground")

    def test_arriving_clears_the_mode(self):
        player = self.make_player()
        start_travel(player, "soho", "walk", now=self.now)

        arrived = update_travel(
            player,
            now=datetime(2026, 8, 26, 9, 20, tzinfo=timezone.utc),
        )

        self.assertTrue(arrived)
        self.assertEqual(player.current_district, "soho")
        self.assertIsNone(player.travel_mode)

    def test_an_old_journey_without_a_mode_reads_as_the_bus(self):
        """Journeys already in flight when this shipped have no mode."""
        player = self.make_player(
            travel_destination="soho",
            travel_until="2026-08-26 09:05:00",
            travel_mode=None,
        )

        active = get_active_travel(player, now=self.now)

        self.assertEqual(active.mode_key, "bus")


if __name__ == "__main__":
    unittest.main()
