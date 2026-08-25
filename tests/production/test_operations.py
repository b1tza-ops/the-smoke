import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.operations import (
    get_campaign,
    resolve_operation,
    start_operation,
)
from database.repositories.players import (
    get_player_by_user_id,
    save_player,
)
from database.repositories.players import create_player
from database.repositories.prologue import (
    choose_background,
    get_or_create_prologue,
)
from database.repositories.users import create_user
from game.operations import CAMPAIGN, get_operation
from game.player import Player


class OperationCampaignTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()
        self.user_id = create_user(
            "operative",
            "operative@example.com",
            "hash",
        )
        create_player(self.user_id, "Operative")
        get_or_create_prologue(self.user_id)
        choose_background(self.user_id, "street_hustler")

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def equip(self, **fields):
        player = self.player()

        for name, value in fields.items():
            setattr(player, name, value)

        save_player(player)
        return player

    def make_ready(self, operation_key):
        connection = get_connection()
        connection.execute(
            """
            UPDATE player_operations
            SET ready_at = DATETIME(CURRENT_TIMESTAMP, '-1 second')
            WHERE user_id = ? AND operation_key = ?
            """,
            (self.user_id, operation_key),
        )
        connection.commit()
        connection.close()

    def stage_of(self, operation_key):
        for status in get_campaign(self.user_id):
            if status.operation.key == operation_key:
                return status

        raise AssertionError(f"{operation_key} is not in the campaign")

    def run_operation(self, operation_key, approach_key):
        start_operation(self.user_id, operation_key, approach_key)
        self.make_ready(operation_key)
        return resolve_operation(self.user_id, operation_key)

    def test_the_campaign_has_five_operations_in_order(self):
        statuses = get_campaign(self.user_id)

        self.assertEqual(len(statuses), 5)
        self.assertEqual(
            [status.operation.key for status in statuses],
            [operation.key for operation in CAMPAIGN],
        )

    def test_only_the_first_operation_starts_unlocked(self):
        statuses = get_campaign(self.user_id)

        self.assertEqual(statuses[0].stage, "available")
        self.assertTrue(
            all(status.stage == "locked" for status in statuses[1:])
        )
        self.assertEqual(
            statuses[1].lock_reason,
            "Complete The Camden Collection first",
        )

    def test_an_operation_runs_then_pays_down_the_debt(self):
        operation, approach, paydown = self.run_operation(
            "camden_collection",
            "slip_through_back",
        )

        self.assertEqual(approach.style, "Stealth")
        self.assertEqual(paydown, 425)
        self.assertEqual(
            get_or_create_prologue(self.user_id)["debt_remaining"],
            1575,
        )

        status = self.stage_of("camden_collection")
        self.assertEqual(status.stage, "completed")
        self.assertEqual(status.paydown, 425)
        self.assertEqual(status.outcome_text, approach.outcome)

    def test_an_operation_cannot_be_resolved_before_it_is_ready(self):
        start_operation(
            self.user_id,
            "camden_collection",
            "talk_your_way_in",
        )

        with self.assertRaises(ValueError):
            resolve_operation(self.user_id, "camden_collection")

        self.assertEqual(
            self.stage_of("camden_collection").stage,
            "active",
        )

    def test_only_one_operation_runs_at_a_time(self):
        self.equip(level=3, current_district="camden")
        start_operation(
            self.user_id,
            "camden_collection",
            "talk_your_way_in",
        )

        self.assertEqual(
            self.stage_of("soho_favour").lock_reason,
            "Complete The Camden Collection first",
        )

        with self.assertRaises(ValueError):
            start_operation(
                self.user_id,
                "camden_collection",
                "force_the_door",
            )

    def test_the_next_operation_needs_its_level_and_district(self):
        self.run_operation("camden_collection", "talk_your_way_in")

        self.assertEqual(
            self.stage_of("soho_favour").lock_reason,
            "Reach level 3",
        )

        self.equip(level=3)
        self.assertEqual(
            self.stage_of("soho_favour").lock_reason,
            "Travel to Soho",
        )

        self.equip(current_district="soho", dexterity=20)
        self.assertEqual(self.stage_of("soho_favour").stage, "available")

    def test_an_approach_below_its_requirement_is_refused(self):
        self.equip(strength=8)

        with self.assertRaises(ValueError) as refusal:
            start_operation(
                self.user_id,
                "camden_collection",
                "force_the_door",
            )

        self.assertIn("strength", str(refusal.exception))

    def test_resolving_an_operation_levels_the_player_up(self):
        self.equip(xp=580, level=3)

        self.run_operation("camden_collection", "slip_through_back")

        player = self.player()
        self.assertEqual(player.xp, 620)
        # 600 XP is level 4, and the health ceiling moves with it.
        self.assertEqual(player.level, 4)
        self.assertEqual(player.max_health, 130)

    def test_the_finale_clears_whatever_debt_is_left(self):
        finale = CAMPAIGN[-1]

        for operation in CAMPAIGN[:-1]:
            self.equip(
                level=operation.required_level,
                current_district=operation.district,
                energy=150,
                nerve=25,
                strength=40,
                speed=40,
                dexterity=40,
            )
            self.run_operation(
                operation.key,
                operation.approaches[0].key,
            )

        debt_before = get_or_create_prologue(
            self.user_id
        )["debt_remaining"]
        self.assertGreater(debt_before, 0)

        self.equip(
            level=finale.required_level,
            current_district=finale.district,
            energy=150,
            nerve=25,
            strength=40,
            speed=40,
            dexterity=40,
        )
        _, _, paydown = self.run_operation(
            finale.key,
            finale.approaches[0].key,
        )

        self.assertEqual(paydown, debt_before)
        self.assertEqual(
            get_or_create_prologue(self.user_id)["debt_remaining"],
            0,
        )

    def test_an_unknown_operation_or_approach_is_refused(self):
        with self.assertRaises(ValueError):
            start_operation(self.user_id, "not_an_operation", "x")

        with self.assertRaises(ValueError):
            start_operation(
                self.user_id,
                "camden_collection",
                "not_an_approach",
            )

    def test_an_operation_cannot_start_from_jail_or_hospital(self):
        self.equip(jail_until="2099-01-01 00:00:00")

        with self.assertRaises(ValueError):
            start_operation(
                self.user_id,
                "camden_collection",
                "talk_your_way_in",
            )

        self.equip(jail_until=None, hospital_until="2099-01-01 00:00:00")

        with self.assertRaises(ValueError):
            start_operation(
                self.user_id,
                "camden_collection",
                "talk_your_way_in",
            )

    def test_starting_an_operation_spends_energy_and_nerve(self):
        before = self.player()

        start_operation(
            self.user_id,
            "camden_collection",
            "slip_through_back",
        )

        approach = get_operation(
            "camden_collection"
        ).approach_for("slip_through_back")
        after = self.player()

        self.assertEqual(after.energy, before.energy - approach.energy)
        self.assertEqual(after.nerve, before.nerve - approach.nerve)


