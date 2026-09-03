"""The rules.

Written as offences and consequences rather than prose, because the only
thing anyone reads a rules page for is "what happens if". Each rule
carries the penalty in its own heading so it cannot be missed.
"""

from dataclasses import dataclass

from game.handbook.blocks import Bullets, Heading, Note, Text


BAN = "Ban"
PERMANENT = "Permanent ban"
WARNING = "Warning, then ban"


@dataclass(frozen=True)
class Rule:
    key: str
    title: str
    penalty: str
    blocks: tuple


INTRO = (
    Text(
        "The Smoke is a competitive game. Everything below exists so that "
        "the person above you on the leaderboard got there the same way "
        "you would have to."
    ),
    Text(
        "Report anything you think breaks these rules through "
        "[feedback](/feedback). Reports are read; guessing publicly in "
        "chat is not a report."
    ),
)

RULES = (
    Rule(
        key="multiple-accounts",
        title="Multiple accounts",
        penalty=PERMANENT,
        blocks=(
            Text(
                "**One person, one account.** Running a second account to "
                "feed your main — cash, items, easy fights, market trades "
                "at rigged prices, bounties posted to be collected by a "
                "friend — is the most damaging thing you can do to a game "
                "this size, because every number on it is comparative."
            ),
            Bullets((
                "Both accounts are banned, not just the second one.",
                "Everything transferred is removed from the receiving "
                "account.",
                "Sharing a household or a network is fine. Say so before "
                "it looks like something else, not after.",
            )),
        ),
    ),
    Rule(
        key="real-money-trading",
        title="Selling anything for real money",
        penalty=PERMANENT,
        blocks=(
            Text(
                "Trading in-game money, items or accounts for real-world "
                "money or for assets in another game is prohibited, on "
                "this site or anywhere else."
            ),
            Bullets((
                "Sellers are banned permanently.",
                "Buyers lose what they bought and are banned.",
                "Offering to do it counts, whether or not it happens.",
            )),
            Text(
                "This is not about protecting revenue. A market where "
                "progress can be bought makes every hour anyone else spent "
                "worth less."
            ),
        ),
    ),
    Rule(
        key="account-sharing",
        title="Sharing or trading accounts",
        penalty=PERMANENT,
        blocks=(
            Text(
                "The account belongs to whoever registered it. Do not give "
                "anyone your password, do not play someone else's account, "
                "and do not sell, gift or inherit one."
            ),
            Text(
                "If you want someone to look after your account while you "
                "are away: no. There is no version of this that is allowed."
            ),
        ),
    ),
    Rule(
        key="automation",
        title="Scripts, bots and automation",
        penalty=BAN,
        blocks=(
            Text(
                "Play with your own hands. Anything that acts for you — a "
                "bot, an auto-clicker, a script that fires crimes or "
                "trains for you, a macro that plays the casino — is "
                "prohibited."
            ),
            Bullets((
                "Tools that only **display** information are fine.",
                "Tools that **take actions** are not, however thin the "
                "wrapper.",
                "Being asleep while your account plays is the test.",
            )),
            Heading("Except for declared agents"),
            Text(
                "There is one sanctioned way to be a machine here. An "
                "**agent account** is issued a key by the owner, plays "
                "through the [API](/api/v1), and is sealed off from "
                "every other player in both directions."
            ),
            Bullets((
                "An agent **cannot** attack, mug, burgle, bail, "
                "bounty or trade with anybody.",
                "**Nor can anybody do those things to an agent.** A "
                "machine that could be robbed would be a cash machine "
                "with a heartbeat.",
                "Agents are kept out of the human standings and have "
                "[a leaderboard of their own](/api/v1/leaderboard).",
                "This is enforced in the database, not in the API, so "
                "there is no way round it from either side.",
            )),
            Note(
                "Running a bot **without** a key is still a ban, and "
                "asking for a key is free. If you want to point "
                "something at this game, say so and it becomes "
                "allowed.",
                tone="warning",
            ),
        ),
    ),
    Rule(
        key="exploits",
        title="Bugs and exploits",
        penalty=BAN,
        blocks=(
            Text(
                "If you find a way to get money, items or stats the game "
                "did not intend to give you, **report it** through "
                "[feedback](/feedback) and stop using it."
            ),
            Bullets((
                "Report it and you keep your account. We would rather know.",
                "Use it quietly and you lose the gains and the account.",
                "Telling other people how to use it is treated as using it.",
            )),
            Note(
                "This game is built and changed quickly. Bugs are expected. "
                "What happens next is the part that matters.",
                tone="info",
            ),
        ),
    ),
    Rule(
        key="conduct",
        title="How you talk to people",
        penalty=WARNING,
        blocks=(
            Text(
                "The setting is criminal. The behaviour is not. Harassment, "
                "threats, slurs, and abuse aimed at someone's race, sex, "
                "religion, sexuality or disability get you removed, and "
                "there is no in-character defence for any of it."
            ),
            Bullets((
                "Rivalry, trash talk and grudges are the game working.",
                "Following someone around to make them stop playing is not.",
                "Posting anyone's real-world details is an immediate "
                "permanent ban, first offence.",
            )),
        ),
    ),
    Rule(
        key="fair-play",
        title="Playing the game as it stands",
        penalty=WARNING,
        blocks=(
            Text(
                "Some things are not cheating but still spoil the game for "
                "everyone. They get a warning first, and a ban if they "
                "carry on."
            ),
            Bullets((
                "Deliberately losing fights to move someone's rating.",
                "Listing items at absurd prices to distort the market.",
                "Impersonating staff, or claiming a decision came from us.",
            )),
        ),
    ),
)

CLOSING = (
    Note(
        "These rules will change as the game does. Anything added here "
        "applies from the day it appears, not retroactively.",
        tone="info",
    ),
)

RULES_BY_KEY = {rule.key: rule for rule in RULES}


def validate_catalogue():
    keys = [rule.key for rule in RULES]
    if len(keys) != len(set(keys)):
        raise ValueError("two rules share a key")
    for rule in RULES:
        if not rule.blocks:
            raise ValueError(f"{rule.key} has no content")
        if not rule.penalty:
            raise ValueError(f"{rule.key} has no stated penalty")


validate_catalogue()
