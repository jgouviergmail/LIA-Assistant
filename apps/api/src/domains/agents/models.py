"""
Agents domain models.
Defines LangGraph state with message truncation reducer compatible with PostgresCheckpointer.
"""

import uuid
from typing import Annotated, Any, cast

import tiktoken
from langchain_core.messages import BaseMessage, SystemMessage
from langchain_core.messages.utils import trim_messages
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from src.core.config import settings
from src.core.field_names import (
    FIELD_METADATA,
    FIELD_RUN_ID,
    FIELD_SESSION_ID,
    FIELD_USER_ID,
)
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.data_registry.state import merge_registry
from src.domains.agents.utils.message_filters import remove_orphan_tool_messages
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def add_messages_with_truncate(
    left: list[BaseMessage], right: list[BaseMessage]
) -> list[BaseMessage]:
    """
    Reducer function for messages that truncates history by tokens first, then by message count.
    Wraps LangGraph's add_messages to support RemoveMessage, then applies truncation.

    Strategy:
    1. Use add_messages(left, right) to handle RemoveMessage properly (LangGraph v1.0 best practice)
    2. Truncate by tokens (MAX_TOKENS_HISTORY) using tiktoken o200k_base encoding
    3. Fallback: If still too many messages, limit by count (MAX_MESSAGES_HISTORY)
    4. Always preserve SystemMessage at the start
    5. Validate OpenAI message sequence (remove orphan ToolMessages)

    The add_messages wrapper ensures that RemoveMessage(id=...) operations are properly
    handled before truncation, allowing for message replacement in HITL workflows.

    The validation step ensures that truncation doesn't create invalid message sequences
    where a ToolMessage exists without its corresponding AIMessage with tool_calls.
    This prevents OpenAI API errors like:
    "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'"

    Args:
        left: Existing messages in state.
        right: New messages to add (may include RemoveMessage instances).

    Returns:
        Truncated and validated list of messages.

    Note:
        Compatible with PostgresCheckpointer for future state persistence.
        Orphan ToolMessages are logged with WARNING level for observability.
        RemoveMessage support added for LangGraph v1.0 compatibility.
    """
    # Step 0: Use add_messages to properly handle RemoveMessage instances
    # This is the LangGraph v1.0 best practice for message management
    # Ignore type error: add_messages has a very broad input signature
    all_messages_result = add_messages(left, right)  # type: ignore
    # add_messages returns a list, but mypy sees the broad union type
    all_messages = cast(list[BaseMessage], all_messages_result)

    if not all_messages:
        return []

    # Step 1: Truncate by TOKENS first (preserves recent context better)
    try:
        encoding = tiktoken.get_encoding(settings.token_encoding_name)

        def token_counter(messages: list[BaseMessage]) -> int:
            """Count tokens in messages using tiktoken."""
            total = 0
            for m in messages:
                content = m.content
                if isinstance(content, str):
                    total += len(encoding.encode(content))
            return total

        trimmed_result = trim_messages(
            all_messages,
            max_tokens=settings.max_tokens_history,
            strategy="last",  # Keep most recent messages
            token_counter=token_counter,
            include_system=True,  # Always preserve SystemMessage
        )
        # trim_messages returns list[BaseMessage]
        trimmed = trimmed_result

        logger.debug(
            "messages_truncated_by_tokens",
            original_count=len(all_messages),
            truncated_count=len(trimmed),
            max_tokens=settings.max_tokens_history,
        )

    except Exception as e:
        logger.warning(
            "token_truncation_failed_fallback_to_messages",
            error=str(e),
            fallback_max_messages=settings.max_messages_history,
        )
        # Fallback to simple message count limit
        trimmed = all_messages

    # Step 2: Fallback - Limit by MESSAGE COUNT if still too many
    if len(trimmed) > settings.max_messages_history:
        # Keep system messages + recent N messages
        system_msgs = [m for m in trimmed if isinstance(m, SystemMessage)]
        recent_msgs = trimmed[-settings.max_messages_history :]

        # Merge, avoiding duplicates
        final = system_msgs + [m for m in recent_msgs if m not in system_msgs]

        logger.debug(
            "messages_truncated_by_count",
            original_count=len(trimmed),
            final_count=len(final),
            max_messages=settings.max_messages_history,
        )

        # Step 3: Validate OpenAI message sequence (remove orphan ToolMessages)
        validated = remove_orphan_tool_messages(final)
        return validated

    # Step 3: Validate OpenAI message sequence (remove orphan ToolMessages)
    validated = remove_orphan_tool_messages(list(trimmed))
    return validated


