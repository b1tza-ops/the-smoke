"""Cars, and the price of being seen in one.

A vehicle is the third thing money buys that keeps paying: the gym
sells stats, housing sells recovery, and a car sells *time* -- the
minutes otherwise spent on a bus, which is the only resource in this
game that never regenerates.

The reason it is not simply a better Underground is the police. Driving
is the one way across London that can be stopped, and how likely that is
depends on how much the car shows off. Most of what follows is about
that trade, and about the garage, which is the first thing to make the
figure on the property page mean anything.
"""

import random
import sqlite3
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from pathlib import Path

from database.core.setup import create_tables
from game.vehicles.definitions import VEHICLES, VEHICLES_BY_KEY, get_vehicle
from game.vehicles.service import (
    DRIVE_KEY,
    MAXIMUM_STOP_CHANCE,
    PULLED_OVER_SECONDS,
    RESALE_RATE,
    VehicleError,
    driving_mode,
    garage_capacity,
    garage_room,
    resale_value,
    stop_chance,
    validate_purchase,
)


class ForecourtTests(unittest.TestCase):
    """The catalogue itself, before anybody owns one."""

    def test_the_ladder_climbs_in_one_direction(self):
        """Dearer is faster, all the way up.

        A rung that costs more and does less is a trap for whoever
        cannot read the table, and there is no reason to build one.
        """
        for cheaper, dearer in zip(VEHICLES, VEHICLES[1:]):
            with self.subTest(rung=dearer.key):
                self.assertGreater(dearer.price, cheaper.price)
                self.assertLess(
                    dearer.duration_multiplier,
                    cheaper.duration_multiplier,
                )

    def test_speed_is_paid_for_in_attention(self):
        """The whole design in one assertion.

        If the quickest car were also the most discreet there would be
        no decision to make once you could afford it.
        """
        for cheaper, dearer in zip(VEHICLES, VEHICLES[1:]):
            with self.subTest(rung=dearer.key):
                self.assertGreaterEqual(
                    dearer.showiness, cheaper.showiness
                )

    def test_the_bicycle_is_slower_than_the_bus(self):
        # Otherwise the free option beats the paid one and the bus
        # stops being a thing anybody ever chooses.
        self.assertGreater(
            VEHICLES_BY_KEY["bicycle"].duration_multiplier, 1.0
        )

    def test_something_beats_the_underground_everywhere(self):
        """The tube is 0.5 and does not run to Hackney.

        A forecourt where nothing beat it would be selling nothing.
        """
        self.assertTrue(any(
            vehicle.duration_multiplier < 0.5 for vehicle in VEHICLES
        ))

    def test_the_first_two_rungs_are_reachable_early(self):
        # A car gated entirely behind the late game is content most
        # players never see.
        self.assertLessEqual(VEHICLES[0].minimum_level, 1)
        self.assertLessEqual(VEHICLES[1].price, 2_000)


class BeingStoppedTests(unittest.TestCase):
    def test_a_clean_player_is_never_stopped(self):
        for vehicle in VEHICLES:
            with self.subTest(vehicle=vehicle.key):
                self.assertEqual(stop_chance(vehicle, 0), 0)

    def test_a_bicycle_is_invisible_at_any_heat(self):
        self.assertEqual(
            stop_chance(VEHICLES_BY_KEY["bicycle"], 100), 0
        )

    def test_the_loudest_car_at_full_heat_is_still_a_coin_toss(self):
        """And the cap is the number the arithmetic actually reaches.

        A ceiling nothing can touch is a lie in the source: it reads
        like a guard and guards nothing.
        """
        worst = stop_chance(VEHICLES_BY_KEY["sable"], 100)

        self.assertEqual(worst, MAXIMUM_STOP_CHANCE)

    def test_no_vehicle_on_the_forecourt_beats_the_cap(self):
        for vehicle in VEHICLES:
            with self.subTest(vehicle=vehicle.key):
                self.assertLessEqual(
                    stop_chance(vehicle, 100), MAXIMUM_STOP_CHANCE
                )

    def test_heat_and_showiness_both_move_it(self):
        sable = VEHICLES_BY_KEY["sable"]
        moped = VEHICLES_BY_KEY["moped"]

        self.assertGreater(
            stop_chance(sable, 50), stop_chance(sable, 10)
        )
        self.assertGreater(
            stop_chance(sable, 50), stop_chance(moped, 50)
        )

    def test_nonsense_heat_never_becomes_a_negative_chance(self):
        sable = VEHICLES_BY_KEY["sable"]

        self.assertEqual(stop_chance(sable, -40), 0)
        self.assertEqual(stop_chance(sable, 5_000), MAXIMUM_STOP_CHANCE)
        self.assertEqual(stop_chance(None, 100), 0)


