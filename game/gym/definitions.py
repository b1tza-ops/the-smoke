from dataclasses import dataclass


@dataclass(frozen=True)
class GymDefinition:
    key: str
    name: str
    district: str
    membership_cost: int
    required_level: int
    strength_multiplier: float
    defence_multiplier: float
    speed_multiplier: float
    dexterity_multiplier: float

    def multiplier_for(self, stat):
        return getattr(self, f"{stat}_multiplier")


DEFAULT_GYM_KEY = "camden_community"

GYMS = (
    GymDefinition(
        key=DEFAULT_GYM_KEY,
        name="Camden Community Gym",
        district="camden",
        membership_cost=0,
        required_level=1,
        strength_multiplier=1.0,
        defence_multiplier=1.0,
        speed_multiplier=1.0,
        dexterity_multiplier=1.0,
    ),
    GymDefinition(
        key="brixton_performance",
        name="Brixton Performance Club",
        district="brixton",
        membership_cost=750,
        required_level=2,
        strength_multiplier=0.9,
        defence_multiplier=1.0,
        speed_multiplier=1.3,
        dexterity_multiplier=1.2,
    ),
    GymDefinition(
        key="soho_combat",
        name="Soho Combat House",
        district="soho",
        membership_cost=2_000,
        required_level=4,
        strength_multiplier=1.25,
        defence_multiplier=1.3,
        speed_multiplier=1.0,
        dexterity_multiplier=1.1,
    ),
)

GYMS_BY_KEY = {
    gym.key: gym
    for gym in GYMS
}


def get_gym(gym_key):
    return GYMS_BY_KEY.get(gym_key)


def get_district_gyms(district_key):
    return tuple(
        gym
        for gym in GYMS
        if gym.district == district_key
    )
