"""The Golden Square.

The important tests here are the arithmetic ones. A casino is only fair
if its house edge is what it claims to be, so the paytables are
recomputed from first principles -- exhaustively for the reels,
hypergeometrically for keno -- and the test fails if a payout is edited
without the return being re-checked. Everything else guards the money:
a round must move exactly the net, and never twice.
"""

import random
import sqlite3
import tempfile
import unittest
from itertools import product
from math import comb
from pathlib import Path
from unittest.mock import patch

from database.core.setup import create_tables
from database.repositories import casino as repo
from database.repositories.players import create_player, get_player_by_user_id
from database.repositories.users import create_user
from game.casino import blackjack, keno, slots
from game.casino.limits import (
    MAXIMUM_PAYOUT,
    MINIMUM_BET,
    MINIMUM_LEVEL,
    CasinoError,
    capped_payout,
    maximum_bet,
    validate_bet,
)
from game.player import Player


# The band every game must sit in. Slots and keno are the sinks; blackjack
# is deliberately near break-even, and is checked separately.
RTP_FLOOR, RTP_CEILING = 0.88, 0.925


class SlotsMathsTests(unittest.TestCase):
    def strip_probability(self, symbol):
        return slots.REEL_WEIGHTS[symbol] / len(slots.STRIP)

    def test_the_reels_return_between_88_and_92_percent(self):
        total = 0.0
        for reels in product(slots.REEL_WEIGHTS, repeat=slots.REEL_COUNT):
            probability = 1.0
            for symbol in reels:
                probability *= self.strip_probability(symbol)
            total += probability * slots.score(reels)[0]

        self.assertGreaterEqual(total, RTP_FLOOR)
        self.assertLessEqual(total, RTP_CEILING)

    def test_the_house_always_keeps_an_edge(self):
        total = sum(
            (lambda p: p * slots.score(reels)[0])(
                self.strip_probability(reels[0])
                * self.strip_probability(reels[1])
                * self.strip_probability(reels[2])
            )
            for reels in product(slots.REEL_WEIGHTS, repeat=slots.REEL_COUNT)
        )
        self.assertLess(total, 1.0, "the reels pay out more than they take")

    def test_the_machine_pays_something_often_enough_to_play(self):
        hits = 0.0
        for reels in product(slots.REEL_WEIGHTS, repeat=slots.REEL_COUNT):
            if slots.score(reels)[0] == 0:
                continue
            probability = 1.0
            for symbol in reels:
                probability *= self.strip_probability(symbol)
            hits += probability
        self.assertGreater(hits, 0.15)

    def test_rarer_symbols_pay_more(self):
        by_weight = sorted(
            slots.REEL_WEIGHTS, key=slots.REEL_WEIGHTS.get, reverse=True
        )
        payouts = [slots.THREE_OF_A_KIND[symbol] for symbol in by_weight]
        self.assertEqual(payouts, sorted(payouts))

    def test_every_symbol_has_a_name_and_a_three_of_a_kind_payout(self):
        for symbol in slots.REEL_WEIGHTS:
            self.assertIn(symbol, slots.SYMBOL_NAMES)
            self.assertGreater(slots.THREE_OF_A_KIND[symbol], 0)

    def test_pairs_only_pay_on_the_higher_symbols(self):
        self.assertTrue(set(slots.PAIR) <= set(slots.REEL_WEIGHTS))
        for symbol in slots.PAIR:
            self.assertLessEqual(slots.REEL_WEIGHTS[symbol], 8)

    def test_scoring_is_order_independent(self):
        self.assertEqual(
            slots.score(("seven", "pint", "seven"))[0],
            slots.score(("pint", "seven", "seven"))[0],
        )

    def test_three_of_a_kind_beats_the_pair_payout(self):
        for symbol in slots.PAIR:
            self.assertGreater(
                slots.THREE_OF_A_KIND[symbol], slots.PAIR[symbol]
            )

    def test_a_spin_pays_the_multiplier_on_the_stake(self):
        rng = random.Random(1)
        result = slots.play(250, rng)
        self.assertEqual(result.payout, 250 * result.multiplier)


