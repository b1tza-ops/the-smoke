from dataclasses import dataclass
from datetime import timedelta

from game.jobs.definitions import (
    CAREERS,
    CareerDefinition,
    JobRoleDefinition,
    get_career,
    get_job_role,
)
from game.player.progression import award_xp
from game.player.regeneration import (
    format_timestamp,
    parse_timestamp,
)
from game.player.status import (
    get_active_restriction,
    normalise_now,
)
from game.world.travel import get_active_travel


SHIFT_SECONDS = 3 * 60 * 60


class JobError(Exception):
    """Base exception for legal job actions."""


class UnknownCareerError(JobError):
    """Raised when a career key is not recognised."""


class AlreadyEmployedError(JobError):
    """Raised when an employed player tries to join again."""


class NotEmployedError(JobError):
    """Raised when an unemployed player tries to work."""


class ShiftAlreadyActiveError(JobError):
    """Raised when a player already has a shift to finish."""


class NoShiftError(JobError):
    """Raised when there is no shift to complete."""


class ShiftNotCompleteError(JobError):
    """Raised when a player tries to claim a shift early."""


class InsufficientEnergyError(JobError):
    """Raised when a player lacks the role's energy cost."""


class JobRestrictedError(JobError):
    """Raised when travel, jail, or hospital prevents work."""


class CareerLocationError(JobError):
    """Raised when a career requires a district the player isn't in."""


@dataclass(frozen=True)
class EmploymentResult:
    career_key: str
    role_key: str


@dataclass(frozen=True)
class ShiftStartResult:
    role_key: str
    energy_spent: int
    started_at: str
    completes_at: str


@dataclass(frozen=True)
class ShiftState:
    role_key: str
    completes_at: str
    remaining_seconds: int
    ready_to_complete: bool


@dataclass(frozen=True)
class ShiftCompletionResult:
    role_key: str
    salary: int
    work_xp: int
    levels_gained: int
    total_career_xp: int
    shifts_completed: int
    promoted_to: str | None


def join_career(player, career_key):
    career = get_career(career_key)

    if career is None:
        raise UnknownCareerError("Career does not exist.")

    if getattr(player, "career_key", None) is not None:
        raise AlreadyEmployedError(
            "Leave your current career before joining another."
        )

    entry_role = career.roles[0]

    if player.level < entry_role.required_level:
        raise JobRestrictedError(
            f"Level {entry_role.required_level} is required."
        )

    if (
        career.required_district is not None
        and getattr(player, "current_district", None)
        != career.required_district
    ):
        raise CareerLocationError(
            f"You must be in {career.required_district.title()} "
            "to join this career."
        )

    player.career_key = career.key
    player.job_role_key = entry_role.key
    player.career_xp = 0
    player.shifts_completed = 0
    player.shift_started_at = None
    player.shift_until = None

    return EmploymentResult(
        career_key=career.key,
        role_key=entry_role.key,
    )


def get_shift_state(player, now=None):
    shift_until = getattr(player, "shift_until", None)

    if shift_until is None:
        return None

    now = normalise_now(now)
    remaining_seconds = max(
        0,
        int(
            (
                parse_timestamp(shift_until)
                - now
            ).total_seconds()
        ),
    )

    return ShiftState(
        role_key=player.job_role_key,
        completes_at=shift_until,
        remaining_seconds=remaining_seconds,
        ready_to_complete=remaining_seconds == 0,
    )


def start_shift(player, now=None):
    role = _require_current_role(player)

    if (
        getattr(player, "shift_started_at", None) is not None
        or getattr(player, "shift_until", None) is not None
    ):
        raise ShiftAlreadyActiveError(
            "Finish your current shift before starting another."
        )

    now = normalise_now(now)

    active_travel = get_active_travel(
        player,
        now=now,
    )

    if active_travel is not None:
        raise JobRestrictedError(
            "You cannot start work while travelling."
        )

    restriction = get_active_restriction(
        player,
        now=now,
    )

    if restriction is not None:
        raise JobRestrictedError(
            f"You cannot start work while in {restriction.kind}."
        )

    if player.energy < role.energy_cost:
        raise InsufficientEnergyError(
            f"This shift requires {role.energy_cost} energy."
        )

    player.energy -= role.energy_cost
    started_at = format_timestamp(now)

    if hasattr(player, "last_energy_update"):
        player.last_energy_update = started_at

    completes_at = format_timestamp(
        now + timedelta(seconds=SHIFT_SECONDS)
    )
    player.shift_started_at = started_at
    player.shift_until = completes_at

    return ShiftStartResult(
        role_key=role.key,
        energy_spent=role.energy_cost,
        started_at=started_at,
        completes_at=completes_at,
    )


