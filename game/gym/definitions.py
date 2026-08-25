from dataclasses import dataclass, field


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
    weight_class: str = "middleweight"
    energy_per_train: int = 10
    exercises: dict[str, str] = field(default_factory=dict)

    def multiplier_for(self, stat):
        return getattr(self, f"{stat}_multiplier")

    def trains(self, stat):
        return self.multiplier_for(stat) > 0

    def exercise_for(self, stat):
        return self.exercises.get(stat, "training sets")


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
        weight_class="lightweight",
        energy_per_train=5,
        exercises={
            "strength": "dumbbell presses",
            "defence": "medicine ball throws",
            "speed": "treadmill intervals",
            "dexterity": "skipping rope drills",
        },
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
        weight_class="lightweight",
        energy_per_train=5,
        exercises={
            "strength": "bench presses",
            "defence": "weighted planks",
            "speed": "shuttle runs",
            "dexterity": "agility ladder work",
        },
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
        weight_class="lightweight",
        energy_per_train=5,
        exercises={
            "strength": "deadlifts",
            "defence": "farmer's walks",
            "speed": "sled pushes",
            "dexterity": "kettlebell flows",
        },
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
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "squat sets",
            "defence": "barbell rows",
            "speed": "power cleans",
        },
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
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "push presses",
            "defence": "sandbag carries",
            "speed": "hill sprints",
            "dexterity": "cone drills",
        },
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
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "heavy bag rounds",
            "defence": "body shield drills",
            "speed": "speed bag work",
            "dexterity": "slip rope drills",
        },
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
        weight_class="heavyweight",
        energy_per_train=25,
        exercises={
            "strength": "clinch work",
            "defence": "guard retention drills",
            "dexterity": "footwork ladders",
        },
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
        weight_class="heavyweight",
        energy_per_train=25,
        exercises={
            "strength": "olympic lifts",
            "defence": "resisted holds",
            "speed": "sprint blocks",
            "dexterity": "reaction-ball drills",
        },
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
