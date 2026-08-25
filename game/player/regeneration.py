from datetime import datetime, timedelta, timezone


ENERGY_POINTS_PER_TICK = 5
ENERGY_TICK_SECONDS = 10 * 60

NERVE_POINTS_PER_TICK = 1
NERVE_TICK_SECONDS = 5 * 60

HAPPINESS_POINTS_PER_TICK = 5
HAPPINESS_TICK_SECONDS = 15 * 60

HEALTH_POINTS_PER_TICK = 5
HEALTH_TICK_SECONDS = 15 * 60


def parse_timestamp(timestamp):
    parsed = datetime.fromisoformat(timestamp)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)

def format_timestamp(timestamp):
    return timestamp.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

def regeneration_forecast(
    current_value,
    maximum_value,
    last_update,
    points_per_tick,
    tick_seconds,
    now=None,
):
    """How long until the next tick, and until this resource is full.

    `regenerate_resource` advances `last_update` to the last completed
    tick boundary, so the time elapsed since it is exactly the progress
    made towards the next one.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if current_value >= maximum_value:
        return {
            "is_full": True,
            "ticks_needed": 0,
            "points_per_tick": points_per_tick,
            "tick_seconds": tick_seconds,
            "seconds_to_next_tick": 0,
            "seconds_to_full": 0,
        }

    elapsed_seconds = max(
        0,
        (now - parse_timestamp(last_update)).total_seconds(),
    )
    seconds_to_next_tick = int(
        tick_seconds - (elapsed_seconds % tick_seconds)
    )

    missing = maximum_value - current_value
    ticks_needed = -(-missing // points_per_tick)  # ceiling

    return {
        "is_full": False,
        "ticks_needed": ticks_needed,
        "points_per_tick": points_per_tick,
        "tick_seconds": tick_seconds,
        "seconds_to_next_tick": seconds_to_next_tick,
        "seconds_to_full": (
            seconds_to_next_tick
            + (ticks_needed - 1) * tick_seconds
        ),
    }


# Value, ceiling, timestamp and rate for every resource that refills on
# the shared regeneration loop. Keyed by the name the HUD uses for the
# meter so a template can ask for a forecast by that name alone.
REGENERATING_RESOURCES = {
    "health": (
        "health",
        "max_health",
        "last_health_update",
        HEALTH_POINTS_PER_TICK,
        HEALTH_TICK_SECONDS,
    ),
    "energy": (
        "energy",
        "max_energy",
        "last_energy_update",
        ENERGY_POINTS_PER_TICK,
        ENERGY_TICK_SECONDS,
    ),
    "nerve": (
        "nerve",
        "max_nerve",
        "last_nerve_update",
        NERVE_POINTS_PER_TICK,
        NERVE_TICK_SECONDS,
    ),
    "happiness": (
        "happiness",
        "max_happiness",
        "last_happiness_update",
        HAPPINESS_POINTS_PER_TICK,
        HAPPINESS_TICK_SECONDS,
    ),
}


def _is_hospitalised(player, now=None):
    hospital_until = getattr(player, "hospital_until", None)

    if not hospital_until:
        return False

    if now is None:
        now = datetime.now(timezone.utc)

    return parse_timestamp(hospital_until) > now


def player_regeneration_forecast(player, resource, now=None):
    """Forecast for one of a player's regenerating meters.

    Returns `None` for anything that does not regenerate, so a template
    can loop over every meter -- experience included -- and only decorate
    the ones that do.
    """
    fields = REGENERATING_RESOURCES.get(resource)

    if fields is None:
        return None

    value_field, maximum_field, update_field, points, seconds = fields

    current_value = getattr(player, value_field, None)
    maximum_value = getattr(player, maximum_field, None)
    last_update = getattr(player, update_field, None)

    if current_value is None or not maximum_value or not last_update:
        return None

    if resource == "health" and _is_hospitalised(player, now):
        # Health is frozen in hospital and restored on discharge, so a
        # countdown here would be a lie. The hospital banner already
        # carries the timer that does apply.
        return None

    return regeneration_forecast(
        current_value,
        maximum_value,
        last_update,
        points,
        seconds,
        now=now,
    )


def regenerate_resource(
    current_value,
    maximum_value,
    last_update,
    points_per_tick,
    tick_seconds,
    now=None
):
    if now is None:
        now = datetime.now(timezone.utc)

    last_update_time = parse_timestamp(last_update)

    if current_value >= maximum_value:
        return maximum_value, format_timestamp(now)

    elapsed_seconds = max(
        0,
        (now - last_update_time).total_seconds()
    )

    completed_ticks = int(elapsed_seconds // tick_seconds)

    if completed_ticks == 0:
        return current_value, format_timestamp(last_update_time)

    recovered_points = completed_ticks * points_per_tick

    new_value = min(
        maximum_value,
        current_value + recovered_points
    )

    if new_value >= maximum_value:
        new_update_time = now
    else:
        new_update_time = last_update_time + timedelta(
            seconds=completed_ticks * tick_seconds
        )

    return new_value, format_timestamp(new_update_time)