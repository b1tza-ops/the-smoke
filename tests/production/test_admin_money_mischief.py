"""Handing out money, and winding people up.

Both tools reach into a live account, so both are tested the same way
and against the same rule: nothing happens to a player without the
player being told, and without the ledger being told.

The silent version of either of these is the dangerous one. Money
appearing from nowhere is indistinguishable from a bug in the economy;
happiness halving for no reason is indistinguishable from a broken
game. A player cannot tell an owner's joke from a defect unless
somebody says so.
"""

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.admin import adjust_player_money, apply_prank
from database.repositories.players import create_player, get_player_by_user_id
from database.repositories.users import create_user
from game.admin.mischief import (
    MAXIMUM_ADJUSTMENT,
    PRANKS,
    AdminActionError,
    adjustment_summary,
    get_prank,
    validate_adjustment,
)
from game.player import Player
from game.world.districts import DISTRICTS
from web.application import app


class AmountTests(unittest.TestCase):
    def test_a_typed_figure_survives_commas_and_a_pound_sign(self):
        self.assertEqual(validate_adjustment("25,000"), 25_000)
        self.assertEqual(validate_adjustment("£5000"), 5_000)
        self.assertEqual(validate_adjustment(" -750 "), -750)

    def test_nonsense_is_refused(self):
        for raw in ("", "lots", None, "1.5", True):
            with self.subTest(raw=raw):
                with self.assertRaises(AdminActionError):
                    validate_adjustment(raw)

    def test_zero_is_refused_because_it_would_log_a_lie(self):
        with self.assertRaises(AdminActionError):
            validate_adjustment("0")

    def test_a_slipped_zero_is_caught_in_both_directions(self):
        for amount in (MAXIMUM_ADJUSTMENT + 1, -MAXIMUM_ADJUSTMENT - 1):
            with self.subTest(amount=amount):
                with self.assertRaises(AdminActionError):
                    validate_adjustment(amount)

        self.assertEqual(
            validate_adjustment(MAXIMUM_ADJUSTMENT), MAXIMUM_ADJUSTMENT
        )

    def test_the_summary_reads_as_what_happened(self):
        self.assertIn("Added £500", adjustment_summary(500, 100, 600))
        self.assertIn("Took £500", adjustment_summary(-500, 600, 100))


