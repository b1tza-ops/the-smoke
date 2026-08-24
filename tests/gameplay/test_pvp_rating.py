import unittest

from game.combat.rating import (
    calculate_rating_change,
    matchmaking_label,
)


class PvpRatingTests(unittest.TestCase):
    def test_even_match_moves_both_players_equally(self):
        change = calculate_rating_change(1000, 1000)
        self.assertEqual(change.winner_after, 1016)
        self.assertEqual(change.loser_after, 984)
        self.assertEqual(change.winner_delta, 16)
        self.assertEqual(change.loser_delta, -16)

    def test_upset_is_worth_more_than_expected_win(self):
        upset = calculate_rating_change(800, 1200)
        expected = calculate_rating_change(1200, 800)
        self.assertGreater(upset.winner_delta, expected.winner_delta)

    def test_rating_has_a_floor(self):
        change = calculate_rating_change(1000, 100)
        self.assertGreaterEqual(change.loser_after, 100)

    def test_matchmaking_labels_rating_distance(self):
        self.assertEqual(matchmaking_label(1000, 1050), "Recommended")
        self.assertEqual(matchmaking_label(1000, 1300), "High risk")
        self.assertEqual(matchmaking_label(1000, 700), "Low reward")


if __name__ == "__main__":
    unittest.main()
