"""Turn-based NPC combat encounters."""

from game.combat.npc import (
    CAMDEN_OPPONENT,
    COMBAT_ENERGY_COST,
    CombatError,
    CombatResult,
    fight_camden_opponent,
    get_combat_block,
)

__all__ = [
    "CAMDEN_OPPONENT",
    "COMBAT_ENERGY_COST",
    "CombatError",
    "CombatResult",
    "fight_camden_opponent",
    "get_combat_block",
]
