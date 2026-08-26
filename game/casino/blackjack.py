"""Blackjack, dealt from a six-deck shoe.

House rules, all of them the player-friendly variants that keep the edge
near half a percent rather than the two or three a stingier table takes:

  * the dealer stands on every 17, soft ones included
  * a natural blackjack pays 3:2
  * doubling is allowed on any opening two cards
  * no splitting and no insurance

The shoe is dealt server-side and persisted between requests, so a hand
in progress survives a page reload and the client never learns the order
of the undealt cards.
"""

import random
from dataclasses import dataclass


RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("S", "H", "D", "C")
DECKS = 6
DEALER_STANDS_ON = 17
BLACKJACK_NUMERATOR, BLACKJACK_DENOMINATOR = 3, 2

# Hand states.
PLAYER_TURN = "player_turn"
SETTLED = "settled"

# Outcomes.
PLAYER_BLACKJACK = "player_blackjack"
PLAYER_WIN = "player_win"
DEALER_WIN = "dealer_win"
PUSH = "push"
PLAYER_BUST = "player_bust"
DEALER_BUST = "dealer_bust"


class BlackjackError(Exception):
    """Raised when an action is not legal on this hand."""


@dataclass(frozen=True)
class HandState:
    shoe: tuple
    cursor: int
    player: tuple
    dealer: tuple
    bet: int
    state: str
    doubled: bool = False
    outcome: str | None = None
    payout: int = 0


def build_shoe(rng=None):
    """A shuffled six-deck shoe, dealt from the front."""
    rng = rng or random
    cards = [rank + suit for _ in range(DECKS) for suit in SUITS for rank in RANKS]
    # Fisher-Yates, using the same randint idiom as the rest of the engine.
    for index in range(len(cards) - 1, 0, -1):
        swap = rng.randint(0, index)
        cards[index], cards[swap] = cards[swap], cards[index]
    return tuple(cards)


def card_rank(card):
    return card[:-1]


def hand_value(cards):
    """Best total for a hand, and whether an ace is still counted as 11."""
    total = 0
    aces = 0
    for card in cards:
        rank = card_rank(card)
        if rank == "A":
            aces += 1
            total += 11
        elif rank in ("10", "J", "Q", "K"):
            total += 10
        else:
            total += int(rank)

    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards)[0] == 21


def is_bust(cards):
    return hand_value(cards)[0] > 21


def _deal(state, count):
    """Take cards off the front of the shoe."""
    taken = state.shoe[state.cursor:state.cursor + count]
    if len(taken) < count:
        raise BlackjackError("The shoe is spent.")
    return taken, state.cursor + count


def open_hand(bet, rng=None):
    """Deal the opening two cards each and settle any natural."""
    shoe = build_shoe(rng)
    state = HandState(
        shoe=shoe, cursor=0, player=(), dealer=(), bet=bet, state=PLAYER_TURN
    )
    player, cursor = _deal(state, 2)
    state = HandState(**{**state.__dict__, "player": player, "cursor": cursor})
    dealer, cursor = _deal(state, 2)
    state = HandState(**{**state.__dict__, "dealer": dealer, "cursor": cursor})

    # A natural on either side ends the hand before the player acts.
    if is_blackjack(state.player) or is_blackjack(state.dealer):
        return _settle(state)
    return state


def hit(state):
    _require_turn(state)
    cards, cursor = _deal(state, 1)
    player = state.player + cards
    state = HandState(**{**state.__dict__, "player": player, "cursor": cursor})
    if is_bust(state.player):
        return _settle(state)
    return state


def double_down(state):
    _require_turn(state)
    if len(state.player) != 2:
        raise BlackjackError("You can only double on your opening two cards.")
    cards, cursor = _deal(state, 1)
    state = HandState(**{
        **state.__dict__,
        "player": state.player + cards,
        "cursor": cursor,
        "bet": state.bet * 2,
        "doubled": True,
    })
    return _settle(state)


def stand(state):
    _require_turn(state)
    return _settle(state)


def _require_turn(state):
    if state.state != PLAYER_TURN:
        raise BlackjackError("This hand is already finished.")


def _play_dealer(state):
    """The dealer draws to 17 and stands on every 17."""
    dealer = state.dealer
    cursor = state.cursor
    while True:
        total, _ = hand_value(dealer)
        if total >= DEALER_STANDS_ON:
            break
        card = state.shoe[cursor:cursor + 1]
        if not card:
            raise BlackjackError("The shoe is spent.")
        dealer += card
        cursor += 1
    return dealer, cursor


def _settle(state):
    player_total, _ = hand_value(state.player)
    player_natural = is_blackjack(state.player)
    dealer_natural = is_blackjack(state.dealer)

    if is_bust(state.player):
        return _finish(state, state.dealer, state.cursor, PLAYER_BUST, 0)

    if player_natural or dealer_natural:
        if player_natural and dealer_natural:
            return _finish(state, state.dealer, state.cursor, PUSH, state.bet)
        if player_natural:
            payout = state.bet + (
                state.bet * BLACKJACK_NUMERATOR // BLACKJACK_DENOMINATOR
            )
            return _finish(
                state, state.dealer, state.cursor, PLAYER_BLACKJACK, payout
            )
        return _finish(state, state.dealer, state.cursor, DEALER_WIN, 0)

    dealer, cursor = _play_dealer(state)
    dealer_total, _ = hand_value(dealer)

    if dealer_total > 21:
        return _finish(state, dealer, cursor, DEALER_BUST, state.bet * 2)
    if dealer_total > player_total:
        return _finish(state, dealer, cursor, DEALER_WIN, 0)
    if dealer_total < player_total:
        return _finish(state, dealer, cursor, PLAYER_WIN, state.bet * 2)
    return _finish(state, dealer, cursor, PUSH, state.bet)


def _finish(state, dealer, cursor, outcome, payout):
    return HandState(**{
        **state.__dict__,
        "dealer": dealer,
        "cursor": cursor,
        "state": SETTLED,
        "outcome": outcome,
        "payout": payout,
    })


OUTCOME_LINES = {
    PLAYER_BLACKJACK: "Blackjack — pays 3:2",
    PLAYER_WIN: "You win",
    DEALER_WIN: "Dealer wins",
    DEALER_BUST: "Dealer busts — you win",
    PLAYER_BUST: "Bust",
    PUSH: "Push — stake returned",
}


def describe(state):
    return OUTCOME_LINES.get(state.outcome, "")
