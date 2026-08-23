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
