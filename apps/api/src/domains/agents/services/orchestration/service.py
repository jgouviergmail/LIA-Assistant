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
from typing import Any

from langchain_core.exceptions import ContextOverflowError
from langchain_core.messages import HumanMessage, RemoveMessage
from langchain_core.runnables import RunnableConfig
from structlog import get_logger

from src.core.config import settings
from src.core.field_names import (
    FIELD_ACTION_REQUESTS,
    FIELD_CONVERSATION_ID,
    FIELD_DECISION,
    FIELD_DRAFT_ID,
    FIELD_INTERRUPT_DATA,
    FIELD_RUN_ID,
    FIELD_SESSION_ID,
    FIELD_TYPE,
    FIELD_USER_ID,
)
from src.domains.agents.constants import (
    ACTION_TYPE_DRAFT_CRITIQUE,
    HITL_DECISION_NEW_REQUEST,
    INTENTION_UNKNOWN,
)
from src.domains.agents.context.store import get_tool_context_store
from src.domains.agents.models import MessagesState, create_initial_state
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
    ) -> AsyncGenerator[GraphChunk, None]:
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
        message_lower = user_message.lower().strip()

        # === STEP 1: Fetch interrupt context from Redis FIRST ===
        # We need to know interrupt_type BEFORE fast paths to handle draft_critique correctly
        # LOT 6 FIX: draft_critique needs {"action": "confirm"} format, not {"decision": "APPROVE"}
        from src.core.config import settings
        from src.domains.agents.utils import HITLStore
        from src.infrastructure.cache.redis import get_redis_cache

        action_context = []
        interrupt_type = None
        draft_id = None

        try:
            redis = await get_redis_cache()
            hitl_store = HITLStore(
                redis_client=redis,
                ttl_seconds=settings.hitl_pending_data_ttl_seconds,
            )

            # Retrieve pending HITL data for context
            pending_data = await hitl_store.get_interrupt(str(conversation_id))
            if pending_data and FIELD_INTERRUPT_DATA in pending_data:
                action_context = pending_data[FIELD_INTERRUPT_DATA].get(FIELD_ACTION_REQUESTS, [])
                # Detect interrupt type from first action request
                if action_context:
                    first_action = action_context[0]
                    interrupt_type = first_action.get(FIELD_TYPE, INTENTION_UNKNOWN)
                    # For draft_critique, extract draft_id
                    if interrupt_type == ACTION_TYPE_DRAFT_CRITIQUE:
                        draft_id = first_action.get(FIELD_DRAFT_ID, INTENTION_UNKNOWN)
        except (ConnectionError, TimeoutError, OSError, RuntimeError) as redis_err:
            logger.warning(
                "approval_decision_redis_fetch_failed",
                run_id=run_id,
                error=str(redis_err),
                error_type=type(redis_err).__name__,
                fallback="proceeding without interrupt context",
            )

        # === FIX 2026-01-11: Detect stale/invalid HITL resumption ===
        # If pending_data exists but action_context is empty, this is a stale HITL state
        # that should NOT be treated as a resumption. Signal to caller that this is
        # a NEW request, not a HITL response.
        if not action_context:
            logger.warning(
                "approval_decision_no_action_context",
                run_id=run_id,
                user_message=user_message[:50],
                interrupt_type=interrupt_type,
                has_pending_data=pending_data is not None,
                reason="No action_context found - treating as new request, not HITL resumption",
            )
            # Return special decision type that signals caller to treat as new message
            return {
                FIELD_DECISION: HITL_DECISION_NEW_REQUEST,
                "user_message": user_message,
                "reason": "Missing action_context - stale HITL state",
            }

        # === LOT 6 FIX: Handle draft_critique BEFORE generic fast paths ===
        # draft_critique_node expects: {"action": "confirm"|"edit"|"cancel", "draft_id": "..."}
        # NOT the generic {"decision": "APPROVE"} format!
        if interrupt_type == "draft_critique":
            logger.info(
                "approval_decision_draft_critique_detected",
                run_id=run_id,
                user_message=user_message[:50],
                draft_id=draft_id,
            )

            # Simple approval patterns for draft_critique → confirm
            if message_lower in {
                "ok",
                "oui",
                "yes",
                "approve",
                "confirme",
                "confirmer",
                "d'accord",
                "dacord",
                "envoie",
                "envoyer",
            }:
                logger.info(
                    "approval_decision_draft_critique_confirm",
                    run_id=run_id,
                    draft_id=draft_id,
                )
                return {
                    "action": "confirm",
                    "draft_id": draft_id,
                }

            # Simple rejection patterns for draft_critique → cancel
            if message_lower in {"non", "no", "reject", "refuse", "annule", "annuler", "cancel"}:
                logger.info(
                    "approval_decision_draft_critique_cancel",
                    run_id=run_id,
                    draft_id=draft_id,
                )
                return {
                    "action": "cancel",
                    "draft_id": draft_id,
                }

            # Complex response - use LLM classifier to detect EDIT intent
            # This handles: "change the content", "shorter", "rephrase", etc.
            try:
                from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

                logger.info(
                    "approval_decision_draft_critique_using_classifier",
                    run_id=run_id,
                    user_message=user_message[:100],
                    draft_id=draft_id,
                )

                classifier = HitlResponseClassifier()
                result = await classifier.classify(
                    user_response=user_message,
                    action_context=action_context,
                )

                logger.info(
                    "approval_decision_draft_critique_classified",
                    run_id=run_id,
                    decision=result.decision,
                    confidence=result.confidence,
                    has_edited_params=bool(result.edited_params),
                )

                if result.decision == "APPROVE":
                    return {
                        "action": "confirm",
                        "draft_id": draft_id,
                    }

                elif result.decision == "REJECT":
                    return {
                        "action": "cancel",
                        "draft_id": draft_id,
                        "reason": result.reasoning,
                    }

                elif result.decision == "EDIT":
                    # Extract modification instructions from edited_params
                    modification_instructions = ""
                    if result.edited_params:
                        modification_instructions = result.edited_params.get(
                            "modification_instructions", ""
                        )
                    # Fallback: use the original user message as instructions
                    if not modification_instructions:
                        modification_instructions = user_message

                    logger.info(
                        "approval_decision_draft_critique_edit",
                        run_id=run_id,
                        draft_id=draft_id,
                        modification_instructions=modification_instructions[:100],
                    )

                    return {
                        "action": "edit",
                        "draft_id": draft_id,
                        "modification_instructions": modification_instructions,
                    }

                elif result.decision == "AMBIGUOUS":
                    # Need clarification - treat as cancel with clarification question
                    # The hitl_dispatch_node will handle re-asking
                    logger.info(
                        "approval_decision_draft_critique_ambiguous",
                        run_id=run_id,
                        draft_id=draft_id,
                        clarification=result.clarification_question,
                    )
                    return {
                        "action": "clarify",
                        "draft_id": draft_id,
                        "clarification_question": result.clarification_question
                        or "Peux-tu préciser ce que tu veux modifier ?",
                    }

                elif result.decision == "REPLAN":
                    # For draft_critique, REPLAN doesn't make sense (no action change possible)
                    # Treat REPLAN as EDIT - user wants to modify the draft content
                    # This handles cases where the classifier misinterprets "modifie..." as action change
                    logger.info(
                        "approval_decision_draft_critique_replan_as_edit",
                        run_id=run_id,
                        draft_id=draft_id,
                        original_decision="REPLAN",
                        converted_to="EDIT",
                    )

                    # Extract modification instructions from reformulated_intent or user message
                    modification_instructions = ""
                    if result.edited_params:
                        modification_instructions = result.edited_params.get(
                            "reformulated_intent", ""
                        ) or result.edited_params.get("modification_instructions", "")

                    # Fallback: use the original user message as instructions
                    if not modification_instructions:
                        modification_instructions = user_message

                    return {
                        "action": "edit",
                        "draft_id": draft_id,
                        "modification_instructions": modification_instructions,
                    }

                else:
                    # Unknown decision - default to cancel
                    logger.warning(
                        "approval_decision_draft_critique_unknown",
                        run_id=run_id,
                        decision=result.decision,
                    )
                    return {
                        "action": "cancel",
                        "draft_id": draft_id,
                        "reason": f"Classification inconnue: {result.decision}",
                    }

            except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
                # FIX 2026-01-12: Classifier failed - fallback to EDIT, not cancel
                # Rationale: If user responds with something complex after seeing a draft
                # (e.g., "use their carven email"), they want to MODIFY the draft.
                # Treating it as cancel is wrong - use the user's message as modification instructions.
                logger.warning(
                    "approval_decision_draft_critique_classifier_error_fallback_to_edit",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    fallback="edit",
                    user_message=user_message[:100],
                )
                return {
                    "action": "edit",
                    "draft_id": draft_id,
                    "modification_instructions": user_message,
                }

        # === FOR_EACH_CONFIRMATION: Handle bulk operation HITL ===
        # task_orchestrator_node expects: {"decision": "APPROVE"|"REJECT"|"EDIT", ...}
        # EDIT must include "exclude_criteria" for item filtering
        # ALWAYS use LLM classifier - no hardcoded patterns (i18n compliance)
        if interrupt_type == "for_each_confirmation":
            logger.info(
                "approval_decision_for_each_confirmation_detected",
                run_id=run_id,
                user_message=user_message[:50],
            )

            try:
                from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

                classifier = HitlResponseClassifier()
                result = await classifier.classify(
                    user_response=user_message,
                    action_context=action_context,
                )

                logger.info(
                    "approval_decision_for_each_classified",
                    run_id=run_id,
                    decision=result.decision,
                    confidence=result.confidence,
                    has_edited_params=bool(result.edited_params),
                )

                if result.decision == "APPROVE":
                    return {"decision": "APPROVE"}

                elif result.decision == "REJECT":
                    return {
                        "decision": "REJECT",
                        "rejection_reason": result.reasoning or "User cancelled",
                    }

                elif result.decision == "EDIT":
                    # Extract exclusion criteria from edited_params
                    exclude_criteria = ""
                    if result.edited_params:
                        exclude_criteria = result.edited_params.get("exclude_criteria", "")
                    # Fallback: use the original user message as criteria
                    if not exclude_criteria:
                        exclude_criteria = user_message

                    logger.info(
                        "approval_decision_for_each_edit",
                        run_id=run_id,
                        exclude_criteria=exclude_criteria[:100],
                    )

                    return {
                        "decision": "EDIT",
                        "exclude_criteria": exclude_criteria,
                    }

                elif result.decision == "REPLAN":
                    # For for_each_confirmation, REPLAN = user wants different items
                    # Treat as EDIT with the user message as exclusion criteria
                    logger.info(
                        "approval_decision_for_each_replan_as_edit",
                        run_id=run_id,
                        original_decision="REPLAN",
                        converted_to="EDIT",
                    )
                    return {
                        "decision": "EDIT",
                        "exclude_criteria": user_message,
                    }

                elif result.decision == "AMBIGUOUS":
                    # Unclear response - treat as REJECT with clarification
                    return {
                        "decision": "REJECT",
                        "rejection_reason": result.clarification_question
                        or "Réponse ambiguë - opération annulée",
                    }

                else:
                    # Unknown decision - default to REJECT for safety
                    logger.warning(
                        "approval_decision_for_each_unknown",
                        run_id=run_id,
                        decision=result.decision,
                    )
                    return {
                        "decision": "REJECT",
                        "rejection_reason": f"Classification inconnue: {result.decision}",
                    }

            except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
                # Classifier failed - treat user message as EDIT criteria
                # This allows natural language exclusion even if classification fails
                logger.warning(
                    "approval_decision_for_each_classifier_error_fallback_to_edit",
                    run_id=run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    fallback="edit",
                    user_message=user_message[:100],
                )
                return {
                    "decision": "EDIT",
                    "exclude_criteria": user_message,
                }

        # === FAST PATH: Simple approval patterns (no LLM needed) ===
        if message_lower in {"ok", "oui", "yes", "approve", "confirme", "d'accord", "dacord"}:
            logger.info(
                "approval_decision_fast_path",
                run_id=run_id,
                decision="APPROVE",
                user_message=user_message[:50],
            )
            return {"decision": "APPROVE"}

        # === FAST PATH: Simple rejection patterns (no LLM needed) ===
        # Only match EXACT "non"/"no" - longer messages need classification
        if message_lower in {"non", "no", "reject", "refuse", "annule", "cancel"}:
            logger.info(
                "approval_decision_fast_path",
                run_id=run_id,
                decision="REJECT",
                user_message=user_message[:50],
            )
            return {
                "decision": "REJECT",
                "rejection_reason": "User declined",
            }

        # === SLOW PATH: Use LLM classifier for complex responses ===
        # This handles EDIT intent like "I want you to search for jean"
        try:
            from src.domains.agents.services.hitl_classifier import HitlResponseClassifier

            logger.info(
                "approval_decision_using_classifier",
                run_id=run_id,
                user_message=user_message[:100],
                action_context_count=len(action_context),
                interrupt_type=interrupt_type,
            )

            # === CLARIFICATION INTERRUPT: Pass user response directly ===
            # For clarification interrupts, user provides the missing info (e.g., "paris" for location)
            # No classification needed - just return the clarification response
            if interrupt_type == "clarification":
                logger.info(
                    "approval_decision_clarification_passthrough",
                    run_id=run_id,
                    user_message=user_message[:100],
                    interrupt_type=interrupt_type,
                )
                return {
                    "clarification": user_message,  # Pass user's response directly
                }

            # Use LLM classifier for nuanced classification
            classifier = HitlResponseClassifier()
            result = await classifier.classify(
                user_response=user_message,
                action_context=action_context,
            )

            logger.info(
                "approval_decision_classified",
                run_id=run_id,
                decision=result.decision,
                confidence=result.confidence,
                reasoning=result.reasoning[:100] if result.reasoning else None,
                has_edited_params=bool(result.edited_params),
            )

            # Convert classifier result to approval_gate_node format
            if result.decision == "APPROVE":
                return {"decision": "APPROVE"}

            elif result.decision == "REJECT":
                return {
                    "decision": "REJECT",
                    "rejection_reason": result.reasoning or "User declined",
                }

            elif result.decision == "EDIT":
                # Build modifications from edited_params
                # Format expected by approval_gate_node:
                # [{"modification_type": "edit_params", "step_id": "step_X", "new_parameters": {...}}]
                modifications = []
                if result.edited_params and action_context:
                    # Import helper function from resumption_strategies
                    from src.domains.agents.services.hitl.resumption_strategies import (
                        _build_plan_modifications_from_classifier,
                    )

                    modifications = _build_plan_modifications_from_classifier(
                        edited_params=result.edited_params,
                        pending_action_requests=action_context,
                        run_id=run_id,
                    )

                return {
                    "decision": "EDIT",
                    "modifications": modifications,
                    "edited_params": result.edited_params,  # Keep raw for logging
                }

            elif result.decision == "REPLAN":
                # Issue #63: User requests different action type (e.g., "detail" instead of "search")
                # Return REPLAN decision with reformulated intent
                replan_instructions = ""
                if result.edited_params:
                    replan_instructions = result.edited_params.get(
                        "reformulated_intent", ""
                    ) or result.edited_params.get("new_action", "")

                logger.info(
                    "approval_decision_replan",
                    run_id=run_id,
                    has_instructions=bool(replan_instructions),
                    reasoning=result.reasoning[:100] if result.reasoning else None,
                )

                return {
                    "decision": "REPLAN",
                    "replan_instructions": replan_instructions,
                    "edited_params": result.edited_params,  # Keep raw for approval_gate
                }

            elif result.decision == "AMBIGUOUS":
                # Treat as REJECT with clarification context
                logger.warning(
                    "approval_decision_ambiguous",
                    run_id=run_id,
                    clarification=result.clarification_question,
                )
                return {
                    "decision": "REJECT",
                    "rejection_reason": result.clarification_question
                    or "Réponse ambiguë, précise ta demande",
                }

            else:
                # Unknown decision type - default to REJECT for safety
                logger.warning(
                    "approval_decision_unknown_type",
                    run_id=run_id,
                    decision=result.decision,
                )
                return {
                    "decision": "REJECT",
                    "rejection_reason": f"Classification inconnue: {result.decision}",
                }

        except (ValueError, KeyError, TypeError, RuntimeError, AttributeError) as e:
            # Fallback to REJECT on classifier error
            logger.error(
                "approval_decision_classifier_error",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
                user_message=user_message[:100],
            )
            return {
                "decision": "REJECT",
                "rejection_reason": f"Erreur de classification: {e!s}",
            }

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

                # === CRITICAL FIX: Restore Pydantic/dataclass models from checkpoint dicts ===
                # PostgresCheckpointer serializes state as JSON, converting models to dicts.
                # When restored, these remain dicts which breaks attribute access (e.g., plan.steps).
                # We must explicitly restore these models for proper type handling.
                #
                # Models that need restoration:
                # 1. execution_plan: ExecutionPlan (Pydantic) - used in route_from_approval_gate
                # 2. validation_result: ValidationResult (dataclass) - used in approval_gate_node

                # Restore ExecutionPlan (Pydantic model)
                if "execution_plan" in state and state["execution_plan"] is not None:
                    execution_plan_data = state["execution_plan"]
                    if isinstance(execution_plan_data, dict):
                        try:
                            from src.domains.agents.orchestration.plan_schemas import ExecutionPlan

                            state["execution_plan"] = ExecutionPlan.model_validate(
                                execution_plan_data
                            )
                            logger.debug(
                                "execution_plan_restored_from_dict",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                plan_id=execution_plan_data.get("plan_id"),
                                steps_count=len(execution_plan_data.get("steps", [])),
                            )
                        except (ValueError, KeyError, TypeError, AttributeError) as restore_err:
                            logger.error(
                                "execution_plan_restore_failed",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                error=str(restore_err),
                                error_type=type(restore_err).__name__,
                                execution_plan_keys=(
                                    list(execution_plan_data.keys())
                                    if isinstance(execution_plan_data, dict)
                                    else None
                                ),
                            )
                            # Clear corrupted execution_plan - will trigger route to response
                            state["execution_plan"] = None

                # Restore ValidationResult (dataclass) - simpler structure, direct instantiation
                if "validation_result" in state and state["validation_result"] is not None:
                    validation_data = state["validation_result"]
                    if isinstance(validation_data, dict):
                        try:
                            from src.domains.agents.orchestration.validator import ValidationResult

                            # ValidationResult is a simple dataclass - reconstruct with key fields
                            # Note: errors/warnings contain ValidationIssue objects, but we only
                            # need is_valid, requires_hitl for HITL flow
                            state["validation_result"] = ValidationResult(
                                is_valid=validation_data.get("is_valid", True),
                                errors=[],  # Skip complex nested objects
                                warnings=[],  # Skip complex nested objects
                                total_cost_usd=validation_data.get("total_cost_usd", 0.0),
                                total_steps=validation_data.get("total_steps", 0),
                                requires_hitl=validation_data.get("requires_hitl", False),
                            )
                            logger.debug(
                                "validation_result_restored_from_dict",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                is_valid=validation_data.get("is_valid"),
                                requires_hitl=validation_data.get("requires_hitl"),
                            )
                        except (ValueError, KeyError, TypeError, AttributeError) as restore_err:
                            logger.error(
                                "validation_result_restore_failed",
                                run_id=run_id,
                                conversation_id=str(conversation_id),
                                error=str(restore_err),
                                error_type=type(restore_err).__name__,
                            )
                            # Keep as dict - code should handle gracefully
                            pass

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
            # Parse user's message to determine approval decision
            # Issue #61 Fix: Now uses LLM classifier for EDIT detection
            decision_data = await self._parse_approval_decision(
                user_message=user_message,
                conversation_id=conversation_id,
                run_id=run_id,
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
        side_channel_queue: asyncio.Queue | None = None,  # SSE side-channel for tools
    ) -> AsyncGenerator[tuple[str, Any], None]:
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
        - Context dict for ToolRuntime
        - Graph.astream() execution with stream_mode=["values", "messages"]

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
                "__deps": tool_deps,
                "__browser_context": browser_context,  # For location-aware tools (weather, places)
                "__user_message": user_message,  # Original message for location phrase detection
                "__side_channel_queue": side_channel_queue,  # SSE side-channel for tools
                # User preferences for planner temporal context (datetime injection)
                "user_timezone": user_timezone,
                "user_language": user_language,
            },
            metadata={
                FIELD_RUN_ID: run_id,
                FIELD_USER_ID: str(user_id),
                FIELD_SESSION_ID: session_id,
                FIELD_CONVERSATION_ID: str(conversation_id),
            },
            callbacks=[token_callback],  # Propagates to ALL nodes automatically
            recursion_limit=settings.agent_max_iterations,  # Security: prevent infinite loops
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

        # Build context dict for ToolRuntime
        context_dict = {
            FIELD_USER_ID: str(user_id),
            FIELD_CONVERSATION_ID: str(conversation_id),
            "thread_id": str(conversation_id),
        }

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
        # Using astream() with stream_mode=["values", "messages"] instead of astream_events()
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
            if is_resuming_interrupt:
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
                    stream_mode=["values", "messages"],
                    context=context_dict,
                ):
                    yield (mode, chunk)
            else:
                # Normal execution with state
                async for mode, chunk in graph.astream(
                    state,
                    runnable_config,
                    stream_mode=["values", "messages"],
                    context=context_dict,
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

        # Build reformulated intent from modifications
        reformulated_intent = build_edit_reformulated_intent(modifications)

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