class MessagesState(TypedDict):
    """
    LangGraph state for conversational agents.
    Compatible with future PostgresCheckpointer for state persistence.

    Schema Version: 1.0 (introduced 2025-10-27)
    Migration Path:
        - v1.0: Initial schema with turn-based isolation
        - Future v2.0: May add parallel execution support, streaming state, etc.

    Attributes:
        messages: List of conversation messages with automatic truncation reducer.
        metadata: Additional metadata (run_id, user_id, session_id, etc.).
        routing_history: History of router decisions for analysis/debugging.
        agent_results: Results from executed agents (limited to 30 for memory management).
                      Keys format: "turn_id:agent_name" (e.g., "3:contacts_agent").
        orchestration_plan: Current execution plan from TaskOrchestrator (V1: sequential).
        current_turn_id: Counter tracking conversation turns (incremented on each user message).
        user_timezone: User's IANA timezone for temporal context in prompts (e.g., "Europe/Paris").
        user_language: User's language code for localized responses (e.g., "fr", "en").
        oauth_scopes: OAuth scopes from active connectors (e.g., ["https://www.googleapis.com/auth/contacts.readonly"]).
        _schema_version: Schema version for forward/backward compatibility (LangGraph v1.0 best practice).

    Schema Evolution Notes:
        - Always increment _schema_version when adding/removing/renaming fields
        - Write migration functions in models.py for backward compatibility
        - Test migrations with checkpoint recovery scenarios
    """

    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    metadata: dict[str, Any]
    routing_history: list[Any]  # Will be RouterOutput objects
    agent_results: dict[str, Any]  # AgentResult objects - limited to 30 max
    orchestration_plan: Any | None  # OrchestratorPlan object
    execution_plan: Any | None  # ExecutionPlan from planner (Phase 5)
    planner_metadata: dict[str, Any] | None  # Planner metadata for streaming to frontend (Phase 5)
    planner_error: (
        dict[str, Any] | None
    )  # Planner error/warning for streaming to frontend (Phase 5)
    current_turn_id: int  # Conversation turn counter for agent result isolation
    session_id: (
        str  # Session identifier for context isolation (Phase 5 - matches thread_id from config)
    )
    user_timezone: str  # User's IANA timezone (e.g., "Europe/Paris", "America/New_York")
    user_language: str  # User's language code (e.g., "fr", "en", "es", "de", "it")
    personality_instruction: (
        str | None
    )  # LLM personality prompt instruction (from Personality.prompt_instruction)
    oauth_scopes: list[
        str
    ]  # OAuth scopes from active connectors (e.g., ["https://www.googleapis.com/auth/contacts.readonly"])
    _schema_version: str  # Schema version (e.g., "1.0", "1.1", "2.0")

    # Phase 5.2B-asyncio: Parallel execution support (native Python asyncio)
    # completed_steps populated by parallel_executor after asyncio.gather() completes
    completed_steps: dict[str, dict[str, Any]]  # Step results by step_id

    # Phase 8: Plan-level HITL approval support
    validation_result: Any | None  # ValidationResult from planner (contains requires_hitl flag)
    approval_evaluation: Any | None  # ApprovalEvaluation from approval strategies
    plan_approved: bool | None  # Approval gate decision (True = approved, False = rejected)
    plan_rejection_reason: str | None  # Rejection reason if plan_approved = False

    # Phase 2 OPTIMPLAN: Semantic Validation (Issue #60)
    semantic_validation: Any | None  # SemanticValidationResult from semantic_validator_node
    clarification_response: str | None  # User response to clarification question
    clarification_field: str | None  # Field for which clarification was asked (e.g., "subject")
    needs_replan: bool  # Flag to trigger planner regeneration after clarification
    replan_instructions: str | None  # Instructions for planner when replanning (from approval_gate)
    exclude_sub_agent_tools: bool  # F6: Exclude sub-agent tools from catalogue during replan
    planner_iteration: (
        int  # Counter for clarification iterations (max: PLANNER_MAX_REPLANS setting)
    )

    # Phase 5.5: Post-processing streaming support
    # When response_node performs post-processing (e.g., photo HTML injection) after LLM generation,
    # it signals via this field so streaming service can emit a STREAM_REPLACE chunk.
    # This ensures frontend receives the complete post-processed content including photos/media.
    content_final_replacement: str | None  # Full post-processed content to replace streamed tokens

    # Context resolution: Turn-based context management for follow-up questions
    # These fields enable proper context handling when users reference previous results
    # (e.g., "and the second one?", "this one", "give me their contact details")
    last_action_turn_id: int | None  # Last turn that executed agents (for reference resolution)
    turn_type: str | None  # Turn classification: "action" | "reference" | "conversational"
    resolved_context: dict[str, Any] | None  # Resolved context items from reference resolution
    detected_intent: (
        str | None
    )  # Semantic intent from SemanticIntentDetector (action|detail|search|list|full)

    # ==========================================================================
    # Memory-Based Reference Resolution (Pre-Planner)
    # ==========================================================================
    # Resolves relational references ("my brother", "my wife") to concrete entity names
    # BEFORE the planner generates the execution plan. Uses memory facts + LLM micro-call.
    # Structure: ResolvedReferences with original_query, enriched_query, mappings
    # Example: {"my brother": "john doe"} allows natural response phrasing
    resolved_references: (
        dict[str, Any] | None
    )  # ResolvedReferences from memory_reference_resolution_service

    # Data Registry (LIA Adaptive Rendering System): Registry for rich frontend rendering
    # The registry stores complete data items (contacts, emails, events) that are:
    # 1. Sent to frontend via SSE (registry_update event)
    # 2. Referenced by LLM using DSL tags (<View id="..." />, <Ref id="...">)
    # 3. Rendered as rich React components by frontend
    # Registry is merged using the merge_registry reducer (last write wins for same ID)
    registry: Annotated[dict[str, RegistryItem], merge_registry]

    # Current Turn Registry (for streaming/display only)
    # This field stores ONLY items touched in the current turn, WITHOUT merging.
    # Used by streaming_service to emit registry_update with correct items.
    # BugFix 2025-12-31: "detail of the second" was showing 2 contacts instead of 1
    # because registry (with merge_registry reducer) accumulated all items.
    # This field is overwritten each turn (no reducer = simple overwrite semantics).
    current_turn_registry: dict[str, RegistryItem] | None

    # Data Registry LOT 4.3: Draft/Critique HITL support
    # When a registry-enabled tool creates a draft requiring confirmation (requires_confirmation=True),
    # parallel_executor populates pending_draft_critique for draft_critique_node to handle.
    # After user confirms/edits/cancels, draft_action_result contains the decision.
    pending_draft_critique: dict[str, Any] | None  # PendingDraftInfo from parallel_executor
    pending_drafts_queue: list[dict[str, Any]]  # Queue for batch draft confirmation (FOR_EACH)
    draft_action_result: dict[str, Any] | None  # User decision: confirm/edit/cancel with details

    # ==========================================================================
    # HITL Dispatch: Generic Human-in-the-Loop Support
    # ==========================================================================
    # These fields support multiple HITL interaction types beyond draft_critique:
    # - Entity Disambiguation: When search returns multiple matches (3 "Jean" contacts)
    # - Tool Confirmation: When tools without drafts need user approval
    #
    # Priority order: Draft > Disambiguation > Confirmation
    # (Don't confirm an action if we don't know which "Jean" to apply it to)
    #
    # Multi-disambiguation protection: If 2 tools request disambiguation in parallel,
    # they are queued in pending_disambiguations_queue and processed sequentially.

    # Entity Disambiguation (post-search): Multiple entities match a query
    pending_entity_disambiguation: (
        dict[str, Any] | None
    )  # DisambiguationContext from entity resolution
    entity_disambiguation_result: dict[str, Any] | None  # User choice from disambiguation options
    pending_disambiguations_queue: list[dict[str, Any]]  # Queue for multi-disambiguation protection

    # Tool Confirmation (tools without drafts): Explicit user approval for sensitive operations
    pending_tool_confirmation: dict[str, Any] | None  # ToolConfirmationContext from tool executor
    tool_confirmation_result: dict[str, Any] | None  # User decision: confirm/cancel

    # ==========================================================================
    # LLM-Native Semantic Architecture State Keys
    # ==========================================================================
    # These fields enable the new semantic architecture that replaces keyword-based routing
    # with LLM function calling + embeddings for tool selection.
    #
    # Context Loader (Phase 0): Query enrichment and temporal/coreference resolution
    working_query: str | None  # Enriched query after context resolution
    working_query_english: (
        str | None
    )  # Semantic Pivot: English intent for tool matching (critical for embeddings)
    injected_memories: str | None  # Memory facts used for context enrichment
    context_resolutions: list[dict[str, Any]]  # List of resolutions applied (temporal, coreference)
    context_confidence: float  # Confidence score of resolution (0.0-1.0)

    # Semantic Agent (Phase 2): ReAct loop with function calling
    filtered_tools: list[str]  # Tool names selected by semantic matching
    react_iteration: int  # ReAct loop iteration counter (protection against infinite loops)
    pending_tool_calls: list[dict[str, Any]]  # Tool calls awaiting HITL approval/execution

    # HITL Tool Gate (Phase 3): Tool-level approval for sensitive operations
    approved_tool_calls: list[dict[str, Any]]  # Tools approved for execution
    tool_approval_required: bool  # Whether HITL approval was needed for this turn

    # Tool Executor (Phase 4): Tool execution results for response synthesis
    # These fields are populated by tool_executor_node and read by response_node
    tool_results: list[dict[str, Any]]  # Results from executed tools (tool_id, tool_name, result)
    execution_errors: list[
        dict[str, Any]
    ]  # Errors from failed tool executions (tool_id, tool_name, error)

    # ==========================================================================
    # V3 Architecture: Query Intelligence State
    # ==========================================================================
    # QueryIntelligence from router_node_v3 for planner_node_v3 consumption.
    # Contains: intent, domains, turn_type, resolved_context, etc.
    query_intelligence: Any | None  # QueryIntelligence from QueryAnalyzerService

    # Tool Selection Result from router_node_v3 for debug panel.
    # Contains: selected_tools, top_score, has_uncertainty, all_scores (calibrated).
    # Serialized as dict for LangGraph streaming compatibility.
    tool_selection_result: dict[str, Any] | None  # ToolSelectionResult serialized

    # PlanningResult from planner_node_v3 for debug panel streaming.
    # Contains: filtered_catalogue, used_template, used_panic_mode, tokens_used, etc.
    # Needed to extract filtered_catalogue for tool_selection debug metrics.
    planning_result: Any | None  # PlanningResult from SmartPlannerService

    # Knowledge Enrichment (Brave Search): Results for debug panel
    # Stores enrichment execution result from response_node for debug metrics emission.
    # Contains: endpoint, keyword_used, results_count, from_cache, error, skip_reason
    knowledge_enrichment_result: dict[str, Any] | None

    # Memory Injection: Debug details for debug panel
    # Stores injected memory details from response_node for tuning min_score/max_results.
    # Contains: memories list (content, score, category), emotional_state, settings used
    memory_injection_debug: dict[str, Any] | None

    # RAG Spaces: Stores injected RAG chunk details from response_node for debug panel.
    # Contains: spaces_searched, chunks_found, chunks_injected, chunks list
    rag_injection_debug: dict[str, Any] | None

    # Personal Journals: Stores injected journal entry details from response_node for debug panel.
    # Contains: entries_found, entries_injected, total_chars_injected, entries list
    journal_injection_debug: dict[str, Any] | None

    # Personal Journals (Planner): Stores injected journal entry details from planner_node for debug.
    # Contains: entries_found, entries_injected, total_chars_injected, entries list
    journal_planner_injection_debug: dict[str, Any] | None

    # Context Compaction: Intelligent history summarization (F4)
    # When conversation history exceeds a dynamic token threshold, the compaction node
    # summarizes old messages preserving critical identifiers (UUIDs, URLs, IDs).
    compaction_summary: str | None  # Last compaction summary (for debug/audit)
    compaction_count: int  # Number of compactions performed in this session

    # Initiative Phase: Post-execution proactive enrichment (ADR-062)
    # The initiative node evaluates execution results and may execute read-only
    # complementary actions or suggest write actions to the user.
    initiative_iteration: int  # Iteration counter (0 = not evaluated yet)
    initiative_results: list[dict[str, Any]]  # Actions executed + reasoning per iteration
    initiative_skipped_reason: str | None  # Why initiative was skipped (debug panel)
    initiative_suggestion: str | None  # Proactive write suggestion for response_node