def complete_shift(player, now=None):
    role = _require_current_role(player)
    state = get_shift_state(player, now=now)

    if state is None:
        raise NoShiftError("There is no shift to complete.")

    if not state.ready_to_complete:
        raise ShiftNotCompleteError(
            "Your shift has not finished yet."
        )

    player.money += role.salary
    player.career_xp += role.work_xp
    player.shifts_completed += 1
    player.shift_started_at = None
    player.shift_until = None

    levels_gained = award_xp(
        player,
        role.work_xp,
    )
    promoted_to = _apply_available_promotion(player)

    return ShiftCompletionResult(
        role_key=role.key,
        salary=role.salary,
        work_xp=role.work_xp,
        levels_gained=levels_gained,
        total_career_xp=player.career_xp,
        shifts_completed=player.shifts_completed,
        promoted_to=promoted_to,
    )


def jobs_menu(player):
    while True:
        print("\n===== JOBS =====")

        if getattr(player, "career_key", None) is None:
            _display_available_careers()
            print(f"{len(CAREERS) + 1}. Back")

            choice = input("Choose: ").strip()

            if choice == str(len(CAREERS) + 1):
                return

            try:
                selected_index = int(choice) - 1
            except ValueError:
                print("\nInvalid option.")
                continue

            if not 0 <= selected_index < len(CAREERS):
                print("\nInvalid option.")
                continue

            career = CAREERS[selected_index]

            try:
                result = join_career(
                    player,
                    career.key,
                )
            except JobError as error:
                print(f"\nCould not join career: {error}")
                continue

            role = get_job_role(result.role_key)
            print(f"\nYou joined {career.name}.")
            print("Starting role:", role.name)
            continue

        career = get_career(player.career_key)
        role = _require_current_role(player)
        state = get_shift_state(player)

        print("Career:", career.name)
        print("Role:", role.name)
        print("Career XP:", player.career_xp)
        print("Shifts completed:", player.shifts_completed)
        print("Energy:", player.energy)
        print("Pay per shift: £", role.salary, sep="")
        print("Shift length: 3 hours")

        if state is not None and not state.ready_to_complete:
            print(
                "Shift remaining:",
                _format_duration(state.remaining_seconds),
            )
            print("\n1. Back")
            input("Choose: ")
            return

        if state is not None:
            print("\n1. Complete shift")
            print("2. Back")
            choice = input("Choose: ").strip()

            if choice == "2":
                return

            if choice != "1":
                print("\nInvalid option.")
                continue

            try:
                result = complete_shift(player)
            except JobError as error:
                print(f"\nCould not complete shift: {error}")
                continue

            print(f"\nShift complete. You earned £{result.salary:,}.")
            print("Work XP +", result.work_xp)

            if result.levels_gained:
                print(
                    "Level up! You are now level",
                    player.level,
                )

            if result.promoted_to is not None:
                promoted_role = get_job_role(
                    result.promoted_to
                )
                print("Promotion:", promoted_role.name)

            continue

        print("\n1. Start three-hour shift")
        print("2. Back")
        choice = input("Choose: ").strip()

        if choice == "2":
            return

        if choice != "1":
            print("\nInvalid option.")
            continue

        try:
            result = start_shift(player)
        except JobError as error:
            print(f"\nCould not start shift: {error}")
            continue

        print("\nShift started.")
        print("Energy used:", result.energy_spent)
        print("Finishes at:", result.completes_at)


def _require_current_role(player):
    role_key = getattr(player, "job_role_key", None)
    role = get_job_role(role_key)

    if role is None:
        raise NotEmployedError(
            "Join a career before working a shift."
        )

    return role


def _apply_available_promotion(player):
    career = get_career(player.career_key)

    if career is None:
        return None

    current_index = next(
        (
            index
            for index, role in enumerate(career.roles)
            if role.key == player.job_role_key
        ),
        None,
    )

    if current_index is None:
        return None

    promoted_to = None

    for role in career.roles[current_index + 1:]:
        if not _meets_requirements(player, role):
            break

        player.job_role_key = role.key
        promoted_to = role.key

    return promoted_to


def _meets_requirements(player, role):
    return (
        player.level >= role.required_level
        and player.career_xp >= role.required_career_xp
        and player.shifts_completed >= role.required_shifts
    )


def _display_available_careers():
    for number, career in enumerate(CAREERS, start=1):
        entry_role = career.roles[0]
        print(
            f"{number}. {career.name} "
            f"({entry_role.name}, £{entry_role.salary:,}/shift)"
        )
        print("   ", career.description)

        if career.required_district is not None:
            print(
                "    Requires:",
                career.required_district.title(),
            )


def _format_duration(total_seconds):
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