class KenoMathsTests(unittest.TestCase):
    def hypergeometric(self, spots, hits):
        return (
            comb(spots, hits)
            * comb(keno.POOL_SIZE - spots, keno.DRAW_SIZE - hits)
            / comb(keno.POOL_SIZE, keno.DRAW_SIZE)
        )

    def test_every_spot_count_returns_between_88_and_92_percent(self):
        for spots, tiers in keno.PAYTABLE.items():
            with self.subTest(spots=spots):
                total = sum(
                    self.hypergeometric(spots, hits) * pay
                    for hits, pay in tiers.items()
                )
                self.assertGreaterEqual(total, RTP_FLOOR)
                self.assertLessEqual(total, RTP_CEILING)

    def test_no_spot_count_is_a_trap_or_a_loophole(self):
        returns = []
        for spots, tiers in keno.PAYTABLE.items():
            returns.append(sum(
                self.hypergeometric(spots, hits) * pay
                for hits, pay in tiers.items()
            ))
        # Nothing should be more than four points better than anything else.
        self.assertLess(max(returns) - min(returns), 0.04)

    def test_the_paytable_covers_exactly_the_offered_spot_counts(self):
        self.assertEqual(
            sorted(keno.PAYTABLE),
            list(range(keno.MINIMUM_SPOTS, keno.MAXIMUM_SPOTS + 1)),
        )

    def test_more_matches_never_pays_less(self):
        for spots, tiers in keno.PAYTABLE.items():
            with self.subTest(spots=spots):
                pays = [tiers[hits] for hits in sorted(tiers)]
                self.assertEqual(pays, sorted(pays))

    def test_the_draw_is_twenty_distinct_numbers_in_range(self):
        rng = random.Random(4)
        for _ in range(50):
            drawn = keno.draw(rng)
            self.assertEqual(len(drawn), keno.DRAW_SIZE)
            self.assertEqual(len(set(drawn)), keno.DRAW_SIZE)
            self.assertTrue(all(1 <= n <= keno.POOL_SIZE for n in drawn))

    def test_a_card_is_scored_on_the_overlap(self):
        hits, multiplier = keno.score((1, 2, 3), (1, 2, 40, 50))
        self.assertEqual(hits, (1, 2))
        self.assertEqual(multiplier, keno.PAYTABLE[3][2])

    def test_bad_cards_are_refused(self):
        for picks in ([1], list(range(1, 9)), [1, 1, 2], [0, 5], [81, 2], ["x", 2]):
            with self.subTest(picks=picks):
                with self.assertRaises(keno.KenoError):
                    keno.validate_picks(picks)

    def test_picks_are_normalised_to_a_sorted_tuple(self):
        self.assertEqual(keno.validate_picks(["9", "3", 5]), (3, 5, 9))


