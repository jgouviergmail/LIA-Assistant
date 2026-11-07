"""
Agents domain graph.
LangGraph StateGraph definition with conditional routing and asyncio parallelism.

Architecture Evolution:
Version 1: Sequential agent execution via TaskOrchestrator
Version 2 (Phase 5.1): ExecutionPlan with sequential PlanExecutor
Version 3 (Phase 5.2B): Map-Reduce parallel execution with waves (DEPRECATED - Command+Send bug)
Version 4 (Phase 5.2B-asyncio - CURRENT): Native asyncio parallel execution

Phase 5.2B-asyncio - Asyncio Pattern:
    Compaction → Router → Planner → Task Orchestrator
                                      ↓ execute_plan_parallel() (asyncio.gather)
                                  Parallel Executor (native Python async)
                                      ↓ completed_steps
                                  agent_results → Response
                                  Response → END
"""

from contextlib import suppress
from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.config import Settings, settings
from src.core.constants import NODE_INITIATIVE
from src.domains.agents.constants import (
    # Agent constants (v3.2 convention: singular domain names)
    AGENT_BROWSER,
    NODE_APPROVAL_GATE,
    NODE_CLARIFICATION,
    NODE_COMPACTION,
    NODE_DRAFT_CRITIQUE,
    NODE_FOR_EACH_CONFIRM,
    NODE_PLANNER,
    NODE_REACT_CALL_MODEL,
    NODE_REACT_EXECUTE_TOOLS,
    NODE_REACT_FINALIZE,
    NODE_REACT_RECOVERY,
    NODE_REACT_SETUP,
    NODE_REFERENCE_DISAMBIGUATION,
    NODE_RESPONSE,
    NODE_ROUTER,
    NODE_SEMANTIC_VALIDATOR,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_PLAN_REJECTION_REASON,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.context import get_tool_context_store
from src.domains.agents.context.runtime_context import LiaRuntimeContext
from src.domains.agents.effects.decisions import note_route

# Phase 2.1.6 - SubGraph Callback Propagation Fix
from src.domains.agents.graphs.base_agent_builder import (
    create_agent_wrapper_node as build_agent_wrapper,
)
from src.domains.agents.models import MessagesState
from src.domains.agents.nodes import (
    approval_gate_node,
    clarification_node,
    compaction_node,
    planner_node,
    response_node,
    router_node,
    semantic_validator_node,
    task_orchestrator_node,
)
from src.domains.agents.nodes.for_each_confirm_node import for_each_confirm_node
from src.domains.agents.nodes.hitl_dispatch_node import hitl_dispatch_node
from src.domains.agents.nodes.initiative_recurrence import initiative_node
from src.domains.agents.nodes.plan_choice import pending_choice, plan_choice_of_turn
from src.domains.agents.nodes.reference_disambiguation_node import (
    asks_which_item,
    reference_disambiguation_node,
)
from src.domains.agents.nodes.routing import (
    route_from_approval_gate,
    route_from_clarification,
    route_from_for_each_confirm,
    route_from_hitl_dispatch,
    route_from_initiative,
    route_from_planner,
    route_from_semantic_validator,
)
from src.domains.agents.orchestration import get_next_agent_from_plan
from src.domains.agents.registry import get_global_registry
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_conditional_edges_total,
    langgraph_node_transitions_total,
)

logger = get_logger(__name__)


