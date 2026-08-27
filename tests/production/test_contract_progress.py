"""Daily contracts, and who can actually finish them.

The board pays £244,000 a year and was worth exactly £0. Progress was
only ever recorded from the player-versus-player route, so a fight
against a street opponent counted for nothing -- and on a server with
almost nobody logged in there is rarely anyone to attack. Four of the
eight contracts also demand a combat approach, which only exists in a
player fight, so 31 days a year rolled a board that no solo player could
touch even in principle.

Street fights now count. The approach contracts stay player-only,
because picking Aggressive or Evasive is a choice that does not exist
against a street opponent, but a day can never again be made entirely
of them.
"""

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from database.core.setup import create_tables
from game.combat.contracts import (
    CONTRACT_POOL,
    CONTRACTS_BY_KEY,
    MINIMUM_SOLO_CONTRACTS,
    daily_contracts,
)


def street_fight(victory=True, cash=0):
    """What game.combat.npc returns -- note `cash_reward`."""
    return SimpleNamespace(
        victory=victory,
        cash_reward=cash,
        opponent_key="market_runner",
    )


def player_fight(victory=True, cash=0):
    """What game.combat.pvp returns -- note `cash_stolen`."""
    return SimpleNamespace(victory=victory, cash_stolen=cash)


class TheBoardIsAlwaysWinnableTests(unittest.TestCase):
    def test_no_day_is_made_entirely_of_player_only_contracts(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for offset in range(365):
            day = start + timedelta(days=offset)
            with self.subTest(day=day.date().isoformat()):
                solo = [
                    contract for contract in daily_contracts(day)
                    if not contract.needs_another_player
                ]
                self.assertGreaterEqual(
                    len(solo),
                    MINIMUM_SOLO_CONTRACTS,
                    "a solo player cannot finish this board",
                )

    def test_a_day_still_has_three_different_contracts(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)

        for offset in range(365):
            day = start + timedelta(days=offset)
            with self.subTest(day=day.date().isoformat()):
                keys = {c.key for c in daily_contracts(day)}
                self.assertEqual(len(keys), 3)

    def test_the_board_is_the_same_all_day(self):
        morning = datetime(2026, 8, 24, 1, tzinfo=timezone.utc)
        evening = datetime(2026, 8, 24, 23, tzinfo=timezone.utc)

        self.assertEqual(
            daily_contracts(morning),
            daily_contracts(evening),
        )

    def test_player_only_contracts_can_still_come_up(self):
        """The guarantee must not quietly delete half the pool."""
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        seen = set()

        for offset in range(365):
            seen.update(
                contract.key
                for contract in daily_contracts(start + timedelta(days=offset))
            )

        self.assertEqual(seen, {c.key for c in CONTRACT_POOL})


class ProgressTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp_dir.name) / "contracts.db",
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user_id = create_user("fighter", "f@example.com", "hash")
        create_player(self.user_id, "Fighter")

        connection = __import__("sqlite3").connect(
            Path(self.temp_dir.name) / "contracts.db"
        )
        self.player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (self.user_id,)
        ).fetchone()[0]
        connection.close()

    def progress(self, contract_key, now):
        from database.repositories.pvp_contracts import get_contract_board

        board = get_contract_board(self.player_id, now=now)
        for state in board.contracts:
            if state.contract.key == contract_key:
                return state.progress
        return None

    def day_running(self, contract_key):
        """A day whose board contains the contract we want to test."""
        start = datetime(2026, 1, 1, 12, tzinfo=timezone.utc)
        for offset in range(365):
            day = start + timedelta(days=offset)
            if any(c.key == contract_key for c in daily_contracts(day)):
                return day
        raise AssertionError(f"{contract_key} never comes up")

    def record(self, result, now, approach=None):
        from database.repositories.pvp_contracts import record_contract_fight

        record_contract_fight(
            self.player_id, result, approach=approach, now=now
        )

    # ------------------------------------------- the bug this fixes

    def test_a_street_fight_counts_towards_a_win_contract(self):
        day = self.day_running("first_blood")

        self.record(street_fight(victory=True), day)

        self.assertEqual(self.progress("first_blood", day), 1)

    def test_a_street_fight_counts_towards_an_attempt_contract(self):
        day = self.day_running("street_patrol")

        for _ in range(3):
            self.record(street_fight(victory=False), day)

        self.assertEqual(self.progress("street_patrol", day), 3)

    def test_street_fight_cash_counts_even_though_the_field_differs(self):
        """`cash_reward` on a street fight, `cash_stolen` on a player one."""
        day = self.day_running("cash_run")

        self.record(street_fight(victory=True, cash=60), day)

        self.assertEqual(self.progress("cash_run", day), 60)

    def test_a_player_fight_still_counts(self):
        day = self.day_running("cash_run")

        self.record(player_fight(victory=True, cash=75), day, "aggressive")

        self.assertEqual(self.progress("cash_run", day), 75)

    def test_losing_moves_attempts_but_not_wins(self):
        day = self.day_running("first_blood")

        self.record(street_fight(victory=False), day)

        self.assertEqual(self.progress("first_blood", day), 0)

    # ------------------------------- what stays behind another player

    def test_a_street_fight_never_satisfies_an_approach_contract(self):
        day = self.day_running("go_loud")

        self.record(street_fight(victory=True), day)

        self.assertEqual(self.progress("go_loud", day), 0)

    def test_the_right_approach_in_a_player_fight_does(self):
        day = self.day_running("go_loud")

        self.record(player_fight(victory=True), day, "aggressive")

        self.assertEqual(self.progress("go_loud", day), 1)

    def test_the_wrong_approach_does_not(self):
        day = self.day_running("go_loud")

        self.record(player_fight(victory=True), day, "evasive")

        self.assertEqual(self.progress("go_loud", day), 0)

    def test_an_unrated_player_attack_still_earns_nothing(self):
        from database.repositories.pvp_contracts import record_contract_fight

        day = self.day_running("first_blood")

        record_contract_fight(
            self.player_id,
            player_fight(victory=True),
            approach="aggressive",
            rated=False,
            now=day,
        )

        self.assertEqual(self.progress("first_blood", day), 0)

    # ------------------------------------------------------ claiming

    def test_a_contract_finished_on_street_fights_pays_out(self):
        from database.repositories.pvp_contracts import claim_contract

        day = self.day_running("first_blood")
        contract = CONTRACTS_BY_KEY["first_blood"]

        self.record(street_fight(victory=True), day)
        claim = claim_contract(self.player_id, "first_blood", now=day)

        self.assertEqual(claim.cash_reward, contract.cash_reward)


