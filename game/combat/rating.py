from dataclasses import dataclass
import math


DEFAULT_PVP_RATING = 1000
RATING_K_FACTOR = 32
MIN_PVP_RATING = 100


@dataclass(frozen=True)
class RatingChange:
    winner_before: int
    winner_after: int
    loser_before: int
    loser_after: int

    @property
    def winner_delta(self):
        return self.winner_after - self.winner_before

    @property
    def loser_delta(self):
        return self.loser_after - self.loser_before


def calculate_rating_change(winner_rating, loser_rating):
    expected = 1 / (
        1 + math.pow(10, (loser_rating - winner_rating) / 400)
    )
    gain = max(1, round(RATING_K_FACTOR * (1 - expected)))
    return RatingChange(
        winner_before=winner_rating,
        winner_after=max(MIN_PVP_RATING, winner_rating + gain),
        loser_before=loser_rating,
        loser_after=max(MIN_PVP_RATING, loser_rating - gain),
    )


def matchmaking_label(player_rating, target_rating):
    difference = target_rating - player_rating
    if abs(difference) <= 100:
        return "Recommended"
    if difference < -250:
        return "Low reward"
    if difference < 0:
        return "Favourable"
    if difference <= 250:
        return "Challenging"
    return "High risk"
