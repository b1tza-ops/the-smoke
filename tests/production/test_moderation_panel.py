import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.moderation import (
    get_account_state,
    get_user_role,
    set_user_role as _seed_role,
)
from database.repositories.players import create_player
from database.repositories.users import create_user
from utils.security import hash_password
from web.application import app


# Hashing is deliberately slow, so hash each fixture password once for
# the whole module rather than per test.
ADMIN_PASSWORD_HASH = hash_password("admin-pass")
MODERATOR_PASSWORD_HASH = hash_password("mod-pass")
PLAYER_PASSWORD_HASH = hash_password("player-pass")

BOOTSTRAP_ENV = {
    "THE_SMOKE_ADMIN_USERNAME": "operator",
    "THE_SMOKE_ADMIN_PASSWORD_HASH": hash_password("operator-pass"),
}


class ModerationPanelTests(unittest.TestCase):
    """The staff-facing side of the moderation backend.

    These exercise the real Flask routes so that role gating and the
    audited actor are verified end to end, not just at the service layer.
    """

    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)

        self.presence_patch = patch(
            "web.application.mark_player_online"
        )
        self.presence_patch.start()
        self.addCleanup(self.presence_patch.stop)

        create_tables()
        self.client = app.test_client()

        self.admin_id = create_user(
            "boss", "boss@example.com", ADMIN_PASSWORD_HASH,
        )
        _seed_role(self.admin_id, "admin")

        self.moderator_id = create_user(
            "steward", "steward@example.com",
            MODERATOR_PASSWORD_HASH,
        )
        _seed_role(self.moderator_id, "moderator")

        self.player_id = create_user(
            "civilian", "civilian@example.com",
            PLAYER_PASSWORD_HASH,
        )
        create_player(self.player_id, "Civilian")

    def sign_in_staff(self, username, password):
        return self.client.post(
            "/admin/login",
            data={"username": username, "password": password},
        )

    def sign_in_operator(self):
        with patch.dict("os.environ", BOOTSTRAP_ENV):
            return self.client.post(
                "/admin/login",
                data={
                    "username": "operator",
                    "password": "operator-pass",
                },
            )

    def test_admin_can_sign_in_with_their_game_account(self):
        response = self.sign_in_staff("boss", "admin-pass")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/admin")
        with self.client.session_transaction() as session:
            self.assertTrue(session["admin_authenticated"])
            self.assertEqual(
                session["admin_user_id"], self.admin_id,
            )
            self.assertEqual(session["admin_role"], "admin")

    def test_moderator_can_sign_in_with_their_game_account(self):
        response = self.sign_in_staff("steward", "mod-pass")

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["admin_role"], "moderator")

    def test_ordinary_player_cannot_sign_in_to_operations(self):
        response = self.sign_in_staff("civilian", "player-pass")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Invalid administrator", response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_authenticated", session)

    def test_wrong_password_cannot_sign_in_to_operations(self):
        response = self.sign_in_staff("boss", "not-the-password")

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_authenticated", session)

    def test_banned_staff_cannot_sign_in_to_operations(self):
        from auth.moderation import ban_user

        ban_user(None, self.moderator_id, "Compromised account")

        response = self.sign_in_staff("steward", "mod-pass")

        self.assertEqual(response.status_code, 200)
        with self.client.session_transaction() as session:
            self.assertNotIn("admin_authenticated", session)

    def test_operator_bootstrap_credential_still_works(self):
        response = self.sign_in_operator()

        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertTrue(session["admin_authenticated"])
            self.assertIsNone(session["admin_user_id"])
            self.assertEqual(session["admin_role"], "admin")

    def test_operations_dashboard_filters_players_and_shows_metrics(self):
        self.sign_in_operator()

        response = self.client.get("/admin?q=Civilian&status=all")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Civilian", response.data)
        self.assertIn(b"Online now", response.data)
        self.assertIn(b"Verified", response.data)
        self.assertIn(b"Restricted", response.data)

        response = self.client.get("/admin?q=not-a-player")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"No accounts match this filter", response.data)

    def test_moderator_suspension_records_them_as_the_actor(self):
        self.sign_in_staff("steward", "mod-pass")

        response = self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={
                "action": "suspend",
                "reason": "Abusive chat",
                "duration_minutes": "60",
            },
        )

        self.assertEqual(response.status_code, 302)
        state, suspended_until = get_account_state(self.player_id)
        self.assertEqual(state, "suspended")
        self.assertIsNotNone(suspended_until)

        from auth.moderation import get_history

        entry = get_history(self.player_id)[0]
        self.assertEqual(entry[3], "suspend")
        self.assertEqual(entry[1], self.moderator_id)
        self.assertEqual(entry[9], "steward")

    def test_operator_actions_are_audited_as_the_server_operator(self):
        self.sign_in_operator()

        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "warn", "reason": "First warning"},
        )

        from auth.moderation import get_history

        entry = get_history(self.player_id)[0]
        self.assertEqual(entry[3], "warn")
        self.assertIsNone(entry[1])
        self.assertIsNone(entry[9])

    def test_moderator_cannot_ban(self):
        self.sign_in_staff("steward", "mod-pass")

        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "ban", "reason": "Trying to ban"},
        )

        state, _ = get_account_state(self.player_id)
        self.assertEqual(state, "active")

    def test_moderator_cannot_change_roles(self):
        self.sign_in_staff("steward", "mod-pass")

        response = self.client.post(
            f"/admin/users/{self.player_id}/role",
            data={"role": "admin"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user_role(self.player_id), "player")

    def test_moderator_cannot_grant_items_or_force_jail(self):
        self.sign_in_staff("steward", "mod-pass")

        inventory = self.client.post(
            f"/admin/users/{self.player_id}/inventory",
            data={
                "action": "grant",
                "item_key": "lockpick",
                "quantity": "5",
            },
        )
        status = self.client.post(
            f"/admin/users/{self.player_id}/status",
            data={
                "restriction": "jail",
                "duration_minutes": "60",
            },
        )

        self.assertEqual(inventory.status_code, 302)
        self.assertEqual(status.status_code, 302)

        from database.repositories.admin import (
            get_admin_player_details,
        )

        details = get_admin_player_details(self.player_id)
        granted = {
            row["item_key"] for row in details["inventory"]
        }
        self.assertNotIn("lockpick", granted)
        self.assertIsNone(details["account"]["jail_until"])

    def test_admin_can_change_roles(self):
        self.sign_in_staff("boss", "admin-pass")

        self.client.post(
            f"/admin/users/{self.player_id}/role",
            data={"role": "moderator"},
        )

        self.assertEqual(
            get_user_role(self.player_id), "moderator",
        )

    def test_a_reason_is_required_for_moderation_actions(self):
        self.sign_in_staff("boss", "admin-pass")

        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "suspend", "reason": "   "},
        )

        state, _ = get_account_state(self.player_id)
        self.assertEqual(state, "active")

    def test_banning_from_the_panel_blocks_the_player_login(self):
        self.sign_in_staff("boss", "admin-pass")
        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "ban", "reason": "Cheating"},
        )
        self.client.get("/admin/logout")

        with patch(
            "web.application.is_email_verified",
            return_value=True,
        ):
            response = self.client.post(
                "/login",
                data={
                    "username": "civilian",
                    "password": "player-pass",
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"suspended or banned", response.data)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_restoring_from_the_panel_lets_the_player_back_in(self):
        self.sign_in_staff("boss", "admin-pass")
        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "ban", "reason": "Cheating"},
        )
        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "reverse", "reason": "Appeal upheld"},
        )
        self.client.get("/admin/logout")

        with patch(
            "web.application.is_email_verified",
            return_value=True,
        ):
            response = self.client.post(
                "/login",
                data={
                    "username": "civilian",
                    "password": "player-pass",
                },
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], "/")

    def test_a_session_without_a_role_must_sign_in_again(self):
        """A cookie from before staff sign-in existed has no actor.

        Rather than guess who is holding it, the panel makes it sign in
        again -- otherwise it would silently act as the operator.
        """
        with self.client.session_transaction() as session:
            session["admin_authenticated"] = True

        page = self.client.get("/admin")
        action = self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={"action": "ban", "reason": "Stale session"},
        )

        self.assertEqual(page.status_code, 302)
        self.assertEqual(
            page.headers["Location"], "/admin/login",
        )
        self.assertEqual(action.status_code, 302)
        state, _ = get_account_state(self.player_id)
        self.assertEqual(state, "active")

    def test_a_non_numeric_suspension_length_is_rejected(self):
        self.sign_in_staff("boss", "admin-pass")

        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={
                "action": "suspend",
                "reason": "Abusive chat",
                "duration_minutes": "two hours",
            },
        )

        state, _ = get_account_state(self.player_id)
        self.assertEqual(state, "active")

    def test_a_blank_suspension_length_suspends_indefinitely(self):
        self.sign_in_staff("boss", "admin-pass")

        self.client.post(
            f"/admin/users/{self.player_id}/moderation",
            data={
                "action": "suspend",
                "reason": "Under investigation",
                "duration_minutes": "",
            },
        )

        state, suspended_until = get_account_state(self.player_id)
        self.assertEqual(state, "suspended")
        self.assertIsNone(suspended_until)

    def test_player_details_page_renders_the_moderation_panel(self):
        self.sign_in_staff("boss", "admin-pass")

        response = self.client.get(
            f"/admin/users/{self.player_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account standing", response.data)
        self.assertIn(b"Moderation history", response.data)
        self.assertIn(b"Assign role", response.data)

    def test_moderator_does_not_see_admin_only_controls(self):
        self.sign_in_staff("steward", "mod-pass")

        response = self.client.get(
            f"/admin/users/{self.player_id}"
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Account standing", response.data)
        self.assertNotIn(b"Assign role", response.data)
        self.assertNotIn(b"Manage items", response.data)
        self.assertNotIn(b"Set player status", response.data)


if __name__ == "__main__":
    unittest.main()