class DrivingModeTests(unittest.TestCase):
    def test_the_mode_is_built_from_the_car(self):
        sable = VEHICLES_BY_KEY["sable"]
        mode = driving_mode(sable)

        self.assertEqual(mode.key, DRIVE_KEY)
        self.assertIn(sable.name, mode.name)
        self.assertEqual(
            mode.duration_multiplier, sable.duration_multiplier
        )

    def test_there_is_no_driving_without_a_car(self):
        with self.assertRaises(VehicleError):
            driving_mode(None)

    def test_a_journey_is_never_instant(self):
        """TransportMode floors every journey at a minute.

        The quickest car on the shortest route must still take time, or
        travel stops being a cost at the top of the game.
        """
        route = SimpleNamespace(cost=20, duration_seconds=300)

        for vehicle in VEHICLES:
            with self.subTest(vehicle=vehicle.key):
                self.assertGreaterEqual(
                    driving_mode(vehicle).duration_seconds(route), 60
                )


class GarageCapacityTests(unittest.TestCase):
    def test_the_bottom_of_the_housing_ladder_has_nowhere_to_park(self):
        self.assertEqual(garage_capacity("tent"), 0)
        self.assertEqual(garage_capacity("hostel"), 0)

    def test_a_van_is_the_cheapest_address_with_a_garage(self):
        self.assertGreater(garage_capacity("van"), 0)

    def test_an_unknown_address_holds_nothing(self):
        self.assertEqual(garage_capacity("houseboat"), 0)

    def test_room_never_goes_negative(self):
        self.assertEqual(garage_room("van", 5), 0)
        self.assertEqual(garage_room("penthouse", 1), 2)

    def test_the_forecourt_buys_back_at_half(self):
        for vehicle in VEHICLES:
            with self.subTest(vehicle=vehicle.key):
                self.assertEqual(
                    resale_value(vehicle),
                    int(vehicle.price * RESALE_RATE),
                )
                self.assertLess(resale_value(vehicle), vehicle.price)


class GarageTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "garage.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.user, self.player = self.make(
            "driver",
            money=500_000,
            level=20,
            residence_key="modern_house",
            current_district="brixton",
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
                + " WHERE user_id = ?",
                (*columns.values(), user_id),
            )
        player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        connection.close()
        return user_id, player_id

    def set(self, **columns):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET "
                + ", ".join(f"{key} = ?" for key in columns)
                + " WHERE id = ?",
                (*columns.values(), self.player),
            )
        connection.close()

    def money(self):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(
            "SELECT money FROM players WHERE id = ?", (self.player,)
        ).fetchone()
        connection.close()
        return row[0]

    def rows(self):
        connection = sqlite3.connect(self.database_path)
        rows = connection.execute(
            "SELECT id, vehicle_key, is_active FROM player_vehicles "
            "WHERE player_id = ? ORDER BY id",
            (self.player,),
        ).fetchall()
        connection.close()
        return rows

    def buy(self, key="hatchback"):
        from database.repositories.vehicles import buy_vehicle

        return buy_vehicle(self.user, key)

    # ---------------------------------------------------------- buying

    def test_buying_takes_the_money_and_parks_the_car(self):
        self.buy("hatchback")

        self.assertEqual(
            self.money(), 500_000 - VEHICLES_BY_KEY["hatchback"].price
        )
        self.assertEqual(len(self.rows()), 1)

    def test_the_first_car_is_the_one_you_drive(self):
        from database.repositories.vehicles import active_vehicle

        self.buy("hatchback")

        self.assertEqual(active_vehicle(self.player).key, "hatchback")

    def test_the_second_car_does_not_take_over_the_drive(self):
        from database.repositories.vehicles import active_vehicle

        self.buy("hatchback")
        self.buy("estate")

        self.assertEqual(active_vehicle(self.player).key, "hatchback")

    def test_a_car_above_your_level_is_refused(self):
        self.set(level=2)

        with self.assertRaises(VehicleError):
            self.buy("sable")

        self.assertEqual(self.money(), 500_000)

    def test_a_car_you_cannot_afford_is_refused(self):
        self.set(money=100)

        with self.assertRaises(VehicleError):
            self.buy("hatchback")

        self.assertEqual(self.rows(), [])

    def test_nowhere_to_park_means_no_sale(self):
        """The garage figure on the property page, finally load-bearing."""
        self.set(residence_key="hostel")

        with self.assertRaises(VehicleError):
            self.buy("hatchback")

        self.assertEqual(self.money(), 500_000)

    def test_a_full_garage_means_no_sale(self):
        self.set(residence_key="van")
        self.buy("hatchback")

        with self.assertRaises(VehicleError):
            self.buy("estate")

        self.assertEqual(len(self.rows()), 1)

    def test_money_only_changes_hands_on_the_forecourt(self):
        self.set(current_district="camden")

        with self.assertRaises(VehicleError):
            self.buy("hatchback")

        self.assertEqual(self.money(), 500_000)

    def test_you_cannot_buy_a_car_from_a_moving_bus(self):
        self.set(travel_destination="soho")

        with self.assertRaises(VehicleError):
            self.buy("hatchback")

    def test_a_model_nobody_sells_is_refused(self):
        with self.assertRaises(VehicleError):
            self.buy("hovercraft")

    # --------------------------------------------------------- selling

    def test_selling_returns_half_and_empties_the_space(self):
        from database.repositories.vehicles import sell_vehicle

        self.buy("estate")
        owned_id = self.rows()[0][0]
        spent = 500_000 - self.money()

        sold, paid = sell_vehicle(self.user, owned_id)

        self.assertEqual(sold.key, "estate")
        self.assertEqual(paid, resale_value(VEHICLES_BY_KEY["estate"]))
        self.assertEqual(self.money(), 500_000 - spent + paid)
        self.assertEqual(self.rows(), [])

    def test_selling_the_same_car_twice_pays_once(self):
        """The refresh case, which is how a resale gets paid twice."""
        from database.repositories.vehicles import sell_vehicle

        self.buy("estate")
        owned_id = self.rows()[0][0]
        sell_vehicle(self.user, owned_id)
        banked = self.money()

        with self.assertRaises(VehicleError):
            sell_vehicle(self.user, owned_id)

        self.assertEqual(self.money(), banked)

    def test_you_cannot_sell_somebody_elses_car(self):
        from database.repositories.vehicles import sell_vehicle

        other_user, _ = self.make(
            "rival", money=100_000, level=20,
            residence_key="modern_house", current_district="brixton",
        )
        self.buy("estate")
        mine = self.rows()[0][0]

        with self.assertRaises(VehicleError):
            sell_vehicle(other_user, mine)

        self.assertEqual(len(self.rows()), 1)

    def test_selling_what_you_were_driving_promotes_the_next_one(self):
        """Otherwise the travel page silently loses its drive option."""
        from database.repositories.vehicles import (
            active_vehicle,
            sell_vehicle,
        )

        self.buy("hatchback")
        self.buy("estate")
        driving = self.rows()[0][0]

        sell_vehicle(self.user, driving)

        self.assertEqual(active_vehicle(self.player).key, "estate")

    def test_selling_the_last_car_leaves_nothing_to_drive(self):
        from database.repositories.vehicles import (
            active_vehicle,
            sell_vehicle,
        )

        self.buy("hatchback")
        sell_vehicle(self.user, self.rows()[0][0])

        self.assertIsNone(active_vehicle(self.player))

    # -------------------------------------------------------- choosing

    def test_choosing_which_one_you_drive(self):
        from database.repositories.vehicles import (
            active_vehicle,
            set_active,
        )

        self.buy("hatchback")
        self.buy("estate")
        second = self.rows()[1][0]

        set_active(self.user, second)

        self.assertEqual(active_vehicle(self.player).key, "estate")

    def test_only_one_car_is_ever_the_one_you_drive(self):
        """Enforced by a partial unique index, not by remembering to.

        Two active rows would make "what am I driving" a question with
        two answers, and the travel page would pick whichever came back
        first.
        """
        from database.repositories.vehicles import set_active

        self.set(residence_key="penthouse")
        self.buy("hatchback")
        self.buy("estate")
        self.buy("saloon")

        for owned_id, _key, _active in self.rows():
            set_active(self.user, owned_id)

        self.assertEqual(
            sum(row[2] for row in self.rows()), 1
        )

    def test_you_can_choose_a_car_from_anywhere(self):
        # The forecourt is in Brixton; the garage is at home.
        from database.repositories.vehicles import set_active

        self.buy("hatchback")
        self.buy("estate")
        self.set(current_district="hackney")

        set_active(self.user, self.rows()[1][0])

        self.assertEqual(self.rows()[1][2], 1)

    def test_you_cannot_drive_somebody_elses_car(self):
        from database.repositories.vehicles import set_active

        other_user, _ = self.make(
            "thief", money=0, level=20,
            residence_key="modern_house", current_district="brixton",
        )
        self.buy("hatchback")

        with self.assertRaises(VehicleError):
            set_active(other_user, self.rows()[0][0])

    # --------------------------------------------------------- housing

    def test_you_cannot_move_somewhere_that_will_not_hold_the_cars(self):
        """A move that shrinks the garage would orphan a vehicle."""
        from database.repositories.housing import move_house, HousingError

        self.buy("hatchback")
        self.buy("estate")

        with self.assertRaises(HousingError):
            move_house(self.user, "council_flat")

        self.assertEqual(len(self.rows()), 2)

    def test_a_move_that_keeps_the_room_is_allowed(self):
        from database.repositories.housing import move_house

        self.buy("hatchback")
        move_house(self.user, "penthouse")

        self.assertEqual(len(self.rows()), 1)


