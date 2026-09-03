from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import random

from database.core.connection import get_connection
from database.repositories.agents import refuse_if_sealed
from database.repositories.bounties import (
    BountyClaim,
    bounty_on,
    claim_on,
)
from game.combat.pvp import (
    AFTERMATH_CHOICES,
    AFTERMATH_HOSPITALISE,
    AFTERMATH_LEAVE,
    AFTERMATH_MUG,
    AFTERMATH_WINDOW_SECONDS,
    MUG_MAXIMUM_PERCENT,
    MUG_MINIMUM_PERCENT,
    PVP_HOSPITAL_SECONDS,
    Aftermath,
    PvpError,
    mug_takings,
)
from game.combat.rating import (
    DEFAULT_PVP_RATING,
    calculate_rating_change,
)
from game.player.regeneration import format_timestamp, parse_timestamp


TARGET_PROTECTION_SECONDS = 10 * 60
REPEAT_REWARD_SECONDS = 60 * 60
DAILY_REWARDED_ATTACKS = 3


@dataclass(frozen=True)
class RecordedAttack:
    attack_id: int
    attacker_before: int
    attacker_after: int
    defender_before: int
    defender_after: int
    rated: bool

    @property
    def attacker_delta(self):
        return self.attacker_after - self.attacker_before


@dataclass(frozen=True)
class AttackLimits:
    protected_seconds: int
    repeat_seconds: int
    rewarded_attacks_today: int

    @property
    def blocked(self):
        return self.protected_seconds > 0

    @property
    def reward_multiplier(self):
        if self.rewarded_attacks_today >= DAILY_REWARDED_ATTACKS:
            return 0.0
        if self.repeat_seconds > 0:
            return 0.25
        return 1.0


