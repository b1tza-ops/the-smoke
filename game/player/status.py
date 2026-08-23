from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from game.player.regeneration import format_timestamp, parse_timestamp


WANTED_DECAY_POINTS = 1
WANTED_DECAY_SECONDS = 10 * 60
MAX_WANTED_LEVEL = 100


@dataclass(frozen=True)
class StatusUpdate:
    wanted_lost: int
    released_from_jail: bool
    discharged_from_hospital: bool


@dataclass(frozen=True)
class ActiveRestriction:
    kind: str
    until: str
    remaining_seconds: int


def normalise_now(now=None):
    if now is None:
        return datetime.now(timezone.utc)

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    return now.astimezone(timezone.utc)


def decay_wanted_level(
    current_level,
    last_update,
    now=None
):
    if current_level < 0:
        raise ValueError("Wanted level cannot be negative")

    current_level = min(current_level, MAX_WANTED_LEVEL)
    now = normalise_now(now)

    if current_level == 0:
        return 0, format_timestamp(now)

    if last_update is None:
        return current_level, format_timestamp(now)

    last_update_time = parse_timestamp(last_update)

    elapsed_seconds = max(
        0,
        (now - last_update_time).total_seconds()
    )

    completed_ticks = int(
        elapsed_seconds // WANTED_DECAY_SECONDS
    )

    if completed_ticks == 0:
        return current_level, format_timestamp(last_update_time)

    wanted_lost = completed_ticks * WANTED_DECAY_POINTS
    new_level = max(0, current_level - wanted_lost)

    if new_level == 0:
        new_update_time = now
    else:
        new_update_time = last_update_time + timedelta(
            seconds=completed_ticks * WANTED_DECAY_SECONDS
        )

    return new_level, format_timestamp(new_update_time)


def update_player_status(player, now=None):
    now = normalise_now(now)
    previous_wanted = player.wanted_level

    wanted_level, wanted_update = decay_wanted_level(
        current_level=player.wanted_level,
        last_update=player.last_wanted_update,
        now=now,
    )

    player.wanted_level = wanted_level
    player.last_wanted_update = wanted_update

    released_from_jail = _clear_if_expired(
        player,
        "jail_until",
        now,
    )

    discharged_from_hospital = _clear_if_expired(
        player,
        "hospital_until",
        now,
    )

    return StatusUpdate(
        wanted_lost=previous_wanted - wanted_level,
        released_from_jail=released_from_jail,
        discharged_from_hospital=discharged_from_hospital,
    )


def add_wanted(player, amount, now=None):
    if amount < 0:
        raise ValueError("Wanted increase cannot be negative")

    now = normalise_now(now)
    update_player_status(player, now=now)
    previous_level = player.wanted_level

    player.wanted_level = min(
        MAX_WANTED_LEVEL,
        previous_level + amount,
    )

    if amount > 0 and previous_level == 0:
        player.last_wanted_update = format_timestamp(now)

    return player.wanted_level

def send_to_jail(player, duration_seconds, now=None):
    if duration_seconds <= 0:
        raise ValueError("Jail duration must be positive")

    now = normalise_now(now)
    player.jail_until = _extended_until(
        current_until=player.jail_until,
        duration_seconds=duration_seconds,
        now=now,
    )

    return player.jail_until


def send_to_hospital(player, duration_seconds, now=None):
    if duration_seconds <= 0:
        raise ValueError("Hospital duration must be positive")

    now = normalise_now(now)
    player.hospital_until = _extended_until(
        current_until=player.hospital_until,
        duration_seconds=duration_seconds,
        now=now,
    )

    return player.hospital_until


def get_active_restriction(player, now=None):
    now = normalise_now(now)
    update_player_status(player, now=now)

    if player.hospital_until is not None:
        return _build_restriction(
            kind="hospital",
            until=player.hospital_until,
            now=now,
        )

    if player.jail_until is not None:
        return _build_restriction(
            kind="jail",
            until=player.jail_until,
            now=now,
        )

    return None


def _clear_if_expired(player, attribute_name, now):
    timestamp = getattr(player, attribute_name)

    if timestamp is None:
        return False

    if parse_timestamp(timestamp) > now:
        return False

    setattr(player, attribute_name, None)
    return True


def _extended_until(current_until, duration_seconds, now):
    starting_time = now

    if current_until is not None:
        current_until_time = parse_timestamp(current_until)

        if current_until_time > now:
            starting_time = current_until_time

    return format_timestamp(
        starting_time + timedelta(seconds=duration_seconds)
    )


def _build_restriction(kind, until, now):
    remaining_seconds = max(
        0,
        int((parse_timestamp(until) - now).total_seconds()),
    )

    return ActiveRestriction(
        kind=kind,
        until=until,
        remaining_seconds=remaining_seconds,
    )