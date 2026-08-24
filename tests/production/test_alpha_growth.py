import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories.growth import (
    apply_referral,
    get_growth_profile,
    get_recent_feedback,
    submit_feedback,
)
from database.repositories.users import create_user


class AlphaGrowthPersistenceTests(unittest.TestCase):
    def test_invites_founder_badges_and_feedback_persist(self):
        with tempfile.TemporaryDirectory() as temp:
            database = Path(temp) / "game.db"

            with patch(
                "database.core.connection.DB_PATH",
                database,
            ):
                create_tables()
                inviter_id = create_user(
                    "founder",
                    "founder@example.com",
                    "hash",
                )
                invite = get_growth_profile(inviter_id)
                self.assertTrue(
                    invite["is_founding_player"]
                )
                self.assertEqual(
                    len(invite["invite_code"]),
                    8,
                )

                recruit_id = create_user(
                    "recruit",
                    "recruit@example.com",
                    "hash",
                )
                self.assertTrue(apply_referral(
                    recruit_id,
                    invite["invite_code"].lower(),
                ))
                self.assertEqual(
                    get_growth_profile(
                        inviter_id
                    )["referral_count"],
                    1,
                )

                feedback_id = submit_feedback(
                    recruit_id,
                    "bug",
                    "The training result was confusing.",
                    "/gym",
                )
                self.assertGreater(feedback_id, 0)
                feedback = get_recent_feedback()
                self.assertEqual(len(feedback), 1)
                self.assertEqual(feedback[0][1], "recruit")
                self.assertEqual(feedback[0][2], "bug")
                self.assertEqual(feedback[0][4], "/gym")

    def test_feedback_validation_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            submit_feedback(1, "invalid", "Long enough message")

        with self.assertRaises(ValueError):
            submit_feedback(1, "bug", "short")


if __name__ == "__main__":
    unittest.main()
