"""Letting other machines play, without letting them eat the game.

The rules page bans automation, and it is right to: a bot that never
sleeps will out-earn every human on the server inside a week, and this
game has real players with real balances. So the ban stays for anything
unsanctioned. What this adds is a declared, walled-off class of player
that is allowed to be a machine.

The wall is the feature. An agent plays the whole single-player game --
crime, the gym, travel, jobs, street fights -- and cannot touch another
player or their money in either direction:

  an agent cannot attack, mug, burgle, bail, bounty or trade
  a human cannot attack, mug, burgle or bounty an agent

Both halves are needed. The first stops a machine farming people; the
second stops people farming a machine, which would be worse, because an
agent that logs in every ninety seconds is a renewable source of
rating, cash and bounty payouts.

What is left is a real game to play and a leaderboard of its own,
sitting alongside the human one rather than inside it.
"""

import secrets


class AgentError(Exception):
    """Raised when an agent may not do something."""


# Long enough that guessing is hopeless, prefixed so a key found in a
# log or a paste is obviously a credential and obviously ours.
KEY_PREFIX = "smoke_agent_"
KEY_BYTES = 32

# Per key. An agent playing properly needs a handful of calls a minute
# -- look, decide, act -- so this is generous for playing and useless
# for hammering. Nerve and energy are the real limiter anyway; this
# only stops a runaway loop taking the site down.
RATE_LIMIT_PER_MINUTE = 60

# Everything that moves value between two players. Named here rather
# than checked ad hoc at each call site, so adding a mechanic that
# takes from another player and forgetting the wall is a visible
# omission rather than an invisible one.
AGENT_SEALED_ACTIONS = (
    "attack",
    "mug",
    "burgle",
    "bail",
    "breakout",
    "bounty",
    "market",
)


def generate_key():
    """A fresh API key. Shown once, stored only as a hash."""
    return KEY_PREFIX + secrets.token_urlsafe(KEY_BYTES)


def looks_like_key(candidate):
    """Cheap shape check, so obvious rubbish never reaches the database.

    Not a validity check -- a well-formed key that nobody issued still
    fails on the hash. This only avoids a query per malformed header.
    """
    return (
        isinstance(candidate, str)
        and candidate.startswith(KEY_PREFIX)
        and len(candidate) > len(KEY_PREFIX) + 20
    )


def sealed_reason(action, actor_is_agent, target_is_agent):
    """Why this interaction is refused, or None if it is allowed.

    Deliberately symmetric. The temptation is to seal only the agent's
    side -- stop the machine robbing people -- but a machine that can
    be robbed is a cash machine with a heartbeat, and the humans would
    find it within a day.
    """
    if action not in AGENT_SEALED_ACTIONS:
        return None

    if actor_is_agent:
        return (
            "Agents play the city, not the people in it. "
            "That is not something an agent may do."
        )

    if target_is_agent:
        return (
            "That player is an agent. Agents cannot be attacked, "
            "robbed or traded with."
        )

    return None