def route_from_router(state: MessagesState) -> str:
    """
    Conditional routing from router node with tiered confidence handling.

    Routes based on detected intention and confidence level:
    - High confidence (≥ router_confidence_high): Direct routing, optimal path
    - Medium confidence (≥ router_confidence_medium): Route with enhanced logging
    - Low confidence (≥ router_confidence_low): Route with low-confidence flag
    - Very low confidence (< router_confidence_low): Fallback to response node

    Phase 6 - Binary Simplification:
    - Router uses binary classification: actionable vs conversational
    - ALL actionable tasks route to planner (simple OR complex)
    - Planner generates ExecutionPlan (1-step simple OR multi-step complex)
    - task_orchestrator executes plans (removed from router options)

    Routing options (binary):
    - "planner": ALL actionable tasks → planner generates ExecutionPlan
      (``react_setup`` in the ReAct execution mode)
    - "response": Conversation or very low confidence → direct response

    An actionable turn whose words fit several shown items first asks which
    one (``reference_disambiguation``, ADR-367); the recorded route stays the
    planning node.

    Legacy compatibility:
    - If old Router prompt returns "task_orchestrator", redirects to "planner"

    Args:
        state: Current LangGraph state with routing_history.

    Returns:
        Next node name ("planner", "react_setup", "reference_disambiguation"
        or "response").
    """
    # NOTE: router_confidence_tier_counter removed (redundant with router_decisions_total)
    # Router confidence is now tracked in router_node.py via router_decisions_total
    routing_history = state.get(STATE_KEY_ROUTING_HISTORY, [])

    if not routing_history:
        logger.warning("route_from_router_no_history_fallback_response")
        # NOTE: Confidence tracking done in router_node.py
        return NODE_RESPONSE

    router_output = routing_history[-1]
    intention = router_output.intention
    confidence = router_output.confidence
    next_node = router_output.next_node

    # Determine confidence tier based on settings
    if confidence >= settings.router_confidence_high:
        tier = "high"
        logger.info(
            "router_high_confidence",
            intention=intention,
            confidence=confidence,
            next_node=next_node,
            threshold=settings.router_confidence_high,
        )
    elif confidence >= settings.router_confidence_medium:
        tier = "medium"
        logger.info(
            "router_medium_confidence",
            intention=intention,
            confidence=confidence,
            next_node=next_node,
            threshold_medium=settings.router_confidence_medium,
            threshold_high=settings.router_confidence_high,
        )
    elif confidence >= settings.router_confidence_low:
        tier = "low"
        logger.warning(
            "router_low_confidence",
            intention=intention,
            confidence=confidence,
            next_node=next_node,
            threshold_low=settings.router_confidence_low,
            threshold_medium=settings.router_confidence_medium,
        )
        # NOTE: a former `state["low_confidence_routing"] = True` mutation was
        # removed here — routing functions cannot write state updates in
        # LangGraph (only node returns are applied), the key was never
        # declared in MessagesState nor read anywhere: dead AND inoperative.
    else:
        # Very low confidence: fallback to response node regardless of intention
        tier = "very_low"
        logger.error(
            "router_very_low_confidence_fallback",
            intention=intention,
            confidence=confidence,
            next_node=next_node,
            threshold_low=settings.router_confidence_low,
            attempted_route=next_node,
        )
        # NOTE: Confidence tracking done in router_node.py
        return NODE_RESPONSE  # Safe fallback

    # NOTE: Confidence tier tracking removed (redundant with router_decisions_total in router_node.py)

    # Phase 6: Binary routing - Router LLM returns "planner" or "response" only
    # Safety: If old prompt version returns "task_orchestrator", redirect to planner
    if next_node == NODE_TASK_ORCHESTRATOR:
        logger.warning(
            "route_from_router_legacy_orchestrator_redirect",
            intention=intention,
            confidence=confidence,
            original_next_node=next_node,
            redirected_to=NODE_PLANNER,
            message="Router v6 binary mode: redirecting task_orchestrator → planner",
        )
        next_node = NODE_PLANNER

    # ADR-070: ReAct execution mode — route to react_setup instead of planner
    if next_node == NODE_PLANNER:
        next_node = _planning_node(state)
        if next_node == NODE_REACT_SETUP:
            logger.info(
                "route_from_router_react_mode",
                intention=intention,
                confidence=confidence,
            )

    # ADR-263 lot 6: the ONE chokepoint where the turn's route is decided —
    # pipeline and ReAct both leave through here. Recording it anywhere else
    # would be a second reading of the same decision. A question asked first
    # (ADR-367) is a step on that route, not another one.
    note_route(next_node)
    # ADR-367: several shown items fit the person's words — ask which, first.
    if next_node != NODE_RESPONSE and asks_which_item(state):
        next_node = NODE_REFERENCE_DISAMBIGUATION

    logger.debug(
        "route_from_router",
        intention=intention,
        confidence=confidence,
        confidence_tier=tier,
        next_node=next_node,
    )

    # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
    langgraph_conditional_edges_total.labels(
        edge_name="route_from_router",
        decision=next_node,
    ).inc()

    # Track node transition
    langgraph_node_transitions_total.labels(
        from_node=NODE_ROUTER,
        to_node=next_node,
    ).inc()

    return next_node


