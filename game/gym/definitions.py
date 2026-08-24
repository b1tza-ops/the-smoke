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
    estimated_energy_to_next: int | None = None

    def multiplier_for(self, stat):
        return getattr(self, f"{stat}_multiplier")

    def gain_for(self, stat, base_gain=2):
        return round(base_gain * self.multiplier_for(stat), 2)


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
        estimated_energy_to_next=200,
    ),
    GymDefinition(
        key="camden_average_joes",
        name="Average Joe's Camden",
        district="camden",
        membership_cost=100,
        required_level=1,
        strength_multiplier=1.2,
        defence_multiplier=1.4,
        speed_multiplier=1.2,
        dexterity_multiplier=1.2,
        estimated_energy_to_next=500,
    ),
    GymDefinition(
        key="camden_ironworks",
        name="Camden Ironworks",
        district="camden",
        membership_cost=250,
        required_level=1,
        strength_multiplier=1.4,
        defence_multiplier=1.5,
        speed_multiplier=1.6,
        dexterity_multiplier=1.4,
        estimated_energy_to_next=1_000,
    ),
    GymDefinition(
        key="brixton_performance",
        name="Brixton Barbell Club",
        district="brixton",
        membership_cost=500,
        required_level=2,
        strength_multiplier=1.6,
        defence_multiplier=1.6,
        speed_multiplier=1.6,
        dexterity_multiplier=0.0,
        estimated_energy_to_next=2_000,
    ),
    GymDefinition(
        key="brixton_south_performance",
        name="South London Performance",
        district="brixton",
        membership_cost=1_000,
        required_level=2,
        strength_multiplier=1.7,
        defence_multiplier=1.7,
        speed_multiplier=1.8,
        dexterity_multiplier=1.6,
        estimated_energy_to_next=2_750,
    ),
    GymDefinition(
        key="soho_combat",
        name="Soho Fitness Rooms",
        district="soho",
        membership_cost=2_500,
        required_level=2,
        strength_multiplier=1.7,
        defence_multiplier=1.8,
        speed_multiplier=1.8,
        dexterity_multiplier=1.9,
        estimated_energy_to_next=3_000,
    ),
    GymDefinition(
        key="soho_fight_lab",
        name="West End Fight Lab",
        district="soho",
        membership_cost=5_000,
        required_level=3,
        strength_multiplier=1.85,
        defence_multiplier=1.85,
        speed_multiplier=0.0,
        dexterity_multiplier=1.85,
        estimated_energy_to_next=3_500,
    ),
    GymDefinition(
        key="soho_london_elite",
        name="London Elite",
        district="soho",
        membership_cost=10_000,
        required_level=4,
        strength_multiplier=2.0,
        defence_multiplier=2.0,
        speed_multiplier=2.0,
        dexterity_multiplier=2.0,
        estimated_energy_to_next=None,
    ),
)

GYMS_BY_KEY = {gym.key: gym for gym in GYMS}


def get_gym(gym_key):
    return GYMS_BY_KEY.get(gym_key)


def get_district_gyms(district_key):
    return tuple(
        gym
        for gym in GYMS
        if gym.district == district_key
    )
