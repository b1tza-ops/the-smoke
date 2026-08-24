from game.combat.streaks import get_streak_progress


def test_streak_progress_starts_towards_first_milestone():
    progress = get_streak_progress(0)
    assert progress["current_title"] == "Unranked run"
    assert progress["next"].wins == 3
    assert progress["wins_remaining"] == 3
    assert progress["progress_percent"] == 0


def test_streak_progress_advances_between_milestones():
    progress = get_streak_progress(7)
    assert progress["current_title"] == "Street enforcer"
    assert progress["next"].wins == 10
    assert progress["wins_remaining"] == 3
    assert progress["progress_percent"] == 40


def test_streak_progress_caps_after_final_milestone():
    progress = get_streak_progress(24)
    assert progress["current_title"] == "London legend"
    assert progress["next"] is None
    assert progress["wins_remaining"] == 0
    assert progress["progress_percent"] == 100


def test_negative_streak_is_safely_normalised():
    assert get_streak_progress(-4)["streak"] == 0
