import unittest
from datetime import datetime, timezone

from game.combat.contracts import (
    daily_contracts,
    daily_key,
    reset_seconds,
)


class PvpContractTests(unittest.TestCase):
    def test_every_day_has_three_unique_contracts(self):
        now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
        contracts = daily_contracts(now)
        self.assertEqual(len(contracts), 3)
        self.assertEqual(len({item.key for item in contracts}), 3)

    def test_rotation_is_stable_for_the_same_day(self):
        morning = datetime(2026, 8, 24, 1, tzinfo=timezone.utc)
        evening = datetime(2026, 8, 24, 23, tzinfo=timezone.utc)
        self.assertEqual(
            daily_contracts(morning),
            daily_contracts(evening),
        )
        self.assertEqual(daily_key(morning), "2026-08-24")

    def test_countdown_uses_one_global_utc_reset(self):
        now = datetime(2026, 8, 24, 23, 59, tzinfo=timezone.utc)
        self.assertEqual(reset_seconds(now), 60)


if __name__ == "__main__":
    unittest.main()
