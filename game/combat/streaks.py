from dataclasses import dataclass


@dataclass(frozen=True)
class StreakMilestone:
    wins: int
    title: str
    description: str


STREAK_MILESTONES = (
    StreakMilestone(3, "On fire", "Three rated victories without a defeat."),
    StreakMilestone(5, "Street enforcer", "Five rated victories in one run."),
    StreakMilestone(10, "Untouchable", "Ten rated victories without losing."),
    StreakMilestone(20, "London legend", "Twenty rated victories in one streak."),
)


def get_streak_progress(streak):
    streak = max(0, int(streak))
    achieved = [item for item in STREAK_MILESTONES if streak >= item.wins]
    next_milestone = next(
        (item for item in STREAK_MILESTONES if streak < item.wins),
        None,
    )
    previous_target = achieved[-1].wins if achieved else 0
    if next_milestone is None:
        progress_percent = 100
        wins_remaining = 0
    else:
        span = next_milestone.wins - previous_target
        progress_percent = round(
            (streak - previous_target) / span * 100
        ) if span else 100
        wins_remaining = next_milestone.wins - streak
    return {
        "streak": streak,
        "achieved": tuple(achieved),
        "current_title": achieved[-1].title if achieved else "Unranked run",
        "next": next_milestone,
        "wins_remaining": wins_remaining,
        "progress_percent": max(0, min(100, progress_percent)),
    }
