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

from typing import Any

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.core.config import Settings, settings
from src.domains.agents.constants import (
    # Agent constants (v3.2 convention: singular domain names)
    AGENT_CONTACT,
    AGENT_EMAIL,
    AGENT_EVENT,
    AGENT_FILE,
    AGENT_PERPLEXITY,
    AGENT_PLACE,
    AGENT_ROUTE,
    AGENT_TASK,
    AGENT_WEATHER,
    AGENT_WIKIPEDIA,
    NODE_APPROVAL_GATE,
    NODE_CLARIFICATION,
    NODE_COMPACTION,
    NODE_DRAFT_CRITIQUE,
    NODE_PLANNER,
    NODE_RESPONSE,
    NODE_ROUTER,
    NODE_SEMANTIC_VALIDATOR,
    NODE_TASK_ORCHESTRATOR,
    STATE_KEY_MESSAGES,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.context import get_tool_context_store

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
from src.domains.agents.nodes.hitl_dispatch_node import hitl_dispatch_node
from src.domains.agents.nodes.routing import (
    route_from_approval_gate,
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
    - "response": Conversation or very low confidence → direct response

    Legacy compatibility:
    - If old Router prompt returns "task_orchestrator", redirects to "planner"

    Args:
        state: Current LangGraph state with routing_history.

    Returns:
        Next node name ("planner" or "response").
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
        logger.warning(
            "router_medium_confidence",
            intention=intention,
            confidence=confidence,
            next_node=next_node,
            threshold_medium=settings.router_confidence_medium,
            threshold_high=settings.router_confidence_high,
            input_preview=str(
                state.get(STATE_KEY_MESSAGES, [])[-1].content
                if state.get(STATE_KEY_MESSAGES)
                else ""
            )[:100],
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
        # Mark state for potential review or additional validation
        # Type ignore: low_confidence_routing is a dynamic flag, not in MessagesState schema
        state["low_confidence_routing"] = True
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
    # LOT 6+ HITL Dispatch: Check for ANY pending HITL request
    # Routes to hitl_dispatch_node which handles:
    # - pending_draft_critique (email/event/contact drafts)
    # - pending_entity_disambiguation (multiple entity matches)
    # - pending_tool_confirmation (tools without drafts needing approval)
    pending_draft = state.get("pending_draft_critique")
    pending_disambiguation = state.get("pending_entity_disambiguation")
    pending_confirmation = state.get("pending_tool_confirmation")

    if pending_draft or pending_disambiguation or pending_confirmation:
        # Determine which HITL type for logging
        hitl_type = (
            "draft_critique"
            if pending_draft
            else ("entity_disambiguation" if pending_disambiguation else "tool_confirmation")
        )
        hitl_data = pending_draft or pending_disambiguation or pending_confirmation

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
        # All agents executed or no plan → go to response for synthesis
        logger.debug("route_from_orchestrator_to_response")

        # PHASE 2.5 - LangGraph Observability: Track conditional edge decision
        langgraph_conditional_edges_total.labels(
            edge_name="route_from_orchestrator",
            decision=NODE_RESPONSE,
        ).inc()

        # Track node transition
        langgraph_node_transitions_total.labels(
            from_node=NODE_TASK_ORCHESTRATOR,
            to_node=NODE_RESPONSE,
        ).inc()

        return NODE_RESPONSE

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
) -> tuple[CompiledStateGraph, Any]:
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
        >>> registry.register_agent("contact_agent", build_contacts_agent)
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

        Simple queries (legacy):
            compaction → router → task_orchestrator → contact_agent → response → END

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
        - Easy to add new agents (register in main.py, add node here)
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
    graph = StateGraph(MessagesState)

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

    # ✅ Add agent nodes dynamically from registry
    # Phase 2.1.6 - SubGraph Callback Propagation Fix
    # Use base_agent_builder's create_agent_wrapper_node with full callback propagation
    # This ensures TokenTrackingCallback, LangFuseHandler, and MetricsCallback
    # propagate to all LLM calls inside the agent subgraphs (ReAct loop)
    # NAMING: domain=entity(singular), agent=domain+"_agent"
    registry_for_wrapper = get_global_registry()

    # Contact agent
    contact_agent_runnable = registry_for_wrapper.get_agent("contact_agent")
    contact_agent_node = build_agent_wrapper(
        agent_runnable=contact_agent_runnable,
        agent_name="contact_agent",
        agent_constant=AGENT_CONTACT,
    )
    graph.add_node(AGENT_CONTACT, contact_agent_node)

    # Email agent
    email_agent_runnable = registry_for_wrapper.get_agent("email_agent")
    email_agent_node = build_agent_wrapper(
        agent_runnable=email_agent_runnable,
        agent_name="email_agent",
        agent_constant=AGENT_EMAIL,
    )
    graph.add_node(AGENT_EMAIL, email_agent_node)

    # Event agent (Google Calendar)
    event_agent_runnable = registry_for_wrapper.get_agent("event_agent")
    event_agent_node = build_agent_wrapper(
        agent_runnable=event_agent_runnable,
        agent_name="event_agent",
        agent_constant=AGENT_EVENT,
    )
    graph.add_node(AGENT_EVENT, event_agent_node)

    # File agent (Google Drive)
    file_agent_runnable = registry_for_wrapper.get_agent("file_agent")
    file_agent_node = build_agent_wrapper(
        agent_runnable=file_agent_runnable,
        agent_name="file_agent",
        agent_constant=AGENT_FILE,
    )
    graph.add_node(AGENT_FILE, file_agent_node)

    # Task agent (Google Tasks)
    task_agent_runnable = registry_for_wrapper.get_agent("task_agent")
    task_agent_node = build_agent_wrapper(
        agent_runnable=task_agent_runnable,
        agent_name="task_agent",
        agent_constant=AGENT_TASK,
    )
    graph.add_node(AGENT_TASK, task_agent_node)

    # Weather agent
    weather_agent_runnable = registry_for_wrapper.get_agent("weather_agent")
    weather_agent_node = build_agent_wrapper(
        agent_runnable=weather_agent_runnable,
        agent_name="weather_agent",
        agent_constant=AGENT_WEATHER,
    )
    graph.add_node(AGENT_WEATHER, weather_agent_node)

    # Wikipedia agent
    wikipedia_agent_runnable = registry_for_wrapper.get_agent("wikipedia_agent")
    wikipedia_agent_node = build_agent_wrapper(
        agent_runnable=wikipedia_agent_runnable,
        agent_name="wikipedia_agent",
        agent_constant=AGENT_WIKIPEDIA,
    )
    graph.add_node(AGENT_WIKIPEDIA, wikipedia_agent_node)

    # Perplexity agent
    perplexity_agent_runnable = registry_for_wrapper.get_agent("perplexity_agent")
    perplexity_agent_node = build_agent_wrapper(
        agent_runnable=perplexity_agent_runnable,
        agent_name="perplexity_agent",
        agent_constant=AGENT_PERPLEXITY,
    )
    graph.add_node(AGENT_PERPLEXITY, perplexity_agent_node)

    # Place agent (Google Places)
    place_agent_runnable = registry_for_wrapper.get_agent("place_agent")
    place_agent_node = build_agent_wrapper(
        agent_runnable=place_agent_runnable,
        agent_name="place_agent",
        agent_constant=AGENT_PLACE,
    )
    graph.add_node(AGENT_PLACE, place_agent_node)

    # Route agent (Google Routes)
    route_agent_runnable = registry_for_wrapper.get_agent("route_agent")
    route_agent_node = build_agent_wrapper(
        agent_runnable=route_agent_runnable,
        agent_name="route_agent",
        agent_constant=AGENT_ROUTE,
    )
    graph.add_node(AGENT_ROUTE, route_agent_node)

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
            NODE_RESPONSE: NODE_RESPONSE,
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

    # Clarification routes back to semantic_validator after user response (Phase 2 OPTIMPLAN)
    # This creates the feedback loop: planner → validator → clarification → validator → ...
    # Note: clarification_node sets needs_replan=True which triggers route to planner
    graph.add_edge(NODE_CLARIFICATION, NODE_SEMANTIC_VALIDATOR)

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
            # OAuth agents (Google) - v3.2 naming: singular domain names
            AGENT_CONTACT: AGENT_CONTACT,
            AGENT_EMAIL: AGENT_EMAIL,
            AGENT_EVENT: AGENT_EVENT,
            AGENT_FILE: AGENT_FILE,
            AGENT_TASK: AGENT_TASK,
            # API key agents (global key)
            AGENT_WEATHER: AGENT_WEATHER,
            AGENT_WIKIPEDIA: AGENT_WIKIPEDIA,
            AGENT_PERPLEXITY: AGENT_PERPLEXITY,
            AGENT_PLACE: AGENT_PLACE,
            AGENT_ROUTE: AGENT_ROUTE,  # LOT 12: Google Routes directions
            # Terminal
            NODE_RESPONSE: NODE_RESPONSE,
        },
    )

    # LOT 6: Draft critique always goes to response after user decision
    # The draft_critique_node handles confirm/edit/cancel via interrupt()
    # After processing, results go to response for synthesis
    graph.add_edge(NODE_DRAFT_CRITIQUE, NODE_RESPONSE)

    # All agents go to response for synthesis
    # OAuth agents (Google) - v3.2 naming: singular domain names
    graph.add_edge(AGENT_CONTACT, NODE_RESPONSE)
    graph.add_edge(AGENT_EMAIL, NODE_RESPONSE)
    graph.add_edge(AGENT_EVENT, NODE_RESPONSE)
    graph.add_edge(AGENT_FILE, NODE_RESPONSE)
    graph.add_edge(AGENT_TASK, NODE_RESPONSE)
    # API key agents (global key)
    graph.add_edge(AGENT_WEATHER, NODE_RESPONSE)
    graph.add_edge(AGENT_WIKIPEDIA, NODE_RESPONSE)
    graph.add_edge(AGENT_PERPLEXITY, NODE_RESPONSE)
    graph.add_edge(AGENT_PLACE, NODE_RESPONSE)
    graph.add_edge(AGENT_ROUTE, NODE_RESPONSE)  # LOT 12: Google Routes

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