class DrivingAcrossLondonTests(unittest.TestCase):
    """The travel rules, with a car in the garage."""

    def player(self, **overrides):
        state = dict(
            id=1,
            current_district="camden",
            level=20,
            money=5_000,
            wanted_level=0,
            travel_destination=None,
            travel_until=None,
            travel_mode=None,
            jail_until=None,
            hospital_until=None,
            last_wanted_update=None,
        )
        state.update(overrides)
        return SimpleNamespace(**state)

    def drive(self, vehicle_key="hatchback", seed=1, **overrides):
        from game.world.travel import start_travel

        player = self.player(**overrides)
        journey = start_travel(
            player,
            "soho",
            DRIVE_KEY,
            vehicle=get_vehicle(vehicle_key),
            rng=random.Random(seed),
        )
        return player, journey

    def test_driving_beats_the_bus_and_costs_less(self):
        from game.world.districts import get_travel_route
        from game.world.transport import get_transport_mode

        route = get_travel_route("camden", "soho")
        bus = get_transport_mode("bus")
        _player, journey = self.drive("estate")

        self.assertLess(
            journey.cost, bus.fare(route)
        )

    def test_a_car_goes_where_the_underground_does_not(self):
        from game.world.travel import start_travel

        player = self.player()
        journey = start_travel(
            player,
            "hackney",
            DRIVE_KEY,
            vehicle=get_vehicle("estate"),
            rng=random.Random(1),
        )

        self.assertEqual(journey.destination_key, "hackney")

    def test_choosing_to_drive_with_an_empty_garage_is_refused(self):
        from game.world.travel import (
            TransportUnavailableError,
            start_travel,
        )

        with self.assertRaises(TransportUnavailableError):
            start_travel(
                self.player(), "soho", DRIVE_KEY, vehicle=None
            )

    def test_a_clean_driver_is_never_stopped(self):
        for seed in range(30):
            player, _journey = self.drive("sable", seed=seed)

            self.assertIsNone(player.jail_until)

    def test_a_wanted_driver_in_a_loud_car_gets_pulled_over(self):
        from game.world.travel import PulledOverError

        stopped = 0
        for seed in range(60):
            try:
                self.drive("sable", seed=seed, wanted_level=100)
            except PulledOverError:
                stopped += 1

        # 50% at the cap, so a run of sixty that never stops anybody
        # would mean the check is not wired in at all.
        self.assertGreater(stopped, 10)

    def test_being_stopped_costs_the_journey_and_not_the_petrol(self):
        from game.world.travel import PulledOverError

        for seed in range(60):
            player = self.player(wanted_level=100)
            try:
                from game.world.travel import start_travel

                start_travel(
                    player, "soho", DRIVE_KEY,
                    vehicle=get_vehicle("sable"),
                    rng=random.Random(seed),
                )
            except PulledOverError:
                self.assertEqual(player.money, 5_000)
                self.assertIsNone(player.travel_destination)
                self.assertIsNotNone(player.jail_until)
                return

        self.fail("never stopped in sixty attempts")

    def test_the_bicycle_gets_home_however_hot_you_are(self):
        for seed in range(40):
            player, journey = self.drive(
                "bicycle", seed=seed, wanted_level=100
            )

            self.assertIsNone(player.jail_until)
            self.assertEqual(journey.destination_key, "soho")

    def test_the_bus_is_never_pulled_over(self):
        from game.world.travel import start_travel

        player = self.player(wanted_level=100)
        start_travel(player, "soho", "bus", rng=random.Random(1))

        self.assertIsNone(player.jail_until)


