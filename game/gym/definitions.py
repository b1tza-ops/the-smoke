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

# The gain bars are drawn against this ceiling. It sits deliberately
# above the best gym in the game, so the top of the roster still has
# visible room above it rather than reading as finished -- Torn's bars
# work the same way, and its expensive mid-game gyms fill less than
# half. Raise it when a gym is added that would otherwise fill the bar.
GAIN_SCALE_MAX = 6.0
GAIN_BAR_SEGMENTS = 12

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
        weight_class="lightweight",
        energy_per_train=5,
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
        weight_class="lightweight",
        energy_per_train=5,
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
        weight_class="lightweight",
        energy_per_train=5,
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
        weight_class="middleweight",
        energy_per_train=10,
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
        estimated_energy_to_next=2_500,
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "olympic lifts",
            "defence": "resisted holds",
            "speed": "sprint blocks",
            "dexterity": "reaction-ball drills",
        },
    ),
    GymDefinition(
        key="shoreditch_warehouse",
        name="The Warehouse",
        district="shoreditch",
        membership_cost=25_000,
        required_level=5,
        strength_multiplier=2.1,
        defence_multiplier=2.1,
        speed_multiplier=2.2,
        dexterity_multiplier=2.2,
        estimated_energy_to_next=4_000,
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "sled pushes",
            "defence": "brazilian jiu-jitsu",
            "speed": "shuttle runs",
            "dexterity": "battle rope waves",
        },
    ),
    GymDefinition(
        key="shoreditch_iron_yard",
        name="Iron Yard",
        district="shoreditch",
        membership_cost=60_000,
        required_level=6,
        strength_multiplier=2.4,
        defence_multiplier=2.3,
        speed_multiplier=2.2,
        dexterity_multiplier=2.2,
        estimated_energy_to_next=6_000,
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "atlas stones",
            "defence": "wrestling rounds",
            "speed": "hill repeats",
            "dexterity": "agility ladders",
        },
    ),
    GymDefinition(
        key="hackney_arches",
        name="The Arches",
        district="hackney",
        membership_cost=150_000,
        required_level=7,
        strength_multiplier=2.6,
        defence_multiplier=2.6,
        speed_multiplier=2.6,
        dexterity_multiplier=2.6,
        estimated_energy_to_next=9_000,
        weight_class="middleweight",
        energy_per_train=10,
        exercises={
            "strength": "log presses",
            "defence": "sambo drills",
            "speed": "track intervals",
            "dexterity": "speed bag",
        },
    ),
    GymDefinition(
        key="hackney_marsh_athletic",
        name="Marsh Athletic",
        district="hackney",
        membership_cost=400_000,
        required_level=9,
        strength_multiplier=3.0,
        defence_multiplier=3.0,
        speed_multiplier=3.2,
        dexterity_multiplier=3.0,
        estimated_energy_to_next=14_000,
        weight_class="heavyweight",
        energy_per_train=25,
        exercises={
            "strength": "yoke carries",
            "defence": "greco-roman rounds",
            "speed": "flying sprints",
            "dexterity": "cone weaves",
        },
    ),
    GymDefinition(
        key="hackney_powerhouse",
        name="Powerhouse",
        district="hackney",
        membership_cost=1_000_000,
        required_level=12,
        strength_multiplier=3.6,
        defence_multiplier=3.5,
        speed_multiplier=3.4,
        dexterity_multiplier=0.0,
        estimated_energy_to_next=22_000,
        weight_class="heavyweight",
        energy_per_train=25,
        exercises={
            "strength": "rack pulls",
            "defence": "clinch rounds",
            "speed": "resisted starts",
        },
    ),
    GymDefinition(
        key="hackney_the_lock",
        name="The Lock",
        district="hackney",
        membership_cost=2_500_000,
        required_level=15,
        strength_multiplier=4.0,
        defence_multiplier=4.0,
        speed_multiplier=4.0,
        dexterity_multiplier=4.0,
        estimated_energy_to_next=None,
        weight_class="heavyweight",
        energy_per_train=25,
        exercises={
            "strength": "competition deadlifts",
            "defence": "full-contact sparring",
            "speed": "flat-out repeats",
            "dexterity": "blind-side drills",
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
