"""Handing out money, and having a laugh at somebody's expense.

Two owner's tools that both reach into a live account, so both are
built the same way and around the same rule: **nothing happens to a
player silently.**

Every prank here writes the player a message. That is not politeness,
it is the difference between a joke and a bug. A player whose happiness
quietly halves does not think "the owner is winding me up", they think
the game is broken, and they are right to -- an unexplained change to
their character is indistinguishable from one. Told what happened, the
same player gets a story out of it. So the message is part of the
effect, not decoration on top of it, and there is no prank without one.

The second rule is that everything is bounded. A hand-typed figure with
a slipped zero is the likeliest way this panel ever does real damage, so
the money tool has a ceiling per action and the pranks carry fixed
amounts nobody types at all.

Pure rules: this decides what a prank *is*. Applying it -- clamping
against the player's own maximums, moving the money, writing the
message -- is `database.repositories.admin`, because all of that is
SQL and this file has none.
"""

from dataclasses import dataclass, field


# The most one action may move, in either direction. Deliberately not
# "whatever you type": this is the one screen in the game that can mint
# currency, and a slipped zero at 3am is a likelier failure than any
# amount of malice.
MAXIMUM_ADJUSTMENT = 10_000_000


@dataclass(frozen=True)
class Prank:
    """One thing the owner can do to somebody, and what they are told.

    `resources` are signed deltas against the player's live columns,
    clamped by the repository to that player's own maximums -- a prank
    can leave somebody miserable but never below zero, and can top
    somebody up but never above the cap their level allows.
    """

    key: str
    label: str
    blurb: str
    message: str
    money: tuple = (0, 0)
    # Used when a money effect moves nothing -- an empty pocket, or a
    # balance already at zero. Without it the player is told their
    # wallet is lighter when it is not, which is the one thing this
    # module is built to avoid.
    foiled_message: str = ""
    resources: dict = field(default_factory=dict)
    scatter: bool = False
    custom_message: bool = False

    @property
    def is_kind(self):
        return self.money[0] > 0 or any(
            value > 0 for value in self.resources.values()
        )


PRANKS = (
    Prank(
        key="word",
        label="Word on the street",
        blurb="Send them any message you like, unsigned.",
        message="",
        custom_message=True,
    ),
    Prank(
        key="pickpocket",
        label="Pickpocket",
        blurb="Lifts £50–£500 off them.",
        message=(
            "Somebody bumped into you coming out of the station and "
            "apologised very politely. Your wallet is lighter."
        ),
        money=(-500, -50),
        foiled_message=(
            "Somebody tried your pockets coming out of the station. "
            "Judging by their face, they were expecting more."
        ),
    ),
    Prank(
        key="envelope",
        label="Envelope under the door",
        blurb="Slips them £100–£1,000.",
        message=(
            "An envelope came through your door with cash in it and no "
            "name on it. You have decided not to ask."
        ),
        money=(100, 1_000),
    ),
    Prank(
        key="bad_pint",
        label="A bad pint",
        blurb="Takes 25 happiness.",
        message=(
            "That last pint was off. You are not feeling clever and you "
            "are not feeling sociable."
        ),
        resources={"happiness": -25},
    ),
    Prank(
        key="livener",
        label="Something in the coffee",
        blurb="Fills their energy and nerve.",
        message=(
            "Whatever was in that coffee, you have never felt more "
            "awake in your life. You could do anything. You might."
        ),
        resources={"energy": 9_999, "nerve": 9_999},
    ),
    Prank(
        key="grassed",
        label="Someone grassed",
        blurb="Adds 15 to their wanted level.",
        message=(
            "Somebody gave the law your name. Nothing has happened yet. "
            "That is the worst part."
        ),
        resources={"wanted_level": 15},
    ),
    Prank(
        key="bundled",
        label="Bundled into a cab",
        blurb="Wakes them up in a random other district.",
        message=(
            "You woke up in {district} with your shoes on and no memory "
            "of the journey. Somebody paid the fare, at least."
        ),
        scatter=True,
    ),
)

_BY_KEY = {prank.key: prank for prank in PRANKS}


def get_prank(key):
    return _BY_KEY.get(key)


class AdminActionError(Exception):
    """Raised when the panel is asked for something it will not do."""


def validate_adjustment(raw_amount):
    """Read a hand-typed figure, or refuse it.

    Returns a signed integer. Negative takes money away; the repository
    is what stops a balance going below zero, because that needs to see
    the balance.
    """
    if isinstance(raw_amount, bool):
        raise AdminActionError("Enter an amount.")

    try:
        amount = int(str(raw_amount).replace(",", "").replace("£", "").strip())
    except (TypeError, ValueError):
        raise AdminActionError("Enter a whole number of pounds.") from None

    if amount == 0:
        raise AdminActionError("Enter an amount other than zero.")

    if abs(amount) > MAXIMUM_ADJUSTMENT:
        raise AdminActionError(
            f"One adjustment cannot move more than "
            f"£{MAXIMUM_ADJUSTMENT:,}."
        )

    return amount


def adjustment_summary(amount, before, after):
    """The line that goes in the audit log and back to the panel."""
    verb = "Added" if amount > 0 else "Took"

    return (
        f"{verb} £{abs(amount):,}. "
        f"Balance £{before:,} to £{after:,}."
    )
