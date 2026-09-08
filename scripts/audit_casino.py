#!/usr/bin/env python3
"""Check the casino against real play rather than against its own maths.

Every settled round is written to `casino_rounds` precisely so this is
possible, and for a long time the tables had only ever been checked
against their own paytables. That is the weaker of the two checks:
arithmetic proves the design is right, this proves the code dealing the
cards agrees with it.

Read-only. It opens the database, counts, and prints.

Usage:

    python3 scripts/audit_casino.py                 the whole book
    python3 scripts/audit_casino.py USERNAME        one player's book

Why the error bars are computed rather than sampled
---------------------------------------------------

A casino's returns are heavy-tailed, and the first version of this
script got that wrong badly enough to accuse a healthy fruit machine of
robbery. The reels pay 750x on three sevens, once every 9,261 spins.
Until that lands the observed spread is tiny, so a standard error taken
from the sample itself comes out far too small and the measured return
looks impossibly low with confident narrow bounds around it.

So for slots and keno the spread is derived from the paytable -- exactly,
the same way the returns are -- rather than measured. The true standard
deviation of a single spin is about 9 times the stake, which is why it
takes roughly 344,000 spins to pin the return to within three points.
Small samples are not evidence of anything and this script says so
instead of guessing.

Blackjack is different: a round pays between nothing and two and a half
times the stake, with no jackpot, so its spread is well behaved and is
measured from the rounds themselves.

Reading the result
------------------

Blackjack's advertised 99.65% assumes basic strategy. A player who
doubles on everything faces closer to 66%, and that is not the house
misbehaving -- it is the condition attached to the number. The rate at
which stakes are raised mid-hand is printed for exactly that reason.
"""

import sys
from itertools import product
from math import sqrt
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.core.connection import DB_PATH, get_connection
from game.casino import keno, slots
from game.casino.blackjack import BASIC_STRATEGY_EDGE
from game.casino.limits import DENOMINATIONS


# A verdict is only worth printing once the interval is this tight.
USEFUL_HALF_WIDTH = 0.03


def slots_spread():
    """Mean and standard deviation of one spin, from the paytable."""
    stops = len(slots.STRIP)
    first = second = 0.0

    for reels in product(slots.REEL_WEIGHTS, repeat=slots.REEL_COUNT):
        probability = 1.0
        for symbol in reels:
            probability *= slots.REEL_WEIGHTS[symbol] / stops
        multiplier = slots.score(reels)[0]
        first += probability * multiplier
        second += probability * multiplier * multiplier

    return first, sqrt(second - first * first)


def keno_spread(spots):
    """Mean and standard deviation of one keno round at this spot count."""
    first = second = 0.0

    for hits in range(spots + 1):
        probability = keno.match_probability(spots, hits)
        multiplier = keno.PAYTABLE[spots].get(hits, 0)
        first += probability * multiplier
        second += probability * multiplier * multiplier

    return first, sqrt(second - first * first)


def _spot_count(detail):
    """Keno logs its rounds as "hits/picks"; the picks set the spread."""
    try:
        return int(str(detail).split("/")[1])
    except (AttributeError, IndexError, ValueError):
        return None


def _rows(connection, username=None):
    if username:
        return connection.execute(
            """
            SELECT r.game, r.bet, r.payout, r.detail
            FROM casino_rounds r
            JOIN players p ON p.id = r.player_id
            JOIN users u ON u.id = p.user_id
            WHERE u.username = ?
            """,
            (username,),
        ).fetchall()

    return connection.execute(
        "SELECT game, bet, payout, detail FROM casino_rounds"
    ).fetchall()


