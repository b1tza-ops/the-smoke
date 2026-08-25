import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from auth.moderation import (
    InsufficientRoleError,
    InvalidRoleError,
    SelfLockoutError,
    UnknownUserError,
    ban_user,
    get_history,
    is_account_blocked,
    reverse_moderation,
    set_user_role,
    suspend_user,
    warn_user,
)
from database.core.setup import create_tables
from database.repositories.moderation import (
    get_account_state,
    get_user_role,
    set_user_role as _seed_role,
)
from database.repositories.users import create_user


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()

        self.admin_id = create_user(
            "admin_one", "admin1@example.com", "hash",
        )
        _seed_role(self.admin_id, "admin")

        self.moderator_id = create_user(
            "mod_one", "mod1@example.com", "hash",
        )
        _seed_role(self.moderator_id, "moderator")

        self.player_id = create_user(
            "player_one", "player1@example.com", "hash",
        )

        self.now = datetime(
            2026, 8, 25, 12, 0, tzinfo=timezone.utc,
        )

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def test_ordinary_users_cannot_moderate(self):
        with self.assertRaises(InsufficientRoleError):
            warn_user(self.player_id, self.moderator_id, "spam")

        with self.assertRaises(InsufficientRoleError):
            suspend_user(self.player_id, self.moderator_id, "spam")

        with self.assertRaises(InsufficientRoleError):
            ban_user(self.player_id, self.moderator_id, "spam")

        with self.assertRaises(InsufficientRoleError):
            set_user_role(self.player_id, self.moderator_id, "admin")

    def test_moderators_cannot_ban_or_change_roles(self):
        with self.assertRaises(InsufficientRoleError):
            ban_user(self.moderator_id, self.player_id, "abuse")

        with self.assertRaises(InsufficientRoleError):
            set_user_role(self.moderator_id, self.player_id, "moderator")

    def test_warning_is_audited_without_changing_state(self):
        warn_user(self.moderator_id, self.player_id, "First warning")

        state, _ = self._account_state(self.player_id)
        self.assertEqual(state, "active")

        history = get_history(self.player_id)
        self.assertEqual(len(history), 1)
        entry = history[0]
        self.assertEqual(entry[1], self.moderator_id)  # actor
        self.assertEqual(entry[2], self.player_id)      # target
        self.assertEqual(entry[3], "warn")               # action_type
        self.assertEqual(entry[4], "First warning")      # reason
        self.assertIsNotNone(entry[8])                   # created_at

    def test_suspension_and_ban_are_audited(self):
        suspend_user(
            self.moderator_id,
            self.player_id,
            "Toxic behaviour",
            duration_minutes=60,
            now=self.now,
        )
        state, _ = self._account_state(self.player_id)
        self.assertEqual(state, "suspended")

        ban_user(self.admin_id, self.player_id, "Repeat offender")
        state, _ = self._account_state(self.player_id)
        self.assertEqual(state, "banned")

        history = get_history(self.player_id)
        action_types = [entry[3] for entry in history]
        self.assertEqual(
            action_types,
            ["ban", "suspend"],  # most recent first
        )

    def test_reason_is_required(self):
        with self.assertRaises(ValueError):
            warn_user(self.moderator_id, self.player_id, "")

        with self.assertRaises(ValueError):
            warn_user(self.moderator_id, self.player_id, "   ")

    def test_banned_accounts_are_blocked_from_login(self):
        ban_user(self.admin_id, self.player_id, "Cheating")

        self.assertTrue(is_account_blocked(self.player_id))

    def test_indefinite_suspension_blocks_login(self):
        suspend_user(
            self.moderator_id,
            self.player_id,
            "Under investigation",
            now=self.now,
        )

        self.assertTrue(
            is_account_blocked(self.player_id, now=self.now)
        )

    def test_temporary_suspension_expires_deterministically(self):
        suspend_user(
            self.moderator_id,
            self.player_id,
            "Cooldown",
            duration_minutes=60,
            now=self.now,
        )

        still_blocked = is_account_blocked(
            self.player_id,
            now=self.now + timedelta(minutes=59),
        )
        self.assertTrue(still_blocked)

        expired = is_account_blocked(
            self.player_id,
            now=self.now + timedelta(minutes=61),
        )
        self.assertFalse(expired)

        state, suspended_until = self._account_state(self.player_id)
        self.assertEqual(state, "active")
        self.assertIsNone(suspended_until)

    def test_repeated_expiry_checks_do_not_error(self):
        suspend_user(
            self.moderator_id,
            self.player_id,
            "Cooldown",
            duration_minutes=10,
            now=self.now,
        )
        later = self.now + timedelta(hours=1)

        self.assertFalse(is_account_blocked(self.player_id, now=later))
        self.assertFalse(is_account_blocked(self.player_id, now=later))

    def test_reverse_moderation_restores_active_state(self):
        suspend_user(
            self.moderator_id,
            self.player_id,
            "Cooldown",
            duration_minutes=60,
            now=self.now,
        )

        reverse_moderation(
            self.moderator_id,
            self.player_id,
            "Appeal accepted",
        )

        state, suspended_until = self._account_state(self.player_id)
        self.assertEqual(state, "active")
        self.assertIsNone(suspended_until)

    def test_reversing_a_ban_requires_admin(self):
        ban_user(self.admin_id, self.player_id, "Cheating")

        with self.assertRaises(InsufficientRoleError):
            reverse_moderation(
                self.moderator_id,
                self.player_id,
                "Appeal accepted",
            )

        reverse_moderation(
            self.admin_id,
            self.player_id,
            "Appeal accepted",
        )
        state, _ = self._account_state(self.player_id)
        self.assertEqual(state, "active")

    def test_last_active_admin_cannot_demote_themselves(self):
        with self.assertRaises(SelfLockoutError):
            set_user_role(self.admin_id, self.admin_id, "moderator")

        self.assertEqual(get_user_role(self.admin_id), "admin")

    def test_last_active_admin_cannot_suspend_or_ban_themselves(self):
        with self.assertRaises(SelfLockoutError):
            suspend_user(self.admin_id, self.admin_id, "oops")

        with self.assertRaises(SelfLockoutError):
            ban_user(self.admin_id, self.admin_id, "oops")

    def test_demotion_is_allowed_with_a_second_active_admin(self):
        second_admin_id = create_user(
            "admin_two", "admin2@example.com", "hash",
        )
        _seed_role(second_admin_id, "admin")

        set_user_role(second_admin_id, self.admin_id, "moderator")

        self.assertEqual(get_user_role(self.admin_id), "moderator")

    def test_admin_can_demote_themselves_if_not_the_last_one(self):
        second_admin_id = create_user(
            "admin_two", "admin2@example.com", "hash",
        )
        _seed_role(second_admin_id, "admin")

        set_user_role(self.admin_id, self.admin_id, "moderator")

        self.assertEqual(get_user_role(self.admin_id), "moderator")

    def test_unknown_role_is_rejected(self):
        with self.assertRaises(InvalidRoleError):
            set_user_role(self.admin_id, self.player_id, "superadmin")

    def test_unknown_actor_or_target_is_rejected(self):
        with self.assertRaises(UnknownUserError):
            warn_user(999_999, self.player_id, "reason")

        with self.assertRaises(UnknownUserError):
            warn_user(self.moderator_id, 999_999, "reason")

    def _account_state(self, user_id):
        return get_account_state(user_id)


if __name__ == "__main__":
    unittest.main()
