from dataclasses import dataclass


@dataclass(frozen=True)
class JobRoleDefinition:
    key: str
    name: str
    salary: int
    energy_cost: int
    work_xp: int
    required_level: int
    required_career_xp: int
    required_shifts: int


@dataclass(frozen=True)
class CareerDefinition:
    key: str
    name: str
    description: str
    roles: tuple[JobRoleDefinition, ...]
    required_district: str | None = None


CONSTRUCTION_ROLES = (
    JobRoleDefinition(
        key="construction_labourer",
        name="Construction Labourer",
        salary=120,
        energy_cost=10,
        work_xp=15,
        required_level=1,
        required_career_xp=0,
        required_shifts=0,
    ),
    JobRoleDefinition(
        key="skilled_labourer",
        name="Skilled Labourer",
        salary=220,
        energy_cost=12,
        work_xp=25,
        required_level=2,
        required_career_xp=60,
        required_shifts=4,
    ),
    JobRoleDefinition(
        key="site_foreman",
        name="Site Foreman",
        salary=400,
        energy_cost=15,
        work_xp=40,
        required_level=4,
        required_career_xp=200,
        required_shifts=10,
    ),
)

HOSPITALITY_ROLES = (
    JobRoleDefinition(
        key="bar_back",
        name="Bar Back",
        salary=110,
        energy_cost=10,
        work_xp=15,
        required_level=1,
        required_career_xp=0,
        required_shifts=0,
    ),
    JobRoleDefinition(
        key="bartender",
        name="Bartender",
        salary=210,
        energy_cost=12,
        work_xp=25,
        required_level=2,
        required_career_xp=60,
        required_shifts=4,
    ),
    JobRoleDefinition(
        key="venue_manager",
        name="Venue Manager",
        salary=380,
        energy_cost=15,
        work_xp=40,
        required_level=4,
        required_career_xp=200,
        required_shifts=10,
    ),
)

TRANSPORT_ROLES = (
    JobRoleDefinition(
        key="courier_rider",
        name="Courier Rider",
        salary=130,
        energy_cost=10,
        work_xp=15,
        required_level=1,
        required_career_xp=0,
        required_shifts=0,
    ),
    JobRoleDefinition(
        key="delivery_driver",
        name="Delivery Driver",
        salary=230,
        energy_cost=12,
        work_xp=25,
        required_level=2,
        required_career_xp=60,
        required_shifts=4,
    ),
    JobRoleDefinition(
        key="logistics_supervisor",
        name="Logistics Supervisor",
        salary=410,
        energy_cost=15,
        work_xp=40,
        required_level=4,
        required_career_xp=200,
        required_shifts=10,
    ),
)

CREATIVE_ROLES = (
    JobRoleDefinition(
        key="gallery_assistant",
        name="Gallery Assistant",
        salary=180,
        energy_cost=10,
        work_xp=18,
        required_level=5,
        required_career_xp=0,
        required_shifts=0,
    ),
    JobRoleDefinition(
        key="studio_manager",
        name="Studio Manager",
        salary=340,
        energy_cost=12,
        work_xp=30,
        required_level=6,
        required_career_xp=90,
        required_shifts=5,
    ),
    JobRoleDefinition(
        key="creative_director",
        name="Creative Director",
        salary=620,
        energy_cost=15,
        work_xp=48,
        required_level=8,
        required_career_xp=280,
        required_shifts=12,
    ),
)

SECURITY_ROLES = (
    JobRoleDefinition(
        key="yard_watchman",
        name="Yard Watchman",
        salary=230,
        energy_cost=10,
        work_xp=20,
        required_level=7,
        required_career_xp=0,
        required_shifts=0,
    ),
    JobRoleDefinition(
        key="close_protection",
        name="Close Protection",
        salary=430,
        energy_cost=13,
        work_xp=34,
        required_level=9,
        required_career_xp=110,
        required_shifts=6,
    ),
    JobRoleDefinition(
        key="security_contractor",
        name="Security Contractor",
        salary=780,
        energy_cost=16,
        work_xp=55,
        required_level=11,
        required_career_xp=330,
        required_shifts=14,
    ),
)

CAREERS = (
    CareerDefinition(
        key="construction",
        name="London Construction",
        description=(
            "Start on the tools and work towards running "
            "a London building site."
        ),
        roles=CONSTRUCTION_ROLES,
    ),
    CareerDefinition(
        key="hospitality",
        name="Soho Hospitality",
        description=(
            "Work the bars and venues of Soho's nightlife scene "
            "and work your way up to running the floor."
        ),
        roles=HOSPITALITY_ROLES,
        required_district="soho",
    ),
    CareerDefinition(
        key="transport",
        name="London Transport",
        description=(
            "Keep London moving as a courier, then a driver, "
            "then a logistics supervisor."
        ),
        roles=TRANSPORT_ROLES,
    ),
    CareerDefinition(
        key="creative",
        name="Shoreditch Creative",
        description=(
            "Hang the work, run the studio, then decide what "
            "Shoreditch looks at next."
        ),
        roles=CREATIVE_ROLES,
        required_district="shoreditch",
    ),
    CareerDefinition(
        key="security",
        name="Hackney Security",
        description=(
            "Watch the yards, then the people, then take the "
            "contracts nobody else will."
        ),
        roles=SECURITY_ROLES,
        required_district="hackney",
    ),
)

CAREERS_BY_KEY = {
    career.key: career
    for career in CAREERS
}

JOB_ROLES_BY_KEY = {
    role.key: role
    for career in CAREERS
    for role in career.roles
}


def get_career(career_key):
    return CAREERS_BY_KEY.get(career_key)


def get_job_role(role_key):
    return JOB_ROLES_BY_KEY.get(role_key)