class BlackjackRuleTests(unittest.TestCase):
    def table(self, player, dealer, bet=100, shoe=("5C",) * 40, insurance=0,
              state=blackjack.PLAYER_TURN):
        return blackjack.TableState(
            shoe=shoe, cursor=0,
            hands=(blackjack.Hand(cards=player, bet=bet),),
            active=0, dealer=dealer, state=state, insurance=insurance,
        )

    def test_a_six_deck_shoe_holds_every_card_six_times(self):
        shoe = blackjack.build_shoe(random.Random(2))
        self.assertEqual(len(shoe), 52 * blackjack.DECKS)
        counts = {}
        for card in shoe:
            counts[card] = counts.get(card, 0) + 1
        self.assertEqual(set(counts.values()), {blackjack.DECKS})

    def test_aces_drop_to_one_rather_than_bust(self):
        self.assertEqual(blackjack.hand_value(("AS", "AD"))[0], 12)
        self.assertEqual(blackjack.hand_value(("AS", "9H", "5C"))[0], 15)
        self.assertEqual(blackjack.hand_value(("AS", "KH"))[0], 21)

    def test_a_soft_hand_is_reported_as_soft(self):
        self.assertTrue(blackjack.hand_value(("AS", "6H"))[1])
        self.assertFalse(blackjack.hand_value(("AS", "6H", "KC"))[1])

    def test_a_natural_pays_three_to_two(self):
        state = blackjack.stand(self.table(("AS", "KH"), ("9D", "7C")))
        hand = state.hands[0]
        self.assertEqual(hand.outcome, blackjack.PLAYER_BLACKJACK)
        self.assertEqual(hand.payout, 250)

    def test_a_split_twenty_one_is_not_a_natural(self):
        hand = blackjack.Hand(cards=("AS", "KH"), bet=100, from_split=True)
        self.assertFalse(hand.natural)

    def test_a_push_returns_the_stake_only(self):
        state = blackjack.stand(self.table(("10S", "9H"), ("10D", "9C")))
        self.assertEqual(state.hands[0].outcome, blackjack.PUSH)
        self.assertEqual(state.hands[0].payout, 100)

    def test_a_bust_pays_nothing_even_against_a_worse_dealer(self):
        state = blackjack.hit(
            self.table(("10S", "9H"), ("4D", "3C"), shoe=("KC",) * 40)
        )
        self.assertEqual(state.hands[0].outcome, blackjack.PLAYER_BUST)
        self.assertEqual(state.hands[0].payout, 0)

    def test_the_dealer_stands_on_every_seventeen(self):
        state = blackjack.stand(self.table(("10S", "8H"), ("AD", "6C")))
        # Soft 17 stands, so the dealer never improves on it.
        self.assertEqual(len(state.dealer), 2)
        self.assertEqual(state.hands[0].outcome, blackjack.PLAYER_WIN)

    def test_doubling_takes_one_card_and_settles(self):
        state = blackjack.double_down(self.table(("6S", "5H"), ("10D", "9C")))
        self.assertEqual(len(state.hands[0].cards), 3)
        self.assertEqual(state.hands[0].bet, 200)
        self.assertEqual(state.state, blackjack.SETTLED)
        self.assertTrue(state.hands[0].doubled)

    def test_doubling_is_refused_after_hitting(self):
        state = self.table(("6S", "5H", "2D"), ("10D", "9C"))
        with self.assertRaises(blackjack.BlackjackError):
            blackjack.double_down(state)

    def test_a_settled_table_cannot_be_played_on(self):
        state = self.table(
            ("10S", "9H"), ("10D", "9C"), state=blackjack.SETTLED
        )
        for action in (blackjack.hit, blackjack.stand, blackjack.double_down):
            with self.assertRaises(blackjack.BlackjackError):
                action(state)

    # ---------------------------------------------------------- surrender

    def test_surrender_returns_half_the_stake(self):
        state = blackjack.surrender(self.table(("JS", "6H"), ("KD", "9C")))
        self.assertEqual(state.hands[0].outcome, blackjack.SURRENDERED)
        self.assertEqual(state.hands[0].payout, 50)
        self.assertEqual(state.staked, 100)

    def test_surrender_is_refused_once_a_hand_has_been_split(self):
        state = self.table(
            ("8S", "8H"), ("6D", "9C"), shoe=("2C", "3D") + ("KC",) * 40
        )
        state = blackjack.split(state)
        self.assertNotIn("surrender", blackjack.available_actions(state))

    def test_the_dealer_does_not_draw_against_a_surrendered_table(self):
        state = blackjack.surrender(self.table(("JS", "6H"), ("5D", "4C")))
        self.assertEqual(len(state.dealer), 2)

    # -------------------------------------------------------------- split

    def test_splitting_makes_two_hands_at_the_same_stake(self):
        state = self.table(
            ("8S", "8H"), ("6D", "9C"), shoe=("2C", "3D") + ("KC",) * 40
        )
        state = blackjack.split(state)
        self.assertEqual(len(state.hands), 2)
        self.assertEqual([hand.bet for hand in state.hands], [100, 100])
        self.assertEqual(state.staked, 200)
        self.assertTrue(all(hand.from_split for hand in state.hands))

    def test_split_aces_take_one_card_each_and_stop(self):
        state = self.table(
            ("AS", "AH"), ("6D", "9C"), shoe=("2C", "3D") + ("KC",) * 40
        )
        state = blackjack.split(state)
        self.assertEqual(state.state, blackjack.SETTLED)
        for hand in state.hands:
            self.assertEqual(len(hand.cards), 2)

    def test_doubling_is_allowed_after_a_split(self):
        state = self.table(
            ("9S", "9H"), ("6D", "9C"), shoe=("2C", "3D", "7H") + ("KC",) * 40
        )
        state = blackjack.split(state)
        self.assertIn("double", blackjack.available_actions(state))

    def test_a_hand_cannot_be_split_beyond_four(self):
        state = self.table(
            ("8S", "8H"), ("6D", "9C"),
            shoe=("8D", "8C", "8H", "8S", "8D", "8C") + ("KC",) * 40,
        )
        for _ in range(6):
            if "split" not in blackjack.available_actions(state):
                break
            state = blackjack.split(state)
        self.assertLessEqual(len(state.hands), blackjack.MAXIMUM_HANDS)
        self.assertNotIn("split", blackjack.available_actions(state))

    def test_unequal_cards_cannot_be_split(self):
        state = self.table(("8S", "9H"), ("6D", "9C"))
        self.assertNotIn("split", blackjack.available_actions(state))

    def test_two_ten_valued_cards_can_be_split(self):
        state = self.table(("KS", "QH"), ("6D", "9C"))
        self.assertIn("split", blackjack.available_actions(state))

    # ---------------------------------------------------------- insurance

    def test_insurance_is_only_offered_against_an_ace(self):
        offered = self.table(
            ("10S", "9H"), ("AD", "7C"), state=blackjack.INSURANCE_OFFERED
        )
        self.assertEqual(
            blackjack.available_actions(offered),
            ("insurance", "decline_insurance"),
        )
        self.assertNotIn(
            "insurance",
            blackjack.available_actions(self.table(("10S", "9H"), ("5D", "7C"))),
        )

    def test_insurance_costs_half_and_pays_two_to_one(self):
        state = self.table(
            ("10S", "9H"), ("AD", "KC"), state=blackjack.INSURANCE_OFFERED
        )
        state = blackjack.take_insurance(state)
        self.assertEqual(state.insurance, 50)
        self.assertEqual(state.insurance_payout, 150)
        # The hand itself loses to the natural, so the table breaks even.
        self.assertEqual(state.staked, 150)
        self.assertEqual(state.payout, 150)

    def test_declining_insurance_against_a_natural_loses_the_hand(self):
        state = self.table(
            ("10S", "9H"), ("AD", "KC"), state=blackjack.INSURANCE_OFFERED
        )
        state = blackjack.decline_insurance(state)
        self.assertEqual(state.state, blackjack.SETTLED)
        self.assertEqual(state.payout, 0)

    def test_insurance_is_lost_when_the_dealer_has_no_natural(self):
        state = self.table(
            ("10S", "9H"), ("AD", "5C"), state=blackjack.INSURANCE_OFFERED
        )
        state = blackjack.take_insurance(state)
        self.assertEqual(state.state, blackjack.PLAYER_TURN)
        state = blackjack.stand(state)
        self.assertEqual(state.insurance_payout, 0)

    def test_actions_are_refused_while_insurance_is_outstanding(self):
        state = self.table(
            ("10S", "9H"), ("AD", "5C"), state=blackjack.INSURANCE_OFFERED
        )
        with self.assertRaises(blackjack.BlackjackError):
            blackjack.hit(state)

    # ----------------------------------------------------------- the edge

    def test_a_naive_player_loses_slowly_rather_than_instantly(self):
        """Never doubling and standing on 17 costs a few percent.

        That is the floor, not the headline: playing the doubles, splits
        and surrenders properly brings it under half a percent. This test
        only pins that the game is neither beatable by accident nor a
        mugging.
        """
        rng = random.Random(99)
        staked = returned = 0
        for _ in range(4000):
            state = blackjack.open_table(100, rng)
            if state.state == blackjack.INSURANCE_OFFERED:
                state = blackjack.decline_insurance(state)
            while state.state == blackjack.PLAYER_TURN:
                total, _ = blackjack.hand_value(state.current.cards)
                state = (
                    blackjack.stand(state) if total >= 17
                    else blackjack.hit(state)
                )
            staked += state.staked
            returned += state.payout

        edge = 1 - returned / staked
        self.assertGreater(edge, 0, "the player is beating the house")
        self.assertLess(edge, 0.10, "standing on 17 should not be punished")


