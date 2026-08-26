"""Blackjack, dealt from a six-deck shoe.

House rules, all the player-friendly variants, which is what keeps the
edge near half a percent rather than the two or three a stingier table
takes:

  * the dealer stands on every 17, soft ones included
  * a natural blackjack pays 3:2
  * doubling on any two cards, including after a split
  * splitting up to four hands; split aces get one card each
  * insurance offered when the dealer shows an ace, paying 2:1
  * late surrender, before any other action, forfeiting half the stake

A split turns one hand into several, so the table -- not the hand -- is
the unit of state. Hands are played left to right; `active` is the one in
front of the player. The shoe is dealt server-side and persisted between
requests, so a table in progress survives a reload and the client never
learns the order of the undealt cards.
"""

import random
from dataclasses import dataclass, replace


RANKS = ("A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K")
SUITS = ("S", "H", "D", "C")
DECKS = 6
DEALER_STANDS_ON = 17
BLACKJACK_NUMERATOR, BLACKJACK_DENOMINATOR = 3, 2
INSURANCE_PAYS = 2
MAXIMUM_HANDS = 4

# Table states.
INSURANCE_OFFERED = "insurance_offered"
PLAYER_TURN = "player_turn"
SETTLED = "settled"

# Per-hand outcomes.
PLAYER_BLACKJACK = "player_blackjack"
PLAYER_WIN = "player_win"
DEALER_WIN = "dealer_win"
PUSH = "push"
PLAYER_BUST = "player_bust"
DEALER_BUST = "dealer_bust"
SURRENDERED = "surrendered"

OUTCOME_LINES = {
    PLAYER_BLACKJACK: "Blackjack — pays 3:2",
    PLAYER_WIN: "Win",
    DEALER_WIN: "Dealer wins",
    DEALER_BUST: "Dealer busts",
    PLAYER_BUST: "Bust",
    PUSH: "Push",
    SURRENDERED: "Surrendered",
}


class BlackjackError(Exception):
    """Raised when an action is not legal on this table."""


@dataclass(frozen=True)
class Hand:
    cards: tuple
    bet: int
    doubled: bool = False
    from_split: bool = False
    split_aces: bool = False
    finished: bool = False
    outcome: str | None = None
    payout: int = 0

    @property
    def total(self):
        return hand_value(self.cards)[0]

    @property
    def soft(self):
        return hand_value(self.cards)[1]

    @property
    def natural(self):
        # A 21 made from split cards is not a natural.
        return (
            len(self.cards) == 2
            and not self.from_split
            and hand_value(self.cards)[0] == 21
        )


@dataclass(frozen=True)
class TableState:
    shoe: tuple
    cursor: int
    hands: tuple
    active: int
    dealer: tuple
    state: str
    insurance: int = 0
    insurance_payout: int = 0

    @property
    def staked(self):
        """Everything the player has put on the table."""
        return sum(hand.bet for hand in self.hands) + self.insurance

    @property
    def payout(self):
        return sum(hand.payout for hand in self.hands) + self.insurance_payout

    @property
    def current(self):
        if not 0 <= self.active < len(self.hands):
            return None
        return self.hands[self.active]


# ------------------------------------------------------------ card maths

def build_shoe(rng=None):
    rng = rng or random
    cards = [rank + suit for _ in range(DECKS) for suit in SUITS for rank in RANKS]
    for index in range(len(cards) - 1, 0, -1):
        swap = rng.randint(0, index)
        cards[index], cards[swap] = cards[swap], cards[index]
    return tuple(cards)


def card_rank(card):
    return card[:-1]


def card_value(card):
    rank = card_rank(card)
    if rank == "A":
        return 11
    return 10 if rank in ("10", "J", "Q", "K") else int(rank)