class PrankCatalogueTests(unittest.TestCase):
    def test_every_prank_tells_the_player_something(self):
        """The rule the whole module rests on."""
        for prank in PRANKS:
            with self.subTest(prank=prank.key):
                self.assertTrue(
                    prank.message or prank.custom_message,
                    f"{prank.key} would change a character silently",
                )

    def test_every_prank_is_reachable_by_key(self):
        for prank in PRANKS:
            self.assertIs(get_prank(prank.key), prank)

    def test_an_unknown_key_is_nothing(self):
        self.assertIsNone(get_prank("nonsense"))

    def test_a_theft_carries_a_line_for_an_empty_pocket(self):
        """Otherwise it tells a skint player their wallet got lighter."""
        for prank in PRANKS:
            if prank.money[0] < 0:
                with self.subTest(prank=prank.key):
                    self.assertTrue(prank.foiled_message)

    def test_the_scatter_prank_names_the_district_it_lands_on(self):
        scatter = [prank for prank in PRANKS if prank.scatter]
        self.assertTrue(scatter)
        for prank in scatter:
            self.assertIn("{district}", prank.message)


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "game.db"
        patcher = patch("database.core.connection.DB_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        create_tables()

        self.user_id = create_user("mark", "mark@example.com", "hash")
        create_player(self.user_id, "Mark")
        self.set(
            money=10_000, happiness=100, max_happiness=100,
            energy=10, max_energy=150, nerve=5, max_nerve=20,
            wanted_level=0, current_district="camden",
        )

    def set(self, **columns):
        assignments = ", ".join(f"{name} = ?" for name in columns)
        connection = sqlite3.connect(self.path)
        with connection:
            connection.execute(
                f"UPDATE players SET {assignments} WHERE user_id = ?",
                (*columns.values(), self.user_id),
            )
        connection.close()

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def notifications(self):
        connection = get_connection()
        rows = connection.execute(
            """
            SELECT message FROM pvp_notifications
            WHERE player_id = (SELECT id FROM players WHERE user_id = ?)
            ORDER BY id
            """,
            (self.user_id,),
        ).fetchall()
        connection.close()
        return [row[0] for row in rows]

    def test_money_goes_in_and_comes_out(self):
        result = adjust_player_money(self.user_id, 5_000)
        self.assertEqual(self.player().money, 15_000)
        self.assertEqual(result["moved"], 5_000)

        adjust_player_money(self.user_id, -2_000)
        self.assertEqual(self.player().money, 13_000)

    def test_nobody_is_pushed_into_debt(self):
        """The rest of the game has no concept of a negative balance."""
        result = adjust_player_money(self.user_id, -999_999)
        self.assertEqual(self.player().money, 0)
        self.assertEqual(result["moved"], -10_000)
        self.assertTrue(result["clamped"])

    def test_a_grant_can_carry_a_message_and_usually_does_not(self):
        adjust_player_money(self.user_id, 100, "From the top floor.")
        self.assertEqual(self.notifications(), ["From the top floor."])

        adjust_player_money(self.user_id, 100)
        self.assertEqual(len(self.notifications()), 1)

    def test_an_account_with_no_character_is_refused(self):
        orphan = create_user("orphan", "orphan@example.com", "hash")
        with self.assertRaises(AdminActionError):
            adjust_player_money(orphan, 100)

    def test_every_prank_leaves_the_player_a_message(self):
        for prank in PRANKS:
            with self.subTest(prank=prank.key):
                before = len(self.notifications())
                apply_prank(
                    self.user_id, prank.key,
                    custom_message="Something you did.",
                )
                self.assertEqual(len(self.notifications()), before + 1)

    def test_a_top_up_stops_at_the_ceiling_the_player_earned(self):
        apply_prank(self.user_id, "livener")
        player = self.player()
        self.assertEqual(player.energy, player.max_energy)
        self.assertEqual(player.nerve, player.max_nerve)

    def test_a_knock_never_goes_below_zero(self):
        self.set(happiness=5)
        apply_prank(self.user_id, "bad_pint")
        self.assertEqual(self.player().happiness, 0)

    def test_the_wanted_level_respects_its_own_cap(self):
        self.set(wanted_level=99)
        apply_prank(self.user_id, "grassed")
        self.assertLessEqual(self.player().wanted_level, 100)

    def test_being_bundled_lands_somewhere_else(self):
        apply_prank(self.user_id, "bundled")
        player = self.player()
        self.assertNotEqual(player.current_district, "camden")
        self.assertIn(
            player.current_district, {d.key for d in DISTRICTS}
        )
        self.assertNotIn("{district}", self.notifications()[-1])

    def test_a_pickpocket_on_an_empty_pocket_does_not_claim_otherwise(self):
        self.set(money=0)
        result = apply_prank(self.user_id, "pickpocket")
        self.assertEqual(self.player().money, 0)
        self.assertEqual(
            result["message"], get_prank("pickpocket").foiled_message
        )

    def test_a_word_needs_words(self):
        with self.assertRaises(AdminActionError):
            apply_prank(self.user_id, "word", custom_message="   ")

    def test_a_word_cannot_be_a_novel(self):
        with self.assertRaises(AdminActionError):
            apply_prank(self.user_id, "word", custom_message="x" * 281)

    def test_an_unknown_prank_changes_nothing(self):
        with self.assertRaises(AdminActionError):
            apply_prank(self.user_id, "defenestrate")
        self.assertEqual(self.notifications(), [])


class PanelTests(unittest.TestCase):
    """The routes, including who is allowed to reach them."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "game.db"
        patcher = patch("database.core.connection.DB_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        create_tables()

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.user_id = create_user("mark", "mark@example.com", "hash")
        create_player(self.user_id, "Mark")

    def client_as(self, role):
        client = app.test_client()
        with client.session_transaction() as session:
            session["admin_authenticated"] = True
            session["admin_role"] = role
            session["admin_user_id"] = None
            session["admin_display_name"] = "Server operator"
        return client

    def money(self):
        return Player(*get_player_by_user_id(self.user_id)).money

    def test_an_administrator_can_adjust_a_balance(self):
        before = self.money()
        response = self.client_as("admin").post(
            f"/admin/users/{self.user_id}/money",
            data={"amount": "25,000"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.money(), before + 25_000)

    def test_a_moderator_cannot(self):
        before = self.money()
        self.client_as("moderator").post(
            f"/admin/users/{self.user_id}/money",
            data={"amount": "1000000"},
        )
        self.assertEqual(self.money(), before)

    def test_a_moderator_cannot_wind_anybody_up_either(self):
        self.client_as("moderator").post(
            f"/admin/users/{self.user_id}/mischief",
            data={"prank": "grassed"},
        )
        self.assertEqual(
            Player(*get_player_by_user_id(self.user_id)).wanted_level, 0
        )

    def test_a_signed_out_visitor_cannot_reach_either(self):
        client = app.test_client()
        for path in ("money", "mischief"):
            response = client.post(
                f"/admin/users/{self.user_id}/{path}",
                data={"amount": "1000", "prank": "grassed"},
            )
            self.assertIn(response.status_code, (302, 401, 403))
        self.assertEqual(self.money(), Player(
            *get_player_by_user_id(self.user_id)
        ).money)

    def test_both_tools_write_to_the_audit_ledger(self):
        client = self.client_as("admin")
        client.post(
            f"/admin/users/{self.user_id}/money",
            data={"amount": "500"},
            follow_redirects=True,
        )
        client.post(
            f"/admin/users/{self.user_id}/mischief",
            data={"prank": "bad_pint"},
            follow_redirects=True,
        )

        connection = get_connection()
        logged = [
            row[0] for row in connection.execute(
                "SELECT action_type FROM player_activity WHERE user_id = ?",
                (self.user_id,),
            )
        ]
        connection.close()

        self.assertIn("admin_money_grant", logged)
        self.assertIn("admin_mischief", logged)

    def test_a_bad_figure_is_reported_rather_than_thrown(self):
        response = self.client_as("admin").post(
            f"/admin/users/{self.user_id}/money",
            data={"amount": "all of it"},
            follow_redirects=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("whole number", response.get_data(as_text=True))

    def test_the_panel_offers_every_prank(self):
        body = self.client_as("admin").get(
            f"/admin/users/{self.user_id}"
        ).get_data(as_text=True)
        for prank in PRANKS:
            self.assertIn(f'value="{prank.key}"', body)


if __name__ == "__main__":
    unittest.main()
