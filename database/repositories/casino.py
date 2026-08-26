"""Money at the tables.

The rules live in `game.casino`; this stakes and settles them inside one
transaction so a second tab cannot bet the same cash twice, and so a
crash between the stake leaving and the payout arriving is impossible.

Blocking rules mirror every other place you have to physically walk into:
right district, not travelling, not in jail or hospital.
"""

import json
import sqlite3

from database.core.connection import get_connection
from game.casino import blackjack, keno, slots
from game.casino.limits import CasinoError, capped_payout, validate_bet


CASINO_DISTRICT = "soho"


def _load_player(connection, user_id, at_the_table=True):
    """Read the player, checking they may start a round.

    `at_the_table` is relaxed for a hand already in progress: the stake
    has left their pocket, so being carried off to hospital or getting on
    a bus must not strand it.
    """
    row = connection.execute(
        """
        SELECT id, level, money, current_district, travel_destination,
               jail_until, hospital_until
        FROM players
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    if row is None:
        raise CasinoError("Player not found.")

    (
        player_id,
        level,
        money,
        district,
        travelling,
        jail_until,
        hospital_until,
    ) = row

    if at_the_table:
        if district != CASINO_DISTRICT:
            raise CasinoError("The Golden Square is in Soho.")
        if travelling:
            raise CasinoError("You cannot gamble while travelling.")
        if jail_until or hospital_until:
            raise CasinoError("You cannot gamble while restricted.")

    return player_id, level, money


def _settle(connection, player_id, game, bet, payout, detail):
    """Move the net and log the round. Caller owns the transaction."""
    payout = capped_payout(payout)
    net = payout - bet
    connection.execute(
        "UPDATE players SET money = money + ? WHERE id = ?",
        (net, player_id),
    )
    connection.execute(
        """
        INSERT INTO casino_rounds (player_id, game, bet, payout, detail)
        VALUES (?, ?, ?, ?, ?)
        """,
        (player_id, game, bet, payout, detail),
    )
    return payout


def play_slots(user_id, bet, rng=None):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(connection, user_id)
        validate_bet(level, bet, money)

        result = slots.play(bet, rng)
        payout = _settle(
            connection, player_id, "slots", bet, result.payout,
            " ".join(result.reels),
        )
        connection.commit()
        return result, payout
    except (CasinoError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def play_keno(user_id, bet, picks, rounds=1, rng=None):
    """Play the same card for one or more rounds, each drawn separately."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(connection, user_id)
        rounds = keno.validate_rounds(rounds)
        picks = keno.validate_picks(picks)
        validate_bet(level, bet, money)

        # Each round is its own wager, so the whole card has to be
        # affordable before any of it is drawn.
        if bet * rounds > money:
            raise CasinoError(
                f"£{bet * rounds:,} for {rounds} rounds is more than you have."
            )

        results = [keno.play(bet, picks, rng) for _ in range(rounds)]
        payout = 0
        for result in results:
            payout += _settle(
                connection, player_id, "keno", bet, result.payout,
                f"{len(result.hits)}/{len(result.picks)}",
            )
        connection.commit()
        return tuple(results), payout
    except (CasinoError, keno.KenoError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


# ------------------------------------------------------------ blackjack

def _encode(state):
    return json.dumps({
        "shoe": list(state.shoe),
        "cursor": state.cursor,
        "active": state.active,
        "dealer": list(state.dealer),
        "state": state.state,
        "insurance": state.insurance,
        "hands": [
            {
                "cards": list(hand.cards),
                "bet": hand.bet,
                "doubled": hand.doubled,
                "from_split": hand.from_split,
                "split_aces": hand.split_aces,
                "finished": hand.finished,
                "outcome": hand.outcome,
                "payout": hand.payout,
            }
            for hand in state.hands
        ],
    })


def _decode(blob):
    raw = json.loads(blob)
    return blackjack.TableState(
        shoe=tuple(raw["shoe"]),
        cursor=raw["cursor"],
        hands=tuple(
            blackjack.Hand(
                cards=tuple(hand["cards"]),
                bet=hand["bet"],
                doubled=hand["doubled"],
                from_split=hand["from_split"],
                split_aces=hand["split_aces"],
                finished=hand["finished"],
                outcome=hand["outcome"],
                payout=hand["payout"],
            )
            for hand in raw["hands"]
        ),
        active=raw["active"],
        dealer=tuple(raw["dealer"]),
        state=raw["state"],
        insurance=raw["insurance"],
    )


def _store_table(connection, player_id, state):
    connection.execute(
        """
        INSERT INTO casino_hands (player_id, staked, table_state)
        VALUES (?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            staked = excluded.staked,
            table_state = excluded.table_state
        """,
        (player_id, state.staked, _encode(state)),
    )


def _read_table(connection, player_id):
    row = connection.execute(
        "SELECT table_state FROM casino_hands WHERE player_id = ?",
        (player_id,),
    ).fetchone()
    return _decode(row[0]) if row else None


def _clear_table(connection, player_id):
    connection.execute(
        "DELETE FROM casino_hands WHERE player_id = ?", (player_id,)
    )


def get_open_table(user_id):
    """The table in progress, if there is one."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _read_table(connection, row[0])
    finally:
        connection.close()


def _settle_table(connection, player_id, state, already_staked):
    """Pay the table out and log it. Returns what was returned."""
    payout = capped_payout(state.payout)
    outstanding = state.staked - already_staked
    connection.execute(
        "UPDATE players SET money = money + ? WHERE id = ?",
        (payout - outstanding, player_id),
    )
    connection.execute(
        """
        INSERT INTO casino_rounds (player_id, game, bet, payout, detail)
        VALUES (?, 'blackjack', ?, ?, ?)
        """,
        (player_id, state.staked, payout, blackjack.describe(state)),
    )
    _clear_table(connection, player_id)
    return payout


def deal_blackjack(user_id, bet, rng=None):
    """Take the opening stake and deal."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(connection, user_id)
        validate_bet(level, bet, money)

        if _read_table(connection, player_id) is not None:
            raise CasinoError("Finish the hand you are playing.")

        state = blackjack.open_table(bet, rng)

        # The opening stake leaves now, and comes back inside the payout.
        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ?",
            (bet, player_id),
        )

        if state.state == blackjack.SETTLED:
            payout = _settle_table(connection, player_id, state, bet)
            connection.commit()
            return state, payout

        _store_table(connection, player_id, state)
        connection.commit()
        return state, None
    except (CasinoError, blackjack.BlackjackError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


ACTIONS = {
    "hit": blackjack.hit,
    "stand": blackjack.stand,
    "double": blackjack.double_down,
    "split": blackjack.split,
    "surrender": blackjack.surrender,
    "insurance": blackjack.take_insurance,
    "decline_insurance": blackjack.decline_insurance,
}


def act_on_table(user_id, action):
    """Play the table in progress."""
    handler = ACTIONS.get(action)
    if handler is None:
        raise CasinoError("That is not a move.")

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        # A table already paid for can always be finished, wherever the
        # player has ended up since.
        player_id, level, money = _load_player(
            connection, user_id, at_the_table=False
        )

        state = _read_table(connection, player_id)
        if state is None:
            raise CasinoError("You have no hand in play.")

        before = state.staked
        state = handler(state)
        extra = state.staked - before

        # Doubling, splitting and insurance each put more on the table.
        if extra > 0:
            if extra > money:
                raise CasinoError("You cannot cover that.")
            connection.execute(
                "UPDATE players SET money = money - ? WHERE id = ?",
                (extra, player_id),
            )

        if state.state == blackjack.SETTLED:
            payout = _settle_table(
                connection, player_id, state, state.staked
            )
            connection.commit()
            return state, payout

        _store_table(connection, player_id, state)
        connection.commit()
        return state, None
    except (CasinoError, blackjack.BlackjackError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def recent_rounds(user_id, limit=12):
    connection = get_connection()
    try:
        return connection.execute(
            """
            SELECT r.game, r.bet, r.payout, r.detail, r.played_at
            FROM casino_rounds r
            JOIN players p ON p.id = r.player_id
            WHERE p.user_id = ?
            ORDER BY r.id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
    finally:
        connection.close()
