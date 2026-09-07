"""What happened while you were away.

The Smoke does a lot to a player who is not looking. Rent accrues,
interest compounds, somebody breaks into the safe, somebody puts a price
on the head, a shift finishes. Every one of those already worked. None
of them was visible on the page a player actually lands on.

The notifications were the worst of it: four separate mechanics write
them -- an attack, a burglary that came off, one that did not, a bounty
posted, a bounty collected -- and they surfaced on exactly one page,
`/pvp`. You could be robbed overnight, log in, and see nothing at all
unless you happened to click through to Player Fights.

The quiet one is rent. A player in arrears keeps their address and
loses everything it does: no faster recovery, no extra carrying space.
That is enforced on every page load and was announced on none of them,
so the symptom was a game that had silently got slower for reasons
nobody could see.

This turns all of it into one ordered list. Pure rules: it is handed
facts and returns entries. Nothing here reads a database or a clock,
which is what lets the whole thing be tested without one.
"""

from dataclasses import dataclass


# Ordered worst-first. An entry's kind decides where it sorts, so the
# thing costing a player money outranks the thing paying them.
URGENT = "urgent"
GOOD = "good"
NEUTRAL = "neutral"

_TONE_ORDER = {URGENT: 0, NEUTRAL: 1, GOOD: 2}


@dataclass(frozen=True)
class Entry:
    kind: str
    tone: str
    headline: str
    detail: str
    link: str
    link_text: str


def _plural(count, word):
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def build(
    *,
    rent_owed=0,
    daily_rent=0,
    loan_balance=0,
    loan_overdue=False,
    missed_payments=0,
    notifications=(),
    shift_ready=False,
    shift_pay=0,
    jail_seconds=0,
    hospital_seconds=0,
):
    """Everything worth telling a player the moment they arrive.

    Keyword-only on purpose. This takes nine facts of similar shape and
    a positional call would be unreadable at both ends -- and a
    transposed pair would be a silent wrong answer rather than an
    error.
    """
    entries = []

    if rent_owed > 0:
        entries.append(Entry(
            kind="rent",
            tone=URGENT,
            headline=f"You owe £{rent_owed:,} in rent",
            detail=(
                "Until it is paid your home does nothing for you — no "
                "faster recovery, no extra carrying space."
                + (f" It runs at £{daily_rent:,} a day." if daily_rent else "")
            ),
            link="/housing/manage",
            link_text="Settle up",
        ))

    if loan_overdue:
        entries.append(Entry(
            kind="loan",
            tone=URGENT,
            headline=f"Ronnie Dell wants £{loan_balance:,}",
            detail=(
                "The payment is overdue."
                + (
                    f" You have missed {_plural(missed_payments, 'payment')}"
                    " — he collects in person."
                    if missed_payments else
                    " He collects in person."
                )
            ),
            link="/loanshark",
            link_text="Pay him",
        ))

    if hospital_seconds > 0:
        entries.append(Entry(
            kind="hospital",
            tone=URGENT,
            headline="You are in hospital",
            detail=(
                f"Out in {_minutes(hospital_seconds)}. Nothing else "
                "works until then."
            ),
            link="/hospital",
            link_text="See how long",
        ))

    if jail_seconds > 0:
        entries.append(Entry(
            kind="jail",
            tone=URGENT,
            headline="You are in a cell",
            detail=(
                f"Out in {_minutes(jail_seconds)}, unless somebody "
                "pays your bail or breaks you out."
            ),
            link="/jail",
            link_text="See the cells",
        ))

    if notifications:
        entries.append(Entry(
            kind="notifications",
            tone=NEUTRAL,
            headline=(
                "Somebody came for you"
                if len(notifications) == 1 else
                f"{len(notifications)} people came for you"
            ),
            detail=_first_lines(notifications),
            link="/pvp",
            link_text="Read them",
        ))

    if shift_ready:
        entries.append(Entry(
            kind="shift",
            tone=GOOD,
            headline="Your shift is finished",
            detail=(
                f"£{shift_pay:,} waiting to be collected."
                if shift_pay else
                "There is pay waiting to be collected."
            ),
            link="/jobs",
            link_text="Collect it",
        ))

    entries.sort(key=lambda entry: _TONE_ORDER[entry.tone])

    return tuple(entries)


def _minutes(seconds):
    if seconds >= 3600:
        hours = seconds // 3600
        return _plural(hours, "hour")

    return _plural(max(1, seconds // 60), "minute")


def _first_lines(notifications, limit=2):
    """The first couple of messages, so the panel says something real.

    A count alone reads as chrome. The actual sentence -- "your home
    was broken into" -- is the thing that makes somebody click.
    """
    shown = [str(item).strip() for item in notifications[:limit]]
    rest = len(notifications) - len(shown)

    if rest > 0:
        shown.append(f"…and {_plural(rest, 'more')}.")

    return " ".join(shown)
