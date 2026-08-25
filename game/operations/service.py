"""Which operation a player can run next, and why not the others.

Pure rules: the repository supplies the stored records, this decides what
the campaign looks like from where the player is standing.
"""

from dataclasses import dataclass

from game.operations.definitions import CAMPAIGN, Operation


COMPLETED = "completed"
ACTIVE = "active"
AVAILABLE = "available"
LOCKED = "locked"


@dataclass(frozen=True)
class OperationStatus:
    operation: Operation
    stage: str
    lock_reason: str | None = None
    approach_key: str | None = None
    outcome_text: str | None = None
    paydown: int = 0
    remaining_seconds: int = 0

    @property
    def is_open(self):
        return self.stage in (ACTIVE, AVAILABLE)


def approach_shortfalls(player, approach):
    """What the player is missing for this approach, if anything."""
    shortfalls = []
    stat_value = getattr(player, approach.stat, 0)

    if stat_value < approach.required_stat:
        shortfalls.append(
            f"{approach.required_stat} {approach.stat}"
        )

    if player.energy < approach.energy:
        shortfalls.append(f"{approach.energy} energy")

    if player.nerve < approach.nerve:
        shortfalls.append(f"{approach.nerve} nerve")

    return shortfalls


def can_attempt(player, approach):
    return not approach_shortfalls(player, approach)


def campaign_status(player, records, district_names=None):
    """Every operation in order, with its stage from here.

    `records` maps an operation key to its stored row. An operation only
    opens once the one before it is done, the level is reached and the
    player is standing in the right district. The chain is what keeps a
    player to one operation at a time: while one is running it is not
    completed, so nothing behind it can open.
    """
    district_names = district_names or {}
    statuses = []
    previous = None

    for operation in CAMPAIGN:
        record = records.get(operation.key)

        if record and record.get("stage") == COMPLETED:
            statuses.append(
                OperationStatus(
                    operation=operation,
                    stage=COMPLETED,
                    approach_key=record.get("approach"),
                    outcome_text=record.get("outcome_text"),
                    paydown=record.get("paydown") or 0,
                )
            )
            previous = operation
            continue

        if record and record.get("stage") == ACTIVE:
            statuses.append(
                OperationStatus(
                    operation=operation,
                    stage=ACTIVE,
                    approach_key=record.get("approach"),
                    remaining_seconds=record.get(
                        "remaining_seconds", 0
                    ),
                )
            )
            previous = operation
            continue

        lock_reason = _lock_reason(
            player,
            operation,
            previous,
            records,
            district_names,
        )
        statuses.append(
            OperationStatus(
                operation=operation,
                stage=LOCKED if lock_reason else AVAILABLE,
                lock_reason=lock_reason,
            )
        )
        previous = operation

    return tuple(statuses)


def _lock_reason(
    player,
    operation,
    previous,
    records,
    district_names,
):
    if previous is not None:
        previous_record = records.get(previous.key) or {}

        if previous_record.get("stage") != COMPLETED:
            return f"Complete {previous.name} first"

    if player.level < operation.required_level:
        return f"Reach level {operation.required_level}"

    if player.current_district != operation.district:
        name = district_names.get(
            operation.district,
            operation.district.title(),
        )
        return f"Travel to {name}"

    return None


def next_operation(statuses):
    """The one the page should lead with."""
    for status in statuses:
        if status.stage == ACTIVE:
            return status

    for status in statuses:
        if status.stage != COMPLETED:
            return status

    return None
