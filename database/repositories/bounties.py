"""The bounty board.

Pure rules live in `game/combat/bounties.py`; this is the part that
holds the money.

A posted bounty is escrowed, exactly like a market listing: the stake
leaves the poster's wallet before the row exists, so a bounty can never
be worth more than somebody actually put up. It comes back out of the
row in one of two ways -- collected by whoever hospitalises the target,
or returned when it lapses a week later.

Every write runs inside BEGIN IMMEDIATE and re-reads under the write
lock. `claim_on` is the exception, and deliberately so: it is handed the
connection of the transaction that is already settling the fight, so
collecting a bounty and putting its target in hospital either both
happen or neither does.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from database.core.connection import get_connection
from game.combat.bounties import (
    BOUNTY_LIFETIME_SECONDS,
    MAXIMUM_OPEN_BOUNTIES,
    NEW_PLAYER_PROTECTION_HOURS,
    BountyError,
    collectable,
    posting_fee,
    seconds_left,
    total_cost,
    validate_stake,
)
from game.player.regeneration import format_timestamp, parse_timestamp


@dataclass(frozen=True)
class PostedBounty:
    target_name: str
    amount: int
    fee: int
    expires_at: str


@dataclass(frozen=True)
class BountyClaim:
    collected: int
    bounties: int
    skipped: int


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _moment(value, fallback):
    stamp = parse_timestamp(value)
    if stamp is None:
        return fallback
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp


def _notify(connection, player_id, message, now):
    connection.execute(
        """
        INSERT INTO pvp_notifications (
            player_id, attack_id, message, created_at
        ) VALUES (?, NULL, ?, ?)
        """,
        (player_id, message, now.isoformat()),
    )


def expire_lapsed(connection, now):
    """Hand back the stake on every bounty whose week is up.

    Run at the top of every read and every write, which is how the rest
    of this game handles time: there is no scheduler, so a clock is
    settled by whoever next looks at it. Refunding under the caller's
    write lock is what stops a bounty being both collected and
    refunded by two requests racing.
    """
    stamp = format_timestamp(now)
    rows = connection.execute(
        """
        SELECT id, poster_id, target_id, amount
        FROM player_bounties
        WHERE status = 'open' AND expires_at <= ?
        """,
        (stamp,),
    ).fetchall()

    for bounty_id, poster_id, target_id, amount in rows:
        changed = connection.execute(
            "UPDATE player_bounties SET status = 'expired' "
            "WHERE id = ? AND status = 'open'",
            (bounty_id,),
        ).rowcount

        if changed != 1:
            continue

        connection.execute(
            "UPDATE players SET money = money + ? WHERE id = ?",
            (amount, poster_id),
        )
        name = _name(connection, target_id)
        _notify(
            connection,
            poster_id,
            f"Nobody collected your £{amount:,} bounty on {name}. "
            "The stake has been returned.",
            now,
        )

    return len(rows)


def _name(connection, player_id):
    row = connection.execute(
        "SELECT name FROM players WHERE id = ?",
        (player_id,),
    ).fetchone()

    return row[0] if row else "a player"


def sweep(now=None):
    """Settle lapsed bounties in a transaction of their own.

    Called once per request that shows the board, rather than by every
    reader: the readers below all filter lapsed rows out in SQL, so
    what the sweep decides is when the stake goes back, not whether a
    dead bounty is visible.
    """
    now = _now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        expired = expire_lapsed(connection, now)
        connection.commit()
        return expired
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def find_target(name):
    """A player id from a typed name, or None.

    The board is London-wide -- a price on a head does not stop at the
    district boundary -- so a target is named rather than picked out of
    the local fight list. Matched without case, because nobody
    remembers whether it was `Vic` or `vic`.
    """
    if not name or not name.strip():
        return None

    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT id FROM players WHERE name = ? COLLATE NOCASE",
            (name.strip(),),
        ).fetchone()
    finally:
        connection.close()

    return row[0] if row else None


def post_bounty(user_id, target_id, amount, now=None):
    """Put money on a name.

    The stake and the fee both leave the poster here. Only the stake is
    recoverable; the fee is the sink that stops the board being a free
    way to move money between two accounts.
    """
    validate_stake(amount)

    now = _now(now)
    cost = total_cost(amount)
    fee = posting_fee(amount)

    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        expire_lapsed(connection, now)

        poster = connection.execute(
            "SELECT id, money FROM players WHERE user_id = ?",
            (user_id,),
        ).fetchone()

        if poster is None:
            raise BountyError("You do not have a character yet.")

        poster_id, money = poster

        if poster_id == target_id:
            raise BountyError(
                "Putting a price on your own head is not a plan."
            )

        target = connection.execute(
            """
            SELECT players.name, users.created_at
            FROM players
            JOIN users ON users.id = players.user_id
            WHERE players.id = ?
            """,
            (target_id,),
        ).fetchone()

        if target is None:
            raise BountyError("That player does not exist.")

        target_name, joined_at = target
        protection = _moment(joined_at, now) + timedelta(
            hours=NEW_PLAYER_PROTECTION_HOURS
        )

        if now < protection:
            raise BountyError(
                f"{target_name} is still under new player protection."
            )

        running = connection.execute(
            """
            SELECT COUNT(*) FROM player_bounties
            WHERE poster_id = ? AND status = 'open'
            """,
            (poster_id,),
        ).fetchone()[0]

        if running >= MAXIMUM_OPEN_BOUNTIES:
            raise BountyError(
                f"You already have {MAXIMUM_OPEN_BOUNTIES} bounties "
                "running. Wait for one to be collected or to lapse."
            )

        if money < cost:
            raise BountyError(
                f"That costs £{cost:,} with the fixer's cut. "
                f"You have £{money:,}."
            )

        moved = connection.execute(
            "UPDATE players SET money = money - ? "
            "WHERE id = ? AND money >= ?",
            (cost, poster_id, cost),
        ).rowcount

        if moved != 1:
            raise BountyError("You cannot afford that.")

        expires = now + timedelta(seconds=BOUNTY_LIFETIME_SECONDS)
        connection.execute(
            """
            INSERT INTO player_bounties (
                poster_id, target_id, amount, fee,
                status, created_at, expires_at
            ) VALUES (?, ?, ?, ?, 'open', ?, ?)
            """,
            (
                poster_id, target_id, amount, fee,
                format_timestamp(now), format_timestamp(expires),
            ),
        )

        poster_name = _name(connection, poster_id)
        _notify(
            connection,
            target_id,
            f"{poster_name} has put £{amount:,} on your head. "
            "It is collected by whoever puts you in hospital.",
            now,
        )

        connection.commit()

        return PostedBounty(
            target_name=target_name,
            amount=amount,
            fee=fee,
            expires_at=format_timestamp(expires),
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_board(viewer_id=None, limit=50, now=None):
    """Every open bounty, dearest head first.

    Grouped by target rather than listed one row per stake, because
    what a hunter needs to know is what a name is worth in total, not
    that four people each want a piece of it.
    """
    now = _now(now)
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                b.target_id,
                players.name,
                players.level,
                SUM(b.amount),
                COUNT(*),
                MIN(b.expires_at),
                MAX(CASE WHEN b.poster_id = ? THEN 1 ELSE 0 END),
                CASE
                    WHEN players.travel_destination IS NOT NULL
                         AND players.travel_until > ?
                    THEN NULL
                    WHEN players.travel_destination IS NOT NULL
                         AND players.travel_until <= ?
                    THEN players.travel_destination
                    ELSE players.current_district
                END
            FROM player_bounties AS b
            JOIN players ON players.id = b.target_id
            WHERE b.status = 'open' AND b.expires_at > ?
            GROUP BY b.target_id
            ORDER BY SUM(b.amount) DESC, players.name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (
                viewer_id or 0,
                format_timestamp(now),
                format_timestamp(now),
                format_timestamp(now),
                limit,
            ),
        ).fetchall()
    finally:
        connection.close()

    board = []
    for row in rows:
        board.append({
            "target_id": row[0],
            "name": row[1],
            "level": row[2],
            "total": row[3],
            "bounties": row[4],
            "seconds_left": seconds_left(_moment(row[5], now), now),
            "yours": bool(row[6]),
            "district": row[7],
        })

    return board


def open_bounty_totals(target_ids, now=None):
    """What each of these heads is worth, for the fight list badges."""
    ids = tuple({int(target_id) for target_id in target_ids})
    if not ids:
        return {}

    now = _now(now)
    placeholders = ",".join("?" for _ in ids)
    connection = get_connection()
    try:
        rows = connection.execute(
            f"""
            SELECT target_id, SUM(amount), COUNT(*)
            FROM player_bounties
            WHERE status = 'open'
              AND expires_at > ?
              AND target_id IN ({placeholders})
            GROUP BY target_id
            """,
            (format_timestamp(now),) + ids,
        ).fetchall()
    finally:
        connection.close()

    return {
        row[0]: {"total": row[1], "bounties": row[2]}
        for row in rows
    }


def bounty_on(target_id, now=None):
    """The total open on one head, or zero."""
    totals = open_bounty_totals((target_id,), now=now)

    return totals.get(int(target_id), {}).get("total", 0)


def bounties_posted_by(poster_id, limit=20):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT b.id, players.name, b.amount, b.status,
                   b.expires_at, b.claimed_at
            FROM player_bounties AS b
            JOIN players ON players.id = b.target_id
            WHERE b.poster_id = ?
            ORDER BY b.id DESC
            LIMIT ?
            """,
            (poster_id, limit),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "id": row[0],
            "name": row[1],
            "amount": row[2],
            "status": row[3],
            "expires_at": row[4],
            "claimed_at": row[5],
        }
        for row in rows
    ]


