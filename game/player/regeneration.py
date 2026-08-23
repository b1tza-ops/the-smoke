from datetime import datetime, timedelta, timezone


ENERGY_POINTS_PER_TICK = 5
ENERGY_TICK_SECONDS = 10 * 60

NERVE_POINTS_PER_TICK = 1 
NERVE_TICK_SECONDS = 5 * 60


def parse_timestamp(timestamp):
    parsed = datetime.fromisoformat(timestamp)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)

def format_timestamp(timestamp):
    return timestamp.astimezone(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
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