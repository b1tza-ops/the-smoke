"""The city directory: every place in London a player can walk into.

The navigation bar grew a link per feature until it stopped being a
navigation bar. This is the directory behind it — one catalogue of
destinations, grouped the way the city actually works: the places that
travel with you, the places in the district you are standing in, and the
places you would have to get on a bus to reach.
"""

from dataclasses import dataclass

from game.shop import VENUES
from game.world.districts import DISTRICTS_BY_KEY


ANYWHERE = None


@dataclass(frozen=True)
class Destination:
    endpoint: str
    name: str
    icon: str
    blurb: str
    # None when the place follows the player around the city.
    district: str | None = ANYWHERE


# Places that exist wherever the player happens to be standing.
UBIQUITOUS = (
    Destination("character", "Character", "character", "Stats, loadout and record."),
    Destination("inventory", "Items", "inventory", "Everything you are carrying."),
    Destination("gym", "Gym", "gym", "Spend energy, buy stats."),
    Destination("crimes", "Crimes", "crimes", "Earn on your nerve."),
    Destination("fight", "Street Fights", "pvp", "Local NPCs, paid in cash and XP."),
    Destination("pvp", "Player Fights", "pvp", "Attack other players for rating."),
    Destination("pvp_contracts", "Contracts", "operations", "Standing daily targets."),
    Destination("pvp_leaderboard", "Leaderboard", "level", "Where you sit against everyone."),
    Destination("prologue", "Operations", "operations", "The debt campaign."),
    Destination("jobs", "Job", "job", "Shift work for steady money."),
    Destination("bank", "Bank", "bank", "Put cash somewhere it earns."),
    Destination("housing", "Housing", "housing", "Where you live, and what it does for you."),
    Destination("item_market", "Item Market", "shop", "Buy and sell with other players."),
    Destination("travel", "Travel Agency", "travel", "Walk, bus or Underground."),
    Destination("hospital", "Hospital", "hospital", "Where losing a fight puts you."),
    Destination("jail", "Jail", "jail", "Where a failed crime puts you."),
    Destination("forum", "Guides", "operations", "How the game works, in writing."),
    Destination("rules", "Rules", "wanted", "What gets you banned."),
)

# Places that belong to one district and stay there. The general store and
# the fence exist in every district, so they are listed against whichever
# one the player is currently in.
LOCAL = (
    Destination("district_shop", "General Store", "shop", "Everyday supplies at local prices."),
    Destination("black_market", "Black Market", "shop", "The fence. Sells nothing, buys anything."),
)

# Places that stand in exactly one district, wherever the player is.
FIXED = (
    Destination(
        "gun_bazaar",
        "Kingsland Arms Bazaar",
        "guns",
        "Pistols and rounds. The only firearms in London.",
        district="hackney",
    ),
    Destination(
        "casino",
        "The Golden Square",
        "casino",
        "Slots, keno and blackjack. The house wins slowly.",
        district="soho",
    ),
    Destination(
        "loan_shark",
        "Ronnie Dell",
        "bank",
        "Lends on a handshake. Collects in person.",
        district="soho",
    ),
    Destination(
        "motors",
        "Coldharbour Motors",
        "car",
        "Buys back time. Sells the attention that comes with it.",
        district="brixton",
    ),
)


@dataclass(frozen=True)
class CitySection:
    title: str
    subtitle: str
    destinations: tuple
    district: str | None = ANYWHERE
    reachable: bool = True


def _district_name(key):
    district = DISTRICTS_BY_KEY.get(key)
    return district.name if district else key.title()


def directory(current_district):
    """The whole city, grouped for the district the player is standing in."""
    here = _district_name(current_district)
    sections = [
        CitySection(
            title=here,
            subtitle="Where you are standing",
            destinations=LOCAL + tuple(
                place for place in FIXED if place.district == current_district
            ),
            district=current_district,
        ),
    ]

    elsewhere = tuple(
        place for place in FIXED if place.district != current_district
    )
    if elsewhere:
        sections.append(
            CitySection(
                title="Elsewhere in London",
                subtitle="You will need to travel to reach these",
                destinations=elsewhere,
                reachable=False,
            )
        )

    sections.append(
        CitySection(
            title="Wherever you are",
            subtitle="These follow you around the city",
            destinations=UBIQUITOUS,
        )
    )
    return tuple(sections)


def validate_catalogue():
    """Every fixed destination must stand in a real district with a venue."""
    for place in FIXED:
        if place.district not in DISTRICTS_BY_KEY:
            raise ValueError(
                f"{place.endpoint} stands in unknown district "
                f"{place.district!r}"
            )

    bazaar_districts = {
        venue["district"] for venue in VENUES.values()
        if venue.get("kind") == "guns"
    }
    fixed_districts = {place.district for place in FIXED}
    if not bazaar_districts <= fixed_districts:
        raise ValueError(
            "a gun venue exists in a district the city directory does not list"
        )


validate_catalogue()
