"""
Agent orchestration logic.
Handles multi-agent coordination, execution planning, and result aggregation.
"""

from src.domains.agents.orchestration.mappers import (
    build_execution_result,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.orchestrator import (
    create_orchestration_plan,
    get_next_agent_from_plan,
)
from src.domains.agents.orchestration.schemas import (
    AgentResult,
    AgentResultData,
    ContactsResultData,
    ExecutionResult,
    OrchestratorPlan,
    StepResult,
)

__all__ = [
    # Orchestration schemas
    "AgentResult",
    "AgentResultData",
    "ContactsResultData",
    "ExecutionResult",
    "OrchestratorPlan",
    "StepResult",
    "build_execution_result",
    "create_orchestration_plan",
    "get_next_agent_from_plan",
    "map_execution_result_to_agent_result",
]