def claim_on(connection, target_id, claimer_id, attack_id, now):
    """Collect every bounty this winner is entitled to, once.

    Called with the connection of the transaction already settling the
    fight, so the payout and the hospital bed commit together. Bounties
    the winner posted themselves are left open rather than paid: you do
    not get your own money back for a fight you were always going to
    have.
    """
    now = _now(now)
    expire_lapsed(connection, now)

    rows = connection.execute(
        """
        SELECT id, poster_id, amount
        FROM player_bounties
        WHERE target_id = ? AND status = 'open'
        """,
        (target_id,),
    ).fetchall()

    open_bounties = [
        {"id": row[0], "poster_id": row[1], "amount": row[2]}
        for row in rows
    ]
    payable, skipped = collectable(open_bounties, claimer_id)

    if not payable:
        return BountyClaim(collected=0, bounties=0, skipped=len(skipped))

    collected = 0
    taken = 0
    target_name = _name(connection, target_id)
    claimer_name = _name(connection, claimer_id)

    for bounty in payable:
        changed = connection.execute(
            """
            UPDATE player_bounties
            SET status = 'claimed', claimed_by = ?,
                claimed_at = ?, attack_id = ?
            WHERE id = ? AND status = 'open'
            """,
            (
                claimer_id, format_timestamp(now), attack_id,
                bounty["id"],
            ),
        ).rowcount

        if changed != 1:
            # Somebody else collected it between the read and the
            # write. Their payout, not ours.
            continue

        collected += 1
        taken += bounty["amount"]
        _notify(
            connection,
            bounty["poster_id"],
            f"{claimer_name} collected your £{bounty['amount']:,} "
            f"bounty on {target_name}.",
            now,
        )

    if not taken:
        return BountyClaim(collected=0, bounties=0, skipped=len(skipped))

    connection.execute(
        "UPDATE players SET money = money + ? WHERE id = ?",
        (taken, claimer_id),
    )
    _notify(
        connection,
        target_id,
        f"{claimer_name} collected £{taken:,} in bounties for "
        "putting you in hospital.",
        now,
    )

    return BountyClaim(
        collected=taken,
        bounties=collected,
        skipped=len(skipped),
    )


def total_open(now=None):
    """Everything currently sat on the board, for the page header."""
    now = _now(now)
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT COALESCE(SUM(amount), 0), COUNT(*)
            FROM player_bounties
            WHERE status = 'open' AND expires_at > ?
            """,
            (format_timestamp(now),),
        ).fetchone()
    finally:
        connection.close()

    return {"total": row[0], "bounties": row[1]}