class BetLimitTests(unittest.TestCase):
    def test_the_door_is_shut_below_the_minimum_level(self):
        with self.assertRaises(CasinoError):
            validate_bet(MINIMUM_LEVEL - 1, 100, 10_000)

    def test_the_ceiling_rises_with_level(self):
        self.assertLess(maximum_bet(3), maximum_bet(10))
        self.assertLess(maximum_bet(10), maximum_bet(40))

    def test_a_low_level_player_cannot_wager_a_fortune(self):
        with self.assertRaises(CasinoError):
            validate_bet(MINIMUM_LEVEL, 1_000_000, 5_000_000)

    def test_stakes_below_the_minimum_are_refused(self):
        with self.assertRaises(CasinoError):
            validate_bet(10, MINIMUM_BET - 1, 10_000)

    def test_a_stake_bigger_than_the_pocket_is_refused(self):
        with self.assertRaises(CasinoError):
            validate_bet(10, 1_000, 999)

    def test_non_integer_stakes_are_refused(self):
        for bet in (True, 10.5, "100", None):
            with self.subTest(bet=bet):
                with self.assertRaises(CasinoError):
                    validate_bet(10, bet, 10_000)

    def test_the_table_maximum_caps_a_freak_payout(self):
        self.assertEqual(capped_payout(MAXIMUM_PAYOUT * 3), MAXIMUM_PAYOUT)
        self.assertEqual(capped_payout(50), 50)


