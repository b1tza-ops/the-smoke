"""The machine-readable city.

The rules page bans automation and goes on banning it. This is the one
sanctioned exception: an account that has declared itself a machine,
plays through this API with a key, and is sealed off from every other
player in both directions -- see `game/agents/service.py` for why both
directions matter.

Design notes, since the intended reader is a language model:

  Every response is JSON, including every error. An agent should never
  have to parse HTML or guess at a redirect.

  Every error carries a stable `error` code as well as a sentence. The
  sentence is for a human reading a log; the code is for branching.

  `GET /api/v1` describes the whole surface, and `GET /api/v1/actions`
  describes what this player can do *right now*, with costs and
  expected values. Between them an agent can work out how to play
  without anybody writing it a bespoke prompt.

The endpoints deliberately reuse the same functions the web pages call.
There is no second implementation of a crime or a training session, so
an agent and a person are playing exactly the same game.
"""

from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request

from database.repositories.agents import authenticate
from game.agents.service import RATE_LIMIT_PER_MINUTE


api = Blueprint("api", __name__, url_prefix="/api/v1")

VERSION = "1.0"


def fail(code, message, status=400, **extra):
    """Every refusal looks the same, whatever caused it."""
    body = {"ok": False, "error": code, "message": message}
    body.update(extra)

    return jsonify(body), status


def ok(**payload):
    return jsonify({"ok": True, **payload})


def _key_from_request():
    header = request.headers.get("Authorization", "")

    if header.startswith("Bearer "):
        return header[7:].strip()

    return request.headers.get("X-Agent-Key", "").strip()


def agent_only(view):
    """Authenticate the key, rate limit it, and hand over the player.

    The rate limit is per key rather than per address, because several
    agents may sit behind one host and one agent may move between
    hosts. It is generous enough that playing properly never touches
    it -- nerve and energy are the real limiter -- and only exists so
    a runaway loop cannot take the site down.
    """
    @wraps(view)
    def guarded(*args, **kwargs):
        raw = _key_from_request()

        if not raw:
            return fail(
                "no_key",
                "Send your key as 'Authorization: Bearer <key>'.",
                401,
            )

        account = authenticate(raw)

        if account is None:
            return fail("bad_key", "That key is not valid.", 401)

        limiter = current_app.config.get("AGENT_RATE_LIMITER")

        if limiter is not None and not limiter.allow(
            f"agent:{account.user_id}",
            RATE_LIMIT_PER_MINUTE,
            60,
        ):
            return fail(
                "rate_limited",
                f"{RATE_LIMIT_PER_MINUTE} calls a minute is the "
                "limit. Slow down; nothing here rewards haste.",
                429,
            )

        g.agent = account

        return view(*args, **kwargs)

    return guarded


# --------------------------------------------------------- discovery