class ThroughTheFightPageTests(unittest.TestCase):
    """The half the unit tests above cannot see.

    The recorder was always capable of crediting a street fight. The bug
    was that the street-fight route never called it, so every test that
    exercised the recorder directly passed while the feature did
    nothing. This drives the actual page.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.database_path = Path(self.temp_dir.name) / "fight.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            self.database_path,
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        from database.repositories.players import create_player
        from database.repositories.users import create_user

        self.user_id = create_user("brawler", "b@example.com", "hash")
        create_player(self.user_id, "Brawler")

        import sqlite3

        connection = sqlite3.connect(self.database_path)
        with connection:
            # Strong enough to win, with the energy to do it repeatedly.
            connection.execute(
                """
                UPDATE players
                SET strength = 200, defence = 200, speed = 200,
                    dexterity = 200, energy = 150, health = 100,
                    current_district = 'camden'
                WHERE user_id = ?
                """,
                (self.user_id,),
            )
        self.player_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (self.user_id,)
        ).fetchone()[0]
        connection.close()

        from web.application import app

        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def board(self):
        from database.repositories.pvp_contracts import get_contract_board

        return get_contract_board(self.player_id)

    def test_fighting_in_the_street_moves_the_contract_board(self):
        before = sum(state.progress for state in self.board().contracts)

        response = self.client.post(
            "/fight", data={"opponent_key": "market_runner"}
        )

        self.assertEqual(response.status_code, 200)

        after = sum(state.progress for state in self.board().contracts)
        self.assertGreater(
            after,
            before,
            "a street fight was fought and no contract moved at all",
        )

    def test_the_board_only_moves_for_contracts_a_street_fight_can_serve(self):
        self.client.post("/fight", data={"opponent_key": "market_runner"})

        for state in self.board().contracts:
            if state.contract.needs_another_player:
                with self.subTest(contract=state.contract.key):
                    self.assertEqual(
                        state.progress,
                        0,
                        "a street fight satisfied a player-only contract",
                    )

    def test_a_refused_fight_records_nothing(self):
        before = sum(state.progress for state in self.board().contracts)

        self.client.post("/fight", data={"opponent_key": "not_a_real_one"})

        after = sum(state.progress for state in self.board().contracts)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