class AgentMessagesState(TypedDict):
    """
    Minimal state schema for create_agent with message truncation.

    This state is specifically designed for LangGraph's create_agent() prebuilt.
    It extends the standard agent state with our custom message truncation reducer
    to prevent memory explosion during ReAct iterations.

    Why separate from MessagesState?
    - create_agent requires specific schema (messages + is_last_step + remaining_steps)
    - MessagesState includes extra fields (metadata, routing_history, etc.) not needed by agent
    - Cleaner separation: Graph-level state vs Agent-level state

    Truncation Strategy:
    - Uses add_messages_with_truncate reducer (100K tokens, fallback 50 messages)
    - Prevents exponential memory growth during tool iterations
    - Critical for agents with large tool responses (e.g., contacts lists)

    Attributes:
        messages: Conversation history with automatic truncation via reducer.
        is_last_step: Indicates if recursion limit reached (managed by LangGraph).
        remaining_steps: Number of remaining iterations before limit (managed by LangGraph).

    Usage:
        agent_graph = create_agent(
            model=llm,
            tools=tools,
            state_schema=AgentMessagesState,  # Enables truncation
        )

    References:
        - LangGraph docs: state_schema parameter
        - LangGraph source: create_agent required keys
        - ADR 008 Addendum: State Truncation Critical Fix
    """

    messages: Annotated[list[BaseMessage], add_messages_with_truncate]
    is_last_step: bool
    remaining_steps: int