class CampaignBackfillTests(unittest.TestCase):
    """The Camden Collection players already ran must carry across."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def build_at_migration_31(self):
        import database.core.migrations as migrations

        full = migrations.MIGRATIONS
        migrations.MIGRATIONS = tuple(
            migration
            for migration in full
            if migration.version < 32
        )
        try:
            create_tables()
        finally:
            migrations.MIGRATIONS = full

        return full

    def test_a_completed_prologue_becomes_a_completed_operation(self):
        import database.core.migrations as migrations

        self.build_at_migration_31()

        user_id = create_user("veteran", "veteran@example.com", "hash")
        create_player(user_id, "Veteran")
        get_or_create_prologue(user_id)

        connection = get_connection()
        connection.execute(
            """
            UPDATE player_prologue
            SET background = 'street_hustler',
                operation_stage = 'completed',
                operation_approach = 'force_the_door',
                operation_started_at = CURRENT_TIMESTAMP,
                completed_at = CURRENT_TIMESTAMP,
                outcome_text = 'The door gave way.',
                debt_remaining = 1450
            WHERE user_id = ?
            """,
            (user_id,),
        )
        connection.commit()
        connection.close()

        # Everything from the build point onwards, which is at least
        # the campaign migration this test is about.
        self.assertIn(32, migrations.run_migrations())

        camden, soho = get_campaign(user_id)[:2]

        self.assertEqual(camden.stage, "completed")
        self.assertEqual(camden.approach_key, "force_the_door")
        self.assertEqual(camden.outcome_text, "The door gave way.")
        self.assertEqual(camden.paydown, 550)
        # The campaign carries straight on from where they stopped.
        self.assertEqual(soho.lock_reason, "Reach level 3")

    def test_a_player_who_never_started_is_left_alone(self):
        import database.core.migrations as migrations

        self.build_at_migration_31()

        user_id = create_user("rookie", "rookie@example.com", "hash")
        create_player(user_id, "Rookie")
        get_or_create_prologue(user_id)

        migrations.run_migrations()

        statuses = get_campaign(user_id)

        self.assertEqual(statuses[0].stage, "available")
        self.assertEqual(statuses[0].paydown, 0)


if __name__ == "__main__":
    unittest.main()
