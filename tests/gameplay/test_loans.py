"""Ronnie Dell's book.

A loan mints money the moment it is taken, so the only thing that keeps
it from being a faucet is that the debt is real: it accrues, it cannot
be escaped by staying off the page, and it costs the player something
to miss a payment. These tests hold that shape -- the arithmetic of the
interest, and the guarantee that every movement of money is exact and
happens once.
"""

import pathlib
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories import loans as repo
from database.repositories.players import create_player, get_player_by_user_id
from database.repositories.users import create_user
from game.economy.loans import (
    DAILY_INTEREST_RATE,
    HOSPITAL_MINUTES,
    MINIMUM_LEVEL,
    MINIMUM_LOAN,
    Loan,
    LoanError,
    apply_repayment,
    clears_arrears,
    headroom,
    hospital_minutes,
    interest_for,
    maximum_loan,
    validate_borrow,
    validate_repayment,
)
from game.player import Player


class LoanArithmeticTests(unittest.TestCase):
    def test_the_ceiling_scales_with_level(self):
        self.assertEqual(maximum_loan(10), 50_000)
        self.assertEqual(maximum_loan(20), 100_000)

    def test_the_ceiling_never_drops_below_the_entry_level(self):
        # Below the minimum level nobody can borrow at all, so the
        # figure quoted must not slide down towards zero with it.
        self.assertEqual(
            maximum_loan(1),
            maximum_loan(MINIMUM_LEVEL),
        )

    def test_headroom_is_what_is_left_under_the_ceiling(self):
        self.assertEqual(headroom(10, 20_000), 30_000)
        self.assertEqual(headroom(10, 50_000), 0)
        self.assertEqual(headroom(10, 90_000), 0)

    def test_interest_is_charged_by_the_second(self):
        # Three days on £20,000 at 2.5% a day.
        self.assertEqual(
            interest_for(20_000, timedelta(days=3)),
            1_500,
        )
        # Half a day costs half as much, rather than nothing until the
        # day ticks over.
        self.assertEqual(
            interest_for(20_000, timedelta(hours=12)),
            250,
        )

    def test_nothing_accrues_on_nothing(self):
        self.assertEqual(
            interest_for(0, timedelta(days=5)),
            0,
        )
        self.assertEqual(
            interest_for(20_000, timedelta(seconds=0)),
            0,
        )
        self.assertEqual(
            interest_for(20_000, timedelta(days=-2)),
            0,
        )

    def test_the_daily_rate_is_the_one_the_page_quotes(self):
        self.assertEqual(DAILY_INTEREST_RATE, 0.025)

    def test_a_missed_payment_costs_more_each_time(self):
        stays = [
            hospital_minutes(missed)
            for missed in range(len(HOSPITAL_MINUTES) + 3)
        ]

        self.assertEqual(stays[: len(HOSPITAL_MINUTES)], list(HOSPITAL_MINUTES))
        # The longest stay repeats rather than growing without limit.
        self.assertEqual(
            stays[len(HOSPITAL_MINUTES):],
            [HOSPITAL_MINUTES[-1]] * 3,
        )
        self.assertEqual(hospital_minutes(-1), HOSPITAL_MINUTES[0])

    def test_repayment_clears_interest_before_principal(self):
        loan = Loan(principal=10_000, interest=500)

        after = apply_repayment(loan, 700)

        self.assertEqual(after.interest, 0)
        self.assertEqual(after.principal, 9_800)

    def test_a_part_payment_only_eats_into_the_interest(self):
        loan = Loan(principal=10_000, interest=500)

        after = apply_repayment(loan, 200)

        self.assertEqual(after.interest, 300)
        self.assertEqual(after.principal, 10_000)

    def test_paying_the_balance_settles_the_loan(self):
        loan = Loan(principal=10_000, interest=500)

        self.assertTrue(apply_repayment(loan, 10_500).settled)

    def test_a_payment_counts_only_if_it_covers_the_interest(self):
        loan = Loan(principal=10_000, interest=500)

        self.assertFalse(clears_arrears(loan, 499))
        self.assertTrue(clears_arrears(loan, 500))
        self.assertTrue(clears_arrears(loan, 10_500))


