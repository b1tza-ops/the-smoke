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


def get_district(district_key):
    return DISTRICTS_BY_KEY[district_key]


def get_travel_route(origin_key, destination_key):
    return TRAVEL_ROUTES_BY_PAIR[
        (origin_key, destination_key)
    ]