"""What happened while you were away, and the page that used to 500.

Four mechanics tell a player something happened to them -- an attack, a
burglary that came off, one that did not, a bounty posted or collected
-- and until now every one of them surfaced on exactly one page,
`/pvp`. A player could be robbed overnight, log in, land on the
dashboard and see nothing at all.

Worse, `/pvp` was the page that crashed. Migration 052 made
`pvp_notifications.attack_id` nullable so that a burglary, which has no
attack to point at, could write a notice. The template kept building a
report URL out of it unconditionally:

    url_for('pvp_report', attack_id=notice.attack_id)

which raises `BuildError` on None. So since burglary shipped, **any
player who had been burgled or had a bounty posted on them got a 500 on
Player Fights** -- the exact page they were being sent to in order to
read about it. `TheNullAttackCrashTests` below is that bug.

The panel itself is deliberately an alert and not an inbox: it shows
unread notices and does not mark them read, because a player who
glances at the dashboard must not lose the detail for ever.
"""

import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.player.digest import GOOD, NEUTRAL, URGENT, build
from game.player.regeneration import format_timestamp


class DigestRulesTests(unittest.TestCase):
    """The pure part: facts in, ordered entries out."""

    def test_a_quiet_player_is_told_nothing(self):
        """Silence is the correct output, not an empty panel.

        A box saying "nothing happened" on every visit is noise, and
        noise is what stops anybody reading the box on the day
        something does happen.
        """
        self.assertEqual(build(), ())

    def test_what_costs_money_outranks_what_pays_it(self):
        entries = build(
            rent_owed=3_850,
            shift_ready=True,
            shift_pay=780,
            notifications=("Somebody broke in.",),
        )

        self.assertEqual(
            [entry.tone for entry in entries],
            [URGENT, NEUTRAL, GOOD],
        )

    def test_the_rent_entry_says_what_it_is_costing_them(self):
        """The quiet one. Arrears suspend every bonus the home gives.

        That is enforced on every page load and was announced on none
        of them, so a player in arrears just found the game had got
        slower for no visible reason.
        """
        entry = build(rent_owed=3_850, daily_rent=550)[0]

        self.assertIn("£3,850", entry.headline)
        self.assertIn("does nothing for you", entry.detail)
        self.assertIn("£550", entry.detail)
        self.assertEqual(entry.link, "/housing/manage")

    def test_the_notice_entry_quotes_a_real_message(self):
        """A bare count reads as chrome.

        "Your home was broken into" is the thing that makes somebody
        click; "3 notifications" is not.
        """
        entry = build(notifications=(
            "Your home was broken into. £1,240 was taken.",
            "raider has put £5,000 on your head.",
            "Somebody tried to break in and did not get in.",
        ))[0]

        self.assertIn("3 people came for you", entry.headline)
        self.assertIn("broken into", entry.detail)
        self.assertIn("1 more", entry.detail)

    def test_one_visitor_is_not_called_several(self):
        entry = build(notifications=("Somebody broke in.",))[0]

        self.assertIn("Somebody came for you", entry.headline)
        self.assertNotIn("1 people", entry.headline)

    def test_an_overdue_loan_names_the_missed_payments(self):
        entry = build(
            loan_balance=12_500, loan_overdue=True, missed_payments=2
        )[0]

        self.assertIn("£12,500", entry.headline)
        self.assertIn("missed 2 payments", entry.detail)
        self.assertEqual(entry.link, "/loanshark")

    def test_a_loan_in_good_standing_is_not_mentioned(self):
        self.assertEqual(
            build(loan_balance=12_500, loan_overdue=False), ()
        )

    def test_being_held_is_reported_with_the_time_left(self):
        cell = build(jail_seconds=1_800)[0]
        ward = build(hospital_seconds=7_200)[0]

        self.assertIn("30 minutes", cell.detail)
        self.assertIn("2 hours", ward.detail)

    def test_a_finished_shift_says_what_it_is_worth(self):
        entry = build(shift_ready=True, shift_pay=780)[0]

        self.assertEqual(entry.tone, GOOD)
        self.assertIn("£780", entry.detail)

    def test_a_shift_still_running_is_not_mentioned(self):
        self.assertEqual(build(shift_ready=False, shift_pay=780), ())

    def test_every_entry_can_be_acted_on(self):
        """An alert with nowhere to go is just an interruption."""
        entries = build(
            rent_owed=100,
            loan_balance=500,
            loan_overdue=True,
            notifications=("Something happened.",),
            shift_ready=True,
            jail_seconds=60,
            hospital_seconds=60,
        )

        self.assertEqual(len(entries), 6)
        for entry in entries:
            with self.subTest(kind=entry.kind):
                self.assertTrue(entry.link.startswith("/"))
                self.assertTrue(entry.link_text)
                self.assertTrue(entry.headline)


