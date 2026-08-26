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


def play_keno(user_id, bet, picks, rng=None):
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(connection, user_id)
        validate_bet(level, bet, money)

        result = keno.play(bet, picks, rng)
        payout = _settle(
            connection, player_id, "keno", bet, result.payout,
            f"{len(result.hits)}/{len(result.picks)}",
        )
        connection.commit()
        return result, payout
    except (CasinoError, keno.KenoError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


# ------------------------------------------------------------ blackjack

def _store_hand(connection, player_id, state):
    connection.execute(
        """
        INSERT INTO casino_hands
            (player_id, bet, shoe, cursor, player_cards, dealer_cards, doubled)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            bet = excluded.bet,
            shoe = excluded.shoe,
            cursor = excluded.cursor,
            player_cards = excluded.player_cards,
            dealer_cards = excluded.dealer_cards,
            doubled = excluded.doubled,
            opened_at = CURRENT_TIMESTAMP
        """,
        (
            player_id,
            state.bet,
            json.dumps(list(state.shoe)),
            state.cursor,
            json.dumps(list(state.player)),
            json.dumps(list(state.dealer)),
            int(state.doubled),
        ),
    )


def _read_hand(connection, player_id):
    row = connection.execute(
        """
        SELECT bet, shoe, cursor, player_cards, dealer_cards, doubled
        FROM casino_hands
        WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()

    if row is None:
        return None

    bet, shoe, cursor, player_cards, dealer_cards, doubled = row
    return blackjack.HandState(
        shoe=tuple(json.loads(shoe)),
        cursor=cursor,
        player=tuple(json.loads(player_cards)),
        dealer=tuple(json.loads(dealer_cards)),
        bet=bet,
        state=blackjack.PLAYER_TURN,
        doubled=bool(doubled),
    )


def _clear_hand(connection, player_id):
    connection.execute(
        "DELETE FROM casino_hands WHERE player_id = ?", (player_id,)
    )


def get_open_hand(user_id):
    """The hand in progress, if there is one. No transaction needed."""
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM players WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            return None
        return _read_hand(connection, row[0])
    finally:
        connection.close()


def deal_blackjack(user_id, bet, rng=None):
    """Take the stake and deal. A natural settles immediately."""
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(connection, user_id)
        validate_bet(level, bet, money)

        if _read_hand(connection, player_id) is not None:
            raise CasinoError("Finish the hand you are playing.")

        state = blackjack.open_hand(bet, rng)

        if state.state == blackjack.SETTLED:
            payout = _settle(
                connection, player_id, "blackjack", state.bet, state.payout,
                state.outcome,
            )
            connection.commit()
            return state, payout

        # The stake is taken now, and returned as part of the payout when
        # the hand settles, so an abandoned hand cannot be a free option.
        connection.execute(
            "UPDATE players SET money = money - ? WHERE id = ?",
            (state.bet, player_id),
        )
        _store_hand(connection, player_id, state)
        connection.commit()
        return state, None
    except (CasinoError, blackjack.BlackjackError, sqlite3.Error):
        connection.rollback()
        raise
    finally:
        connection.close()


def act_on_hand(user_id, action):
    """Hit, stand or double the hand in progress."""
    if action not in ("hit", "stand", "double"):
        raise CasinoError("That is not a move.")

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        player_id, level, money = _load_player(
            connection, user_id, at_the_table=False
        )

        state = _read_hand(connection, player_id)
        if state is None:
            raise CasinoError("You have no hand in play.")

        if action == "double":
            # The extra stake is taken now; the original already left.
            if state.bet > money:
                raise CasinoError("You cannot cover the double.")
            state = blackjack.double_down(state)
            connection.execute(
                "UPDATE players SET money = money - ? WHERE id = ?",
                (state.bet // 2, player_id),
            )
        elif action == "hit":
            state = blackjack.hit(state)
        else:
            state = blackjack.stand(state)

        if state.state == blackjack.SETTLED:
            _clear_hand(connection, player_id)
            payout = capped_payout(state.payout)
            connection.execute(
                "UPDATE players SET money = money + ? WHERE id = ?",
                (payout, player_id),
            )
            connection.execute(
                """
                INSERT INTO casino_rounds
                    (player_id, game, bet, payout, detail)
                VALUES (?, 'blackjack', ?, ?, ?)
                """,
                (player_id, state.bet, payout, state.outcome),
            )
            connection.commit()
            return state, payout

        _store_hand(connection, player_id, state)
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