def get_pvp_targets(attacker_id, district, now=None):
    now = _normalise_now(now)
    timestamp = format_timestamp(now)
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                players.id, players.user_id, players.name,
                players.level, players.health, players.money,
                players.strength, players.defence,
                players.speed, players.dexterity,
                players.jail_until, players.hospital_until,
                players.travel_destination, players.travel_until,
                players.shift_until, users.created_at,
                COALESCE(rating.rating, 1000),
                players.max_health,
                players.residence_key
            FROM players
            JOIN users ON users.id = players.user_id
            LEFT JOIN player_pvp_ratings AS rating
                ON rating.player_id = players.id
            WHERE players.id != ?
              AND players.id NOT IN (
                  SELECT players.id FROM agent_keys
                  JOIN players ON players.user_id = agent_keys.user_id
                  WHERE agent_keys.revoked_at IS NULL
              )
              AND (
                  CASE
                      WHEN travel_destination IS NOT NULL
                           AND travel_until <= ?
                      THEN travel_destination
                      ELSE current_district
                  END
              ) = ?
              AND NOT (
                  travel_destination IS NOT NULL
                  AND travel_until > ?
              )
            ORDER BY players.level ASC, players.name COLLATE NOCASE ASC
            LIMIT 40
            """,
            (attacker_id, timestamp, district, timestamp),
        ).fetchall()
    finally:
        connection.close()

    return [
        {
            "id": row[0],
            "user_id": row[1],
            "name": row[2],
            "level": row[3],
            "health": row[4],
            "max_health": row[17],
            # Appended to the SELECT rather than inserted, so none of
            # the indices above move.
            "residence_key": row[-1],
            "money": row[5],
            "strength": row[6],
            "defence": row[7],
            "speed": row[8],
            "dexterity": row[9],
            "beginner_protection_seconds": _beginner_seconds(
                row[15], now
            ),
            "rating": row[16],
            "restricted": (
                _timestamp_active(row[10])
                or _timestamp_active(row[11])
                or (
                    row[12] is not None
                    and _timestamp_active(row[13])
                )
                or _timestamp_active(row[14])
            ),
        }
        for row in rows
    ]


def get_target_user_id(player_id):
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT user_id FROM players WHERE id = ?",
            (player_id,),
        ).fetchone()
    finally:
        connection.close()
    return None if row is None else row[0]


def get_attack_limits(attacker_id, defender_id, now=None):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        last_against_target = connection.execute(
            """
            SELECT created_at
            FROM player_pvp_attacks
            WHERE attacker_id = ? AND defender_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (attacker_id, defender_id),
        ).fetchone()
        last_received = connection.execute(
            """
            SELECT created_at
            FROM player_pvp_attacks
            WHERE defender_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (defender_id,),
        ).fetchone()
        day_start = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        rewarded_today = connection.execute(
            """
            SELECT COUNT(*)
            FROM player_pvp_attacks
            WHERE attacker_id = ? AND defender_id = ?
              AND created_at >= ? AND reward_multiplier > 0
            """,
            (attacker_id, defender_id, day_start.isoformat()),
        ).fetchone()[0]
    finally:
        connection.close()

    return AttackLimits(
        protected_seconds=_remaining(
            last_received, TARGET_PROTECTION_SECONDS, now
        ),
        repeat_seconds=_remaining(
            last_against_target, REPEAT_REWARD_SECONDS, now
        ),
        rewarded_attacks_today=rewarded_today,
    )


def record_pvp_attack(
    attacker_id,
    defender_id,
    approach,
    result,
    reward_multiplier,
    now=None,
):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        cursor = connection.execute(
            """
            INSERT INTO player_pvp_attacks (
                attacker_id, defender_id, approach, outcome,
                cash_stolen, xp_reward, reward_multiplier,
                rounds_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                attacker_id,
                defender_id,
                approach,
                "victory" if result.victory else "defeat",
                result.cash_stolen,
                result.xp_reward,
                reward_multiplier,
                json.dumps([
                    {
                        "round": event.round_number,
                        "actor": event.actor,
                        "event": event.event,
                        "damage": event.damage,
                    }
                    for event in result.rounds
                ]),
                now.isoformat(),
            ),
        )
        attack_id = cursor.lastrowid
        attacker_rating = _rating_row(connection, attacker_id)
        defender_rating = _rating_row(connection, defender_id)
        rated = reward_multiplier >= 1
        attacker_after = attacker_rating[0]
        defender_after = defender_rating[0]
        if rated:
            if result.victory:
                change = calculate_rating_change(
                    attacker_rating[0], defender_rating[0]
                )
                attacker_after = change.winner_after
                defender_after = change.loser_after
                _write_rating(
                    connection, attacker_id, attacker_after,
                    win=True, previous=attacker_rating,
                    now=now,
                )
                _write_rating(
                    connection, defender_id, defender_after,
                    win=False, previous=defender_rating,
                    now=now,
                )
            else:
                change = calculate_rating_change(
                    defender_rating[0], attacker_rating[0]
                )
                defender_after = change.winner_after
                attacker_after = change.loser_after
                _write_rating(
                    connection, defender_id, defender_after,
                    win=True, previous=defender_rating,
                    now=now,
                )
                _write_rating(
                    connection, attacker_id, attacker_after,
                    win=False, previous=attacker_rating,
                    now=now,
                )

        connection.execute(
            """
            DELETE FROM pvp_attack_reservations
            WHERE defender_id = ? AND attacker_id = ?
            """,
            (defender_id, attacker_id),
        )
        connection.execute(
            """
            INSERT INTO pvp_notifications (
                player_id, attack_id, message, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                defender_id,
                attack_id,
                "Another player attacked you.",
                now.isoformat(),
            ),
        )
        connection.commit()
        return RecordedAttack(
            attack_id=attack_id,
            attacker_before=attacker_rating[0],
            attacker_after=attacker_after,
            defender_before=defender_rating[0],
            defender_after=defender_after,
            rated=rated,
        )
    finally:
        connection.close()


def get_recent_pvp_attacks(player_id, limit=12):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT
                combat.id, combat.outcome, combat.cash_stolen,
                combat.xp_reward, combat.created_at,
                attacker.name, defender.name,
                combat.attacker_id = ?,
                combat.attacker_id, combat.defender_id
            FROM player_pvp_attacks AS combat
            JOIN players AS attacker ON attacker.id = combat.attacker_id
            JOIN players AS defender ON defender.id = combat.defender_id
            WHERE combat.attacker_id = ? OR combat.defender_id = ?
            ORDER BY combat.id DESC LIMIT ?
            """,
            (player_id, player_id, player_id, limit),
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "id": row[0],
            "outcome": row[1],
            "cash_stolen": row[2],
            "xp_reward": row[3],
            "created_at": row[4],
            "attacker_name": row[5],
            "defender_name": row[6],
            "was_attacker": bool(row[7]),
            "attacker_id": row[8],
            "defender_id": row[9],
        }
        for row in rows
    ]


