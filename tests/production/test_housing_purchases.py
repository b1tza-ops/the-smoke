"""Buying a home and fitting it out, on the money side.

The first cut of this feature committed the goods and then subtracted
the price from a Player object for the caller to persist later. That
left two holes: a request that died in between installed a facility for
free, and two browser tabs could buy £11,000 of facilities with
£10,000, because each request checked its own snapshot of the balance.

Both are reproduced here as tests, because neither shows up in ordinary
single-request play and neither would be reported by the player it
benefits.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.housing import (
    facilities_for,
    install_facility,
    move_house,
)
from database.repositories.players import (
    create_player,
    get_player_by_user_id,
)
from database.repositories.users import create_user
from game.housing import FACILITIES, HousingError, InsufficientCashError
from game.player import Player


class HousingPurchaseTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "housing.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.user_id = create_user("owner", "owner@example.com", "hash")
        create_player(self.user_id, "Owner")
        self.set_money(10_000)

    def set_money(self, amount):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "UPDATE players SET money = ? WHERE user_id = ?",
                (amount, self.user_id),
            )
        connection.close()

    def money(self):
        return Player(*get_player_by_user_id(self.user_id)).money

    def residence(self):
        return Player(
            *get_player_by_user_id(self.user_id)
        ).residence_key

    # ------------------------------------------------ facilities

    def test_installing_a_facility_charges_for_it(self):
        _facility, remaining = install_facility(self.user_id, "hot_tub")

        self.assertEqual(remaining, 7_000)
        self.assertEqual(self.money(), 7_000)
        self.assertEqual(facilities_for(self.user_id), {"hot_tub"})

    def test_the_charge_lands_without_anyone_saving_the_player(self):
        # The money must be gone the moment the facility exists, not
        # when some later call gets round to persisting a Player.
        install_facility(self.user_id, "sauna")

        self.assertEqual(self.money(), 7_500)

    def test_two_requests_cannot_spend_the_same_money(self):
        # Two tabs. Each began with a £10,000 snapshot; between them
        # they are asking for £11,000 of facilities.
        install_facility(self.user_id, "hot_tub")   # £3,000

        with self.assertRaises(InsufficientCashError):
            install_facility(self.user_id, "pool")  # £8,000

        self.assertEqual(self.money(), 7_000)
        self.assertEqual(facilities_for(self.user_id), {"hot_tub"})

    def test_a_refused_facility_leaves_nothing_behind(self):
        self.set_money(100)

        with self.assertRaises(InsufficientCashError):
            install_facility(self.user_id, "pool")

        self.assertEqual(self.money(), 100)
        self.assertEqual(facilities_for(self.user_id), set())

    def test_a_facility_cannot_be_bought_twice(self):
        install_facility(self.user_id, "interior")
        before = self.money()

        with self.assertRaises(HousingError):
            install_facility(self.user_id, "interior")

        self.assertEqual(self.money(), before)

    def test_an_unknown_facility_is_refused(self):
        with self.assertRaises(HousingError):
            install_facility(self.user_id, "helipad")

        self.assertEqual(self.money(), 10_000)

    def test_every_facility_can_be_afforded_and_installed(self):
        self.set_money(1_000_000)

        for key in FACILITIES:
            install_facility(self.user_id, key)

        self.assertEqual(
            facilities_for(self.user_id),
            set(FACILITIES),
        )

    # ------------------------------------------------ residences

    def test_moving_house_charges_and_moves_together(self):
        residence, remaining = move_house(self.user_id, "council_flat")

        self.assertEqual(residence.key, "council_flat")
        self.assertEqual(remaining, 9_000)
        self.assertEqual(self.money(), 9_000)
        self.assertEqual(self.residence(), "council_flat")

    def test_a_house_that_cannot_be_afforded_moves_nothing(self):
        with self.assertRaises(InsufficientCashError):
            move_house(self.user_id, "penthouse")

        self.assertEqual(self.money(), 10_000)
        self.assertEqual(self.residence(), "tent")

    def test_two_requests_cannot_buy_two_houses_with_one_budget(self):
        move_house(self.user_id, "council_house")   # £4,500

        with self.assertRaises(InsufficientCashError):
            move_house(self.user_id, "apartment")   # £12,000

        self.assertEqual(self.money(), 5_500)
        self.assertEqual(self.residence(), "council_house")

    def test_moving_where_you_already_live_is_refused(self):
        move_house(self.user_id, "council_flat")
        before = self.money()

        with self.assertRaises(HousingError):
            move_house(self.user_id, "council_flat")

        self.assertEqual(self.money(), before)

    def test_an_unknown_residence_is_refused(self):
        with self.assertRaises(HousingError):
            move_house(self.user_id, "buckingham_palace")

        self.assertEqual(self.money(), 10_000)


if __name__ == "__main__":
    unittest.main()