@api.get("")
@api.get("/")
def index():
    """What this API is and everything it can do.

    Unauthenticated on purpose: an agent should be able to read the
    manual before it has a key, and a person should be able to see
    what a machine is allowed to do without asking.
    """
    return ok(
        version=VERSION,
        game="The Smoke",
        summary=(
            "A London crime game. You have energy, nerve and happiness "
            "that refill over time; you spend nerve on crimes, energy "
            "on fighting and training, and happiness makes training "
            "worth more. Everything else follows from that."
        ),
        authentication={
            "header": "Authorization: Bearer <key>",
            "alternative": "X-Agent-Key: <key>",
            "how_to_get_one": (
                "A key is issued by the site owner with "
                "scripts/issue_agent_key.py. Agents are a declared "
                "class of account, not a thing you can grant yourself."
            ),
            "rate_limit": f"{RATE_LIMIT_PER_MINUTE} calls a minute",
        },
        rules_for_agents={
            "sealed": (
                "Agents cannot attack, mug, burgle, bail, bounty or "
                "trade with another player, and cannot be attacked, "
                "robbed or traded with in return. This is enforced in "
                "the database, not in this API, so there is no way "
                "around it and no point looking for one."
            ),
            "everything_else": (
                "Crime, the gym, travel, jobs and street fights are "
                "the whole game as a human plays it, and are open."
            ),
            "unsanctioned_automation": (
                "Still a ban, for accounts without a key. This is the "
                "sanctioned way to be a machine here."
            ),
        },
        endpoints=[
            {
                "method": "GET", "path": "/api/v1",
                "auth": False,
                "does": "This document.",
            },
            {
                "method": "GET", "path": "/api/v1/me",
                "auth": True,
                "does": "Everything about your player right now.",
            },
            {
                "method": "GET", "path": "/api/v1/actions",
                "auth": True,
                "does": (
                    "What you can do this second, with what each "
                    "costs and what it is worth. Start here."
                ),
            },
            {
                "method": "POST", "path": "/api/v1/crime",
                "auth": True,
                "body": {"crime": "crime key from /actions"},
                "does": "Commit a crime. Spends nerve.",
            },
            {
                "method": "POST", "path": "/api/v1/train",
                "auth": True,
                "body": {
                    "stat": "strength | defence | speed | dexterity",
                    "gym": "gym key (optional, defaults to your gym)",
                    "trains": "how many (optional, default 1)",
                },
                "does": "Train at a gym. Spends energy and happiness.",
            },
            {
                "method": "POST", "path": "/api/v1/travel",
                "auth": True,
                "body": {
                    "district": "district key",
                    "mode": "walk | bus | underground | drive",
                },
                "does": "Start a journey. Blocks everything until it lands.",
            },
            {
                "method": "POST", "path": "/api/v1/fight",
                "auth": True,
                "body": {"opponent": "opponent key from /actions"},
                "does": "Fight a street opponent. Spends energy.",
            },
            {
                "method": "GET", "path": "/api/v1/leaderboard",
                "auth": False,
                "does": "The agent standings. Machines only.",
            },
        ],
        advice=(
            "Poll /actions, pick the affordable line with the best "
            "return, act, repeat. Nerve refills slower than energy, so "
            "crime is usually the binding constraint. Jail and hospital "
            "block everything -- check `blocked` before planning."
        ),
    )


# ------------------------------------------------------------- state

def _load(user_id):
    from database.repositories.players import get_player_by_user_id
    from game.player.model import Player
    from game.player.status import update_player_status
    from game.world.travel import update_travel

    row = get_player_by_user_id(user_id)

    if row is None:
        return None

    player = Player(*row)
    update_travel(player)
    update_player_status(player)

    return player


def _blocked(player):
    """Why this player cannot act, or None.

    One place, so `/me`, `/actions` and every POST agree about it --
    an agent that is told it can act and is then refused has no way to
    tell a rule from a bug.
    """
    if player.jail_until is not None:
        return "in_jail"
    if player.hospital_until is not None:
        return "in_hospital"
    if player.travel_destination is not None:
        return "travelling"
    if getattr(player, "shift_until", None) is not None:
        return "working_a_shift"

    return None


def _meters(player):
    return {
        "health": {"now": player.health, "max": player.max_health},
        "energy": {"now": player.energy, "max": player.max_energy},
        "nerve": {"now": player.nerve, "max": player.max_nerve},
        "happiness": {
            "now": player.happiness, "max": player.max_happiness
        },
    }


@api.get("/me")
@agent_only
def me():
    player = _load(g.agent.user_id)

    if player is None:
        return fail("no_character", "That account has no character.", 404)

    from database.repositories.agents import is_agent

    return ok(
        agent={"label": g.agent.label, "calls": g.agent.calls},
        player={
            "id": player.id,
            "name": player.name,
            "level": player.level,
            "xp": player.xp,
            "money": player.money,
            "bank": player.bank_balance,
            "district": player.current_district,
            "wanted_level": player.wanted_level,
            "is_agent": is_agent(player.id),
        },
        stats={
            "strength": player.strength,
            "defence": player.defence,
            "speed": player.speed,
            "dexterity": player.dexterity,
        },
        meters=_meters(player),
        blocked=_blocked(player),
        until={
            "jail": player.jail_until,
            "hospital": player.hospital_until,
            "travel": player.travel_until,
        },
    )


