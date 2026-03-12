"""
Orchestration logic for multi-agent coordination.

Version 1 (current): Sequential execution only.
Version 2 (future): Parallel execution with dependency management.
"""

import structlog

from src.core.field_names import FIELD_STATUS
from src.domains.agents.constants import (
    # v3.2 naming: singular domain names
    AGENT_CONTACT,
    EXECUTION_MODE_SEQUENTIAL,
    INTENTION_CONTACT,
    INTENTION_CONTACT_DETAILS,
    INTENTION_CONTACT_LIST,
    INTENTION_CONTACT_SEARCH,
    STATE_KEY_AGENT_RESULTS,
    STATE_KEY_CURRENT_TURN_ID,
    STATE_KEY_ORCHESTRATION_PLAN,
    STATUS_ERROR,
    STATUS_SUCCESS,
    make_agent_result_key,
)
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.models import MessagesState
from src.domains.agents.orchestration.schemas import OrchestratorPlan

logger = structlog.get_logger(__name__)


async def create_orchestration_plan(
    router_output: RouterOutput,
    state: MessagesState,
) -> OrchestratorPlan:
    """
    Create orchestration plan based on router decision.

    Version 1: Sequential execution only.
    Maps user intentions to agents that should be called.

    Version 2 (future): Will support parallel execution with dependency graph.

    Args:
        router_output: Router decision with intention and confidence.
        state: Current LangGraph state (for context-aware planning).

    Returns:
        OrchestratorPlan with agents to call and execution mode.

    Example:
        >>> router_output = RouterOutput(
        ...     intention="contacts_search",
        ...     confidence=0.9,
        ...     context_label="contact",
        ...     next_node="task_orchestrator"
        ... )
        >>> plan = await create_orchestration_plan(router_output, state)
        >>> # plan.agents_to_call == ["contacts_agent"]
        >>> # plan.execution_mode == "sequential"

    """

    # V1: Simple intention-to-agent mapping (sequential only)
    # Maps router intention (e.g., "contacts_search") to agents to execute
    # v3.2 naming: singular domain names
    intention_to_agents: dict[str, list[str]] = {
        INTENTION_CONTACT_SEARCH: [AGENT_CONTACT],
        INTENTION_CONTACT_LIST: [AGENT_CONTACT],
        INTENTION_CONTACT_DETAILS: [AGENT_CONTACT],
        INTENTION_CONTACT: [AGENT_CONTACT],  # Fallback for old router outputs
    }

    # Use intention (not context_label) for mapping - more reliable
    agents = intention_to_agents.get(router_output.intention, [])

    # Log planning decision
    logger.info(
        "orchestration_plan_created",
        intention=router_output.intention + " -> " + router_output.context_label,
        confidence=router_output.confidence,
        agents_count=len(agents),
        agents=agents,
        execution_mode=EXECUTION_MODE_SEQUENTIAL,  # V1 hardcoded
    )

    # Create plan
    plan = OrchestratorPlan(
        agents_to_call=agents,
        execution_mode=EXECUTION_MODE_SEQUENTIAL,  # V1: Sequential only
        metadata={
            "version": "v1_sequential",
            "intention": router_output.intention,
            "confidence": router_output.confidence,
            "context_label": router_output.context_label,
            "reasoning": router_output.reasoning,
        },
    )

    return plan


def should_execute_agent(agent_name: str, state: MessagesState) -> bool:
    """
    Check if an agent should be executed.

    Prevents duplicate execution if agent already ran in current cycle.

    Args:
        agent_name: Name of the agent to check.
        state: Current LangGraph state.

    Returns:
        True if agent should execute, False if already executed.
    """
    agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})

    # Check if agent already executed in this cycle
    if agent_name in agent_results:
        result = agent_results[agent_name]
        # Only skip if status is success or connector_disabled (final states)
        if result[FIELD_STATUS] in [STATUS_SUCCESS, "connector_disabled"]:
            logger.debug(
                "agent_already_executed",
                agent_name=agent_name,
                status=result[FIELD_STATUS],
            )
            return False

    return True


def get_next_agent_from_plan(state: MessagesState) -> str | None:
    """
    Get next agent to execute from orchestration plan.

    Version 1: Returns first unexecuted agent (sequential).
    Version 2 (future): Will handle dependency resolution for parallel execution.

    V2 (with turn_id): Uses composite keys "turn_id:agent_name" to check execution status.

    Args:
        state: Current LangGraph state with orchestration_plan and current_turn_id.

    Returns:
        Next agent name to execute, or None if all agents completed.

    Example:
        >>> # Assume plan has ["contacts_agent", "emails_agent"]
        >>> # Turn 3: contacts_agent already executed (key "3:contacts_agent" exists)
        >>> next_agent = get_next_agent_from_plan(state)
        >>> # next_agent == "emails_agent" (key "3:emails_agent" doesn't exist yet)
    """
    plan = state.get(STATE_KEY_ORCHESTRATION_PLAN)
    if not plan:
        logger.debug("no_orchestration_plan")
        return None

    # Handle both dict (new format) and object (legacy format)
    agents_to_call = plan.get("agents_to_call") if isinstance(plan, dict) else plan.agents_to_call
    if not agents_to_call:
        logger.debug("empty_agents_to_call")
        return None

    agent_results = state.get(STATE_KEY_AGENT_RESULTS, {})
    turn_id = state.get(STATE_KEY_CURRENT_TURN_ID, 0)

    # V1: Sequential - find first unexecuted agent
    for agent_name in agents_to_call:
        composite_key = make_agent_result_key(turn_id, agent_name)

        if composite_key not in agent_results:
            # Handle both dict and object format for execution_mode
            execution_mode = (
                plan.get("execution_mode") if isinstance(plan, dict) else plan.execution_mode
            )
            logger.debug(
                "next_agent_selected",
                agent_name=agent_name,
                turn_id=turn_id,
                composite_key=composite_key,
                execution_mode=execution_mode,
            )
            return str(agent_name)

        # If agent failed, skip to next (don't retry in V1)
        result = agent_results[composite_key]
        if result[FIELD_STATUS] == STATUS_ERROR:
            logger.warning(
                "agent_failed_skipping",
                agent_name=agent_name,
                turn_id=turn_id,
                error=result.get("error"),
            )
            continue

    # All agents executed
    logger.debug(
        "all_agents_executed",
        agents=plan.agents_to_call,
        turn_id=turn_id,
        results_count=len(agent_results),
    )
    return None
