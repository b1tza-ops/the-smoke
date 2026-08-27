from dataclasses import dataclass
from datetime import datetime, timezone
import random


@dataclass(frozen=True)
class PvpContract:
    key: str
    name: str
    description: str
    metric: str
    target: int
    cash_reward: int
    xp_reward: int
    item_key: str | None = None
    required_approach: str | None = None

    @property
    def needs_another_player(self):
        """Whether this contract can only be finished against a person.

        The approach contracts are about PvP tactics -- picking
        Aggressive or Evasive is a choice that only exists in a player
        fight -- so they stay player-only. Everything else counts any
        fight, including street opponents.
        """
        return self.required_approach is not None


CONTRACT_POOL = (
    PvpContract(
        "first_blood", "First blood",
        "Win one fight, against anyone.", "wins", 1,
        150, 30, "energy_drink",
    ),
    PvpContract(
        "street_patrol", "Street patrol",
        "Finish three fights, win or lose.", "attempts", 3,
        225, 40,
    ),
    PvpContract(
        "clean_sweep", "Clean sweep",
        "Win two fights, against anyone.", "wins", 2,
        300, 55, "first_aid_kit",
    ),
    PvpContract(
        "cash_run", "Cash run",
        "Take £100 from fights.", "cash", 100,
        200, 45,
    ),
    PvpContract(
        "go_loud", "Go loud",
        "Win a player fight using Aggressive.", "approach_wins", 1,
        225, 45, None, "aggressive",
    ),
    PvpContract(
        "hold_the_line", "Hold the line",
        "Win a player fight using Defensive.", "approach_wins", 1,
        225, 45, None, "defensive",
    ),
    PvpContract(
        "precision_work", "Precision work",
        "Win a player fight using Precise.", "approach_wins", 1,
        225, 45, None, "precise",
    ),
    PvpContract(
        "untouchable", "Untouchable",
        "Win a player fight using Evasive.", "approach_wins", 1,
        225, 45, None, "evasive",
    ),
)
CONTRACTS_BY_KEY = {contract.key: contract for contract in CONTRACT_POOL}


DAILY_CONTRACT_COUNT = 3

# At least this many of each day's contracts must be finishable without
# another player. The board used to be sampled freely from the pool, and
# four of the eight need a person on the other side, so 31 days a year
# rolled a board a solo player could not touch at all -- on a server
# with almost nobody on it, that is most days made worthless.
MINIMUM_SOLO_CONTRACTS = 2

SOLO_CONTRACTS = tuple(
    contract for contract in CONTRACT_POOL
    if not contract.needs_another_player
)


def daily_contracts(now=None):
    """Three contracts, the same for everyone, rerolled at UTC midnight.

    Seeded off the date so every player sees the same board without
    anything being stored, and so yesterday's board can still be worked
    out when a fight needs recording against it.
    """
    now = _now(now)
    generator = random.Random(now.date().toordinal())

    chosen = generator.sample(SOLO_CONTRACTS, MINIMUM_SOLO_CONTRACTS)
    remaining = [
        contract for contract in CONTRACT_POOL
        if contract not in chosen
    ]
    chosen += generator.sample(
        remaining,
        DAILY_CONTRACT_COUNT - MINIMUM_SOLO_CONTRACTS,
    )
    generator.shuffle(chosen)

    return tuple(chosen)


def daily_key(now=None):
    return _now(now).date().isoformat()


def reset_seconds(now=None):
    now = _now(now)
    from datetime import timedelta
    tomorrow = datetime.combine(
        now.date() + timedelta(days=1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    )
    return max(0, int((tomorrow - now).total_seconds()))


def _now(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