# Nerve refills at twelve an hour, which is the rate every income
# figure in this game is measured against. Kept here beside the only
# thing that uses it rather than imported from a test.
NERVE_PER_HOUR = 12
SECONDS_PER_NERVE = 3600 / NERVE_PER_HOUR


def _crime_view(crime, player):
    """One crime, with the arithmetic an agent actually needs.

    `expected_per_nerve` is the obvious figure and the wrong one to
    optimise: it ignores jail, and jail is time during which no nerve
    can be spent at all. `expected_per_hour` is the number that
    decides -- nerve regeneration plus the sentence you can expect to
    serve for attempting this.

    On today's ladder the two agree in every district, because the
    crime rewards were set from a curve. They are not guaranteed to,
    and an agent optimising the wrong one would quietly earn less
    while looking like it was winning, so both are published and the
    right one is named.
    """
    expected = (
        (crime.min_reward + crime.max_reward) / 2
        * crime.success_chance / 100
    )
    per_nerve = expected / crime.nerve_cost
    jail_per_nerve = (
        crime.jail_chance / 100 * crime.jail_seconds / crime.nerve_cost
    )

    return {
        "key": crime.key,
        "name": crime.name,
        "nerve": crime.nerve_cost,
        "success_percent": crime.success_chance,
        "pays": [crime.min_reward, crime.max_reward],
        "expected": round(expected),
        "expected_per_nerve": round(per_nerve, 1),
        "expected_per_hour": round(
            per_nerve * 3600 / (SECONDS_PER_NERVE + jail_per_nerve)
        ),
        "jail_percent": crime.jail_chance,
        "jail_seconds": crime.jail_seconds,
        "expected_jail_seconds": round(
            crime.jail_chance / 100 * crime.jail_seconds
        ),
        "affordable": player.nerve >= crime.nerve_cost,
    }


def _opponent_view(opponent, player):
    """One street opponent, and how badly it might go.

    `affordable` used to mean "you have the energy", which is true and
    not the question. Losing costs a hospital stay, and an agent at
    half health has no way to know that from an energy figure -- so the
    health it is walking in with, and how it compares, are here too.
    """
    from game.combat.npc import combat_power, payout_share

    theirs = combat_power(
        opponent.strength, opponent.defence,
        opponent.speed, opponent.dexterity,
    )
    mine = combat_power(
        player.strength, player.defence,
        player.speed, player.dexterity,
    )

    return {
        "key": opponent.key,
        "name": opponent.name,
        "energy": opponent.energy_cost,
        "pays": [opponent.cash_min, opponent.cash_max],
        "xp": opponent.xp_reward,
        "their_power": round(theirs),
        "your_power": round(mine),
        # Below 1.0 you are the stronger. Above it, you are not.
        "power_ratio": round(theirs / max(1, mine), 2),
        # What is left of their purse once you have outgrown them.
        "payout_share": round(payout_share(player, opponent), 2),
        "your_health": [player.health, player.max_health],
        "affordable": player.energy >= opponent.energy_cost,
    }


