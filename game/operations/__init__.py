"""The debt campaign: a chain of district operations."""

from game.operations.definitions import (
    CAMPAIGN,
    FIRST_OPERATION_KEY,
    OPERATIONS_BY_KEY,
    Approach,
    Operation,
    get_operation,
)
from game.operations.service import (
    ACTIVE,
    AVAILABLE,
    COMPLETED,
    LOCKED,
    OperationStatus,
    approach_shortfalls,
    campaign_status,
    can_attempt,
    next_operation,
)

__all__ = [
    "ACTIVE",
    "AVAILABLE",
    "CAMPAIGN",
    "COMPLETED",
    "FIRST_OPERATION_KEY",
    "LOCKED",
    "OPERATIONS_BY_KEY",
    "Approach",
    "Operation",
    "OperationStatus",
    "approach_shortfalls",
    "campaign_status",
    "can_attempt",
    "get_operation",
    "next_operation",
]
