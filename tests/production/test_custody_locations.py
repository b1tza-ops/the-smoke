import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.connection import get_connection
from database.core.setup import create_tables
from database.repositories.hospital import (
    get_hospital_patients,
)
from database.repositories.jail import get_jail_inmates
from database.repositories.players import create_player
from database.repositories.users import create_user


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