@api.get("/actions")
@agent_only
def actions():
    """What is worth doing right now, with the arithmetic done.

    An agent should not have to reverse-engineer the economy from a
    catalogue. Expected values are the same ones the guides quote, so
    a machine and a person reading the handbook see the same game.
    """
    from game.crime import CRIMES
    from game.combat.npc import get_district_opponents
    from game.gym.formula import happiness_cost
    from game.gym.service import get_district_gyms
    from game.world.districts import DISTRICTS, get_travel_route
    from game.world.transport import available_modes

    player = _load(g.agent.user_id)

    if player is None:
        return fail("no_character", "That account has no character.", 404)

    blocked = _blocked(player)
    here = player.current_district

    crimes = [
        _crime_view(crime, player)
        for crime in CRIMES
        if crime.district.casefold() == here.casefold()
    ]

    gyms = [
        {
            "key": gym.key,
            "name": gym.name,
            "energy_per_train": gym.energy_per_train,
            "happiness_per_train": happiness_cost(gym.energy_per_train),
            "trains": [
                stat for stat in
                ("strength", "defence", "speed", "dexterity")
                if gym.multiplier_for(stat) > 0
            ],
            "joined": gym.key in (player.unlocked_gyms or ()),
            "membership": gym.membership_cost,
            "affordable": player.energy >= gym.energy_per_train,
        }
        for gym in get_district_gyms(here)
    ]

    opponents = [
        _opponent_view(opponent, player)
        for opponent in get_district_opponents(here)
    ]

    journeys = []
    for district in DISTRICTS:
        if district.key == here:
            continue
        try:
            route = get_travel_route(here, district.key)
        except KeyError:
            continue
        journeys.append({
            "district": district.key,
            "name": district.name,
            "needs_level": district.minimum_level,
            "reachable": player.level >= district.minimum_level,
            "modes": [
                {
                    "mode": mode.key,
                    "fare": mode.fare(route),
                    "seconds": mode.duration_seconds(route),
                }
                for mode in available_modes(here, district.key)
            ],
        })

    return ok(
        district=here,
        blocked=blocked,
        meters=_meters(player),
        crimes=crimes,
        gyms=gyms,
        opponents=opponents,
        travel=journeys,
        note=(
            "`blocked` being set means every action below will be "
            "refused until it clears."
            if blocked else
            "Nothing is stopping you acting."
        ),
        how_to_choose={
            "crimes": (
                "Optimise `expected_per_hour`, not "
                "`expected_per_nerve`. The per-nerve figure ignores "
                "jail, and jail is time you cannot spend nerve in."
            ),
            "fights": (
                "`power_ratio` above 1.0 means the opponent is "
                "stronger than you. Losing costs a hospital stay, so "
                "check `your_health` before a close one."
            ),
        },
    )


# ------------------------------------------------------------ acting

def _acting_player():
    """The player, or a refusal. Used by every POST below."""
    player = _load(g.agent.user_id)

    if player is None:
        return None, fail(
            "no_character", "That account has no character.", 404
        )

    blocked = _blocked(player)

    if blocked:
        return None, fail(
            blocked,
            f"You cannot act: {blocked.replace('_', ' ')}.",
            409,
        )

    return player, None


def _body():
    return request.get_json(silent=True) or request.form or {}


@api.post("/crime")
@agent_only
def crime():
    from database.repositories.players import save_player
    from game.crime import CRIMES_BY_KEY
    from game.crime.service import commit_crime

    player, refusal = _acting_player()
    if refusal:
        return refusal

    chosen = CRIMES_BY_KEY.get(str(_body().get("crime", "")))

    if chosen is None:
        return fail(
            "unknown_crime",
            "No such crime. GET /api/v1/actions for the list.",
            404,
        )

    if chosen.district.casefold() != player.current_district.casefold():
        return fail(
            "wrong_district",
            f"{chosen.name} is in {chosen.district}. "
            f"You are in {player.current_district.title()}.",
            409,
        )

    if player.nerve < chosen.nerve_cost:
        return fail(
            "not_enough_nerve",
            f"{chosen.name} costs {chosen.nerve_cost} nerve and you "
            f"have {player.nerve}.",
            409,
        )

    result = commit_crime(player, chosen)
    save_player(player)

    # Real attribute names, not `getattr(..., 0)`. A default hides a
    # renamed field behind a plausible zero: the first run of this
    # endpoint reported £0 across five successful robberies and looked
    # entirely healthy doing it.
    return ok(
        crime=chosen.key,
        success=bool(result.success),
        payout=result.cash_reward,
        xp=result.xp_reward,
        loot=result.loot_item_name,
        reason=result.reason,
        jailed=player.jail_until is not None,
        hospitalised=player.hospital_until is not None,
        meters=_meters(player),
    )


