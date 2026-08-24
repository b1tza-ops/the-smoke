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


CONTRACT_POOL = (
    PvpContract(
        "first_blood", "First blood",
        "Win one rated player fight.", "wins", 1,
        150, 30, "energy_drink",
    ),
    PvpContract(
        "street_patrol", "Street patrol",
        "Complete three rated player fights.", "attempts", 3,
        225, 40,
    ),
    PvpContract(
        "clean_sweep", "Clean sweep",
        "Win two rated player fights.", "wins", 2,
        300, 55, "first_aid_kit",
    ),
    PvpContract(
        "cash_run", "Cash run",
        "Mug £100 from rated player fights.", "cash", 100,
        200, 45,
    ),
    PvpContract(
        "go_loud", "Go loud",
        "Win a rated fight using Aggressive.", "approach_wins", 1,
        225, 45, None, "aggressive",
    ),
    PvpContract(
        "hold_the_line", "Hold the line",
        "Win a rated fight using Defensive.", "approach_wins", 1,
        225, 45, None, "defensive",
    ),
    PvpContract(
        "precision_work", "Precision work",
        "Win a rated fight using Precise.", "approach_wins", 1,
        225, 45, None, "precise",
    ),
    PvpContract(
        "untouchable", "Untouchable",
        "Win a rated fight using Evasive.", "approach_wins", 1,
        225, 45, None, "evasive",
    ),
)
CONTRACTS_BY_KEY = {contract.key: contract for contract in CONTRACT_POOL}


def daily_contracts(now=None):
    now = _now(now)
    generator = random.Random(now.date().toordinal())
    return tuple(generator.sample(CONTRACT_POOL, 3))


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