class CasinoMoneyTests(unittest.TestCase):
    """Money only moves through the repository, so it is checked there."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        database_path = Path(self.temp_dir.name) / "casino.db"
        self.database_patch = patch(
            "database.core.connection.DB_PATH", database_path
        )
        self.database_patch.start()
        self.addCleanup(self.database_patch.stop)
        create_tables()

        self.user_id = create_user("punter", "punter@example.com", "hash")
        create_player(self.user_id, "Punter")
        self.set(level=10, current_district="soho", money=100_000)

    def set(self, **columns):
        assignments = ", ".join(f"{name} = ?" for name in columns)
        connection = sqlite3.connect(self.database_patch.new)
        with connection:
            connection.execute(
                f"UPDATE players SET {assignments} WHERE user_id = ?",
                (*columns.values(), self.user_id),
            )
        connection.close()

    def player(self):
        return Player(*get_player_by_user_id(self.user_id))

    def test_a_spin_moves_exactly_the_net(self):
        rng = random.Random(6)
        for _ in range(30):
            before = self.player().money
            result, payout = repo.play_slots(self.user_id, 100, rng)
            self.assertEqual(self.player().money, before - 100 + payout)

    def test_a_keno_card_moves_exactly_the_net(self):
        rng = random.Random(6)
        before = self.player().money
        cards, payout = repo.play_keno(
            self.user_id, 200, [4, 8, 15, 16], 1, rng
        )
        self.assertEqual(len(cards), 1)
        self.assertEqual(self.player().money, before - 200 + payout)

    def test_keno_rounds_each_cost_the_stake(self):
        rng = random.Random(6)
        before = self.player().money
        cards, payout = repo.play_keno(
            self.user_id, 100, [4, 8, 15], 5, rng
        )
        self.assertEqual(len(cards), 5)
        self.assertEqual(self.player().money, before - 500 + payout)

    def test_every_keno_round_is_drawn_separately(self):
        rng = random.Random(6)
        cards, payout = repo.play_keno(
            self.user_id, 100, [4, 8, 15], 8, rng
        )
        draws = {card.drawn for card in cards}
        self.assertGreater(len(draws), 1, "every round drew the same numbers")

    def test_too_many_rounds_is_refused(self):
        with self.assertRaises(keno.KenoError):
            repo.play_keno(self.user_id, 100, [1, 2, 3], 99, random.Random(1))

    def test_rounds_the_player_cannot_afford_are_refused(self):
        self.set(money=450)
        before = self.player().money
        with self.assertRaises(CasinoError):
            repo.play_keno(self.user_id, 100, [1, 2, 3], 10, random.Random(1))
        self.assertEqual(self.player().money, before)

    def test_every_round_is_written_to_the_book(self):
        rng = random.Random(6)
        repo.play_slots(self.user_id, 100, rng)
        repo.play_keno(self.user_id, 100, [1, 2, 3], 1, rng)
        games = [row[0] for row in repo.recent_rounds(self.user_id)]
        self.assertEqual(sorted(games), ["keno", "slots"])

    def play_out(self, state, payout):
        """Finish a table with legal moves, whatever phase it is in."""
        while payout is None:
            actions = blackjack.available_actions(state)
            move = (
                "decline_insurance" if "decline_insurance" in actions
                else "stand"
            )
            state, payout = repo.act_on_table(self.user_id, move)
        return state, payout

    def test_the_stake_leaves_when_the_hand_is_dealt(self):
        rng = random.Random(8)
        before = self.player().money
        state, payout = repo.deal_blackjack(self.user_id, 500, rng)
        if payout is None:
            self.assertEqual(self.player().money, before - 500)
        else:
            self.assertEqual(self.player().money, before - 500 + payout)

    def test_a_table_settles_back_to_the_right_balance(self):
        rng = random.Random(12)
        for _ in range(25):
            before = self.player().money
            state, payout = repo.deal_blackjack(self.user_id, 100, rng)
            state, payout = self.play_out(state, payout)
            self.assertEqual(
                self.player().money, before - state.staked + payout
            )

    def test_every_extra_stake_is_taken_when_it_is_put_down(self):
        """Doubles, splits and insurance each move money the moment they
        happen, not when the table settles."""
        rng = random.Random(77)
        seen = set()
        wanted = {"split", "double", "insurance", "surrender"}
        for _ in range(900):
            before = self.player().money
            state, payout = repo.deal_blackjack(self.user_id, 100, rng)
            while payout is None:
                actions = blackjack.available_actions(state)
                move = next(
                    (want for want in wanted if want in actions and want not in seen),
                    None,
                )
                if move is None:
                    move = (
                        "decline_insurance" if "decline_insurance" in actions
                        else "stand"
                    )
                seen.add(move)
                state, payout = repo.act_on_table(self.user_id, move)
            self.assertEqual(
                self.player().money, before - state.staked + payout
            )
            if wanted <= seen:
                return
        self.skipTest("not every branch came up")

    def test_a_second_table_is_refused_while_one_is_open(self):
        rng = random.Random(3)
        state, payout = repo.deal_blackjack(self.user_id, 100, rng)
        if payout is None:
            with self.assertRaises(CasinoError):
                repo.deal_blackjack(self.user_id, 100, rng)

    def test_acting_without_a_table_is_refused(self):
        with self.assertRaises(CasinoError):
            repo.act_on_table(self.user_id, "stand")

    def test_an_unknown_move_is_refused(self):
        with self.assertRaises(CasinoError):
            repo.act_on_table(self.user_id, "fold")

    def test_the_casino_cannot_be_played_from_another_district(self):
        self.set(current_district="camden")
        with self.assertRaises(CasinoError):
            repo.play_slots(self.user_id, 100, random.Random(1))

    def test_the_casino_is_shut_while_restricted(self):
        self.set(jail_until="2030-01-01T00:00:00Z")
        with self.assertRaises(CasinoError):
            repo.play_slots(self.user_id, 100, random.Random(1))

    def test_a_refused_round_moves_no_money_and_logs_nothing(self):
        before = self.player().money
        with self.assertRaises(CasinoError):
            repo.play_slots(self.user_id, 10_000_000, random.Random(1))
        self.assertEqual(self.player().money, before)
        self.assertEqual(repo.recent_rounds(self.user_id), [])

    def test_a_table_can_be_finished_after_leaving_soho(self):
        # The stake has already gone; getting on a bus must not strand it.
        rng = random.Random(17)
        state, payout = repo.deal_blackjack(self.user_id, 100, rng)
        if payout is not None:
            self.skipTest("settled on the deal")
        self.set(current_district="camden")
        state, payout = self.play_out(state, payout)
        self.assertEqual(state.state, blackjack.SETTLED)


if __name__ == "__main__":
    unittest.main()