@api.post("/train")
@agent_only
def train_stat():
    from database.repositories.housing import facilities_for
    from database.repositories.players import save_player
    from game.gym.service import GymError, select_gym, train
    from game.housing.service import gym_gain_bonus

    player, refusal = _acting_player()
    if refusal:
        return refusal

    body = _body()
    stat = str(body.get("stat", "")).lower()

    if stat not in ("strength", "defence", "speed", "dexterity"):
        return fail(
            "unknown_stat",
            "Train strength, defence, speed or dexterity.",
            400,
        )

    gym_key = str(body.get("gym") or player.current_gym_key or "")

    try:
        trains = max(1, int(body.get("trains", 1)))
    except (TypeError, ValueError):
        return fail("bad_trains", "`trains` must be a whole number.", 400)

    from game.gym.definitions import get_gym

    gym = get_gym(gym_key)

    if gym is None:
        return fail("unknown_gym", "No such gym.", 404)

    try:
        select_gym(player, gym_key)
        outcome = train(
            player,
            stat,
            energy=trains * gym.energy_per_train,
            gym_key=gym_key,
            home_bonus_percent=gym_gain_bonus(
                facilities_for(g.agent.user_id)
            ),
        )
    except (GymError, ValueError) as gym_error:
        return fail("refused", str(gym_error), 409)

    if not outcome:
        return fail(
            "not_enough_energy",
            f"{trains} train(s) needs "
            f"{trains * gym.energy_per_train} energy and you have "
            f"{player.energy}.",
            409,
        )

    save_player(player)

    return ok(
        gym=gym_key,
        stat=stat,
        trains=outcome.trains,
        gained=outcome.stat_gain,
        energy_spent=outcome.energy_spent,
        happiness_spent=outcome.happiness_spent,
        meters=_meters(player),
    )


@api.post("/travel")
@agent_only
def travel_to():
    from database.repositories.players import save_player
    from database.repositories.vehicles import active_vehicle
    from game.world.travel import TravelError, start_travel

    player, refusal = _acting_player()
    if refusal:
        return refusal

    body = _body()

    try:
        journey = start_travel(
            player,
            str(body.get("district", "")),
            str(body.get("mode", "bus")),
            vehicle=active_vehicle(player.id),
        )
    except TravelError as travel_error:
        return fail("refused", str(travel_error), 409)

    save_player(player)

    return ok(
        destination=journey.destination_key,
        mode=journey.mode_key,
        fare=journey.cost,
        arrives_at=journey.arrives_at,
        meters=_meters(player),
    )


@api.post("/fight")
@agent_only
def fight_npc():
    from database.repositories.players import save_player
    from game.combat.npc import (
        CombatError,
        fight_opponent,
        get_combat_block,
        get_district_opponents,
    )
    from game.inventory.equipment import get_equipment_summary

    player, refusal = _acting_player()
    if refusal:
        return refusal

    wanted = str(_body().get("opponent", ""))
    opponent = next(
        (
            candidate
            for candidate in get_district_opponents(
                player.current_district
            )
            if candidate.key == wanted
        ),
        None,
    )

    if opponent is None:
        return fail(
            "unknown_opponent",
            "No such opponent here. GET /api/v1/actions for the list.",
            404,
        )

    block = get_combat_block(player, opponent)

    if block:
        return fail("refused", block, 409)

    try:
        result = fight_opponent(
            player,
            get_equipment_summary(player.id),
            opponent,
        )
    except CombatError as combat_error:
        return fail("refused", str(combat_error), 409)

    save_player(player)

    return ok(
        opponent=opponent.key,
        won=bool(result.victory),
        payout=result.cash_reward,
        xp=result.xp_reward,
        hospitalised=player.hospital_until is not None,
        meters=_meters(player),
    )


@api.get("/leaderboard")
def leaderboard():
    """The machines, ranked among themselves.

    Open without a key: the point of a leaderboard is that people can
    see it. Agents are kept out of the human standings and given their
    own, so neither table is distorted by the other.
    """
    from database.repositories.agents import roster

    return ok(agents=roster())
