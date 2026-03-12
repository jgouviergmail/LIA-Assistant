"""
Agent orchestration logic.
Handles multi-agent coordination, execution planning, and result aggregation.
"""

from src.domains.agents.orchestration.adaptive_replanner import (
    AdaptiveRePlanner,
    ExecutionAnalysis,
    RecoveryStrategy,
    RePlanContext,
    RePlanDecision,
    RePlanResult,
    RePlanTrigger,
    analyze_execution_results,
    should_trigger_replan,
)
from src.domains.agents.orchestration.mappers import map_execution_result_to_agent_result
from src.domains.agents.orchestration.orchestrator import (
    create_orchestration_plan,
    get_next_agent_from_plan,
    should_execute_agent,
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
    # Adaptive Re-Planner (INTELLIPLANNER Phase E)
    "AdaptiveRePlanner",
    "ExecutionAnalysis",
    "RecoveryStrategy",
    "RePlanContext",
    "RePlanDecision",
    "RePlanResult",
    "RePlanTrigger",
    "analyze_execution_results",
    "should_trigger_replan",
    # Orchestration schemas
    "AgentResult",
    "AgentResultData",
    "ContactsResultData",
    "ExecutionResult",
    "OrchestratorPlan",
    "StepResult",
    "create_orchestration_plan",
    "get_next_agent_from_plan",
    "map_execution_result_to_agent_result",
    "should_execute_agent",
]
