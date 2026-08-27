"""Rent: the first thing in this game that costs money over and over.

Everything else was buy-once. A player who had bought the ladder, the
fittings and the gyms had nothing left to spend on, which is the same
"nothing to do at the top" problem in a different costume.

The shape matters as much as the number. Falling behind suspends what
the home does for you and nothing else -- no eviction, no lost items,
no lost home. A sink that can take your things away is not a sink, it
is a trap, and these tests are mostly about holding that line.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.housing import (
    install_facility,
    move_house,
    pay_upkeep,
    upkeep_for,
)
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.users import create_user
from game.housing import HousingError, InsufficientCashError, get_residence
from game.housing.service import (
    MAXIMUM_UPKEEP_ARREARS_DAYS,
    daily_upkeep,
    upkeep_owed,
)
from game.player import Player


class UpkeepArithmeticTests(unittest.TestCase):
    def test_the_tent_is_free_forever(self):
        self.assertEqual(daily_upkeep(get_residence("tent")), 0)
        self.assertEqual(
            upkeep_owed(get_residence("tent"), timedelta(days=30)),
            0,
        )

    def test_the_cheapest_room_still_costs_real_money(self):
        """The floor is the point of the ladder.

        Rent used to be 0.3% of the purchase price, which made the
        hostel room £1 a day. That is not a sink, it is a rounding
        error: a player could hold it forever and never notice.

        £150 is about a quarter of a new player's three-hour day of
        Camden crime, which is the same bite the penthouse takes out of
        a developed player's.
        """
        self.assertEqual(daily_upkeep(get_residence("hostel")), 150)

    def test_every_home_you_pay_for_costs_at_least_the_floor(self):
        from game.housing import RESIDENCES

        for home in RESIDENCES:
            if home.purchase_price == 0:
                continue
            with self.subTest(residence=home.key):
                self.assertGreaterEqual(daily_upkeep(home), 150)

    def test_the_ladder_never_goes_backwards(self):
        """A dearer home must never be cheaper to keep."""
        from game.housing import RESIDENCES

        rents = [daily_upkeep(home) for home in RESIDENCES]

        self.assertEqual(rents, sorted(rents))

    def test_rent_scales_with_what_you_bought(self):
        cheap = daily_upkeep(get_residence("council_flat"))
        dear = daily_upkeep(get_residence("penthouse"))

        self.assertGreater(dear, cheap)
        self.assertEqual(dear, 550)

    def test_it_is_charged_by_the_second(self):
        home = get_residence("penthouse")

        self.assertEqual(upkeep_owed(home, timedelta(days=1)), 550)
        # Half a day costs half, rather than nothing until a day ticks.
        self.assertEqual(upkeep_owed(home, timedelta(hours=12)), 275)

    def test_a_long_absence_cannot_produce_a_bill_nobody_can_pay(self):
        home = get_residence("penthouse")
        a_year = upkeep_owed(home, timedelta(days=365))

        self.assertEqual(
            a_year,
            daily_upkeep(home) * MAXIMUM_UPKEEP_ARREARS_DAYS,
        )

    def test_nothing_accrues_backwards(self):
        self.assertEqual(
            upkeep_owed(get_residence("penthouse"), timedelta(days=-5)),
            0,
        )


class UpkeepThroughTheGameTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "upkeep.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.user_id = create_user("tenant", "tenant@example.com", "hash")
        create_player(self.user_id, "Tenant")
        self.set(money=300_000)

    def set(self, **columns):
        assignments = ", ".join(f"{key} = ?" for key in columns)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                f"UPDATE players SET {assignments} WHERE user_id = ?",
                (*columns.values(), self.user_id),
            )
        connection.close()

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def owe_rent_for(self, days):
        """Wind the rent clock back so a bill has built up."""
        moved = datetime.now(timezone.utc) - timedelta(days=days)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                """
                UPDATE player_housing_upkeep
                SET settled_at = ?
                WHERE player_id = (
                    SELECT id FROM players WHERE user_id = ?
                )
                """,
                (moved.strftime("%Y-%m-%d %H:%M:%S"), self.user_id),
            )
        connection.close()

    def test_a_tent_dweller_never_owes_anything(self):
        state = upkeep_for(self.user_id)

        self.assertEqual(state["daily"], 0)
        self.assertEqual(state["owed"], 0)
        self.assertFalse(state["in_arrears"])

    def test_buying_a_home_starts_the_clock_without_a_bill(self):
        move_house(self.user_id, "penthouse")

        state = upkeep_for(self.user_id)

        self.assertEqual(state["daily"], 550)
        self.assertEqual(state["owed"], 0)

    def test_rent_builds_up_over_time(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)
        self.owe_rent_for(3)

        self.assertEqual(upkeep_for(self.user_id)["owed"], 1650)

    def test_paying_clears_the_bill_and_takes_the_money(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)
        self.owe_rent_for(2)
        before = self.player().money

        paid, left = pay_upkeep(self.user_id)

        self.assertEqual(paid, 1100)
        self.assertEqual(left, 0)
        self.assertEqual(self.player().money, before - 1100)
        self.assertFalse(upkeep_for(self.user_id)["in_arrears"])

    def test_paying_when_straight_is_refused(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)

        with self.assertRaises(HousingError):
            pay_upkeep(self.user_id)

    def test_a_bill_you_cannot_afford_takes_nothing(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)
        self.owe_rent_for(5)
        self.set(money=10)

        with self.assertRaises(InsufficientCashError):
            pay_upkeep(self.user_id)

        self.assertEqual(self.player().money, 10)
        self.assertTrue(upkeep_for(self.user_id)["in_arrears"])

    # ------------------------------------------- what arrears cost

    def energy_in_an_hour(self):
        moved = datetime.now(timezone.utc) - timedelta(hours=1)
        stamp = moved.strftime("%Y-%m-%d %H:%M:%S")
        self.set(energy=0, last_energy_update=stamp)
        return self.player().energy

    def test_arrears_suspend_the_recovery_bonus(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)

        paid_up = self.energy_in_an_hour()
        self.owe_rent_for(3)
        behind = self.energy_in_an_hour()

        self.assertEqual(paid_up, 40)
        self.assertEqual(behind, 30, "the bonus survived the arrears")

    def test_paying_restores_it_at_once(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)
        self.owe_rent_for(3)
        self.assertEqual(self.energy_in_an_hour(), 30)

        pay_upkeep(self.user_id)

        self.assertEqual(self.energy_in_an_hour(), 40)

    def test_arrears_take_the_extra_carrying_space_too(self):
        from game.inventory import INVENTORY_SLOT_CAPACITY, slot_capacity

        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)

        self.assertEqual(slot_capacity(self.player()), 100)

        self.owe_rent_for(3)

        self.assertEqual(
            slot_capacity(self.player()),
            INVENTORY_SLOT_CAPACITY,
        )

    def test_arrears_never_take_the_home_or_anything_in_it(self):
        # The whole point. A player who cannot pay loses the benefit and
        # nothing else: they keep the address, the fittings and the
        # items, and one payment puts it all back.
        move_house(self.user_id, "penthouse")
        install_facility(self.user_id, "hot_tub")
        upkeep_for(self.user_id)
        self.owe_rent_for(9)

        from database.repositories.housing import facilities_for

        self.assertEqual(self.player().residence_key, "penthouse")
        self.assertEqual(facilities_for(self.user_id), {"hot_tub"})
        self.assertGreater(self.player().money, 0)

    def test_moving_back_to_the_tent_leaves_no_bill_behind(self):
        move_house(self.user_id, "penthouse")
        upkeep_for(self.user_id)
        self.owe_rent_for(4)
        self.assertTrue(upkeep_for(self.user_id)["in_arrears"])

        move_house(self.user_id, "tent")

        state = upkeep_for(self.user_id)
        self.assertEqual(state["owed"], 0)
        self.assertFalse(state["in_arrears"])


if __name__ == "__main__":
    unittest.main()
