"""Roles, account states, and an audited moderation trail.

This is a backend foundation only -- it does not wire into the existing
`/admin` panel, which still uses its own single shared credential. A
future staff tool can call these functions once real per-account admin
sessions exist.

The acting account's role is always looked up fresh from the database
inside these functions; nothing here trusts a role passed in from a
caller, so a spoofed or stale client-side role can't grant access.

The audit trail (`moderation_actions`) is append-only by construction:
the repository layer only exposes inserts and reads for that table, so
there is no code path that can edit or delete a past entry.
"""

from datetime import timedelta

from database.repositories.moderation import (
    apply_account_state,
    count_active_admins,
    get_account_state,
    get_moderation_history,
    get_user_role,
    record_moderation_action,
    set_user_role as _persist_role,
)
from game.player.regeneration import format_timestamp, parse_timestamp
from game.player.status import normalise_now


ROLES = ("player", "moderator", "admin")
MODERATOR_ROLES = ("moderator", "admin")
ADMIN_ROLES = ("admin",)


class ModerationError(Exception):
    """Base exception for moderation actions."""


class InsufficientRoleError(ModerationError):
    """Raised when the acting account lacks the required role."""


class UnknownUserError(ModerationError):
    """Raised when the actor or target account does not exist."""


class InvalidRoleError(ModerationError):
    """Raised when an unrecognised role is requested."""


class SelfLockoutError(ModerationError):
    """Raised when an action would strip the last active admin of access."""


def is_account_blocked(user_id, now=None):
    """Return whether the account is currently blocked from logging in.

    A suspension with a past expiry is lifted here, deterministically,
    the same lazy-expiry pattern jail/hospital/wanted level already use.
    """
    state, suspended_until = get_account_state(user_id)

    if state is None:
        raise UnknownUserError("Account does not exist.")

    if state == "banned":
        return True

    if state == "suspended":
        if suspended_until is None:
            return True

        if parse_timestamp(suspended_until) > normalise_now(now):
            return True

        apply_account_state(user_id, "active", None)
        return False

    return False


def warn_user(actor_user_id, target_user_id, reason):
    _require_role(actor_user_id, MODERATOR_ROLES)
    state, _ = _require_target(target_user_id)
    reason = _require_reason(reason)

    record_moderation_action(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action_type="warn",
        reason=reason,
        previous_state=state,
        new_state=state,
    )


def suspend_user(
    actor_user_id,
    target_user_id,
    reason,
    duration_minutes=None,
    now=None,
):
    _require_role(actor_user_id, MODERATOR_ROLES)
    state, _ = _require_target(target_user_id)
    reason = _require_reason(reason)
    _guard_self_lockout(actor_user_id, target_user_id)

    if duration_minutes is not None:
        if (
            isinstance(duration_minutes, bool)
            or not isinstance(duration_minutes, int)
            or duration_minutes <= 0
        ):
            raise ValueError(
                "Duration must be a positive number of minutes."
            )

        suspended_until = format_timestamp(
            normalise_now(now)
            + timedelta(minutes=duration_minutes)
        )
    else:
        suspended_until = None

    apply_account_state(target_user_id, "suspended", suspended_until)
    record_moderation_action(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action_type="suspend",
        reason=reason,
        previous_state=state,
        new_state="suspended",
        expires_at=suspended_until,
    )

    return suspended_until


def ban_user(actor_user_id, target_user_id, reason):
    _require_role(actor_user_id, ADMIN_ROLES)
    state, _ = _require_target(target_user_id)
    reason = _require_reason(reason)
    _guard_self_lockout(actor_user_id, target_user_id)

    apply_account_state(target_user_id, "banned", None)
    record_moderation_action(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action_type="ban",
        reason=reason,
        previous_state=state,
        new_state="banned",
    )


def reverse_moderation(actor_user_id, target_user_id, reason):
    state, _ = _require_target(target_user_id)
    reason = _require_reason(reason)

    _require_role(
        actor_user_id,
        ADMIN_ROLES if state == "banned" else MODERATOR_ROLES,
    )

    apply_account_state(target_user_id, "active", None)
    record_moderation_action(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action_type="reverse",
        reason=reason,
        previous_state=state,
        new_state="active",
    )


def set_user_role(actor_user_id, target_user_id, new_role):
    _require_role(actor_user_id, ADMIN_ROLES)

    if new_role not in ROLES:
        raise InvalidRoleError(f"Unknown role: {new_role}")

    current_role = get_user_role(target_user_id)

    if current_role is None:
        raise UnknownUserError("Target account does not exist.")

    if current_role == new_role:
        return

    if current_role == "admin" and new_role != "admin":
        _guard_self_lockout(actor_user_id, target_user_id)

    _persist_role(target_user_id, new_role)
    record_moderation_action(
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        action_type="role_change",
        reason=f"Role changed from {current_role} to {new_role}.",
        previous_state=current_role,
        new_state=new_role,
    )


def get_history(target_user_id):
    return get_moderation_history(target_user_id)


def _require_role(actor_user_id, allowed_roles):
    role = get_user_role(actor_user_id)

    if role is None:
        raise UnknownUserError("Acting account does not exist.")

    if role not in allowed_roles:
        raise InsufficientRoleError(
            "This action requires a higher role."
        )

    return role


def _require_target(target_user_id):
    state, suspended_until = get_account_state(target_user_id)

    if state is None:
        raise UnknownUserError("Target account does not exist.")

    return state, suspended_until


def _require_reason(reason):
    if not reason or not reason.strip():
        raise ValueError("A reason is required.")

    return reason.strip()


def _guard_self_lockout(actor_user_id, target_user_id):
    if actor_user_id != target_user_id:
        return

    if get_user_role(target_user_id) != "admin":
        return

    if count_active_admins() <= 1:
        raise SelfLockoutError(
            "You are the last active administrator and cannot "
            "remove your own access."
        )