class LoanValidationTests(unittest.TestCase):
    def test_borrowing_is_gated_on_level(self):
        with self.assertRaises(LoanError) as raised:
            validate_borrow(MINIMUM_LEVEL - 1, 5_000, 0)

        self.assertIn(str(MINIMUM_LEVEL), str(raised.exception))

    def test_the_floor_is_enforced(self):
        with self.assertRaises(LoanError):
            validate_borrow(10, MINIMUM_LOAN - 1, 0)

        self.assertEqual(
            validate_borrow(10, MINIMUM_LOAN, 0),
            MINIMUM_LOAN,
        )

    def test_borrowing_cannot_exceed_the_headroom(self):
        with self.assertRaises(LoanError):
            validate_borrow(10, 30_001, 20_000)

        self.assertEqual(
            validate_borrow(10, 30_000, 20_000),
            30_000,
        )

    def test_a_maxed_out_borrower_is_turned_away(self):
        with self.assertRaises(LoanError):
            validate_borrow(10, MINIMUM_LOAN, 50_000)

    def test_an_amount_must_be_a_whole_number(self):
        for bad in ("5000", 5_000.5, None, True):
            with self.assertRaises(LoanError):
                validate_borrow(10, bad, 0)

            with self.assertRaises(LoanError):
                validate_repayment(bad, 5_000, 10_000)

    def test_overpaying_settles_rather_than_being_refused(self):
        # Typing a round number to clear a small debt should pay the
        # debt, not be rejected for money that was never charged.
        self.assertEqual(
            validate_repayment(1_000_000, 3_200, 5_000),
            3_200,
        )

    def test_paying_more_than_you_carry_is_refused(self):
        with self.assertRaises(LoanError):
            validate_repayment(5_000, 20_000, 4_999)

    def test_paying_nothing_is_refused(self):
        for bad in (0, -100):
            with self.assertRaises(LoanError):
                validate_repayment(bad, 5_000, 10_000)

    def test_paying_a_debt_you_do_not_have_is_refused(self):
        with self.assertRaises(LoanError):
            validate_repayment(1_000, 0, 10_000)


class LoanBookTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = Path(self.temp_dir.name) / "loans.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        self.database_path = database_path
        create_tables()

        self.user_id = create_user("borrower", "borrower@example.com", "hash")
        create_player(self.user_id, "Borrower")
        self.set(level=10, current_district="soho", money=5_000)

    def set(self, **columns):
        assignments = ", ".join(f"{name} = ?" for name in columns)
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                f"UPDATE players SET {assignments} WHERE user_id = ?",
                (*columns.values(), self.user_id),
            )
        connection.close()

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def wind_back(self, **delta):
        """Age the loan's clock so interest has had time to accrue."""
        moved = datetime.now(timezone.utc) - timedelta(**delta)
        stamp = moved.strftime("%Y-%m-%d %H:%M:%S")
        connection = sqlite3.connect(self.database_path)
        with connection:
            connection.execute(
                """
                UPDATE player_loans
                SET interest_accrued_at = ?, due_at = ?
                WHERE player_id = (
                    SELECT id FROM players WHERE user_id = ?
                )
                """,
                (stamp, stamp, self.user_id),
            )
        connection.close()

    def test_borrowing_credits_the_cash_and_opens_the_book(self):
        taken, principal = repo.borrow(self.user_id, 20_000)

        self.assertEqual(taken, 20_000)
        self.assertEqual(principal, 20_000)
        self.assertEqual(self.player().money, 25_000)

        state = repo.get_loan(self.user_id)
        self.assertEqual(state["loan"].principal, 20_000)
        self.assertEqual(state["loan"].interest, 0)
        self.assertEqual(state["headroom"], 30_000)

    def test_interest_accrues_from_elapsed_time_alone(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=3)

        state = repo.get_loan(self.user_id)

        self.assertEqual(state["loan"].principal, 20_000)
        self.assertEqual(state["loan"].interest, 1_500)
        self.assertTrue(state["overdue"])

    def test_repaying_takes_exactly_the_money_once(self):
        repo.borrow(self.user_id, 20_000)
        before = self.player().money

        paid, after = repo.repay(self.user_id, 8_000)

        self.assertEqual(paid, 8_000)
        self.assertEqual(after.principal, 12_000)
        self.assertEqual(self.player().money, before - 8_000)

    def test_clearing_the_debt_restores_the_headroom(self):
        repo.borrow(self.user_id, 20_000)

        _paid, after = repo.repay(self.user_id, 20_000)

        self.assertTrue(after.settled)
        self.assertEqual(
            repo.get_loan(self.user_id)["headroom"],
            50_000,
        )

    def test_overpaying_only_takes_what_is_owed(self):
        repo.borrow(self.user_id, 20_000)
        before = self.player().money

        paid, after = repo.repay(self.user_id, 999_999)

        self.assertEqual(paid, 20_000)
        self.assertTrue(after.settled)
        self.assertEqual(self.player().money, before - 20_000)

    def test_a_second_loan_cannot_be_taken_while_interest_is_owed(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=3)

        with self.assertRaises(LoanError):
            repo.borrow(self.user_id, 1_000)

    def test_borrowing_is_refused_outside_soho(self):
        self.set(current_district="camden")

        with self.assertRaises(LoanError) as raised:
            repo.borrow(self.user_id, 5_000)

        self.assertIn("Soho", str(raised.exception))

    def test_a_debt_can_be_paid_from_any_district(self):
        repo.borrow(self.user_id, 5_000)
        self.set(current_district="hackney")

        paid, _after = repo.repay(self.user_id, 1_000)

        self.assertEqual(paid, 1_000)

    def test_a_failed_borrow_moves_no_money(self):
        before = self.player().money

        with self.assertRaises(LoanError):
            repo.borrow(self.user_id, MINIMUM_LOAN - 1)

        self.assertEqual(self.player().money, before)
        self.assertIsNone(repo.get_loan(self.user_id)["due_at"])

    def test_a_late_payer_is_collected_from(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=4)

        minutes = repo.collect_if_overdue(self.user_id)

        self.assertEqual(minutes, HOSPITAL_MINUTES[0])
        self.assertIsNotNone(self.player().hospital_until)

    def test_a_second_missed_payment_costs_longer(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=4)
        repo.collect_if_overdue(self.user_id)
        self.wind_back(days=4)

        self.assertEqual(
            repo.collect_if_overdue(self.user_id),
            HOSPITAL_MINUTES[1],
        )

    def test_a_payer_in_good_standing_is_left_alone(self):
        repo.borrow(self.user_id, 20_000)

        self.assertIsNone(repo.collect_if_overdue(self.user_id))
        self.assertIsNone(self.player().hospital_until)

    def test_a_player_with_no_loan_is_left_alone(self):
        self.assertIsNone(repo.collect_if_overdue(self.user_id))

    def test_covering_the_interest_buys_another_period(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=3)
        interest = repo.get_loan(self.user_id)["loan"].interest

        repo.repay(self.user_id, interest)

        self.assertFalse(repo.get_loan(self.user_id)["overdue"])
        self.assertIsNone(repo.collect_if_overdue(self.user_id))

    def test_underpaying_the_interest_does_not_buy_time(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=3)
        interest = repo.get_loan(self.user_id)["loan"].interest

        repo.repay(self.user_id, interest - 1)

        self.assertIsNotNone(repo.collect_if_overdue(self.user_id))

    def test_a_collection_never_shortens_a_stay_already_being_served(self):
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=4)
        release = datetime.now(timezone.utc) + timedelta(hours=12)
        self.set(
            hospital_until=release.strftime("%Y-%m-%d %H:%M:%S")
        )

        repo.collect_if_overdue(self.user_id)

        # The half-hour Ronnie would have added must not cut a stay
        # that already runs twelve hours.
        held_until = datetime.fromisoformat(
            self.player().hospital_until.replace("Z", "+00:00")
        )
        self.assertGreater(
            held_until,
            datetime.now(timezone.utc) + timedelta(hours=6),
        )

    def test_the_book_records_every_movement(self):
        repo.borrow(self.user_id, 20_000)
        repo.repay(self.user_id, 5_000)

        kinds = [row[0] for row in repo.recent_transactions(self.user_id)]

        self.assertEqual(kinds, ["repay", "borrow"])

    def test_a_settled_loan_remembers_the_missed_payments(self):
        # Paying up must not wipe the record; a defaulter who clears the
        # book and borrows again starts from the stay they earned.
        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=4)
        repo.collect_if_overdue(self.user_id)
        # Walk out of hospital; the point under test is the record the
        # book keeps, not the stay that earned it.
        self.set(money=100_000, hospital_until=None)
        repo.repay(self.user_id, 999_999)

        repo.borrow(self.user_id, 20_000)
        self.wind_back(days=4)

        self.assertEqual(
            repo.collect_if_overdue(self.user_id),
            HOSPITAL_MINUTES[1],
        )