def create_initial_state(
    user_id: uuid.UUID,
    session_id: str,
    run_id: str,
    user_timezone: str = "Europe/Paris",
    user_language: str = "fr",
    oauth_scopes: list[str] | None = None,
    personality_instruction: str | None = None,
) -> MessagesState:
    """
    Create initial empty state for a new conversation with user preferences.

    Args:
        user_id: User UUID.
        session_id: Session identifier.
        run_id: Unique run identifier for tracing.
        user_timezone: User's IANA timezone (default: "Europe/Paris").
        user_language: User's language code (default: "fr").
        oauth_scopes: OAuth scopes from active connectors (default: empty list).
        personality_instruction: LLM personality prompt instruction (default: None = use default).

    Returns:
        Initial MessagesState with metadata, user preferences, and schema version.

    Example:
        >>> state = create_initial_state(
        ...     user_id=uuid4(),
        ...     session_id="session_123",
        ...     run_id="run_456",
        ...     user_timezone="America/New_York",
        ...     user_language="en",
        ...     oauth_scopes=["https://www.googleapis.com/auth/contacts.readonly"]
        ... )
    """
    return MessagesState(
        messages=[],
        metadata={
            FIELD_USER_ID: str(user_id),
            FIELD_SESSION_ID: session_id,
            FIELD_RUN_ID: run_id,
        },
        routing_history=[],
        agent_results={},
        orchestration_plan=None,
        execution_plan=None,  # ExecutionPlan from planner (Phase 5)
        planner_metadata=None,  # Planner metadata for streaming (Phase 5)
        planner_error=None,  # Planner error/warning for streaming (Phase 5)
        current_turn_id=0,  # Start at turn 0
        session_id=session_id,  # Session identifier for context isolation (Phase 5)
        user_timezone=user_timezone,  # User's IANA timezone for temporal context
        user_language=user_language,  # User's language code for localized responses
        personality_instruction=personality_instruction,  # LLM personality prompt instruction
        oauth_scopes=oauth_scopes or [],  # OAuth scopes from active connectors
        _schema_version=CURRENT_SCHEMA_VERSION,  # Use constant for consistency
        completed_steps={},  # Phase 5.2B-asyncio: Parallel execution step results
        validation_result=None,  # Phase 8: Plan validation result
        approval_evaluation=None,  # Phase 8: Approval strategies evaluation
        plan_approved=None,  # Phase 8: Plan approval decision
        plan_rejection_reason=None,  # Phase 8: Plan rejection reason
        # Phase 2 OPTIMPLAN: Semantic Validation (Issue #60)
        semantic_validation=None,  # SemanticValidationResult from semantic_validator_node
        clarification_response=None,  # User response to clarification question
        clarification_field=None,  # Field for which clarification was asked (e.g., "subject")
        needs_replan=False,  # Flag to trigger planner regeneration after clarification
        replan_instructions=None,  # Instructions for planner when replanning (from approval_gate)
        exclude_sub_agent_tools=False,  # F6: Not excluded on initial state
        planner_iteration=0,  # Counter for clarification iterations (max: PLANNER_MAX_REPLANS setting)
        content_final_replacement=None,  # Phase 5.5: Post-processed content replacement
        last_action_turn_id=None,  # Context resolution: Last turn with agent execution
        turn_type=None,  # Context resolution: Turn type classification
        resolved_context=None,  # Context resolution: Resolved reference context
        detected_intent=None,  # Semantic intent from SemanticIntentDetector (action|detail|search|list|full)
        resolved_references=None,  # Memory reference resolution: ResolvedReferences from pre-planner
        registry={},  # Data Registry: Registry for rich frontend rendering (empty at start)
        current_turn_registry=None,  # Data Registry: Current turn registry items
        # Data Registry LOT 4.3: Draft/Critique HITL support
        pending_draft_critique=None,  # PendingDraftInfo from parallel_executor
        pending_drafts_queue=[],  # Queue for batch draft confirmation (FOR_EACH)
        draft_action_result=None,  # User decision: confirm/edit/cancel with details
        # HITL Dispatch: Entity Disambiguation
        pending_entity_disambiguation=None,  # DisambiguationContext from entity resolution
        entity_disambiguation_result=None,  # User choice from disambiguation
        pending_disambiguations_queue=[],  # Queue for multi-disambiguation protection
        # HITL Dispatch: Tool Confirmation
        pending_tool_confirmation=None,  # ToolConfirmationContext from tool executor
        tool_confirmation_result=None,  # User decision: confirm/cancel
        # LLM-Native Semantic Architecture: Context Loader (Phase 0)
        working_query=None,  # Enriched query after context resolution
        working_query_english=None,  # Semantic Pivot: English intent for tool matching
        injected_memories=None,  # Memory facts used for context enrichment
        context_resolutions=[],  # List of resolutions applied
        context_confidence=1.0,  # Default high confidence
        # LLM-Native Semantic Architecture: Semantic Agent (Phase 2)
        filtered_tools=[],  # Tool names selected by semantic matching
        react_iteration=0,  # ReAct loop iteration counter
        pending_tool_calls=[],  # Tool calls awaiting execution
        # LLM-Native Semantic Architecture: HITL Tool Gate (Phase 3)
        approved_tool_calls=[],  # Tools approved for execution
        tool_approval_required=False,  # Whether HITL was needed
        # LLM-Native Semantic Architecture: Tool Executor (Phase 4)
        tool_results=[],  # Results from executed tools
        execution_errors=[],  # Errors from failed tool executions
        # V3 Architecture: Query Intelligence State
        query_intelligence=None,  # QueryIntelligence from router_node_v3 for planner
        tool_selection_result=None,  # ToolSelectionResult from router_node_v3 for debug panel
        planning_result=None,  # PlanningResult from planner_node_v3 for debug panel
        # Knowledge Enrichment (Brave Search)
        knowledge_enrichment_result=None,  # Enrichment result for debug panel
        # Memory Injection debug (debug panel tuning)
        memory_injection_debug=None,  # Memory injection metrics for debug panel
        # RAG Spaces debug (debug panel)
        rag_injection_debug=None,  # RAG injection metrics for debug panel
        # Journal Injection debug (debug panel)
        journal_injection_debug=None,  # Journal injection metrics for debug panel
        journal_planner_injection_debug=None,  # Journal planner injection metrics for debug panel
        # Context Compaction (F4)
        compaction_summary=None,  # Last compaction summary
        compaction_count=0,  # Compactions performed
        # Initiative Phase (ADR-062)
        initiative_iteration=0,
        initiative_results=[],
        initiative_skipped_reason=None,
        initiative_suggestion=None,
    )


