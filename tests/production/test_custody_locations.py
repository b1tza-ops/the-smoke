import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.hospital import (
    get_hospital_patients,
)
from database.repositories.jail import (
    attempt_jail_break,
    bail_out_inmate,
    calculate_bail_cost,
    get_jail_inmates,
)
from database.repositories.players import create_player
from database.repositories.users import create_user
from game.crime import CRIMES_BY_KEY


class CustodyLocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database_patch = patch(
            "database.core.connection.DB_PATH",
            Path(self.temp.name) / "game.db",
        )
        self.database_patch.start()
        create_tables()

        self.patient_user = create_user(
            "patient",
            "patient@example.com",
            "hash",
        )
        self.inmate_user = create_user(
            "inmate",
            "inmate@example.com",
            "hash",
        )
        self.expired_user = create_user(
            "expired",
            "expired@example.com",
            "hash",
        )
        create_player(self.patient_user, "Patient")
        create_player(self.inmate_user, "Inmate")
        create_player(self.expired_user, "Expired")

    def tearDown(self):
        self.database_patch.stop()
        self.temp.cleanup()

    def admit_inmate(self, minutes=2):
        connection = get_connection()
        connection.execute(
            """
            UPDATE players
            SET jail_until = DATETIME(
                CURRENT_TIMESTAMP,
                ?
            )
            WHERE user_id = ?
            """,
            (f"+{minutes} minutes", self.inmate_user),
        )
        inmate_id = connection.execute(
            "SELECT id FROM players WHERE user_id = ?",
            (self.inmate_user,),
        ).fetchone()[0]
        connection.commit()
        connection.close()
        return inmate_id

    def test_sentence_severity_and_bail_scale_together(self):
        self.assertEqual(
            CRIMES_BY_KEY[
                "camden_shoplift"
            ].jail_seconds,
            10 * 60,
        )
        self.assertEqual(
            CRIMES_BY_KEY[
                "soho_nightclub"
            ].jail_seconds,
            3 * 24 * 60 * 60,
        )

        short_bail = calculate_bail_cost(
            level=1,
            remaining_seconds=10 * 60,
        )
        severe_bail = calculate_bail_cost(
            level=1,
            remaining_seconds=3 * 24 * 60 * 60,
        )

        self.assertEqual(short_bail, 250)
        self.assertEqual(severe_bail, 43300)
        self.assertGreater(severe_bail, short_bail)

    def test_player_can_pay_another_players_bail(self):
        inmate_id = self.admit_inmate()
        result = bail_out_inmate(
            self.expired_user,
            inmate_id,
        )

        self.assertTrue(result["success"])
        self.assertGreater(result["cost"], 0)

        connection = get_connection()
        helper_money = connection.execute(
            "SELECT money FROM players WHERE user_id = ?",
            (self.expired_user,),
        ).fetchone()[0]
        inmate_until = connection.execute(
            "SELECT jail_until FROM players WHERE id = ?",
            (inmate_id,),
        ).fetchone()[0]
        connection.close()

        self.assertEqual(
            helper_money,
            500 - result["cost"],
        )
        self.assertIsNone(inmate_until)

    def test_successful_breakout_spends_nerve_and_releases(self):
        inmate_id = self.admit_inmate()
        rng = Mock()
        rng.randint.return_value = 1

        result = attempt_jail_break(
            self.expired_user,
            inmate_id,
            rng=rng,
        )

        self.assertTrue(result["success"])
        connection = get_connection()
        helper_nerve = connection.execute(
            "SELECT nerve FROM players WHERE user_id = ?",
            (self.expired_user,),
        ).fetchone()[0]
        inmate_until = connection.execute(
            "SELECT jail_until FROM players WHERE id = ?",
            (inmate_id,),
        ).fetchone()[0]
        connection.close()

        self.assertEqual(helper_nerve, 15)
        self.assertIsNone(inmate_until)

    def test_caught_breakout_adds_wanted_and_jails_helper(self):
        inmate_id = self.admit_inmate()
        rng = Mock()
        rng.randint.return_value = 100

        result = attempt_jail_break(
            self.expired_user,
            inmate_id,
            rng=rng,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["consequence"], "caught")

        connection = get_connection()
        helper = connection.execute(
            """
            SELECT nerve, wanted_level, jail_until
            FROM players
            WHERE user_id = ?
            """,
            (self.expired_user,),
        ).fetchone()
        inmate_until = connection.execute(
            "SELECT jail_until FROM players WHERE id = ?",
            (inmate_id,),
        ).fetchone()[0]
        connection.close()

        self.assertEqual(helper[0], 15)
        self.assertEqual(helper[1], 3)
        self.assertIsNotNone(helper[2])
        self.assertIsNotNone(inmate_until)

    def test_live_hospital_and_jail_registers(self):
        connection = get_connection()
        connection.execute(
            """
            UPDATE players
            SET hospital_until = DATETIME(
                CURRENT_TIMESTAMP,
                '+5 minutes'
            )
            WHERE user_id = ?
            """,
            (self.patient_user,),
        )
        connection.execute(
            """
            UPDATE players
            SET jail_until = DATETIME(
                CURRENT_TIMESTAMP,
                '+8 minutes'
            ),
                wanted_level = 12
            WHERE user_id = ?
            """,
            (self.inmate_user,),
        )
        connection.execute(
            """
            UPDATE players
            SET hospital_until = DATETIME(
                CURRENT_TIMESTAMP,
                '-1 minute'
            ),
                jail_until = DATETIME(
                    CURRENT_TIMESTAMP,
                    '-1 minute'
                )
            WHERE user_id = ?
            """,
            (self.expired_user,),
        )
        connection.commit()
        connection.close()

        patients = get_hospital_patients()
        inmates = get_jail_inmates()

        self.assertEqual(
            [patient["name"] for patient in patients],
            ["Patient"],
        )
        self.assertGreater(
            patients[0]["remaining_seconds"],
            0,
        )
        self.assertEqual(
            [inmate["name"] for inmate in inmates],
            ["Inmate"],
        )
        self.assertEqual(inmates[0]["wanted_level"], 12)
        self.assertGreater(
            inmates[0]["remaining_seconds"],
            0,
        )


if __name__ == "__main__":
    unittest.main()