def _timestamp_active(value):
    if value is None:
        return False
    return parse_timestamp(value) > datetime.now(timezone.utc)


def _remaining(row, seconds, now):
    if row is None:
        return 0
    expiry = parse_timestamp(row[0]) + timedelta(seconds=seconds)
    return max(0, int((expiry - now).total_seconds()))


def _normalise_now(now):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


class AttackReservationError(Exception):
    """Raised when an atomic PvP attack reservation fails."""


def reserve_pvp_attack(attacker_id, defender_id, now=None):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        refuse_if_sealed(
            connection, "attack", attacker_id, defender_id
        )
        stale_before = now - timedelta(minutes=2)
        connection.execute(
            """
            DELETE FROM pvp_attack_reservations
            WHERE reserved_at < ?
            """,
            (stale_before.isoformat(),),
        )

        beginner_row = connection.execute(
            """
            SELECT users.created_at
            FROM players
            JOIN users ON users.id = players.user_id
            WHERE players.id = ?
            """,
            (defender_id,),
        ).fetchone()
        if beginner_row is None:
            raise AttackReservationError(
                "That player does not exist."
            )
        beginner_seconds = _beginner_seconds(
            beginner_row[0], now
        )
        if beginner_seconds > 0:
            raise AttackReservationError(
                "That player has beginner protection for "
                f"{beginner_seconds} seconds."
            )

        protected_row = connection.execute(
            """
            SELECT created_at
            FROM player_pvp_attacks
            WHERE defender_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (defender_id,),
        ).fetchone()
        protected_seconds = _remaining(
            protected_row, TARGET_PROTECTION_SECONDS, now
        )
        if protected_seconds > 0:
            raise AttackReservationError(
                "That player is under attack protection for "
                f"{protected_seconds} seconds."
            )

        try:
            connection.execute(
                """
                INSERT INTO pvp_attack_reservations (
                    defender_id, attacker_id, reserved_at
                )
                VALUES (?, ?, ?)
                """,
                (defender_id, attacker_id, now.isoformat()),
            )
        except Exception as error:
            raise AttackReservationError(
                "Another fight against that player is already starting."
            ) from error
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
    return get_attack_limits(attacker_id, defender_id, now=now)


def release_pvp_attack(attacker_id, defender_id):
    connection = get_connection()
    try:
        connection.execute(
            """
            DELETE FROM pvp_attack_reservations
            WHERE defender_id = ? AND attacker_id = ?
            """,
            (defender_id, attacker_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_pvp_report(attack_id, viewer_id):
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT
                combat.id, combat.outcome, combat.approach,
                combat.cash_stolen, combat.xp_reward,
                combat.rounds_json, combat.created_at,
                attacker.name, defender.name,
                combat.attacker_id, combat.defender_id
            FROM player_pvp_attacks AS combat
            JOIN players AS attacker ON attacker.id = combat.attacker_id
            JOIN players AS defender ON defender.id = combat.defender_id
            WHERE combat.id = ?
              AND (combat.attacker_id = ? OR combat.defender_id = ?)
            """,
            (attack_id, viewer_id, viewer_id),
        ).fetchone()
    finally:
        connection.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "outcome": row[1],
        "approach": row[2],
        "cash_stolen": row[3],
        "xp_reward": row[4],
        "rounds": json.loads(row[5]),
        "created_at": row[6],
        "attacker_name": row[7],
        "defender_name": row[8],
        "attacker_id": row[9],
        "defender_id": row[10],
        "viewer_was_attacker": row[9] == viewer_id,
    }


def get_unread_pvp_notifications(player_id):
    connection = get_connection()
    try:
        rows = connection.execute(
            """
            SELECT id, attack_id, message, created_at
            FROM pvp_notifications
            WHERE player_id = ? AND read_at IS NULL
            ORDER BY id DESC LIMIT 10
            """,
            (player_id,),
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "id": row[0],
            "attack_id": row[1],
            "message": row[2],
            "created_at": row[3],
        }
        for row in rows
    ]