def validate_state_consistency(state: MessagesState) -> list[str]:
    """
    Validate state consistency and detect corruption early.

    This function performs comprehensive state validation following LangGraph v1.0
    best practices. It checks for internal consistency between state fields to
    prevent cascading errors downstream.

    Validations:
    1. **Turn ID Consistency**: Ensures agent_results keys don't reference future turns
    2. **Plan-Result Alignment**: Verifies agent results match orchestration plan
    3. **Key Format Validation**: Checks agent_results keys follow "turn_id:agent_name" format
    4. **Orphan Detection**: Finds agent results without corresponding orchestration plan
    5. **Negative Turn Detection**: Prevents invalid negative turn_id values

    Args:
        state: Current MessagesState to validate.

    Returns:
        List of validation issues (empty list = valid state).

    Usage:
        >>> issues = validate_state_consistency(state)
        >>> if issues:
        ...     logger.error("state_validation_failed", issues=issues)
        ...     raise StateValidationError(issues)

    Best Practice (LangGraph v1.0):
        Call this function at critical checkpoints:
        - After router_node execution
        - Before response_node execution
        - After state updates in reducers

    Example Issues:
        - "Future turn detected: 5:contacts_agent (current=3)"
        - "Unexpected agent results: {'emails_agent'} (not in plan)"
        - "Invalid agent_results key format: 'contacts_no_turn_id'"
        - "Negative turn_id detected: -1"

    Note:
        This function is non-destructive (read-only). It only reports issues
        without modifying state. Use for defensive programming and debugging.
    """
    issues = []

    # Extract state fields
    turn_id = state.get("current_turn_id", 0)
    agent_results = state.get("agent_results", {})
    plan = state.get("orchestration_plan")

    # Validation 1: Check for negative turn_id
    if turn_id < 0:
        issues.append(f"Negative turn_id detected: {turn_id}")

    # Validation 2: Validate agent_results key format and turn_id consistency
    for key in agent_results.keys():
        if ":" not in key:
            issues.append(
                f"Invalid agent_results key format: '{key}' (expected 'turn_id:agent_name')"
            )
            continue

        parts = key.split(":", 1)
        if len(parts) != 2:
            issues.append(f"Invalid agent_results key format: '{key}' (malformed composite key)")
            continue

        try:
            result_turn_id = int(parts[0])
            agent_name = parts[1]

            # Check for future turn_ids
            if result_turn_id > turn_id:
                issues.append(f"Future turn detected: {key} (current_turn_id={turn_id})")

            # Check for empty agent names
            if not agent_name:
                issues.append(f"Empty agent name in key: '{key}'")

        except ValueError:
            issues.append(f"Invalid turn_id in key: '{key}' (turn_id must be integer)")

    # Validation 3: Check plan-result alignment (if plan exists)
    if plan and hasattr(plan, "agents_to_call"):
        expected_agents = set(plan.agents_to_call)

        # Extract agent names from current turn results only
        current_turn_results = {
            key.split(":", 1)[1]
            for key in agent_results.keys()
            if ":" in key and key.split(":", 1)[0] == str(turn_id)
        }

        # Check for unexpected agents (results without plan entry)
        unexpected = current_turn_results - expected_agents
        if unexpected:
            issues.append(
                f"Unexpected agent results for turn {turn_id}: {unexpected} "
                f"(not in orchestration plan: {expected_agents})"
            )

    # Validation 4: Check messages field exists and is valid
    messages = state.get("messages")
    if messages is None:
        issues.append("Missing 'messages' field in state")
    elif not isinstance(messages, list):
        issues.append(f"Invalid 'messages' type: {type(messages).__name__} (expected list)")

    # Validation 5: Check metadata field exists
    metadata = state.get(FIELD_METADATA)
    if metadata is None:
        issues.append("Missing 'metadata' field in state")
    elif not isinstance(metadata, dict):
        issues.append(f"Invalid 'metadata' type: {type(metadata).__name__} (expected dict)")

    return issues