class ForecourtPageTests(unittest.TestCase):
    """The forecourt through the actual routes.

    The rules above prove the money moves correctly. This proves a
    player can reach it: the page renders, the forms post, and the car
    turns up on the travel page afterwards.
    """

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "pages.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        presence = patch("web.application.mark_player_online")
        presence.start()
        self.addCleanup(presence.stop)

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user = create_user("driver", "driver@example.com", "hash")
        create_player(self.user, "driver")
        self.set(
            money=500_000, level=20,
            residence_key="modern_house", current_district="brixton",
        )

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user

    def set(self, **columns):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET "
                + ", ".join(f"{key} = ?" for key in columns)
                + " WHERE user_id = ?",
                (*columns.values(), self.user),
            )
        connection.close()

    def buy(self, key="estate"):
        return self.client.post(
            "/motors", data={"action": "buy", "vehicle_key": key}
        ).data.decode()

    def test_the_forecourt_opens(self):
        response = self.client.get("/motors")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Coldharbour Motors", response.data.decode())

    def test_buying_from_the_form_puts_it_in_the_garage(self):
        self.assertIn("Marlow Estate is yours", self.buy())

        page = self.client.get("/motors").data.decode()

        self.assertIn("Your garage", page)
        self.assertIn("Driving", page)

    def test_the_car_turns_up_on_the_travel_page(self):
        self.buy()

        self.assertIn(
            "Drive the Marlow Estate",
            self.client.get("/travel").data.decode(),
        )

    def test_the_travel_page_shows_the_risk_only_when_wanted(self):
        self.buy()

        self.assertNotIn(
            "% stopped", self.client.get("/travel").data.decode()
        )

        self.set(wanted_level=100)

        self.assertIn(
            "% stopped", self.client.get("/travel").data.decode()
        )

    def test_the_city_directory_lists_the_forecourt(self):
        self.assertIn(
            "Coldharbour Motors",
            self.client.get("/city").data.decode(),
        )

    def test_every_refusal_is_a_sentence_not_a_crash(self):
        self.set(current_district="camden")
        self.assertIn("in Brixton", self.buy())

        self.set(current_district="brixton")
        self.assertIn("do not sell that", self.buy("spaceship"))
        self.assertIn(
            "not one of the cars",
            self.client.post(
                "/motors", data={"action": "sell", "owned_id": "abc"}
            ).data.decode(),
        )

    def test_the_forecourt_needs_a_login(self):
        with self.client.session_transaction() as session:
            session.clear()

        response = self.client.get("/motors")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])


if __name__ == "__main__":
    unittest.main()
