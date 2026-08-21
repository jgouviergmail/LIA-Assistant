"""
OrchestrationService: Graph execution and state management.

Responsibilities:
- Execute LangGraph with streaming
- Load or create graph state
- Manage tool dependency injection
- Handle graph configuration

Extracted from: service.py stream_chat_response() (Phase 3.3)
"""

import asyncio
import time
import uuid
from collections.abc import AsyncGenerator
from contextlib import suppress
from typing import Any

from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from structlog import get_logger

from src.core.config import settings
from src.core.field_names import (
    FIELD_CONVERSATION_ID,
    FIELD_DECISION,
    FIELD_IS_AUTOMATED_SOURCE,
    FIELD_RUN_ID,
    FIELD_SESSION_ID,
    FIELD_USER_ID,
)
from src.core.i18n import DEFAULT_LANGUAGE
from src.domains.agents.constants import (
    HITL_DECISION_NEW_REQUEST,
)
from src.domains.agents.context.runtime_context_builder import build_runtime_context
from src.domains.agents.context.store import get_tool_context_store
from src.domains.agents.models import (
    MessagesState,
    create_initial_state,
    migrate_state_to_current,
    needs_migration,
)
from src.infrastructure.llm.instrumentation import enrich_config_with_callbacks
from src.infrastructure.observability.callbacks import TokenTrackingCallback
from src.infrastructure.observability.metrics_agents import agent_messages_history_count
from src.infrastructure.observability.metrics_langgraph import (
    langgraph_graph_duration_seconds,
    langgraph_graph_errors_total,
    langgraph_graph_executions_total,
    langgraph_graph_interrupts_total,
    langgraph_graph_recursion_limit_exceeded_total,
)

logger = get_logger(__name__)


class GraphChunk:
    """
    Raw graph execution event.

    Types:
    - node: Node execution started
    - edge: Edge traversal
    - tool_call: Tool invocation
    - tool_result: Tool result
    - end: Graph execution finished
    """

    def __init__(self, event_type: str, data: dict[str, Any]):
        self.type = event_type
        self.data = data