# ============================================================================
# SCHEMA MIGRATION FUNCTIONS (LangGraph v1.0 Best Practice)
# ============================================================================

CURRENT_SCHEMA_VERSION = "1.1"


def get_state_schema_version(state: MessagesState) -> str:
    """
    Get schema version from state.

    Args:
        state: State to check.

    Returns:
        Schema version string (e.g., "1.0"). Returns "0.0" for legacy states.
    """
    return state.get("_schema_version", "0.0")


def needs_migration(state: MessagesState) -> bool:
    """
    Check if state needs schema migration.

    Args:
        state: State to check.

    Returns:
        True if state schema is older than current schema.
    """
    current_version = get_state_schema_version(state)
    return current_version != CURRENT_SCHEMA_VERSION


def migrate_state_to_current(state: MessagesState) -> MessagesState:
    """
    Migrate state to current schema version.

    This function applies all necessary migrations to bring an old state
    to the current schema version. Migrations are idempotent and safe.

    Args:
        state: State to migrate (may be modified in-place).

    Returns:
        Migrated state with current schema version.

    Migration Path:
        0.0 (legacy) → 1.0 (add _schema_version field)
        1.0 → 1.1 (F4: add compaction_summary, compaction_count)

    Usage:
        >>> # After loading state from checkpoint
        >>> if needs_migration(state):
        ...     logger.info("migrating_state", from_version=get_state_schema_version(state))
        ...     state = migrate_state_to_current(state)

    Note:
        Always test migrations with production checkpoint data before deploying.
    """
    current_version = get_state_schema_version(state)

    logger.info(
        "state_migration_check",
        current_version=current_version,
        target_version=CURRENT_SCHEMA_VERSION,
    )

    # Migration: 0.0 → 1.0 (add _schema_version field)
    if current_version == "0.0":
        logger.info("migrating_state_0.0_to_1.0")
        state["_schema_version"] = "1.0"
        current_version = "1.0"

    # Migration: 1.0 → 1.1 (add compaction fields — F4)
    if current_version == "1.0":
        logger.info("migrating_state_1.0_to_1.1")
        if "compaction_summary" not in state:
            state["compaction_summary"] = None
        if "compaction_count" not in state:
            state["compaction_count"] = 0
        state["_schema_version"] = "1.1"
        current_version = "1.1"

    # Verify final version
    if current_version != CURRENT_SCHEMA_VERSION:
        logger.error(
            "state_migration_incomplete",
            final_version=current_version,
            expected_version=CURRENT_SCHEMA_VERSION,
        )

    return state
