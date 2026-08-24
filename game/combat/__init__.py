"""Turn-based NPC combat encounters."""

from game.combat.npc import (
    CAMDEN_OPPONENT,
    COMBAT_ENERGY_COST,
    OPPONENTS,
    OPPONENTS_BY_KEY,
    CombatError,
    CombatResult,
    fight_camden_opponent,
    fight_opponent,
    get_combat_block,
    get_district_opponents,
)
from game.combat.records import (
    EncounterRecord,
    get_encounter_records,
    record_encounter,
)

__all__ = [
    "CAMDEN_OPPONENT",
    "COMBAT_ENERGY_COST",
    "OPPONENTS",
    "OPPONENTS_BY_KEY",
    "CombatError",
    "CombatResult",
    "EncounterRecord",
    "fight_camden_opponent",
    "fight_opponent",
    "get_combat_block",
    "get_district_opponents",
    "get_encounter_records",
    "record_encounter",
]