def mark_pvp_notifications_read(player_id, now=None):
    now = _normalise_now(now)
    connection = get_connection()
    try:
        connection.execute(
            """
            UPDATE pvp_notifications
            SET read_at = ?
            WHERE player_id = ? AND read_at IS NULL
            """,
            (now.isoformat(), player_id),
        )
        connection.commit()
    finally:
        connection.close()


def _beginner_seconds(created_at, now):
    if created_at is None:
        return 0
    expiry = parse_timestamp(created_at) + timedelta(hours=72)
    return max(0, int((expiry - now).total_seconds()))


def get_pvp_profile(player_id):
    connection = get_connection()
    try:
        rating = _rating_row(connection, player_id)
    finally:
        connection.close()
    return {
        "rating": rating[0],
        "wins": rating[1],
        "losses": rating[2],
        "streak": rating[3],
        "best_rating": rating[4],
    }


def get_pvp_leaderboard(district=None, limit=50):
    connection = get_connection()
    try:
        parameters = []
        where = ""
        if district is not None:
            where = "WHERE players.current_district = ?"
            parameters.append(district)
        parameters.append(limit)
        rows = connection.execute(
            f"""
            SELECT
                players.id, players.name, players.level,
                players.current_district,
                COALESCE(rating.rating, {DEFAULT_PVP_RATING}),
                COALESCE(rating.wins, 0),
                COALESCE(rating.losses, 0),
                COALESCE(rating.streak, 0)
            FROM players
            LEFT JOIN player_pvp_ratings AS rating
                ON rating.player_id = players.id
            {where}
            ORDER BY
                COALESCE(rating.rating, {DEFAULT_PVP_RATING}) DESC,
                COALESCE(rating.wins, 0) DESC,
                players.name COLLATE NOCASE ASC
            LIMIT ?
            """,
            parameters,
        ).fetchall()
    finally:
        connection.close()
    return [
        {
            "rank": index,
            "id": row[0],
            "name": row[1],
            "level": row[2],
            "district": row[3],
            "rating": row[4],
            "wins": row[5],
            "losses": row[6],
            "streak": row[7],
        }
        for index, row in enumerate(rows, start=1)
    ]


def _rating_row(connection, player_id):
    row = connection.execute(
        """
        SELECT rating, wins, losses, streak, best_rating
        FROM player_pvp_ratings WHERE player_id = ?
        """,
        (player_id,),
    ).fetchone()
    if row is not None:
        return row
    connection.execute(
        """
        INSERT OR IGNORE INTO player_pvp_ratings (
            player_id, rating, best_rating
        )
        VALUES (?, ?, ?)
        """,
        (player_id, DEFAULT_PVP_RATING, DEFAULT_PVP_RATING),
    )
    return (DEFAULT_PVP_RATING, 0, 0, 0, DEFAULT_PVP_RATING)


def _write_rating(connection, player_id, rating, win, previous, now):
    wins = previous[1] + (1 if win else 0)
    losses = previous[2] + (0 if win else 1)
    streak = previous[3] + 1 if win else 0
    best = max(previous[4], rating)
    connection.execute(
        """
        INSERT INTO player_pvp_ratings (
            player_id, rating, wins, losses,
            streak, best_rating, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(player_id) DO UPDATE SET
            rating = excluded.rating,
            wins = excluded.wins,
            losses = excluded.losses,
            streak = excluded.streak,
            best_rating = excluded.best_rating,
            updated_at = excluded.updated_at
        """,
        (
            player_id, rating, wins, losses,
            streak, best, now.isoformat(),
        ),
    )


# ------------------------------------------------- what happens after
#
# A won fight leaves `aftermath` NULL: the winner has not yet said what
# they are doing with the person on the floor. Everything below settles
# that, and it is the only place the choice is applied, so a fight
# cannot be cashed twice.


@dataclass(frozen=True)
class PendingAftermath:
    attack_id: int
    defender_id: int
    defender_name: str
    defender_money: int
    reward_multiplier: float
    seconds_left: int
    # What hospitalising them is worth. Shown on the choice, because a
    # decision between their pockets and their price is only a decision
    # if you can see both.
    bounty: int = 0