def _planning_node(state: MessagesState) -> str:
    """Where an actionable turn is planned: the ReAct loop or the planner (ADR-070)."""
    if state.get("execution_mode", "pipeline") == "react" and settings.react_agent_enabled:
        return NODE_REACT_SETUP
    return NODE_PLANNER


def route_from_reference_disambiguation(state: MessagesState) -> str:
    """Route after « which of the items shown did you mean? » (ADR-367).

    Args:
        state: Graph state after the question was answered.

    Returns:
        The response when the person declined to choose — nothing is done —
        else the planning node of the turn's execution mode; for a plan's
        choice, the orchestrator, which resumes the plan — on the chosen item, or
        without the act nobody chose an item for.
    """
    if plan_choice_of_turn(state) is not None:
        next_node = NODE_TASK_ORCHESTRATOR
    elif state.get(STATE_KEY_PLAN_REJECTION_REASON):
        next_node = NODE_RESPONSE
    else:
        next_node = _planning_node(state)
    langgraph_node_transitions_total.labels(
        from_node=NODE_REFERENCE_DISAMBIGUATION,
        to_node=next_node,
    ).inc()
    return next_node


def route_from_orchestrator(state: MessagesState) -> str:
    """
    Conditional routing from task_orchestrator node.

    Routes to next agent in orchestration plan, or to response if all agents done.

    Version 1 (Legacy): Sequential execution - returns first unexecuted agent.
    Version 2 (Phase 5.2B-asyncio - CURRENT): Asyncio parallel execution.
        - task_orchestrator executes plan and populates agent_results
        - Always route to response (or next agent for legacy mode)

    LOT 6 - Draft Critique Flow:
        - If pending_draft_critique exists, route to draft_critique node
        - draft_critique uses interrupt() for HITL (confirm/edit/cancel)
        - After user decision, routes back to response

    Args:
        state: Current LangGraph state with orchestration_plan and agent_results.

    Returns:
        Next node name (agent name, "draft_critique", or "response").
    """
    # Replay-safe FOR_EACH HITL (2026-07): the orchestrator persisted the
    # pre-executed context and expects the dedicated confirmation node to run
    # (one interrupt per node execution). An approved ctx never routes here —
    # the confirm node routes straight back to the orchestrator.
    # ADR-367 amendment: the plan would act on the first of several items a
    # lookup found — the person is asked which one before anything acts.
    if pending_choice(state) is not None:
        langgraph_node_transitions_total.labels(
            from_node=NODE_TASK_ORCHESTRATOR,
            to_node=NODE_REFERENCE_DISAMBIGUATION,
        ).inc()
        return NODE_REFERENCE_DISAMBIGUATION

    for_each_ctx = state.get("for_each_hitl_ctx")
    if isinstance(for_each_ctx, dict) and not for_each_ctx.get("approved"):
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_orchestrator",
            decision=NODE_FOR_EACH_CONFIRM,
        ).inc()
        langgraph_node_transitions_total.labels(
            from_node=NODE_TASK_ORCHESTRATOR,
            to_node=NODE_FOR_EACH_CONFIRM,
        ).inc()
        return NODE_FOR_EACH_CONFIRM

    # LOT 6+ HITL Dispatch: Check for ANY pending HITL request
    # Routes to hitl_dispatch_node which handles:
    # - pending_draft_critique (email/event/contact drafts)
    # - pending_tool_confirmation (tools without drafts needing approval)
    pending_draft = state.get("pending_draft_critique")
    pending_confirmation = state.get("pending_tool_confirmation")

    if pending_draft or pending_confirmation:
        # Determine which HITL type for logging
        hitl_type = "draft_critique" if pending_draft else "tool_confirmation"
        hitl_data = pending_draft or pending_confirmation

        logger.info(
            "route_from_orchestrator_to_hitl_dispatch",
            hitl_type=hitl_type,
            draft_id=hitl_data.get("draft_id") if isinstance(hitl_data, dict) else None,
            draft_type=hitl_data.get("draft_type") if isinstance(hitl_data, dict) else None,
        )

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_orchestrator",
            decision=NODE_DRAFT_CRITIQUE,  # Keep label for backward compatibility
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_TASK_ORCHESTRATOR,
            to_node=NODE_DRAFT_CRITIQUE,  # Keep label for backward compatibility
        ).inc()

        return NODE_DRAFT_CRITIQUE

    # Phase 5.2B-asyncio: task_orchestrator handles execution internally
    # No need to check execution_plan - if it was used, agent_results are already populated
    # Just route to next agent (legacy) or response

    # Legacy: Get next agent from plan
    next_agent = get_next_agent_from_plan(state)

    if not next_agent:
        # All agents executed or no plan → initiative evaluates results (ADR-062)
        logger.debug("route_from_orchestrator_to_initiative")

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_orchestrator",
            decision=NODE_INITIATIVE,
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_TASK_ORCHESTRATOR,
            to_node=NODE_INITIATIVE,
        ).inc()

        return NODE_INITIATIVE

    logger.debug(
        "route_from_orchestrator_to_agent",
        next_agent=next_agent,
    )

    # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
    langgraph_conditional_edges_total.labels(
        edge_name="route_from_orchestrator",
        decision=next_agent,
    ).inc()

    # Track node transition
    langgraph_node_transitions_total.labels(
        from_node=NODE_TASK_ORCHESTRATOR,
        to_node=next_agent,
    ).inc()

    return next_agent