def _book(rows, game):
    """Totals for one game, plus what it takes to put bounds on them.

    Stakes vary, so the effective sample size is not the number of
    rounds: one £50,000 hand carries as much weight as a hundred £500
    ones. `(sum of stakes)^2 / (sum of squared stakes)` is that weight
    expressed as a round count.
    """
    staked = returned = 0
    squares = 0
    rounds = 0
    ratio_squares = 0.0
    spots = {}

    for row_game, bet, payout, detail in rows:
        if row_game != game or not bet:
            continue
        rounds += 1
        staked += bet
        returned += payout
        squares += bet * bet
        ratio = payout / bet
        ratio_squares += ratio * ratio
        if game == "keno":
            count = _spot_count(detail)
            if count is not None:
                spots[count] = spots.get(count, 0) + 1

    if not rounds:
        return None

    effective = (staked * staked) / squares if squares else 0

    if game == "slots":
        deviation = slots_spread()[1]
    elif game == "keno":
        # Rounds are a mix of spot counts, each with its own spread.
        total = sum(spots.values()) or 1
        variance = sum(
            share / total * keno_spread(count)[1] ** 2
            for count, share in spots.items()
            if count in keno.PAYTABLE
        )
        deviation = sqrt(variance) if variance else 0.0
    else:
        # Bounded payouts, so the rounds themselves are a fair guide.
        mean = returned / staked if staked else 0.0
        deviation = sqrt(max(0.0, ratio_squares / rounds - mean * mean))

    return {
        "rounds": rounds,
        "staked": staked,
        "returned": returned,
        "measured": returned / staked if staked else 0.0,
        "error": deviation / sqrt(effective) if effective else 0.0,
        "deviation": deviation,
    }


def advertised():
    low, high = keno.return_range()

    return {
        "slots": (slots.return_to_player(),) * 2,
        "keno": (low, high),
        "blackjack": (1 - BASIC_STRATEGY_EDGE,) * 2,
    }


def report(rows):
    targets = advertised()
    seen = False

    for game in ("slots", "keno", "blackjack"):
        book = _book(rows, game)
        if book is None:
            continue
        seen = True

        low, high = targets[game]
        half = 1.96 * book["error"]
        band = (
            f"{low * 100:.2f}%"
            if low == high
            else f"{low * 100:.2f}%-{high * 100:.2f}%"
        )

        print(f"\n{game.upper()}")
        print(f"  rounds played : {book['rounds']:,}")
        print(f"  staked        : £{book['staked']:,}")
        print(f"  returned      : £{book['returned']:,}")
        print(f"  net to house  : £{book['staked'] - book['returned']:,}")
        print(
            f"  measured RTP  : {book['measured'] * 100:.2f}%"
            f"  ± {half * 100:.2f} at 95%"
        )
        print(f"  advertised    : {band}")

        if half > USEFUL_HALF_WIDTH:
            needed = (1.96 * book["deviation"] / USEFUL_HALF_WIDTH) ** 2
            print(
                f"  verdict       : too few rounds to judge. This game needs"
                f" about {needed:,.0f}"
            )
            print(
                f"                  to place the return within"
                f" {USEFUL_HALF_WIDTH * 100:.0f} points."
            )
        elif book["measured"] - half <= high and book["measured"] + half >= low:
            print("  verdict       : agrees with the advertised figure")
        else:
            print("  verdict       : DOES NOT AGREE -- worth investigating")

    if not seen:
        print("\nNo rounds have been played yet.")


def doubling(rows):
    """How often blackjack players are raising a stake mid-hand.

    A doubled or split hand is logged at more than the opening stake,
    and the chip rail only offers round denominations, so a stake that
    is not a chip is a hand somebody put more money on.
    """
    hands = [row for row in rows if row[0] == "blackjack" and row[1]]
    if not hands:
        return

    raised = [row for row in hands if row[1] not in DENOMINATIONS]
    share = len(raised) / len(hands) * 100

    print("\nBLACKJACK, how it is being played")
    print(f"  hands                : {len(hands):,}")
    print(f"  stake raised mid-hand: {len(raised):,}  ({share:.1f}%)")
    print("  Basic strategy doubles or splits about 12% of hands.")

    if share > 25:
        print(
            "  Well above that, so the players are choosing a worse game"
            " than the one advertised."
        )


def main(argv):
    username = argv[1] if len(argv) > 1 else None

    if not Path(DB_PATH).exists():
        print(f"No database at {DB_PATH}.")
        return 1

    connection = get_connection()
    try:
        rows = _rows(connection, username)
    finally:
        connection.close()

    who = f"for {username}" if username else "across every player"
    print(f"The Golden Square, {who}.")
    print(f"Database: {DB_PATH}")

    report(rows)
    doubling(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