class LoanSharkPortraitTests(unittest.TestCase):
    """His face is a file, not a declaration.

    The page has to read correctly both before the artwork exists and
    after, so the portrait is resolved once at import and falls back to
    his initials. These hold both halves of that.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            pathlib.Path(self.temp_dir.name) / "portrait.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from web.application import app

        self.app = app
        app.config["SECRET_KEY"] = "portrait-test"
        self.user_id = create_user("looker", "looker@example.com", "hash")
        create_player(self.user_id, "Looker")
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def page(self):
        return self.client.get("/loanshark").get_data(as_text=True)

    def test_initials_stand_in_until_the_artwork_lands(self):
        with patch("web.application._LOAN_SHARK_PORTRAIT", None):
            rendered = self.page()

        self.assertIn(">RD<", rendered)
        self.assertNotIn("ronnie-dell", rendered)

    def test_the_artwork_is_shown_once_it_exists(self):
        from web.application import LOAN_SHARK_PORTRAIT

        with patch(
            "web.application._LOAN_SHARK_PORTRAIT",
            LOAN_SHARK_PORTRAIT,
        ):
            rendered = self.page()

        self.assertIn(LOAN_SHARK_PORTRAIT, rendered)
        self.assertIn('alt="Ronnie Dell"', rendered)

    def test_the_portrait_folder_is_where_it_is_looked_for(self):
        from web.application import LOAN_SHARK_PORTRAIT

        # The fallback is silent, so a renamed folder would never be
        # noticed. Pin the directory the file is expected to land in.
        folder = (
            pathlib.Path(self.app.static_folder) / LOAN_SHARK_PORTRAIT
        ).parent

        self.assertTrue(
            folder.is_dir(),
            f"{folder} does not exist, so the portrait can never load",
        )


if __name__ == "__main__":
    unittest.main()
