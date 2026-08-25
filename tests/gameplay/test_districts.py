from datetime import datetime, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from game.world.districts import (
    DISTRICTS,
    DISTRICTS_BY_KEY,
    TRAVEL_ROUTES,
    DistrictDefinition,
    TravelRoute,
    get_travel_route,
    validate_catalogue,
)
from game.world.travel import (
    DistrictLockedError,
    start_travel,
    update_travel,
)


class DistrictCatalogueTests(unittest.TestCase):
    def test_london_has_five_districts(self):
        self.assertEqual(len(DISTRICTS), 5)
        self.assertEqual(
            [district.key for district in DISTRICTS],
            [
                "camden",
                "brixton",
                "soho",
                "shoreditch",
                "hackney",
            ],
        )

    def test_east_london_unlocks_later(self):
        self.assertEqual(
            DISTRICTS_BY_KEY["shoreditch"].minimum_level,
            5,
        )
        self.assertEqual(
            DISTRICTS_BY_KEY["hackney"].minimum_level,
            7,
        )

    def test_every_pair_of_districts_has_a_route(self):
        keys = [district.key for district in DISTRICTS]

        for origin in keys:
            for destination in keys:
                if origin == destination:
                    continue

                with self.subTest(route=(origin, destination)):
                    route = get_travel_route(origin, destination)
                    self.assertGreater(route.duration_seconds, 0)
                    self.assertGreaterEqual(route.cost, 0)

    def test_the_route_table_is_a_complete_graph(self):
        districts = len(DISTRICTS)

        self.assertEqual(
            len(TRAVEL_ROUTES),
            districts * (districts - 1) // 2,
        )

    def test_a_route_costs_the_same_in_both_directions(self):
        for route in TRAVEL_ROUTES:
            with self.subTest(route=route.district_a):
                there = get_travel_route(
                    route.district_a,
                    route.district_b,
                )
                back = get_travel_route(
                    route.district_b,
                    route.district_a,
                )
                self.assertEqual(there, back)

    def test_neighbouring_districts_are_the_shortest_hops(self):
        shortest = min(
            route.duration_seconds
            for route in TRAVEL_ROUTES
        )

        # Shoreditch and Hackney are next to each other, and Brixton is
        # across the river from both.
        self.assertEqual(
            get_travel_route("shoreditch", "hackney").duration_seconds,
            shortest,
        )
        self.assertGreater(
            get_travel_route("brixton", "hackney").duration_seconds,
            get_travel_route("camden", "hackney").duration_seconds,
        )


class CatalogueValidationTests(unittest.TestCase):
    """The catalogue checks itself at import; these prove it bites."""

    def patched(self, districts=None, routes=None):
        return patch.multiple(
            "game.world.districts",
            DISTRICTS=districts or DISTRICTS,
            TRAVEL_ROUTES=routes or TRAVEL_ROUTES,
            DISTRICTS_BY_KEY={
                district.key: district
                for district in (districts or DISTRICTS)
            },
        )

    def test_a_missing_route_is_rejected(self):
        with self.patched(routes=TRAVEL_ROUTES[:-1]):
            with self.assertRaisesRegex(ValueError, "No route between"):
                validate_catalogue()

    def test_an_unknown_district_in_a_route_is_rejected(self):
        broken = TRAVEL_ROUTES + (
            TravelRoute(
                district_a="camden",
                district_b="peckham",
                cost=10,
                duration_seconds=60,
            ),
        )

        with self.patched(routes=broken):
            with self.assertRaisesRegex(ValueError, "unknown district"):
                validate_catalogue()

    def test_a_route_to_itself_is_rejected(self):
        broken = TRAVEL_ROUTES + (
            TravelRoute(
                district_a="camden",
                district_b="camden",
                cost=10,
                duration_seconds=60,
            ),
        )

        with self.patched(routes=broken):
            with self.assertRaisesRegex(ValueError, "leads to itself"):
                validate_catalogue()

    def test_a_duplicated_route_is_rejected(self):
        broken = TRAVEL_ROUTES + (TRAVEL_ROUTES[0],)

        with self.patched(routes=broken):
            with self.assertRaisesRegex(ValueError, "defined twice"):
                validate_catalogue()

    def test_a_free_instant_route_is_rejected(self):
        broken = TRAVEL_ROUTES[:-1] + (
            TravelRoute(
                district_a="shoreditch",
                district_b="hackney",
                cost=20,
                duration_seconds=0,
            ),
        )

        with self.patched(routes=broken):
            with self.assertRaisesRegex(ValueError, "impossible fare"):
                validate_catalogue()

    def test_duplicate_district_keys_are_rejected(self):
        broken = DISTRICTS + (
            DistrictDefinition(
                key="camden",
                name="Camden Again",
                description="A second Camden.",
                minimum_level=1,
            ),
        )

        with self.patched(districts=broken):
            with self.assertRaisesRegex(ValueError, "must be unique"):
                validate_catalogue()


class EastLondonTravelTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    def make_player(self, **overrides):
        values = {
            "level": 7,
            "money": 500,
            "current_district": "camden",
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def test_a_level_seven_player_can_reach_hackney(self):
        player = self.make_player()

        result = start_travel(player, "hackney", now=self.now)

        self.assertEqual(result.cost, 35)
        self.assertEqual(result.arrives_at, "2026-08-25 12:09:00")
        self.assertEqual(player.money, 465)

        arrived = update_travel(
            player,
            now=datetime(2026, 8, 25, 12, 9, tzinfo=timezone.utc),
        )

        self.assertTrue(arrived)
        self.assertEqual(player.current_district, "hackney")
        self.assertIsNone(player.travel_destination)

    def test_shoreditch_is_locked_below_level_five(self):
        player = self.make_player(level=4)

        with self.assertRaises(DistrictLockedError):
            start_travel(player, "shoreditch", now=self.now)

        self.assertEqual(player.money, 500)
        self.assertIsNone(player.travel_destination)

    def test_hackney_is_locked_below_level_seven(self):
        player = self.make_player(level=6)

        with self.assertRaises(DistrictLockedError):
            start_travel(player, "hackney", now=self.now)

    def test_shoreditch_opens_at_level_five(self):
        player = self.make_player(level=5, current_district="soho")

        result = start_travel(player, "shoreditch", now=self.now)

        self.assertEqual(result.cost, 25)
        self.assertEqual(result.arrives_at, "2026-08-25 12:06:00")


if __name__ == "__main__":
    unittest.main()