class OrchestrationService:
    """
    Service for graph execution and state management.

    Responsibilities:
    - Execute LangGraph with streaming
    - Load existing state from checkpoints
    - Create initial state for new conversations
    - Inject tool dependencies into execution context
    """

    async def execute_graph(
        self,
        graph: Any,  # CompiledGraph
        input_state: MessagesState,
        runnable_config: RunnableConfig,
    ) -> AsyncGenerator[GraphChunk]:
        """
        Execute LangGraph and yield raw events.

        Args:
            graph: Compiled LangGraph instance
            input_state: Initial graph state
            runnable_config: LangGraph configuration (thread_id, checkpointer, etc.)

        Yields:
            GraphChunk: Raw graph events (node, edge, tool_call, etc.)

        Example:
            >>> async for chunk in service.execute_graph(graph, state, config):
            ...     if chunk.type == "tool_call":
            ...         print(f"Tool called: {chunk.data['tool_name']}")
        """
        logger.info(
            "graph_execution_started",
            thread_id=runnable_config.get("configurable", {}).get("thread_id"),
            messages_count=len(input_state.get("messages", [])),
        )

        try:
            # Execute graph with streaming
            async for event in graph.astream_events(input_state, runnable_config, version="v2"):
                event_type = event.get("event")
                data = event.get("data", {})

                # Dashboard 15 langgraph_streaming_events metric (non-critical)
                with suppress(Exception):
                    from src.infrastructure.observability.metrics_langgraph import (
                        langgraph_streaming_events_total,
                    )

                    langgraph_streaming_events_total.labels(
                        event_name=str(event_type or "unknown")
                    ).inc()

                # Yield graph event
                yield GraphChunk(event_type=event_type, data=data)

        except asyncio.CancelledError:
            # Client disconnected — not an error, just log and re-raise
            logger.info(
                "graph_execution_cancelled",
                thread_id=runnable_config.get("configurable", {}).get("thread_id"),
            )
            raise

        except (TimeoutError, RuntimeError, ValueError, OSError) as e:
            logger.error(
                "graph_execution_error",
                exc_info=True,
                error=str(e),
                error_type=type(e).__name__,
            )
            raise

    async def _parse_approval_decision(
        self,
        user_message: str,
        conversation_id: uuid.UUID,
        run_id: str,
        user_language: str = DEFAULT_LANGUAGE,
    ) -> dict[str, Any]:
        """
        Parse user's natural language message to extract approval decision.

        Uses HitlResponseClassifier for intelligent classification that handles:
        - APPROVE: "ok", "oui", "yes", "approve", "confirme"
        - REJECT: "non", "no", "reject", "refuse", "annule"
        - EDIT: "je veux que tu recherches jean", "non recherche paul", etc.
        - AMBIGUOUS: unclear responses requiring clarification

        Issue #61 Fix: Now uses LLM-based classifier instead of simple pattern matching
        to properly detect EDIT intent in plan-level HITL.

        Args:
            user_message: User's response message
            conversation_id: Conversation UUID for Redis lookup
            run_id: Run ID for logging
            user_language: Language of the static notices the parser may emit
                (ambiguity, clarification) — taken from the checkpointed state
                by the caller, since some are streamed verbatim to the user

        Returns:
            dict with "decision" key (APPROVE/REJECT/EDIT/REPLAN/AMBIGUOUS)
            For EDIT: includes "modifications" list
            For REPLAN: includes "replan_instructions" string

        Example:
            >>> decision = await service._parse_approval_decision("ok", conv_id, run_id)
            {"decision": "APPROVE"}
            >>> decision = await service._parse_approval_decision("non", conv_id, run_id)
            {"decision": "REJECT", "rejection_reason": "User declined"}
            >>> decision = await service._parse_approval_decision(
            ...     "je veux que tu recherches jean", conv_id, run_id
            ... )
            {"decision": "EDIT", "modifications": [...]}
            >>> decision = await service._parse_approval_decision(
            ...     "detail de jean dupond", conv_id, run_id
            ... )
            {"decision": "REPLAN", "replan_instructions": "detail de jean dupond"}
        """
        from src.domains.agents.services.orchestration.approval_decision import (
            parse_approval_decision,
        )

        return await parse_approval_decision(user_message, conversation_id, run_id, user_language)

    async def _inject_proactive_messages(
        self,
        state: dict[str, Any],
        conversation_id: uuid.UUID,
        checkpoint_created_at: str | None,
        run_id: str,
    ) -> int:
        """
        Inject proactive notification messages into state from conversation_messages.

        Proactive notifications (interests, birthdays, etc.) are dispatched by the
        scheduler and archived in conversation_messages, but NOT written to LangGraph
        checkpoints. This method bridges that gap by querying those messages and
        injecting them as AIMessage into state["messages"] before the user's new
        message, giving the LLM context about what the user may be replying to.

        Args:
            state: Current graph state (modified in-place).
            conversation_id: Conversation UUID (= user_id in 1:1 mapping).
            checkpoint_created_at: ISO timestamp from StateSnapshot.created_at,
                or None if no checkpoint exists (new conversation).
            run_id: Run identifier for structured logging.

        Returns:
            Number of proactive messages injected.
        """
        from datetime import UTC, datetime, timedelta

        from langchain_core.messages import AIMessage

        from src.core.config import settings
        from src.domains.conversations.repository import ConversationRepository
        from src.infrastructure.database import get_db_context

        try:
            # Determine the cutoff timestamp
            if checkpoint_created_at is not None:
                cutoff = datetime.fromisoformat(checkpoint_created_at)
                # Ensure timezone-aware (UTC if naive)
                if cutoff.tzinfo is None:
                    cutoff = cutoff.replace(tzinfo=UTC)
            else:
                # No checkpoint (new conversation): look back configurable window
                cutoff = datetime.now(UTC) - timedelta(
                    hours=settings.proactive_inject_lookback_hours
                )

            # Query proactive messages and convert to AIMessages within session scope
            # (access ORM attributes before session closes to avoid DetachedInstanceError)
            async with get_db_context() as db:
                repo = ConversationRepository(db)
                proactive_msgs = await repo.get_proactive_messages_after(
                    conversation_id=conversation_id,
                    after_timestamp=cutoff,
                    limit=settings.proactive_inject_max_messages,
                )

                if not proactive_msgs:
                    logger.debug(
                        "no_proactive_messages_to_inject",
                        run_id=run_id,
                        conversation_id=str(conversation_id),
                        cutoff=cutoff.isoformat(),
                    )
                    return 0

                # Convert DB messages to LangChain AIMessages
                # New UUIDs auto-generated → add_messages_with_truncate won't deduplicate
                injected_count = 0
                for msg in proactive_msgs:
                    metadata_type = ""
                    if msg.message_metadata and isinstance(msg.message_metadata, dict):
                        metadata_type = msg.message_metadata.get("type", "proactive")

                    ai_message = AIMessage(
                        content=msg.content,
                        additional_kwargs={
                            "proactive_notification": True,
                            "proactive_type": metadata_type,
                            "original_created_at": (
                                msg.created_at.isoformat() if msg.created_at else None
                            ),
                        },
                    )
                    state["messages"].append(ai_message)
                    injected_count += 1

            logger.info(
                "proactive_messages_injected",
                run_id=run_id,
                conversation_id=str(conversation_id),
                injected_count=injected_count,
                cutoff=cutoff.isoformat(),
                checkpoint_existed=checkpoint_created_at is not None,
            )

            return injected_count

        except Exception as e:
            # CRITICAL: Never let proactive injection failure break the chat flow
            logger.warning(
                "proactive_message_injection_failed",
                run_id=run_id,
                conversation_id=str(conversation_id),
                error=str(e),
                error_type=type(e).__name__,
            )
            return 0

    async def load_or_create_state(
        self,
        graph: Any,  # CompiledGraph
        conversation_id: uuid.UUID,
        user_message: str,
        user_id: uuid.UUID,
        session_id: str,
        run_id: str,
        user_timezone: str,
        user_language: str,
        oauth_scopes: list[str],
        personality_instruction: str | None = None,
        is_hitl_resumption: bool = False,
        user_display_name: str | None = None,
        hitl_decision: dict[str, Any] | None = None,
    ) -> MessagesState:
        """
        Load existing state from checkpoints or create initial state.

        Extracted from: service.py lines 250-346 (Phase 3.3)

        Handles:
        - Checkpoint loading with backward compatibility
        - Legacy migration (old agent_results format)
        - Initial state creation for new conversations
        - User message addition
        - Turn ID increment
        - User preferences update (timezone, language, oauth_scopes)

        Args:
            graph: Compiled LangGraph instance
            conversation_id: Conversation UUID (used as thread_id)
            user_message: User's message content
            user_id: User UUID
            session_id: Session identifier
            run_id: Unique run identifier
            user_timezone: User's IANA timezone
            user_language: User's language code
            oauth_scopes: User's OAuth scopes from active connectors
            personality_instruction: LLM personality prompt instruction (optional)
            is_hitl_resumption: True if resuming from HITL interrupt (detected via Redis).
                               Used as fallback when checkpoint-based detection fails.
            user_display_name: User's friendly first name for sender/signature context
                               (optional).
            hitl_decision: Structured one-click decision (Lot 1 option B). When
                           provided on a resumption, the resume payload is built
                           deterministically (classifier bypassed); a stale or
                           mismatched decision raises HitlDecisionStaleError
                           (fail-closed, never processed as a new turn).

        Returns:
            MessagesState: Loaded or newly created state with user message added

        Example:
            >>> state = await service.load_or_create_state(
            ...     graph, conversation_id, "Hello",
            ...     user_id, session_id, run_id,
            ...     "Europe/Paris", "fr", []
            ... )
        """
        # === CRITICAL: Load existing state from LangGraph checkpoints ===
        # This restores conversation context from previous sessions
        # Without this, LangGraph starts with empty state every time, losing all context!
        runnable_config_for_state = RunnableConfig(configurable={"thread_id": str(conversation_id)})

        # Initialize is_interrupted BEFORE try block to avoid UnboundLocalError
        # if exception occurs during checkpoint loading.
        # Use is_hitl_resumption as initial value - this is the router's Redis-based detection
        # which serves as fallback when checkpoint-based detection (tasks.interrupts) fails.
        # This ensures HITL resumption works even if the interrupt was cleared from checkpoint.
        is_interrupted = is_hitl_resumption
        checkpoint_created_at: str | None = None

        try:
            current_state = await graph.aget_state(runnable_config_for_state)

            # === PHASE 8 - HITL: Detect if we're resuming from an interrupt ===
            # When LangGraph pauses at interrupt(), StateSnapshot.tasks contains PregelTask objects
            # Each PregelTask has an 'interrupts' field - if non-empty, graph is paused
            # We need to check if there's a pending interrupt BEFORE adding the user message
            if current_state and current_state.tasks:
                # Check if any task has active interrupts
                for task in current_state.tasks:
                    if hasattr(task, "interrupts") and task.interrupts:
                        is_interrupted = True
                        logger.info(
                            "detected_pending_interrupt",
                            run_id=run_id,
                            conversation_id=str(conversation_id),
                            task_id=task.id if hasattr(task, "id") else "unknown",
                            task_name=task.name if hasattr(task, "name") else "unknown",
                            interrupts_count=len(task.interrupts),
                        )
                        break

            if current_state and current_state.values and current_state.values.get("messages"):
                # State exists in checkpoints - restore it
                state = current_state.values
                checkpoint_created_at = current_state.created_at

                # === SCHEMA MIGRATION (F7) ===
                # Bring checkpoints written by older code up to the current
                # state schema. Migrations are idempotent and purely additive
                # (defaults for missing keys) — see migrate_state_to_current.
                # This formalizes what the ad-hoc guards below (current_turn_id,
                # legacy agent_results) were doing case by case.
                if needs_migration(state):
                    logger.info(
                        "state_schema_migration",
                        run_id=run_id,
                        conversation_id=str(conversation_id),
                        from_version=state.get("_schema_version", "0.0"),
                    )
                    state = migrate_state_to_current(state)

                # NOTE: there is deliberately NO model restoration here.
                # A checkpointed object comes back with its type intact — the
                # serializer rebuilds allowlisted types through their constructor
                # (measured on 99 real plans and 44 verdicts: none degraded). What
                # keeps it that way is a CI test, not runtime code:
                # tests/unit/domains/conversations/test_checkpoint_allowlist_guard.py
                # fails the build if an allowlist entry stops naming a definition
                # site — the drift that actually caused a degradation in the past.
                #
                # The restoration that used to sit here could never help: an object
                # only comes back as a dict when it no longer passes its own
                # validation, and `model_validate` then fails for the very same
                # reason. Its ValidationResult half rebuilt with `errors=[]`, which
                # would have silently emptied the blockers ADR-184 reports to the
                # user. Modifications made here are dropped on an interrupt resume
                # anyway (the graph receives Command(resume=...), not this dict).
                # See ADR-195.

                # === MIGRATION: Normalize old agent_results keys (backward compatibility) ===
                agent_results = state.get("agent_results", {})
                has_old_keys = any(":" not in key for key in agent_results.keys())

                if has_old_keys:
                    logger.warning(
                        "legacy_agent_results_detected_clearing",
                        run_id=run_id,
                        conversation_id=str(conversation_id),
                        old_keys_count=len(agent_results),
                    )
                    # Clear old format to prevent hybrid state
                    state["agent_results"] = {}

                # Ensure current_turn_id exists (for legacy checkpoints)
                if "current_turn_id" not in state:
                    state["current_turn_id"] = 0
                    logger.info(
                        "turn_id_initialized_for_legacy_state",
                        run_id=run_id,
                        conversation_id=str(conversation_id),
                    )

                # Update user preferences (may have changed since last session)
                state["user_timezone"] = user_timezone
                state["user_language"] = user_language
                state["user_display_name"] = user_display_name  # Refresh sender identity
                state["oauth_scopes"] = oauth_scopes  # Update OAuth scopes from active connectors
                state["personality_instruction"] = (
                    personality_instruction  # Update personality instruction
                )

                logger.info(
                    "state_loaded_from_checkpoint",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    existing_message_count=len(state.get("messages", [])),
                    turn_id=state.get("current_turn_id", 0),
                    user_timezone=user_timezone,
                    user_language=user_language,
                    oauth_scopes_count=len(oauth_scopes),
                    has_personality=personality_instruction is not None,
                )
            else:
                # First message or no checkpoint - create new state with user preferences
                state = create_initial_state(
                    user_id,
                    session_id,
                    run_id,
                    user_timezone=user_timezone,
                    user_language=user_language,
                    oauth_scopes=oauth_scopes,
                    personality_instruction=personality_instruction,
                    user_display_name=user_display_name,
                )
                logger.info(
                    "new_state_created",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    user_timezone=user_timezone,
                    user_language=user_language,
                    oauth_scopes_count=len(oauth_scopes),
                    has_personality=personality_instruction is not None,
                )
        except (
            RuntimeError,
            ValueError,
            ConnectionError,
            OSError,
            AttributeError,
        ) as checkpoint_error:
            # Fallback to new state if checkpoint read fails
            logger.warning(
                "checkpoint_load_failed_using_new_state",
                run_id=run_id,
                error=str(checkpoint_error),
                error_type=type(checkpoint_error).__name__,
            )
            state = create_initial_state(
                user_id,
                session_id,
                run_id,
                user_timezone=user_timezone,
                user_language=user_language,
                oauth_scopes=oauth_scopes,
                personality_instruction=personality_instruction,
                user_display_name=user_display_name,
            )

        # === PROACTIVE MESSAGE INJECTION ===
        # Inject proactive notification messages sent since the last checkpoint.
        # These are stored in conversation_messages but not in LangGraph checkpoints.
        # Without injection, the LLM has no context when a user replies to a notification.
        await self._inject_proactive_messages(
            state=state,
            conversation_id=conversation_id,
            checkpoint_created_at=checkpoint_created_at,
            run_id=run_id,
        )

        # === TURN ISOLATION: Clear previous turn's attachments (evolution F4) ===
        # Prevents attachments from turn N being visible at turn N+1
        state.get("metadata", {}).pop("current_turn_attachments", None)

        # Add user message to state (always add, even when resuming from interrupt)
        state["messages"].append(HumanMessage(content=user_message))

        # === INCREMENT TURN_ID: New conversation turn begins ===
        state["current_turn_id"] = state.get("current_turn_id", 0) + 1

        # === PHASE 8 - HITL: Prepare interrupt resumption data ===
        # Store interrupt state for later use in execute_graph_stream()
        # When there's a pending interrupt, we need to use Command(resume=decision_data)
        # instead of passing state to graph.astream()
        if is_interrupted:
            if hitl_decision is not None:
                # Lot 1 option B: one-click approval — deterministic mapping,
                # no classifier call. Raises HitlDecisionStaleError on any
                # mismatch (propagated to the stream layer as a typed error).
                from src.domains.agents.services.orchestration.approval_decision import (
                    build_structured_decision,
                )

                decision_data = await build_structured_decision(
                    hitl_decision=hitl_decision,
                    conversation_id=conversation_id,
                    run_id=run_id,
                )
            else:
                # Parse user's message to determine approval decision
                # Issue #61 Fix: Now uses LLM classifier for EDIT detection
                decision_data = await self._parse_approval_decision(
                    user_message=user_message,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    # From the checkpoint: the language the previous turn ran in.
                    # Some resume notices are streamed verbatim to the user.
                    user_language=state.get("user_language") or DEFAULT_LANGUAGE,
                )

            # === FIX 2026-01-11: Handle NEW_REQUEST (stale HITL state) ===
            # If _parse_approval_decision returns NEW_REQUEST, this means there's no valid
            # HITL context in Redis. Treat this as a new message, not a HITL resumption.
            if decision_data.get(FIELD_DECISION) == HITL_DECISION_NEW_REQUEST:
                logger.warning(
                    "stale_hitl_detected_treating_as_new_request",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    user_message=user_message[:50],
                    reason=decision_data.get("reason"),
                )

                # Clean up stale pending_hitl from Redis using HITLStore
                try:
                    from src.domains.agents.utils import HITLStore
                    from src.infrastructure.cache.redis import get_redis_cache

                    redis = await get_redis_cache()
                    hitl_store = HITLStore(
                        redis_client=redis,
                        ttl_seconds=settings.hitl_pending_data_ttl_seconds,
                    )
                    await hitl_store.clear_if_invalid(str(conversation_id))
                except (ConnectionError, TimeoutError, RuntimeError, OSError) as cleanup_err:
                    logger.error(
                        "stale_hitl_cleanup_failed",
                        run_id=run_id,
                        error=str(cleanup_err),
                        error_type=type(cleanup_err).__name__,
                    )

                # Reset is_interrupted flag to treat as new message
                is_interrupted = False

                # Don't set _interrupt_resume_data - skip to normal flow
            else:
                logger.info(
                    "detected_interrupt_resumption",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    user_message=user_message,
                    parsed_decision=decision_data.get(FIELD_DECISION),
                    has_modifications="modifications" in decision_data,
                )

                # Store decision data in state metadata for execute_graph_stream to use
                # We'll pass Command(resume=decision_data) instead of state
                # NOTE: _interrupt_resume_data is a temporary field not in MessagesState TypedDict
                # We use cast to tell MyPy this is intentional (field is consumed before state persistence)
                #
                # CRITICAL FIX: Include user_message for Command(update={messages: [...]})
                # LangGraph restores state from checkpoint, ignoring local dict changes.
                # We must pass the new user message via Command(update=...) so the planner
                # sees BOTH the original request AND the clarification response.
                from typing import cast

                state_dict = cast(dict[str, Any], state)
                state_dict["_interrupt_resume_data"] = {
                    **decision_data,
                    "_user_message": user_message,  # Pass to _build_hitl_resume_command
                }

        # === Per-turn state cleanup (Phase 8 - Plan-level HITL) ===
        # NOTE: State cleanup now happens in router_node (first node in graph)
        # because modifications here (before graph.astream()) aren't persisted.
        # Graph reloads from PostgreSQL checkpoint, ignoring local dict changes.
        # See router_node.py lines 155-190 for implementation.

        logger.debug(
            "new_conversation_turn",
            run_id=run_id,
            turn_id=state["current_turn_id"],
        )

        # Track message history count
        agent_messages_history_count.observe(len(state["messages"]))

        # Cast to MessagesState for proper return type
        # NOTE: state is dict[str, Any] internally, but conforms to MessagesState structure
        from typing import cast

        return cast(MessagesState, state)

    async def execute_graph_stream(
        self,
        graph: Any,  # CompiledGraph
        state: MessagesState,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        session_id: str,
        run_id: str,
        tool_deps: Any,  # ToolDependencies
        tracker: Any,  # TrackingContext
        browser_context: Any | None = None,  # BrowserContext from frontend
        user_message: str = "",  # Original user message for location phrase detection
        user_memory_enabled: bool = True,  # User preference for long-term memory
        user_journals_enabled: bool = False,  # User preference for personal journals
        user_psyche_enabled: bool = False,  # User preference for psyche engine
        user_display_mode: str = "cards",  # User display mode (cards/html/markdown)
        user_execution_mode: str = "pipeline",  # Execution mode (pipeline/react) — ADR-070
        is_automated_source: bool = False,  # True for automated runs (scheduled actions)
        side_channel_queue: asyncio.Queue | None = None,  # SSE side-channel for tools
    ) -> AsyncGenerator[tuple[str, Any]]:
        """
        Execute graph with streaming and yield raw (mode, chunk) tuples.

        Extracted from: service.py lines 390-438 (Phase 3.3)

        Handles:
        - RunnableConfig creation with thread_id, callbacks, metadata
        - Tool dependencies injection (__deps)
        - Browser context injection (__browser_context) for location-aware tools
        - User message injection (__user_message) for location phrase detection
        - Token tracking callback
        - Langfuse callbacks for observability
        - Runtime context passed to graph.astream (not yet consumed — see ADR-231)
        - Graph.astream() execution with stream_mode=["values", "messages", "updates", "custom"]

        Args:
            graph: Compiled LangGraph instance
            state: Initial graph state (with user message added)
            conversation_id: Conversation UUID (thread_id)
            user_id: User UUID
            session_id: Session identifier
            run_id: Unique run identifier
            tool_deps: Tool dependencies container (DB session, services, clients)
            tracker: Token tracking context
            browser_context: Browser context (geolocation, etc.) for location-aware tools
            user_message: Original user message for location phrase detection (e.g., "chez moi")
            user_memory_enabled: User preference for long-term memory (extraction + injection)
            user_journals_enabled: User preference for personal journals (extraction + injection)
            is_automated_source: True for automated runs (scheduled actions); placed in
                configurable so response_node skips memory/interest/journal/psyche extraction

        Yields:
            (mode, chunk): Raw graph stream outputs
                - mode: "values" (state updates) or "messages" (message updates)
                - chunk: State dict or message tuple

        Example:
            >>> async for mode, chunk in service.execute_graph_stream(...):
            ...     if mode == "values":
            ...         print(f"State update: {chunk.keys()}")
            ...     elif mode == "messages":
            ...         print(f"Message: {chunk}")
        """
        # === TRACKING: Create token tracking callback ===
        # Modern approach (2025): Callbacks intercept ALL LLM calls,
        # including with_structured_output() which doesn't add AIMessage to state.
        token_callback = TokenTrackingCallback(tracker, run_id)

        # === Long-Term Memory: Get store for psychological profile injection ===
        # Phase 4 LangMem: Store is passed via configurable for response_node access
        # NOTE: Memory features are always enabled
        memory_store = None
        try:
            memory_store = await get_tool_context_store()
        except (RuntimeError, ValueError, ConnectionError, OSError) as e:
            logger.warning(
                "memory_store_init_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

        # Extract user preferences from state for planner temporal context
        from src.core.constants import DEFAULT_TIMEZONE

        user_timezone = state.get("user_timezone", DEFAULT_TIMEZONE)
        user_language = state.get("user_language", settings.default_language)

        # === NEW: Create RunnableConfig with thread_id for checkpoint persistence ===
        runnable_config = RunnableConfig(
            configurable={
                "thread_id": str(conversation_id),  # Links to LangGraph checkpoint
                FIELD_USER_ID: user_id,
                "langgraph_user_id": str(user_id),  # For LangMem memory injection
                "store": memory_store,  # For long-term memory injection
                "user_memory_enabled": user_memory_enabled,  # User preference for memory
                "user_journals_enabled": user_journals_enabled,  # User preference for journals
                "user_psyche_enabled": user_psyche_enabled,  # User preference for psyche engine
                "user_display_mode": user_display_mode,  # User display mode (cards/html/markdown)
                "user_execution_mode": user_execution_mode,  # Execution mode (pipeline/react) — ADR-070
                # Automated-source flag survives Langfuse enrichment (only metadata is
                # overwritten, configurable is preserved) — read by response_node guard.
                FIELD_IS_AUTOMATED_SOURCE: is_automated_source,
                "__deps": tool_deps,
                "__browser_context": browser_context,  # For location-aware tools (weather, places)
                "__user_message": user_message,  # Original message for location phrase detection
                "__side_channel_queue": side_channel_queue,  # SSE side-channel for tools
                # User preferences for planner temporal context (datetime injection)
                "user_timezone": user_timezone,
                "user_language": user_language,
                # Sender identity for content-generating tools (email signatures)
                "user_display_name": state.get("user_display_name"),
            },
            metadata={
                FIELD_RUN_ID: run_id,
                FIELD_USER_ID: str(user_id),
                FIELD_SESSION_ID: session_id,
                FIELD_CONVERSATION_ID: str(conversation_id),
            },
            callbacks=[token_callback],  # Propagates to ALL nodes automatically
            # ADR-070: ReAct mode needs higher recursion_limit (each iteration = 2 transitions)
            recursion_limit=(
                settings.react_agent_max_iterations * 2 + 15
                if user_execution_mode == "react"
                else settings.agent_max_iterations
            ),
        )

        # === Phase 6 - LLM Observability: Enrich config with Langfuse callbacks ===
        # Add Langfuse callbacks + metadata (session_id, user_id, tags) for tracing
        runnable_config = enrich_config_with_callbacks(
            runnable_config,
            llm_type="agent_graph",
            session_id=session_id,
            user_id=str(user_id),
            metadata={
                FIELD_RUN_ID: run_id,
                FIELD_CONVERSATION_ID: str(conversation_id),
            },
            trace_name=f"agent_conversation_{run_id[:8]}",
        )

        # Typed run-scoped context (ADR-231), built by the single builder so
        # this frozen service does not grow a second construction site.
        runtime_context = build_runtime_context(
            state=state,
            user_id=user_id,
            conversation_id=conversation_id,
            memory_store=memory_store,
            tool_deps=tool_deps,
            browser_context=browser_context,
            user_message=user_message,
            side_channel_queue=side_channel_queue,
            user_memory_enabled=user_memory_enabled,
            user_journals_enabled=user_journals_enabled,
            user_psyche_enabled=user_psyche_enabled,
            user_display_mode=user_display_mode,
            user_execution_mode=user_execution_mode,
            is_automated_source=is_automated_source,
        )

        # === PHASE 8 - HITL: Check if resuming from interrupt ===
        # If _interrupt_resume_data is present, use Command(resume=...) pattern
        # instead of passing state directly
        # NOTE: Use cast to access temporary field (not in MessagesState TypedDict)
        from typing import cast

        state_dict = cast(dict[str, Any], state)
        resume_data = state_dict.get("_interrupt_resume_data")
        is_resuming_interrupt = resume_data is not None

        if is_resuming_interrupt:
            logger.info(
                "graph_stream_resuming_from_interrupt",
                run_id=run_id,
                conversation_id=str(conversation_id),
                decision=resume_data.get("decision") if isinstance(resume_data, dict) else None,
                messages_count=len(state.get("messages", [])),
                turn_id=state.get("current_turn_id", 0),
            )
            # Clean up the temporary flag (safe deletion)
            state_dict.pop("_interrupt_resume_data", None)
        else:
            logger.info(
                "graph_stream_starting",
                run_id=run_id,
                conversation_id=str(conversation_id),
                messages_count=len(state.get("messages", [])),
                turn_id=state.get("current_turn_id", 0),
            )

        # === Stream outputs from graph using recommended LangGraph API ===
        # Using astream() with stream_mode=["values", "messages", "updates", "custom"] instead of astream_events()
        # Reason: LangGraph documentation states "astream_events is usually not necessary with LangGraph"
        # Benefits: Type-safe state access, simpler code, better performance
        #
        # PHASE 8 - HITL Resumption:
        # - Normal execution: Pass state dict to continue/start execution
        # - Interrupt resumption: Pass Command(resume=decision_data) to provide value to interrupt()
        from langgraph.errors import GraphInterrupt, GraphRecursionError

        # PHASE 2.5 - LangGraph Observability: Track graph execution
        start_time = time.perf_counter()
        graph_completed = False

        try:
            if isinstance(resume_data, dict):
                # Resume from interrupt with decision data
                # The Command(resume=...) value becomes the return value of interrupt() call
                #
                # === CRITICAL FIX: Plan-level EDIT needs message reformulation ===
                # LangGraph v1.0.3+ best practice: Use Command(resume=..., update={...})
                # to modify state during HITL resumption.
                #
                # When user EDITs parameters (e.g., "recherche plutot jean"):
                # - The plan is modified with new params
                # - But HumanMessage still shows original ("recherche jean")
                # - LLM sees mismatch → wrong response
                # Solution: Replace HumanMessage with reformulated intent
                command_input = await self._build_hitl_resume_command(
                    graph=graph,
                    resume_data=resume_data,
                    runnable_config=runnable_config,
                    run_id=run_id,
                )

                async for mode, chunk in graph.astream(
                    command_input,
                    runnable_config,
                    # "custom" added in Day 2: nodes use langgraph.config.get_stream_writer
                    # to push compaction_start/done events that the streaming service
                    # forwards to the frontend SSE stream.
                    stream_mode=["values", "messages", "updates", "custom"],
                    context=runtime_context,
                    # Explicit intent (was the implicit default): checkpoint
                    # writes happen asynchronously per step — per-step
                    # persistence is required for HITL interrupts/resume while
                    # "sync" would add write latency to the SSE hot path.
                    durability="async",
                ):
                    yield (mode, chunk)
            else:
                # Normal execution with state
                async for mode, chunk in graph.astream(
                    state,
                    runnable_config,
                    stream_mode=["values", "messages", "updates", "custom"],
                    context=runtime_context,
                    durability="async",  # explicit intent — see resume branch above
                ):
                    yield (mode, chunk)

            # Graph completed successfully
            graph_completed = True
            duration = time.perf_counter() - start_time
            langgraph_graph_duration_seconds.observe(duration)
            langgraph_graph_executions_total.labels(status="success").inc()

            logger.debug(
                "graph_execution_complete",
                run_id=run_id,
                duration_seconds=duration,
                conversation_id=str(conversation_id),
            )

        except GraphRecursionError as e:
            # Recursion limit exceeded (infinite loop detection)
            duration = time.perf_counter() - start_time
            langgraph_graph_duration_seconds.observe(duration)
            langgraph_graph_recursion_limit_exceeded_total.labels(
                max_recursion_limit=str(settings.agent_max_iterations)
            ).inc()
            langgraph_graph_errors_total.labels(error_type="GraphRecursionError").inc()
            langgraph_graph_executions_total.labels(status="error").inc()

            logger.error(
                "graph_recursion_limit_exceeded",
                run_id=run_id,
                error=str(e),
                max_iterations=settings.agent_max_iterations,
                duration_seconds=duration,
            )
            raise

        except GraphInterrupt:
            # Graph interrupted (HITL approval gate)
            duration = time.perf_counter() - start_time
            langgraph_graph_duration_seconds.observe(duration)
            langgraph_graph_interrupts_total.labels(interrupt_type="hitl_approval").inc()
            langgraph_graph_executions_total.labels(status="interrupted").inc()

            logger.info(
                "graph_interrupted",
                run_id=run_id,
                duration_seconds=duration,
                interrupt_type="hitl_approval",
            )
            raise

        except ContextOverflowError as e:
            # Context window exceeded during LLM call inside a graph node
            # LangGraph propagates this as-is (no wrapping)
            duration = time.perf_counter() - start_time
            if not graph_completed:
                langgraph_graph_duration_seconds.observe(duration)
            langgraph_graph_errors_total.labels(error_type="ContextOverflowError").inc()
            langgraph_graph_executions_total.labels(status="error").inc()
            logger.error(
                "graph_context_overflow",
                run_id=run_id,
                error=str(e),
                duration_seconds=duration,
            )
            raise

        except asyncio.CancelledError:
            # Client disconnected during streaming — graceful termination, not an error
            duration = time.perf_counter() - start_time
            if not graph_completed:
                langgraph_graph_duration_seconds.observe(duration)
            langgraph_graph_executions_total.labels(status="cancelled").inc()

            logger.info(
                "graph_stream_cancelled",
                run_id=run_id,
                duration_seconds=duration,
            )
            raise

        except (TimeoutError, RuntimeError, ValueError, OSError) as e:
            # Actual errors
            duration = time.perf_counter() - start_time
            if not graph_completed:
                langgraph_graph_duration_seconds.observe(duration)

            error_type = type(e).__name__
            langgraph_graph_errors_total.labels(error_type=error_type).inc()
            langgraph_graph_executions_total.labels(status="error").inc()

            logger.error(
                "graph_stream_error",
                exc_info=True,
                run_id=run_id,
                error=str(e),
                error_type=error_type,
                duration_seconds=duration,
            )
            raise

        finally:
            # GUARANTEE: Persist tracked tokens even on exception.
            # Shield from cancellation to prevent DB connection leaks:
            # without shield, CancelledError interrupts the DB session context
            # manager, leaving connections checked out from the pool.
            try:
                await asyncio.shield(tracker.commit())
            except asyncio.CancelledError:
                # shield() re-raises CancelledError to the caller after the
                # shielded coroutine completes — safe to suppress here since
                # the original CancelledError is already being propagated.
                logger.info(
                    "tracker_commit_completed_after_cancellation",
                    run_id=run_id,
                )
            except (
                RuntimeError,
                ValueError,
                ConnectionError,
                AttributeError,
                OSError,
            ) as commit_error:
                logger.error(
                    "tracker_commit_failed_in_finally",
                    run_id=run_id,
                    error=str(commit_error),
                    error_type=type(commit_error).__name__,
                    exc_info=True,
                )

    async def _build_hitl_resume_command(
        self,
        graph: Any,  # CompiledGraph
        resume_data: dict[str, Any],
        runnable_config: RunnableConfig,
        run_id: str,
    ) -> Any:
        """
        Build Command for HITL resumption with optional message reformulation.

        LangGraph v1.0.3+ best practice: Use Command(resume=..., update={...})
        to modify state during HITL resumption.

        For EDIT decisions:
        - The plan is modified with new parameters (e.g., "jean" instead of "jean")
        - But HumanMessage in state still shows original query ("recherche jean")
        - LLM sees mismatch between query and results → wrong response
        - Solution: Replace HumanMessage with reformulated intent matching actual query

        Args:
            graph: Compiled LangGraph instance
            resume_data: Parsed approval decision (from _parse_approval_decision)
            runnable_config: RunnableConfig with thread_id, callbacks
            run_id: Unique run ID for logging

        Returns:
            Command object with resume value and optional message updates
        """
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        from src.domains.agents.constants import STATE_KEY_MESSAGES
        from src.domains.agents.services.hitl.resumption_strategies import (
            build_edit_reformulated_intent,
            resolve_user_language,
        )

        # CRITICAL FIX: Extract user_message before processing
        # LangGraph restores state from checkpoint, ignoring local dict changes.
        # We MUST pass the new user message via Command(update=...) so nodes see it.
        user_message = resume_data.pop("_user_message", None)

        # LOT 6 FIX: draft_critique uses "action" key, not "decision"
        # For draft_critique, the user message is NOT needed in state - only the action matters.
        # The draft_critique_node uses interrupt() return value, not state messages.
        # CRITICAL: Adding update={messages: [...]} causes LangGraph to treat this as a new
        # message requiring processing, which restarts the graph from router instead of
        # resuming at draft_critique_node. This causes the double-confirmation bug.
        if "action" in resume_data:
            logger.info(
                "hitl_resume_command_draft_critique",
                run_id=run_id,
                action=resume_data.get("action"),
                draft_id=resume_data.get("draft_id"),
            )
            return Command(resume=resume_data)  # No update needed for draft_critique

        decision = resume_data.get("decision", "").upper()
        modifications = resume_data.get("modifications", [])

        # Only EDIT decisions with modifications need message reformulation
        if decision != "EDIT" or not modifications:
            # Non-EDIT case: Still need to add user message to state
            if user_message:
                logger.info(
                    "hitl_resume_command_adding_user_message",
                    run_id=run_id,
                    decision=decision,
                    user_message_preview=(
                        user_message[:50] if len(user_message) > 50 else user_message
                    ),
                )
                return Command(
                    resume=resume_data,
                    update={STATE_KEY_MESSAGES: [HumanMessage(content=user_message)]},
                )

            logger.debug(
                "hitl_resume_command_no_reformulation",
                run_id=run_id,
                decision=decision,
                reason="Not EDIT or no modifications",
            )
            return Command(resume=resume_data)

        # Build reformulated intent from modifications (localized to the user)
        resume_user_language = await resolve_user_language(graph, runnable_config)
        reformulated_intent = build_edit_reformulated_intent(modifications, resume_user_language)

        if not reformulated_intent:
            logger.debug(
                "hitl_resume_command_no_reformulation",
                run_id=run_id,
                decision=decision,
                reason="build_edit_reformulated_intent returned None",
            )
            return Command(resume=resume_data)

        # Load state snapshot to get last HumanMessage ID
        try:
            snapshot = await graph.aget_state(runnable_config, subgraphs=False)
            messages = snapshot.values.get(STATE_KEY_MESSAGES, [])

            # Find the last HumanMessage ID (search from end)
            last_human_msg_id = None
            original_content = None
            for msg in reversed(messages):
                if hasattr(msg, "type") and msg.type == "human":
                    if hasattr(msg, "id") and msg.id:
                        last_human_msg_id = msg.id
                        original_content = msg.content if hasattr(msg, "content") else None
                        break

            # Build message updates: [RemoveMessage(...), HumanMessage(...)]
            from langchain_core.messages import BaseMessage

            messages_to_update: list[BaseMessage] = []

            if last_human_msg_id:
                messages_to_update.append(RemoveMessage(id=last_human_msg_id))
                logger.info(
                    "hitl_edit_removing_original_message",
                    run_id=run_id,
                    message_id=last_human_msg_id,
                    original_content=original_content[:50] if original_content else None,
                    reason="Replacing to avoid LLM confusion",
                )
            else:
                logger.warning(
                    "hitl_edit_no_message_id_found",
                    run_id=run_id,
                    messages_count=len(messages),
                    note="Cannot remove, will add reformulated only",
                )

            # Add reformulated intent
            messages_to_update.append(HumanMessage(content=reformulated_intent))

            logger.info(
                "hitl_edit_message_reformulation_applied",
                run_id=run_id,
                original_content=original_content[:50] if original_content else None,
                reformulated_intent=reformulated_intent,
                modifications_count=len(modifications),
            )

            return Command(
                resume=resume_data,
                update={STATE_KEY_MESSAGES: messages_to_update},
            )

        except (RuntimeError, ValueError, KeyError, AttributeError) as e:
            # Fallback: If state loading fails, proceed without message update
            logger.error(
                "hitl_edit_state_load_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                fallback="Proceeding without message reformulation",
            )
            return Command(resume=resume_data)
