from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from game.world.districts import DISTRICTS_BY_KEY
from game.jobs import (
    CAREERS,
    SHIFT_SECONDS,
    AlreadyEmployedError,
    CareerLocationError,
    InsufficientEnergyError,
    JobRestrictedError,
    NoShiftError,
    ShiftAlreadyActiveError,
    ShiftNotCompleteError,
    cancel_shift,
    complete_shift,
    get_job_role,
    get_shift_state,
    join_career,
    start_shift,
)


class JobSystemTests(unittest.TestCase):
    def make_player(self, **overrides):
        values = {
            "level": 1,
            "xp": 0,
            "money": 500,
            "energy": 100,
            "career_key": None,
            "job_role_key": None,
            "career_xp": 0,
            "shifts_completed": 0,
            "shift_started_at": None,
            "shift_until": None,
            "current_district": "camden",
            "travel_destination": None,
            "travel_until": None,
            "wanted_level": 0,
            "last_wanted_update": None,
            "jail_until": None,
            "hospital_until": None,
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def setUp(self):
        self.now = datetime(
            2026,
            8,
            24,
            9,
            0,
            tzinfo=timezone.utc,
        )

    def test_player_can_join_construction_career(self):
        player = self.make_player()

        result = join_career(
            player,
            "construction",
        )

        self.assertEqual(result.career_key, "construction")
        self.assertEqual(
            player.job_role_key,
            "construction_labourer",
        )
        self.assertEqual(player.career_xp, 0)
        self.assertEqual(player.shifts_completed, 0)

    def test_player_cannot_join_second_career(self):
        player = self.make_player(
            career_key="construction",
            job_role_key="construction_labourer",
        )

        with self.assertRaises(AlreadyEmployedError):
            join_career(player, "construction")

    def test_shift_takes_three_hours_and_spends_energy(self):
        player = self.make_player()
        join_career(player, "construction")

        result = start_shift(
            player,
            now=self.now,
        )

        self.assertEqual(SHIFT_SECONDS, 10_800)
        self.assertEqual(player.energy, 90)
        self.assertEqual(
            result.started_at,
            "2026-08-24 09:00:00",
        )
        self.assertEqual(
            result.completes_at,
            "2026-08-24 12:00:00",
        )

        state = get_shift_state(
            player,
            now=self.now + timedelta(hours=1),
        )

        self.assertEqual(state.remaining_seconds, 7_200)
        self.assertFalse(state.ready_to_complete)

    def test_shift_cannot_be_claimed_early(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)

        with self.assertRaises(ShiftNotCompleteError):
            complete_shift(
                player,
                now=self.now + timedelta(hours=2),
            )

        self.assertEqual(player.money, 500)
        self.assertEqual(player.career_xp, 0)
        self.assertEqual(player.shifts_completed, 0)

    def test_completed_shift_pays_once_and_awards_xp(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)

        result = complete_shift(
            player,
            now=self.now + timedelta(hours=3),
        )

        self.assertEqual(result.salary, 120)
        self.assertEqual(result.work_xp, 15)
        self.assertEqual(player.money, 620)
        self.assertEqual(player.xp, 15)
        self.assertEqual(player.career_xp, 15)
        self.assertEqual(player.shifts_completed, 1)
        self.assertIsNone(player.shift_started_at)
        self.assertIsNone(player.shift_until)

        with self.assertRaises(NoShiftError):
            complete_shift(
                player,
                now=self.now + timedelta(hours=4),
            )

        self.assertEqual(player.money, 620)

    def test_player_is_promoted_when_requirements_are_met(self):
        player = self.make_player(
            level=2,
            xp=100,
            career_key="construction",
            job_role_key="construction_labourer",
            career_xp=45,
            shifts_completed=3,
        )
        start_shift(player, now=self.now)

        result = complete_shift(
            player,
            now=self.now + timedelta(hours=3),
        )

        self.assertEqual(
            result.promoted_to,
            "skilled_labourer",
        )
        self.assertEqual(
            player.job_role_key,
            "skilled_labourer",
        )
        self.assertEqual(player.career_xp, 60)
        self.assertEqual(player.shifts_completed, 4)

    def test_every_career_is_defined_once(self):
        keys = [career.key for career in CAREERS]

        self.assertEqual(
            set(keys),
            {
                "construction",
                "hospitality",
                "transport",
                "creative",
                "security",
            },
        )
        self.assertEqual(len(keys), len(set(keys)))

    def test_district_careers_name_a_real_district(self):
        for career in CAREERS:
            if career.required_district is None:
                continue

            with self.subTest(career=career.key):
                self.assertIn(career.required_district, DISTRICTS_BY_KEY)

    def test_player_can_join_hospitality_career_in_soho(self):
        player = self.make_player(current_district="soho")

        result = join_career(player, "hospitality")

        self.assertEqual(result.career_key, "hospitality")
        self.assertEqual(player.job_role_key, "bar_back")

    def test_hospitality_career_requires_soho(self):
        player = self.make_player(current_district="camden")

        with self.assertRaises(CareerLocationError):
            join_career(player, "hospitality")

        self.assertIsNone(player.career_key)

    def test_transport_career_has_no_district_requirement(self):
        for district in ("camden", "brixton", "soho"):
            with self.subTest(district=district):
                player = self.make_player(
                    current_district=district,
                )

                result = join_career(player, "transport")

                self.assertEqual(
                    result.career_key,
                    "transport",
                )
                self.assertEqual(
                    player.job_role_key,
                    "courier_rider",
                )

    def test_hospitality_shift_pays_and_can_promote(self):
        player = self.make_player(
            current_district="soho",
            level=2,
            xp=100,
            career_key="hospitality",
            job_role_key="bar_back",
            career_xp=45,
            shifts_completed=3,
        )
        start_shift(player, now=self.now)

        result = complete_shift(
            player,
            now=self.now + timedelta(hours=3),
        )

        self.assertEqual(result.salary, 110)
        self.assertEqual(result.promoted_to, "bartender")
        self.assertEqual(player.job_role_key, "bartender")

    def test_transport_shift_pays_and_can_promote(self):
        player = self.make_player(
            level=2,
            xp=100,
            career_key="transport",
            job_role_key="courier_rider",
            career_xp=45,
            shifts_completed=3,
        )
        start_shift(player, now=self.now)

        result = complete_shift(
            player,
            now=self.now + timedelta(hours=3),
        )

        self.assertEqual(result.salary, 130)
        self.assertEqual(result.promoted_to, "delivery_driver")
        self.assertEqual(player.job_role_key, "delivery_driver")

    def test_leaving_early_pays_for_the_time_worked(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)
        role = get_job_role("construction_labourer")

        result = cancel_shift(
            player,
            now=self.now + timedelta(hours=1),
        )

        # One hour of a three-hour shift.
        self.assertEqual(result.percent_worked, 33)
        self.assertEqual(result.salary, role.salary // 3)
        self.assertEqual(result.work_xp, role.work_xp // 3)
        self.assertEqual(player.money, 500 + result.salary)
        self.assertEqual(player.career_xp, result.work_xp)
        self.assertIsNone(player.shift_started_at)
        self.assertIsNone(player.shift_until)

    def test_leaving_early_does_not_count_as_a_completed_shift(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)

        cancel_shift(player, now=self.now + timedelta(hours=2))

        self.assertEqual(player.shifts_completed, 0)

    def test_leaving_immediately_pays_nothing(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)

        result = cancel_shift(player, now=self.now)

        self.assertEqual(result.salary, 0)
        self.assertEqual(result.work_xp, 0)
        self.assertEqual(result.percent_worked, 0)
        self.assertEqual(player.money, 500)

    def test_leaving_early_never_pays_more_than_the_full_shift(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)
        role = get_job_role("construction_labourer")

        result = cancel_shift(
            player,
            now=self.now + timedelta(days=2),
        )

        self.assertEqual(result.salary, role.salary)
        self.assertEqual(result.percent_worked, 100)

    def test_leaving_early_is_worse_than_finishing(self):
        """The whole point: seeing a shift through always wins."""
        quitter = self.make_player()
        join_career(quitter, "construction")
        start_shift(quitter, now=self.now)
        cancel_shift(quitter, now=self.now + timedelta(hours=2))

        grafter = self.make_player()
        join_career(grafter, "construction")
        start_shift(grafter, now=self.now)
        complete_shift(grafter, now=self.now + timedelta(hours=3))

        self.assertLess(quitter.money, grafter.money)
        self.assertLess(quitter.career_xp, grafter.career_xp)
        self.assertLess(
            quitter.shifts_completed, grafter.shifts_completed,
        )
        self.assertEqual(quitter.energy, grafter.energy)

    def test_leaving_early_can_still_trigger_a_promotion(self):
        player = self.make_player(
            level=2,
            xp=100,
            career_key="construction",
            job_role_key="construction_labourer",
            career_xp=55,
            shifts_completed=4,
        )
        start_shift(player, now=self.now)

        result = cancel_shift(
            player,
            now=self.now + timedelta(hours=2),
        )

        self.assertEqual(result.promoted_to, "skilled_labourer")
        self.assertEqual(player.job_role_key, "skilled_labourer")

    def test_cannot_leave_a_shift_that_was_never_started(self):
        player = self.make_player()
        join_career(player, "construction")

        with self.assertRaises(NoShiftError):
            cancel_shift(player, now=self.now)

    def test_active_shift_blocks_second_shift(self):
        player = self.make_player()
        join_career(player, "construction")
        start_shift(player, now=self.now)

        with self.assertRaises(ShiftAlreadyActiveError):
            start_shift(
                player,
                now=self.now + timedelta(hours=1),
            )

    def test_insufficient_energy_prevents_shift(self):
        role = get_job_role("construction_labourer")
        player = self.make_player(
            energy=role.energy_cost - 1,
        )
        join_career(player, "construction")

        with self.assertRaises(InsufficientEnergyError):
            start_shift(player, now=self.now)

        self.assertEqual(
            player.energy,
            role.energy_cost - 1,
        )
        self.assertIsNone(player.shift_until)

    def test_jail_and_travel_prevent_shift(self):
        jailed_player = self.make_player(
            jail_until="2026-08-24 10:00:00",
        )
        join_career(jailed_player, "construction")

        with self.assertRaises(JobRestrictedError):
            start_shift(
                jailed_player,
                now=self.now,
            )

        travelling_player = self.make_player(
            travel_destination="soho",
            travel_until="2026-08-24 09:05:00",
        )
        join_career(
            travelling_player,
            "construction",
        )

        with self.assertRaises(JobRestrictedError):
            start_shift(
                travelling_player,
                now=self.now,
            )


if __name__ == "__main__":
    unittest.main()