def get_pending_aftermath(attacker_id, now=None):
    """The winner's most recent fight still awaiting a decision.

    None once it is settled or the window has closed, which is what
    stops a player banking a win and mugging days later when their
    victim has money worth taking.
    """
    now = _normalise_now(now)
    connection = get_connection()
    try:
        row = connection.execute(
            """
            SELECT a.id, a.defender_id, p.name, p.money,
                   a.reward_multiplier, a.created_at
            FROM player_pvp_attacks AS a
            JOIN players AS p ON p.id = a.defender_id
            WHERE a.attacker_id = ?
              AND a.outcome = 'victory'
              AND a.aftermath IS NULL
            ORDER BY a.id DESC
            LIMIT 1
            """,
            (attacker_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        return None

    left = _seconds_left(row[5], now)
    if left <= 0:
        return None

    return PendingAftermath(
        attack_id=row[0],
        defender_id=row[1],
        defender_name=row[2],
        defender_money=row[3],
        reward_multiplier=row[4],
        seconds_left=left,
        bounty=bounty_on(row[1], now=now),
    )


def _seconds_left(created_at, now):
    started = parse_timestamp(created_at)
    if started is None:
        return 0
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)

    elapsed = (now - started).total_seconds()

    return max(0, int(AFTERMATH_WINDOW_SECONDS - elapsed))


def settle_aftermath(attack_id, attacker_id, choice, rng=None, now=None):
    """Apply the winner's choice, once.

    The whole thing runs inside one immediate transaction: the row is
    re-read and re-checked under the write lock, so two requests racing
    each other cannot both mug the same beaten player.
    """
    if choice not in AFTERMATH_CHOICES:
        raise PvpError("That is not something you can do.")

    rng = rng or random.SystemRandom()
    now = _normalise_now(now)
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """
            SELECT defender_id, reward_multiplier, created_at
            FROM player_pvp_attacks
            WHERE id = ? AND attacker_id = ?
              AND outcome = 'victory' AND aftermath IS NULL
            """,
            (attack_id, attacker_id),
        ).fetchone()

        if row is None:
            raise PvpError("That fight has already been settled.")

        defender_id, reward_multiplier, created_at = row

        if _seconds_left(created_at, now) <= 0:
            # Too late to take anything, but the fight still has to
            # stop being pending or it hangs around for ever.
            connection.execute(
                "UPDATE player_pvp_attacks SET aftermath = ? WHERE id = ?",
                (AFTERMATH_LEAVE, attack_id),
            )
            connection.commit()
            raise PvpError("They got away before you decided.")

        taken = 0
        claim = BountyClaim(collected=0, bounties=0, skipped=0)

        if choice == AFTERMATH_MUG:
            money = connection.execute(
                "SELECT money FROM players WHERE id = ?",
                (defender_id,),
            ).fetchone()[0]
            taken = mug_takings(
                money,
                rng.randint(MUG_MINIMUM_PERCENT, MUG_MAXIMUM_PERCENT),
                reward_multiplier,
            )
            if taken:
                moved = connection.execute(
                    """
                    UPDATE players SET money = money - ?
                    WHERE id = ? AND money >= ?
                    """,
                    (taken, defender_id, taken),
                ).rowcount
                if moved != 1:
                    # They spent it between the read and the write.
                    taken = 0
                else:
                    connection.execute(
                        "UPDATE players SET money = money + ? WHERE id = ?",
                        (taken, attacker_id),
                    )

        elif choice == AFTERMATH_HOSPITALISE:
            until = now + timedelta(seconds=PVP_HOSPITAL_SECONDS)
            connection.execute(
                """
                UPDATE players
                SET hospital_until = ?, health = 0
                WHERE id = ?
                """,
                (format_timestamp(until), defender_id),
            )
            # A hospital bed is what a bounty pays for. Collected on
            # this same connection so the payout and the bed commit
            # together -- there is no state where somebody is in
            # hospital and the money that put them there is still on
            # the board.
            claim = claim_on(
                connection, defender_id, attacker_id, attack_id, now
            )

        connection.execute(
            """
            UPDATE player_pvp_attacks
            SET aftermath = ?, cash_stolen = ?
            WHERE id = ? AND aftermath IS NULL
            """,
            (choice, taken, attack_id),
        )
        connection.commit()

        return Aftermath(
            choice=choice,
            cash_stolen=taken,
            bounty_collected=claim.collected,
            bounty_count=claim.bounties,
        )
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