def hand_value(cards):
    """Best total, and whether an ace is still being counted as eleven."""
    total = sum(card_value(card) for card in cards)
    aces = sum(1 for card in cards if card_rank(card) == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total, aces > 0


def is_blackjack(cards):
    return len(cards) == 2 and hand_value(cards)[0] == 21


def is_bust(cards):
    return hand_value(cards)[0] > 21


def dealer_shows_ace(state):
    return bool(state.dealer) and card_rank(state.dealer[0]) == "A"


# --------------------------------------------------------------- dealing

def _take(state, count):
    cards = state.shoe[state.cursor:state.cursor + count]
    if len(cards) < count:
        raise BlackjackError("The shoe is spent.")
    return cards, state.cursor + count


def open_table(bet, rng=None):
    """Deal two cards each, then offer insurance or settle a natural."""
    shoe = build_shoe(rng)
    state = TableState(
        shoe=shoe, cursor=0, hands=(Hand(cards=(), bet=bet),), active=0,
        dealer=(), state=PLAYER_TURN,
    )
    player, cursor = _take(state, 2)
    state = replace(
        state, hands=(replace(state.hands[0], cards=player),), cursor=cursor
    )
    dealer, cursor = _take(state, 2)
    state = replace(state, dealer=dealer, cursor=cursor)

    if dealer_shows_ace(state):
        return replace(state, state=INSURANCE_OFFERED)
    if state.hands[0].natural or is_blackjack(state.dealer):
        return settle(state)
    return state


# --------------------------------------------------------------- actions

def _require_turn(state):
    if state.state != PLAYER_TURN:
        if state.state == INSURANCE_OFFERED:
            raise BlackjackError("Answer the insurance offer first.")
        raise BlackjackError("This table is already finished.")
    if state.current is None:
        raise BlackjackError("There is no hand in front of you.")


def available_actions(state):
    """What the player may legally do right now."""
    if state.state == INSURANCE_OFFERED:
        return ("insurance", "decline_insurance")
    if state.state != PLAYER_TURN or state.current is None:
        return ()

    hand = state.current
    actions = ["hit", "stand"]
    opening = len(hand.cards) == 2

    if opening and not hand.split_aces:
        actions.append("double")
    if (
        opening
        and not hand.from_split
        and len(state.hands) == 1
        and not state.insurance
    ):
        actions.append("surrender")
    if (
        opening
        and len(state.hands) < MAXIMUM_HANDS
        and card_value(hand.cards[0]) == card_value(hand.cards[1])
    ):
        actions.append("split")
    return tuple(actions)


def _require(state, action):
    if action not in available_actions(state):
        raise BlackjackError(f"You cannot {action.replace('_', ' ')} here.")


def take_insurance(state):
    _require(state, "insurance")
    # Half the opening stake, taken as a side bet.
    stake = state.hands[0].bet // 2
    state = replace(state, insurance=stake, state=PLAYER_TURN)
    return _after_insurance(state)


def decline_insurance(state):
    _require(state, "decline_insurance")
    return _after_insurance(replace(state, state=PLAYER_TURN))


def _after_insurance(state):
    """Once insurance is answered, a dealer natural ends it immediately."""
    if is_blackjack(state.dealer) or state.hands[0].natural:
        return settle(state)
    return state


def hit(state):
    _require_turn(state)
    _require(state, "hit")
    cards, cursor = _take(state, 1)
    hand = replace(state.current, cards=state.current.cards + cards)
    state = _replace_current(replace(state, cursor=cursor), hand)

    if is_bust(hand.cards):
        return _finish_hand(state)
    return state


def double_down(state):
    _require_turn(state)
    _require(state, "double")
    cards, cursor = _take(state, 1)
    hand = replace(
        state.current,
        cards=state.current.cards + cards,
        bet=state.current.bet * 2,
        doubled=True,
    )
    return _finish_hand(_replace_current(replace(state, cursor=cursor), hand))


def stand(state):
    _require_turn(state)
    _require(state, "stand")
    return _finish_hand(state)


def surrender(state):
    _require_turn(state)
    _require(state, "surrender")
    hand = replace(
        state.current,
        finished=True,
        outcome=SURRENDERED,
        payout=state.current.bet // 2,
    )
    state = _replace_current(state, hand)
    return _advance(state)


def split(state):
    _require_turn(state)
    _require(state, "split")

    hand = state.current
    aces = card_rank(hand.cards[0]) == "A"
    first, second = hand.cards

    cards, cursor = _take(state, 2)
    state = replace(state, cursor=cursor)

    left = Hand(
        cards=(first, cards[0]), bet=hand.bet,
        from_split=True, split_aces=aces,
    )
    right = Hand(
        cards=(second, cards[1]), bet=hand.bet,
        from_split=True, split_aces=aces,
    )
    hands = (
        state.hands[:state.active] + (left, right) + state.hands[state.active + 1:]
    )
    state = replace(state, hands=hands)

    # Split aces take exactly one card each and are then done.
    if aces:
        state = _replace_current(state, replace(left, finished=True))
        state = _advance(state)
        if state.state == PLAYER_TURN and state.current is not None:
            state = _replace_current(
                state, replace(state.current, finished=True)
            )
            state = _advance(state)
    return state


# ------------------------------------------------------------ settlement

def _replace_current(state, hand):
    hands = list(state.hands)
    hands[state.active] = hand
    return replace(state, hands=tuple(hands))


def _finish_hand(state):
    return _advance(_replace_current(state, replace(state.current, finished=True)))


def _advance(state):
    """Move to the next unfinished hand, or settle the table."""
    for index in range(state.active + 1, len(state.hands)):
        if not state.hands[index].finished:
            return replace(state, active=index)
    return settle(state)


def _play_dealer(state):
    dealer = state.dealer
    cursor = state.cursor
    while hand_value(dealer)[0] < DEALER_STANDS_ON:
        card = state.shoe[cursor:cursor + 1]
        if not card:
            raise BlackjackError("The shoe is spent.")
        dealer += card
        cursor += 1
    return dealer, cursor


def settle(state):
    dealer_natural = is_blackjack(state.dealer)

    insurance_payout = 0
    if state.insurance:
        # Insurance pays 2:1 and returns the side stake, or loses it.
        insurance_payout = (
            state.insurance + state.insurance * INSURANCE_PAYS
            if dealer_natural else 0
        )

    # The dealer only draws if some hand is still live.
    live = [
        hand for hand in state.hands
        if hand.outcome != SURRENDERED and not is_bust(hand.cards)
    ]
    if dealer_natural or not live:
        dealer, cursor = state.dealer, state.cursor
    else:
        dealer, cursor = _play_dealer(state)

    dealer_total = hand_value(dealer)[0]
    dealer_busted = dealer_total > 21

    settled = []
    for hand in state.hands:
        if hand.outcome == SURRENDERED:
            settled.append(hand)
            continue
        settled.append(_settle_hand(hand, dealer_total, dealer_busted, dealer_natural))

    return replace(
        state,
        hands=tuple(settled),
        dealer=dealer,
        cursor=cursor,
        state=SETTLED,
        insurance_payout=insurance_payout,
    )


def _settle_hand(hand, dealer_total, dealer_busted, dealer_natural):
    if is_bust(hand.cards):
        return replace(hand, finished=True, outcome=PLAYER_BUST, payout=0)

    if hand.natural:
        if dealer_natural:
            return replace(hand, finished=True, outcome=PUSH, payout=hand.bet)
        won = hand.bet * BLACKJACK_NUMERATOR // BLACKJACK_DENOMINATOR
        return replace(
            hand, finished=True, outcome=PLAYER_BLACKJACK, payout=hand.bet + won
        )

    if dealer_natural:
        return replace(hand, finished=True, outcome=DEALER_WIN, payout=0)

    total = hand.total
    if dealer_busted:
        return replace(
            hand, finished=True, outcome=DEALER_BUST, payout=hand.bet * 2
        )
    if total > dealer_total:
        return replace(
            hand, finished=True, outcome=PLAYER_WIN, payout=hand.bet * 2
        )
    if total < dealer_total:
        return replace(hand, finished=True, outcome=DEALER_WIN, payout=0)
    return replace(hand, finished=True, outcome=PUSH, payout=hand.bet)


def describe(state):
    """One line summarising how the table finished."""
    if state.state != SETTLED:
        return ""
    if len(state.hands) == 1 and not state.insurance:
        return OUTCOME_LINES.get(state.hands[0].outcome, "")

    parts = [
        OUTCOME_LINES.get(hand.outcome, "") for hand in state.hands
    ]
    if state.insurance:
        parts.append(
            "insurance paid" if state.insurance_payout else "insurance lost"
        )
    return ", ".join(part for part in parts if part)