# Phase 2.1.6 - SubGraph Callback Propagation Fix
# REMOVED: Local create_agent_wrapper_node() function (was lines 218-301)
# Reason: This wrapper did NOT propagate callbacks to subgraph LLM calls,
#         causing 65% of tokens to be missing from DB (contact_agent subgraph).
# Replaced with: base_agent_builder.create_agent_wrapper_node() which includes
#                full callback propagation via merged_config pattern.
# See: CORRECTIONS_BREAKTHROUGH_V5.md for complete analysis


async def build_graph(
    config: Settings | None = None, checkpointer: Any = None
) -> tuple[CompiledStateGraph[MessagesState, LiaRuntimeContext, MessagesState, MessagesState], Any]:
    """
    Factory function to build LangGraph StateGraph.

    Args:
        config: Optional Settings instance. Defaults to global settings.
        checkpointer: Optional checkpointer for state persistence (AsyncPostgresSaver).
                     If provided, overrides registry's checkpointer for this graph.
                     Typically left None to use the global registry's checkpointer.

    Returns:
        Tuple of (CompiledStateGraph, AsyncPostgresStore):
            - graph: Compiled StateGraph ready for execution
            - store: AsyncPostgresStore instance for persistent contextual references

    Example:
        >>> # Registry configured at startup (main.py)
        >>> registry = AgentRegistry(checkpointer=checkpointer, store=store)
        >>> registry.register_agent("query_agent", build_query_agent)
        >>> set_global_registry(registry)
        >>>
        >>> # Build graph (uses registry's checkpointer/store)
        >>> graph, store = build_graph()
        >>> result = await graph.ainvoke(
        ...     initial_state,
        ...     config=RunnableConfig(configurable={"thread_id": "123"})
        ... )

    Graph Structure (Phase 5.2B-asyncio + Phase 2 OPTIMPLAN + LOT 6 Draft Critique + F4 Compaction):
        Entry: compaction → router (compaction is pass-through when not needed)

        Complex queries (asyncio parallel with semantic validation):
            compaction → router → planner → semantic_validator
                              ↓ (if requires_clarification)
                              ↓ clarification → (needs_replan) → planner
                              ↓ (if valid OR max_iterations)
                              ↓ approval_gate → task_orchestrator
                              ↓ execute_plan_parallel() (asyncio.gather)
                              ↓ completed_steps + agent_results
                              ↓ (if pending_draft_critique)
                              ↓ draft_critique → (interrupt for HITL)
                              → response → END

        Draft Critique Flow (LOT 6 - requires_confirmation tools):
            task_orchestrator → draft_critique → response
            - Tools return requires_confirmation=True in tool_metadata
            - parallel_executor extracts draft info from registry_updates
            - task_orchestrator sets pending_draft_critique in state
            - draft_critique uses interrupt() for HITL (confirm/edit/cancel)
            - After user decision, routes to response for synthesis

        Conversation:
            compaction → router → response → END

        Clarification Feedback Loop (Phase 2 OPTIMPLAN):
            - Max iterations: configurable via PLANNER_MAX_REPLANS (default: 2)
            - Protection: After max iterations, bypass clarification → approval_gate
            - planner_iteration counter prevents infinite loops

        Note: task_orchestrator executes ExecutionPlan internally using asyncio.
        No Send() or Command patterns - true Python-native parallelism.

    Persistence:
        - Checkpointer from global registry enables state persistence
        - State is saved after each node execution
        - Checkpoints retrieved via thread_id in RunnableConfig
        - Enables conversation continuity across sessions

    Agent Registry Pattern:
        - Agents obtained via get_global_registry().get_agent(name)
        - Lazy initialization (built on first access)
        - Automatic dependency injection (checkpointer, store)
        - A compiled agent registers in startup/agents.py and gets its node here; a domain
          is its manifests and calls its tools from the plan (ADR-371)
    """
    logger.info(
        "building_graph",
        checkpoint_enabled=checkpointer is not None,
    )

    # ✅ Get tool context store BEFORE compiling the graph
    # The store is injected at graph.compile(store=store) level
    # This enables InjectedStore in all tools (context_tools, google_contacts_tools)
    store = await get_tool_context_store()

    # Initialize StateGraph with MessagesState schema
    graph = StateGraph(MessagesState, context_schema=LiaRuntimeContext)

    # ✅ Create agent wrapper nodes using generic factory pattern
    # Agents are obtained from the global registry with automatic dependency injection
    # (checkpointer, store) configured at application startup in main.py
    #
    # Benefits of the registry pattern:
    # - Decouples agent registration from graph building
    # - Enables easy addition of new agents without modifying this file
    # - Centralizes dependency management (checkpointer, store)
    # - Improves testability (can mock registry for tests)
    # - Lazy initialization (agents built only when first used)
    #
    # The wrapper node pattern (vs. direct subgraph addition) enables:
    # - Clean state management (results stored in agent_results)
    # - Proper interrupt bubbling from agent middleware to parent graph
    # - Correct Command(resume=...) handling
    # - Isolation of agent concerns from parent graph logic
    #
    # Reference: https://langchain-ai.github.io/langgraph/how-tos/human_in_the_loop/

    # Add nodes
    # F4: Compaction node runs before router to summarize long conversation histories
    graph.add_node(NODE_COMPACTION, compaction_node)
    graph.add_node(NODE_ROUTER, router_node)
    graph.add_node(NODE_PLANNER, planner_node)  # Phase 5: LLM-based plan generation
    graph.add_node(
        NODE_SEMANTIC_VALIDATOR, semantic_validator_node
    )  # Phase 2 OPTIMPLAN: Semantic validation
    graph.add_node(NODE_CLARIFICATION, clarification_node)  # Phase 2 OPTIMPLAN: Clarification HITL
    graph.add_node(NODE_APPROVAL_GATE, approval_gate_node)  # Phase 8: Plan-level HITL
    graph.add_node(NODE_TASK_ORCHESTRATOR, task_orchestrator_node)
    graph.add_node(NODE_DRAFT_CRITIQUE, hitl_dispatch_node)  # LOT 6+: Generic HITL dispatch
    # ADR-367: « which of the items shown did you mean? », before planning.
    graph.add_node(NODE_REFERENCE_DISAMBIGUATION, reference_disambiguation_node)

    # ✅ Add agent nodes dynamically from registry
    # Phase 2.1.6 - SubGraph Callback Propagation Fix
    # Use base_agent_builder's create_agent_wrapper_node with full callback propagation
    # This ensures TokenTrackingCallback, LangFuseHandler, and MetricsCallback
    # propagate to all LLM calls inside the agent subgraphs (ReAct loop)
    # NAMING: domain=entity(singular), agent=domain+"_agent"
    registry_for_wrapper = get_global_registry()

    # Browser agent (F7 - auto-detected, registered if Playwright available)
    _browser_registered = False
    # Browser agent not registered (Playwright not installed)
    with suppress(Exception):
        browser_agent_runnable = registry_for_wrapper.get_agent("browser_agent")
        browser_agent_node = build_agent_wrapper(
            agent_runnable=browser_agent_runnable,
            agent_name="browser_agent",
            agent_constant=AGENT_BROWSER,
        )
        graph.add_node(AGENT_BROWSER, browser_agent_node)
        _browser_registered = True

    graph.add_node(NODE_RESPONSE, response_node)

    # Set entry point: compaction runs first, then unconditionally routes to router
    # F4: Compaction node is a pass-through when no compaction is needed (returns {})
    graph.set_entry_point(NODE_COMPACTION)
    graph.add_edge(NODE_COMPACTION, NODE_ROUTER)

    # Conditional routing from router (Phase 6 - Binary Simplification)
    # Router routes to:
    # - planner: ALL actionable tasks (simple OR complex) → planner generates ExecutionPlan
    # - response: Conversation or very low confidence
    #
    # REMOVED: Direct Router → task_orchestrator route (was ambiguous)
    # NOW: ALL actionable queries go through planner (generates 1-step OR multi-step plans)
    graph.add_conditional_edges(
        NODE_ROUTER,
        route_from_router,
        {
            NODE_PLANNER: NODE_PLANNER,
            NODE_REACT_SETUP: NODE_REACT_SETUP,  # ADR-070: ReAct execution mode
            NODE_RESPONSE: NODE_RESPONSE,
            NODE_REFERENCE_DISAMBIGUATION: NODE_REFERENCE_DISAMBIGUATION,  # ADR-367
        },
    )
    graph.add_conditional_edges(
        NODE_REFERENCE_DISAMBIGUATION,
        route_from_reference_disambiguation,
        {
            NODE_PLANNER: NODE_PLANNER,
            NODE_REACT_SETUP: NODE_REACT_SETUP,
            NODE_RESPONSE: NODE_RESPONSE,
            NODE_TASK_ORCHESTRATOR: NODE_TASK_ORCHESTRATOR,  # a plan's choice resumes it
        },
    )

    # Planner routes conditionally based on HITL requirements (Phase 8)
    # Phase 2 OPTIMPLAN: Added semantic_validator in the flow
    # If plan requires approval → semantic_validator (for validation before approval)
    # Otherwise → task_orchestrator (direct execution, no HITL)
    # 2026-01: Added response fallback for empty plans (conversational queries that
    # slipped through routing, or queries with no applicable tools)
    graph.add_conditional_edges(
        NODE_PLANNER,
        route_from_planner,
        {
            "approval_gate": NODE_SEMANTIC_VALIDATOR,  # Phase 2: Validate BEFORE approval
            "task_orchestrator": NODE_TASK_ORCHESTRATOR,
            "response": NODE_RESPONSE,  # Fallback for empty plans (0 steps)
        },
    )

    # Semantic validator routes based on validation result (Phase 2 OPTIMPLAN)
    # If requires_clarification=True → clarification (HITL interrupt)
    # If needs_replan=True (after clarification) → planner (regenerate)
    # If max_iterations reached → approval_gate (bypass clarification)
    # Otherwise → approval_gate (validation OK)
    graph.add_conditional_edges(
        NODE_SEMANTIC_VALIDATOR,
        route_from_semantic_validator,
        {
            "clarification": NODE_CLARIFICATION,
            "planner": NODE_PLANNER,  # Feedback loop for clarification
            "approval_gate": NODE_APPROVAL_GATE,
        },
    )

    # Clarification routes back to semantic_validator after user response
    # (Phase 2 OPTIMPLAN feedback loop: planner → validator → clarification →
    # validator → …), EXCEPT when the user cancelled during clarification —
    # the abort exits straight to response (Lot 1 Phase 0: without this exit
    # a cancel intent looped forever through replanning).
    graph.add_conditional_edges(
        NODE_CLARIFICATION,
        route_from_clarification,
        {
            "semantic_validator": NODE_SEMANTIC_VALIDATOR,
            "response": NODE_RESPONSE,
        },
    )

    # Approval gate routes based on user decision
    # If approved → task_orchestrator (execute plan)
    # If REPLAN → planner (regenerate plan with new instructions)
    # If rejected → response (explain rejection)
    graph.add_conditional_edges(
        NODE_APPROVAL_GATE,
        route_from_approval_gate,
        {
            "task_orchestrator": NODE_TASK_ORCHESTRATOR,
            "planner": NODE_PLANNER,  # REPLAN: regenerate plan with user instructions
            "response": NODE_RESPONSE,
        },
    )

    # Conditional routing from task_orchestrator
    # Routes to:
    # - draft_critique: If pending_draft_critique exists (LOT 6: requires_confirmation tools)
    # - next agent: Legacy routing for simple plans
    # - response: If all agents done or execution_plan completed (Phase 5.2B-asyncio)
    graph.add_conditional_edges(
        NODE_TASK_ORCHESTRATOR,
        route_from_orchestrator,
        {
            NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE,  # LOT 6: Draft HITL
            NODE_FOR_EACH_CONFIRM: NODE_FOR_EACH_CONFIRM,  # 2026-07: replay-safe bulk HITL
            NODE_REFERENCE_DISAMBIGUATION: NODE_REFERENCE_DISAMBIGUATION,  # ADR-367 amendment
            # Browser agent (F7 - conditional)
            **({AGENT_BROWSER: AGENT_BROWSER} if _browser_registered else {}),
            # Terminal → initiative evaluation (ADR-062)
            NODE_INITIATIVE: NODE_INITIATIVE,
        },
    )

    # LOT 6: Draft critique goes to initiative for post-execution evaluation (ADR-062).
    # 2026-07 (replay-safe EDIT loop): the edge is conditional — while a draft
    # critique is still pending (edit/replan/clarify decisions), the node
    # self-loops so each interrupt runs in its OWN node execution and the
    # modified draft is checkpointed before the next one. Terminal decisions
    # route to initiative exactly like the historical fixed edge.
    graph.add_conditional_edges(
        NODE_DRAFT_CRITIQUE,
        route_from_hitl_dispatch,
        {
            NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE,  # Self-loop: draft still pending
            NODE_TASK_ORCHESTRATOR: NODE_TASK_ORCHESTRATOR,  # Spec D7: waiting steps resume
            NODE_INITIATIVE: NODE_INITIATIVE,  # Done: proceed to initiative
        },
    )

    # 2026-07: Replay-safe FOR_EACH bulk-confirmation node. The orchestrator
    # persists the pre-executed context and routes here; one interrupt per
    # node execution (approve → back to orchestrator; edit → self-loop with
    # the filtered list checkpointed; cancel → initiative, the historical
    # terminal destination of the in-orchestrator cancel).
    graph.add_node(NODE_FOR_EACH_CONFIRM, for_each_confirm_node)
    graph.add_conditional_edges(
        NODE_FOR_EACH_CONFIRM,
        route_from_for_each_confirm,
        {
            NODE_FOR_EACH_CONFIRM: NODE_FOR_EACH_CONFIRM,  # Self-loop after EDIT
            NODE_TASK_ORCHESTRATOR: NODE_TASK_ORCHESTRATOR,  # Approved: resume execution
            NODE_INITIATIVE: NODE_INITIATIVE,  # Cancelled
        },
    )

    # The browser agent goes to initiative for post-execution evaluation (ADR-062)
    if _browser_registered:
        graph.add_edge(AGENT_BROWSER, NODE_INITIATIVE)

    # ADR-062: Initiative node evaluates results, optionally executes read-only
    # actions, then routes to response. Pass-through when feature flag is off.
    graph.add_node(NODE_INITIATIVE, initiative_node)
    graph.add_conditional_edges(
        NODE_INITIATIVE,
        route_from_initiative,
        {
            NODE_INITIATIVE: NODE_INITIATIVE,  # Loop: re-evaluate after actions
            NODE_RESPONSE: NODE_RESPONSE,  # Done: proceed to synthesis
        },
    )

    # ========================================================================
    # ADR-070: ReAct Execution Mode — Custom loop in parent graph
    # ========================================================================
    from src.domains.agents.nodes.react_nodes import (
        react_call_model_node,
        react_execute_tools_node,
        react_finalize_node,
        react_setup_node,
    )
    from src.domains.agents.nodes.react_recovery import react_recovery_node
    from src.domains.agents.nodes.routing import (
        route_from_react_call_model,
        route_from_react_execute_tools,
        route_from_react_finalize,
    )

    graph.add_node(NODE_REACT_SETUP, react_setup_node)
    graph.add_node(NODE_REACT_CALL_MODEL, react_call_model_node)
    graph.add_node(NODE_REACT_EXECUTE_TOOLS, react_execute_tools_node)
    graph.add_node(NODE_REACT_FINALIZE, react_finalize_node)
    graph.add_node(NODE_REACT_RECOVERY, react_recovery_node)

    # ReAct flow: setup → call_model ←→ execute_tools → finalize → response
    #   call_model → recovery → call_model when a final answer declares facts it
    #   could not obtain and a pass is left (ADR-310).
    #   execute_tools → hitl_dispatch (draft_critique) when a mutation tool
    #   prepared a draft requiring confirmation (parity with the pipeline flow).
    graph.add_edge(NODE_REACT_SETUP, NODE_REACT_CALL_MODEL)
    graph.add_conditional_edges(
        NODE_REACT_CALL_MODEL,
        route_from_react_call_model,
        {
            NODE_REACT_EXECUTE_TOOLS: NODE_REACT_EXECUTE_TOOLS,
            NODE_REACT_FINALIZE: NODE_REACT_FINALIZE,
            NODE_REACT_RECOVERY: NODE_REACT_RECOVERY,
        },
    )
    graph.add_edge(NODE_REACT_RECOVERY, NODE_REACT_CALL_MODEL)
    # Draft confirmation handoff vs. normal loop-back to the model.
    graph.add_conditional_edges(
        NODE_REACT_EXECUTE_TOOLS,
        route_from_react_execute_tools,
        {
            NODE_REACT_EXECUTE_TOOLS: NODE_REACT_EXECUTE_TOOLS,  # Checkpoint each safe segment
            NODE_REACT_FINALIZE: NODE_REACT_FINALIZE,  # Budget exhausted between segments
            NODE_REACT_CALL_MODEL: NODE_REACT_CALL_MODEL,  # Loop back (no draft)
            NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE,  # Draft → shared HITL dispatch
        },
    )
    # ADR-070 + ADR-062: nominal ReAct path may pass through Initiative for proactive
    # read-only enrichment (gated by INITIATIVE_REACT_ENABLED). The draft path keeps
    # its own independent edge into NODE_INITIATIVE, so this does not affect drafts.
    graph.add_conditional_edges(
        NODE_REACT_FINALIZE,
        route_from_react_finalize,
        {NODE_INITIATIVE: NODE_INITIATIVE, NODE_RESPONSE: NODE_RESPONSE},
    )

    # Response is terminal
    graph.add_edge(NODE_RESPONSE, END)

    # ✅ Get checkpointer from registry if not provided
    # This enables using the global registry's checkpointer configured at startup
    if checkpointer is None:
        registry = get_global_registry()
        checkpointer = registry._checkpointer
        logger.debug(
            "using_registry_checkpointer",
            has_checkpointer=checkpointer is not None,
        )

    logger.info(
        "graph_built_successfully",
        version="v1_sequential",
        checkpoint_enabled=checkpointer is not None,
        using_agent_registry=True,
    )

    # ✅ Compile parent graph with both checkpointer AND store
    # - checkpointer: PostgresSaver for persistent state + HITL interrupts
    #   (from global registry if not explicitly provided)
    # - store: Enables InjectedStore in all tools (no need to pass in config)
    # The store is compiled into the graph, not passed at invocation time
    #
    # NOTE: recursion_limit must be passed at invocation time (ainvoke/astream),
    # not at compile time. It's part of RunnableConfig, not compile kwargs.
    # See service.py where we pass recursion_limit in the config dict.
    #
    # Phase 6 - LLM Observability: Langfuse Tracing Pattern (2025)
    #
    # ❌ DO NOT apply callbacks at compilation time via .with_config()
    # ✅ INSTEAD: Pass callbacks at invocation time via RunnableConfig
    #
    # Reason: Langfuse CallbackHandler must receive request-specific context
    # (session_id, user_id, metadata) which is only available at invocation.
    # Applying callbacks here would create a global handler without context.
    #
    # Current Implementation (CORRECT):
    #   service.py uses create_instrumented_config() to build RunnableConfig
    #   with callbacks + metadata, then passes to graph.astream(config=...)
    #
    # This ensures:
    #   - All nodes inherit callbacks via LangGraph's config propagation
    #   - Tools and sub-graphs automatically traced
    #   - Session-specific metadata correctly attached
    #   - No manual instrumentation needed in node functions
    #
    # References:
    #   - https://langfuse.com/docs/integrations/langchain/example-langgraph-agents
    #   - "Pass callbacks during graph invocation using config={'callbacks': [handler]}"
    compiled_graph = graph.compile(
        checkpointer=checkpointer,
        store=store,
    )
    return compiled_graph, store
