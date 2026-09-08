"""The tool that checks the casino against real play.

The first version of this script accused a healthy fruit machine of
robbery. It took the spread of returns from the sample it was auditing,
and a sample that has not yet seen the 750x jackpot looks far steadier
than the game really is -- so the error bars came out narrow, the
measured return came out low, and the verdict came out confidently
wrong.

These tests exist because an auditing tool that lies is worse than no
tool at all: it either sends somebody hunting a bug that is not there,
or teaches them to ignore it when it finally cries for a real reason.
"""

import sqlite3
import tempfile
import unittest
from itertools import product
from math import comb, sqrt
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from game.casino import keno, slots

from scripts.audit_casino import (
    USEFUL_HALF_WIDTH,
    _book,
    _spot_count,
    advertised,
    keno_spread,
    slots_spread,
)


class SpreadTests(unittest.TestCase):
    """The standard deviations, recomputed from first principles."""

    def test_the_slots_spread_matches_an_independent_enumeration(self):
        stops = len(slots.STRIP)
        first = second = 0.0
        for reels in product(slots.REEL_WEIGHTS, repeat=slots.REEL_COUNT):
            probability = 1.0
            for symbol in reels:
                probability *= slots.REEL_WEIGHTS[symbol] / stops
            multiplier = slots.score(reels)[0]
            first += probability * multiplier
            second += probability * multiplier * multiplier

        mean, deviation = slots_spread()
        self.assertAlmostEqual(mean, first, places=10)
        self.assertAlmostEqual(deviation, sqrt(second - first * first), places=10)

    def test_the_slots_spread_is_dominated_by_the_jackpot(self):
        """This is the fact the broken version missed.

        Nine times the stake, on a game whose average return is under
        one. Any error bar not built from this is fiction.
        """
        _, deviation = slots_spread()
        self.assertGreater(deviation, 8.0)

        # And so a few thousand spins cannot possibly settle anything.
        half_width = 1.96 * deviation / sqrt(4_000)
        self.assertGreater(half_width, USEFUL_HALF_WIDTH * 5)

    def test_every_keno_spread_matches_the_hypergeometric_sum(self):
        for spots in keno.PAYTABLE:
            first = second = 0.0
            for hits in range(spots + 1):
                probability = (
                    comb(spots, hits)
                    * comb(keno.POOL_SIZE - spots, keno.DRAW_SIZE - hits)
                    / comb(keno.POOL_SIZE, keno.DRAW_SIZE)
                )
                multiplier = keno.PAYTABLE[spots].get(hits, 0)
                first += probability * multiplier
                second += probability * multiplier * multiplier

            mean, deviation = keno_spread(spots)
            self.assertAlmostEqual(mean, first, places=10)
            self.assertAlmostEqual(
                deviation, sqrt(second - first * first), places=10,
                msg=f"{spots} spots",
            )

    def test_the_advertised_figures_are_the_ones_the_games_pay(self):
        targets = advertised()
        self.assertEqual(targets["slots"], (slots.return_to_player(),) * 2)
        self.assertEqual(targets["keno"], keno.return_range())


class SpotCountTests(unittest.TestCase):
    def test_a_keno_round_reports_the_spots_it_was_played_at(self):
        self.assertEqual(_spot_count("3/5"), 5)
        self.assertEqual(_spot_count("0/2"), 2)

    def test_a_detail_that_is_not_a_keno_line_is_ignored(self):
        for detail in ("Blackjack — pays 3:2", "", None, "pint cab bell"):
            self.assertIsNone(_spot_count(detail))


class BookTests(unittest.TestCase):
    """The arithmetic over a ledger, on rounds whose answer is known."""

    def rows(self, game, count, bet, payout, detail=""):
        return [(game, bet, payout, detail)] * count

    def test_a_book_totals_what_was_staked_and_returned(self):
        book = _book(self.rows("slots", 10, 100, 50), "slots")
        self.assertEqual(book["rounds"], 10)
        self.assertEqual(book["staked"], 1_000)
        self.assertEqual(book["returned"], 500)
        self.assertEqual(book["measured"], 0.5)

    def test_a_game_with_no_rounds_has_no_book(self):
        self.assertIsNone(_book(self.rows("slots", 3, 100, 0), "keno"))

    def test_rounds_of_other_games_are_left_out(self):
        rows = self.rows("slots", 4, 100, 0) + self.rows("keno", 2, 100, 300, "2/2")
        self.assertEqual(_book(rows, "keno")["rounds"], 2)

    def test_the_slots_error_bar_ignores_how_calm_the_sample_looks(self):
        """Four thousand losing spins must not read as a tight result."""
        book = _book(self.rows("slots", 4_000, 100, 0), "slots")
        self.assertEqual(book["measured"], 0.0)
        self.assertAlmostEqual(
            book["error"], slots_spread()[1] / sqrt(4_000), places=9
        )
        self.assertGreater(1.96 * book["error"], USEFUL_HALF_WIDTH)

    def test_one_huge_stake_does_not_count_as_a_thousand_small_ones(self):
        """Effective sample size, not round count.

        A book of one enormous hand and many tiny ones is dominated by
        the enormous one, and the error bar has to say so.
        """
        many_small = _book(self.rows("blackjack", 100, 100, 100), "blackjack")
        one_large = _book(
            self.rows("blackjack", 99, 100, 100)
            + self.rows("blackjack", 1, 1_000_000, 1_000_000),
            "blackjack",
        )
        self.assertEqual(one_large["rounds"], 100)
        # Same rounds, but nearly all the money rides on a single hand.
        self.assertLessEqual(one_large["error"], many_small["error"] + 1e-9)

    def test_a_keno_book_weights_each_spot_count_by_how_often_it_is_played(self):
        two = _book(self.rows("keno", 100, 100, 0, "0/2"), "keno")
        five = _book(self.rows("keno", 100, 100, 0, "0/5"), "keno")

        self.assertAlmostEqual(two["deviation"], keno_spread(2)[1], places=9)
        self.assertAlmostEqual(five["deviation"], keno_spread(5)[1], places=9)
        # Five spots carries the 880x prize, so it is much the wilder.
        self.assertGreater(five["deviation"], two["deviation"] * 2)


class LedgerTests(unittest.TestCase):
    """The query, against a real schema."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = Path(self.temp_dir.name) / "audit.db"
        patcher = patch("database.core.connection.DB_PATH", database_path)
        patcher.start()
        self.addCleanup(patcher.stop)
        create_tables()
        self.database_path = database_path

    def test_the_ledger_columns_the_audit_reads_are_the_ones_written(self):
        """A rename in `casino_rounds` must break this, not the script."""
        connection = sqlite3.connect(self.database_path)
        columns = {
            row[1] for row in
            connection.execute("PRAGMA table_info(casino_rounds)")
        }
        connection.close()

        for column in ("player_id", "game", "bet", "payout", "detail"):
            self.assertIn(column, columns)


if __name__ == "__main__":
    unittest.main()
