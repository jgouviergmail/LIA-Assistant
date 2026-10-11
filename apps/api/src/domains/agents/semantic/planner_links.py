"""Concrete parameter sources for a planner revising an existing plan."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from src.core.config import get_settings
from src.domains.agents.semantic.expansion_service import (
    generate_linking_hints_for_plan,
)

if TYPE_CHECKING:
    from src.domains.agents.orchestration.plan_schemas import ExecutionPlan


def dependencies_with_plan_sources(section: str, plan: ExecutionPlan | None) -> str:
    """Append available, shape-compatible references without changing user values."""
    if plan is None or not get_settings().semantic_linking_enabled:
        return section
    hints = generate_linking_hints_for_plan(
        [{"step_id": step.step_id, "tool_name": step.tool_name or ""} for step in plan.steps]
    )
    if not hints:
        return section
    return "\n".join(
        part for part in (section, json.dumps({"plan_parameter_sources": hints})) if part
    )
