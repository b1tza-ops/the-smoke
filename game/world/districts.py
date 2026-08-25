from dataclasses import dataclass


@dataclass(frozen=True)
class DistrictDefinition:
    key: str
    name: str
    description: str
    minimum_level: int


@dataclass(frozen=True)
class TravelRoute:
    district_a: str
    district_b: str
    cost: int
    duration_seconds: int


DISTRICTS = (
    DistrictDefinition(
        key="camden",
        name="Camden",
        description=(
            "Crowded markets, music venues and plenty "
            "of opportunities for new criminals."
        ),
        minimum_level=1,
    ),
    DistrictDefinition(
        key="brixton",
        name="Brixton",
        description=(
            "Busy streets and warehouses where greater "
            "risks can bring greater rewards."
        ),
        minimum_level=1,
    ),
    DistrictDefinition(
        key="soho",
        name="Soho",
        description=(
            "Nightclubs, tourists and wealthy targets "
            "in the heart of London."
        ),
        minimum_level=2,
    ),
    DistrictDefinition(
        key="shoreditch",
        name="Shoreditch",
        description=(
            "Tech money and gallery openings on old East End "
            "ground, with warehouse parties until morning."
        ),
        minimum_level=5,
    ),
    DistrictDefinition(
        key="hackney",
        name="Hackney",
        description=(
            "Canal-side lock-ups and quiet estates where "
            "London's serious money moves without a sound."
        ),
        minimum_level=7,
    ),
)


TRAVEL_ROUTES = (
    TravelRoute(
        district_a="camden",
        district_b="brixton",
        cost=35,
        duration_seconds=10 * 60,
    ),
    TravelRoute(
        district_a="camden",
        district_b="soho",
        cost=20,
        duration_seconds=5 * 60,
    ),
    TravelRoute(
        district_a="brixton",
        district_b="soho",
        cost=30,
        duration_seconds=8 * 60,
    ),
    # East London. Shoreditch and Hackney sit next to each other and
    # a long way from Brixton, and the fares follow the map.
    TravelRoute(
        district_a="camden",
        district_b="shoreditch",
        cost=30,
        duration_seconds=8 * 60,
    ),
    TravelRoute(
        district_a="soho",
        district_b="shoreditch",
        cost=25,
        duration_seconds=6 * 60,
    ),
    TravelRoute(
        district_a="brixton",
        district_b="shoreditch",
        cost=40,
        duration_seconds=11 * 60,
    ),
    TravelRoute(
        district_a="camden",
        district_b="hackney",
        cost=35,
        duration_seconds=9 * 60,
    ),
    TravelRoute(
        district_a="soho",
        district_b="hackney",
        cost=40,
        duration_seconds=11 * 60,
    ),
    TravelRoute(
        district_a="brixton",
        district_b="hackney",
        cost=50,
        duration_seconds=14 * 60,
    ),
    TravelRoute(
        district_a="shoreditch",
        district_b="hackney",
        cost=20,
        duration_seconds=5 * 60,
    ),
)


DISTRICTS_BY_KEY = {
    district.key: district
    for district in DISTRICTS
}


TRAVEL_ROUTES_BY_PAIR = {
    pair: route
    for route in TRAVEL_ROUTES
    for pair in (
        (route.district_a, route.district_b),
        (route.district_b, route.district_a),
    )
}


def validate_catalogue():
    """Check the map is complete and consistent.

    Every district has to be reachable from every other one in a single
    hop, because travel offers a direct fare between any two -- a
    missing route would show up as a district the player simply cannot
    reach. Run at import so a bad edit fails loudly rather than at the
    moment somebody tries to travel.
    """
    keys = [district.key for district in DISTRICTS]

    if len(keys) != len(set(keys)):
        raise ValueError("District keys must be unique.")

    seen = set()

    for route in TRAVEL_ROUTES:
        for key in (route.district_a, route.district_b):
            if key not in DISTRICTS_BY_KEY:
                raise ValueError(
                    f"Route references unknown district '{key}'."
                )

        if route.district_a == route.district_b:
            raise ValueError(
                f"Route from '{route.district_a}' leads to itself."
            )

        if route.cost < 0 or route.duration_seconds <= 0:
            raise ValueError(
                f"Route {route.district_a}-{route.district_b} "
                "has an impossible fare or duration."
            )

        pair = frozenset((route.district_a, route.district_b))

        if pair in seen:
            raise ValueError(
                f"Route {route.district_a}-{route.district_b} "
                "is defined twice."
            )

        seen.add(pair)

    for origin in keys:
        for destination in keys:
            if origin == destination:
                continue

            if frozenset((origin, destination)) not in seen:
                raise ValueError(
                    f"No route between '{origin}' and '{destination}'."
                )


def get_district(district_key):
    return DISTRICTS_BY_KEY[district_key]


def get_travel_route(origin_key, destination_key):
    return TRAVEL_ROUTES_BY_PAIR[
        (origin_key, destination_key)
    ]


validate_catalogue()
