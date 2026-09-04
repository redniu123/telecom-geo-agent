"""Serializable state contract for the bounded P0 workflow."""

from __future__ import annotations

from typing import Literal, TypedDict

from telecom_core.models import BOMResult, RouteResult, TelecomTask, ValidationResult


class AgentState(TypedDict):
    user_request: str
    task: TelecomTask | None
    first_route: RouteResult | None
    final_route: RouteResult | None
    validation_history: list[ValidationResult]
    forbidden_asset_ids: list[str]
    repair_count: int
    bom_result: BOMResult | None
    execution_log: list[str]
    status: Literal["pending", "completed", "failed"]
    error: str | None


def new_agent_state(user_request: str) -> AgentState:
    """Create a fresh state using only JSON-serializable values."""

    return {
        "user_request": user_request,
        "task": None,
        "first_route": None,
        "final_route": None,
        "validation_history": [],
        "forbidden_asset_ids": [],
        "repair_count": 0,
        "bom_result": None,
        "execution_log": [],
        "status": "pending",
        "error": None,
    }