class DigestFactsTests(unittest.TestCase):
    """The reads, which must not move anything.

    This runs on the busiest page in the game -- the one every session
    starts on. Every existing way of getting these numbers settles a
    clock inside `BEGIN IMMEDIATE`, which is right where those live and
    wrong here.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "digest.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", self.database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user = create_user("tenant", "t@example.com", "hash")
        create_player(self.user, "tenant")
        self.run_sql(
            "UPDATE players SET money = 50000, "
            "residence_key = 'penthouse', current_district = 'camden'"
        )

    def run_sql(self, statement, *params):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(statement, params)
        connection.close()

    def read(self, statement):
        connection = sqlite3.connect(self.database_path)
        row = connection.execute(statement).fetchone()
        connection.close()
        return row

    def player(self):
        from database.repositories.players import get_player_by_user_id
        from game.player.model import Player

        return Player(*get_player_by_user_id(self.user))

    def owe_rent(self, days=7):
        stamp = (
            datetime.now(timezone.utc) - timedelta(days=days)
        ).strftime("%Y-%m-%d %H:%M:%S")
        self.run_sql(
            "INSERT INTO player_housing_upkeep "
            "(player_id, settled_at, arrears) VALUES (1, ?, 0)",
            stamp,
        )

    def test_it_reads_the_rent_without_settling_it(self):
        from database.repositories.digest import facts_for

        self.owe_rent(7)
        before = self.read(
            "SELECT settled_at FROM player_housing_upkeep"
        )[0]

        facts = facts_for(self.player())

        self.assertEqual(facts["rent_owed"], 7 * 550)
        self.assertEqual(
            self.read("SELECT settled_at FROM player_housing_upkeep")[0],
            before,
            "the digest moved the rent marker; it must only read",
        )

    def test_it_agrees_with_what_the_game_is_charging(self):
        """The loader uses the same figure to suspend the home.

        If these two ever disagree the panel would announce a debt the
        game is not charging, or stay quiet about one it is.
        """
        from database.repositories.digest import facts_for

        self.owe_rent(3)
        facts = facts_for(self.player())

        # The home is suspended, so its bonuses are gone -- which is
        # exactly what the panel is there to explain.
        self.assertGreater(facts["rent_owed"], 0)
        self.assertEqual(facts["daily_rent"], 550)

    def test_a_player_with_no_home_owes_nothing(self):
        from database.repositories.digest import facts_for

        self.run_sql("UPDATE players SET residence_key = 'tent'")

        self.assertEqual(facts_for(self.player())["rent_owed"], 0)

    def test_it_reads_the_loan_without_accruing_interest(self):
        from database.repositories.digest import facts_for

        stamp = (
            datetime.now(timezone.utc) - timedelta(days=4)
        ).strftime("%Y-%m-%d %H:%M:%S")
        self.run_sql(
            "INSERT INTO player_loans (player_id, principal, interest, "
            "missed_payments, taken_at, interest_accrued_at, due_at) "
            "VALUES (1, 10000, 0, 1, ?, ?, ?)",
            stamp, stamp, stamp,
        )

        facts = facts_for(self.player())

        self.assertGreater(facts["loan_balance"], 10_000)
        self.assertTrue(facts["loan_overdue"])
        self.assertEqual(facts["missed_payments"], 1)
        self.assertEqual(
            self.read("SELECT interest FROM player_loans")[0],
            0,
            "the digest accrued interest; it must only read",
        )

    def test_no_loan_is_not_a_crash(self):
        from database.repositories.digest import facts_for

        facts = facts_for(self.player())

        self.assertEqual(facts["loan_balance"], 0)
        self.assertFalse(facts["loan_overdue"])

    def test_it_reads_notifications_without_marking_them_read(self):
        from database.repositories.digest import facts_for

        self.run_sql(
            "INSERT INTO pvp_notifications "
            "(player_id, attack_id, message, created_at) "
            "VALUES (1, NULL, 'Your home was broken into.', ?)",
            format_timestamp(datetime.now(timezone.utc)),
        )

        facts = facts_for(self.player())

        self.assertEqual(len(facts["notifications"]), 1)
        self.assertIsNone(
            self.read(
                "SELECT read_at FROM pvp_notifications"
            )[0],
            "the dashboard consumed the notice it was pointing at",
        )


class TheNullAttackCrashTests(unittest.TestCase):
    """`/pvp` 500'd for anybody who had been burgled.

    Migration 052 made `attack_id` nullable on purpose -- a burglary is
    not an attack and has no row to point at. The template went on
    building a report URL out of it, and `url_for` raises `BuildError`
    on None.

    So every player the burglary and bounty features were written for
    got a crash on the one page that would have told them about it.
    """

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "pvp.db"
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

        self.user = create_user("victim", "v@example.com", "hash")
        create_player(self.user, "victim")

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user

    def notify(self, message, attack_id=None):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                "INSERT INTO pvp_notifications "
                "(player_id, attack_id, message, created_at) "
                "VALUES (1, ?, ?, ?)",
                (
                    attack_id,
                    message,
                    format_timestamp(datetime.now(timezone.utc)),
                ),
            )
        connection.close()

    def test_a_burglary_notice_does_not_take_the_page_down(self):
        self.notify("Your home was broken into. £1,240 was taken.")

        response = self.client.get("/pvp")

        self.assertEqual(response.status_code, 200)
        self.assertIn("broken into", response.get_data(as_text=True))

    def test_a_bounty_notice_does_not_take_the_page_down(self):
        self.notify("raider has put £5,000 on your head.")

        response = self.client.get("/pvp")

        self.assertEqual(response.status_code, 200)

    def test_a_notice_without_an_attack_offers_no_report_link(self):
        """There is no report to link to, so it must not pretend."""
        self.notify("Your home was broken into.")

        body = self.client.get("/pvp").get_data(as_text=True)

        self.assertIn("While you were out", body)
        self.assertNotIn("/pvp/report/None", body)


class DashboardPanelTests(unittest.TestCase):
    """The panel on the page a session actually starts on."""

    def setUp(self):
        from web.application import app

        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "home.db"
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
        from database.repositories.prologue import get_or_create_prologue
        from database.repositories.users import create_user

        self.user = create_user("tenant", "t@example.com", "hash")
        create_player(self.user, "tenant")
        get_or_create_prologue(self.user)
        self.run_sql(
            "UPDATE players SET money = 50000, "
            "residence_key = 'penthouse', current_district = 'camden'"
        )
        # The dashboard bounces to /prologue until it is finished, so
        # without this the panel is never reached at all.
        self.run_sql(
            "UPDATE player_prologue SET completed_at = ?",
            format_timestamp(datetime.now(timezone.utc)),
        )

        app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user

    def run_sql(self, statement, *params):
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(statement, params)
        connection.close()

    def dashboard(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)

        return response.get_data(as_text=True)

    def test_a_quiet_player_gets_no_panel(self):
        self.assertNotIn("While you were out", self.dashboard())

    def test_arrears_reach_the_landing_page(self):
        stamp = (
            datetime.now(timezone.utc) - timedelta(days=7)
        ).strftime("%Y-%m-%d %H:%M:%S")
        self.run_sql(
            "INSERT INTO player_housing_upkeep "
            "(player_id, settled_at, arrears) VALUES (1, ?, 0)",
            stamp,
        )

        body = self.dashboard()

        self.assertIn("While you were out", body)
        self.assertIn("£3,850", body)

    def test_a_burglary_reaches_the_landing_page(self):
        self.run_sql(
            "INSERT INTO pvp_notifications "
            "(player_id, attack_id, message, created_at) "
            "VALUES (1, NULL, 'Your home was broken into.', ?)",
            format_timestamp(datetime.now(timezone.utc)),
        )

        body = self.dashboard()

        self.assertIn("came for you", body)
        self.assertIn("broken into", body)

    def test_the_panel_does_not_consume_what_it_points_at(self):
        """The dashboard is the alert; `/pvp` is the inbox.

        A player who glances at the panel must not lose the detail.
        """
        self.run_sql(
            "INSERT INTO pvp_notifications "
            "(player_id, attack_id, message, created_at) "
            "VALUES (1, NULL, 'Your home was broken into.', ?)",
            format_timestamp(datetime.now(timezone.utc)),
        )

        self.dashboard()
        self.dashboard()

        connection = sqlite3.connect(self.database_path)
        unread = connection.execute(
            "SELECT COUNT(*) FROM pvp_notifications "
            "WHERE read_at IS NULL"
        ).fetchone()[0]
        connection.close()

        self.assertEqual(unread, 1)

    def test_reading_the_inbox_clears_the_panel(self):
        self.run_sql(
            "INSERT INTO pvp_notifications "
            "(player_id, attack_id, message, created_at) "
            "VALUES (1, NULL, 'Your home was broken into.', ?)",
            format_timestamp(datetime.now(timezone.utc)),
        )

        self.assertIn("came for you", self.dashboard())
        self.client.get("/pvp")

        self.assertNotIn("came for you", self.dashboard())


if __name__ == "__main__":
    unittest.main()
