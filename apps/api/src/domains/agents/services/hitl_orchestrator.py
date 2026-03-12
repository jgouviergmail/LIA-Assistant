"""
HITLOrchestrator: Orchestrate HITL (Human-in-the-Loop) flows.

Responsibilities:
- Classify user responses to HITL questions (LLM-based)
- Build approval decisions (approve/reject/edit)
- Validate HITL security and parameters
- Store tool_call_id mappings for rejection handling
- Handle classification errors and ambiguous responses
- Generate clarification questions
- LOT 6: Handle structured draft actions (bypass classification)
"""

import json
import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from langchain_core.runnables import RunnableConfig
from langgraph.errors import GraphInterrupt
from structlog import get_logger

from src.core.constants import MAX_HITL_ACTIONS_PER_REQUEST
from src.core.field_names import FIELD_ERROR_TYPE, FIELD_RUN_ID, FIELD_USER_ID
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.constants import (
    HITL_DECISION_AMBIGUOUS,
    HITL_DECISION_EDIT,
    STATE_KEY_MESSAGES,
)
from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.prompts import (
    HITL_CLARIFICATION_GENERIC_MESSAGE,
    HITL_CLASSIFICATION_FALLBACK_MESSAGE,
)
from src.domains.agents.services.hitl.policies import ApprovalDecisionBuilder
from src.domains.agents.services.hitl.validator import HitlValidator
from src.infrastructure.llm.instrumentation import enrich_config_with_callbacks

if TYPE_CHECKING:
    from src.domains.agents.services.orchestration.service import GraphChunk
    from src.domains.agents.utils.hitl_store import HITLStore
    from src.domains.chat.service import TrackingContext

logger = get_logger(__name__)


# ============================================================================
# LOT 6: Draft Action Detection Helpers
# ============================================================================


def parse_draft_action_if_json(user_message: str) -> dict[str, Any] | None:
    """Parse user message as draft action JSON if applicable.

    LOT 6: Draft Critique HITL - Frontend sends structured JSON for draft actions.

    The frontend (useDraftActions.ts) sends:
        {
            "type": "draft_action",
            "draft_id": "draft_abc123",
            "action": "confirm" | "edit" | "cancel",
            "updated_content": {...} | null
        }

    Args:
        user_message: Raw user message string from frontend.

    Returns:
        Parsed dict if valid draft action JSON, None otherwise.

    Example:
        >>> msg = '{"type": "draft_action", "action": "confirm", "draft_id": "d123"}'
        >>> result = parse_draft_action_if_json(msg)
        >>> result == {"type": "draft_action", "action": "confirm", "draft_id": "d123"}
    """
    # Quick check - must look like JSON
    if not user_message or not user_message.strip().startswith("{"):
        return None

    try:
        parsed = json.loads(user_message.strip())

        # Validate it's a draft action
        if not isinstance(parsed, dict):
            return None

        if parsed.get("type") != "draft_action":
            return None

        # Must have action and draft_id
        if "action" not in parsed or "draft_id" not in parsed:
            logger.warning(
                "invalid_draft_action_json_missing_fields",
                parsed_keys=list(parsed.keys()),
            )
            return None

        # Validate action type
        valid_actions = {"confirm", "edit", "cancel"}
        if parsed.get("action") not in valid_actions:
            logger.warning(
                "invalid_draft_action_type",
                action=parsed.get("action"),
                valid_actions=list(valid_actions),
            )
            return None

        logger.info(
            "draft_action_json_parsed",
            action=parsed.get("action"),
            draft_id=parsed.get("draft_id"),
            has_updated_content=parsed.get("updated_content") is not None,
        )

        return parsed

    except json.JSONDecodeError:
        # Not JSON - will be handled by normal classifier
        return None
    except Exception as e:
        logger.debug(
            "draft_action_parse_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


def is_draft_critique_hitl(pending_action_requests: list[dict] | None) -> bool:
    """Check if pending HITL is a draft critique type.

    LOT 6: Used to determine if we should bypass LLM classification.

    Args:
        pending_action_requests: Action requests from pending HITL.

    Returns:
        True if first action is draft_critique type.
    """
    if not pending_action_requests:
        return False

    first_action = pending_action_requests[0]
    return first_action.get("type") == "draft_critique"


class HitlResponse:
    """User's response to HITL question."""

    def __init__(
        self,
        response_type: str,  # "plan_approval", "tool_approval", "clarification"
        decision: str | None = None,  # "approve", "reject", "edit", "ambiguous"
        edited_plan: dict[str, Any] | None = None,
        clarification_text: str | None = None,
    ):
        self.response_type = response_type
        self.decision = decision
        self.edited_plan = edited_plan
        self.clarification_text = clarification_text


class ValidationResult:
    """Result of HITL response validation."""

    def __init__(self, is_valid: bool, errors: list[str] | None = None):
        self.is_valid = is_valid
        self.errors = errors or []


def _track_response_time_metrics(
    interrupt_ts: str | None,
    decision: str,
    run_id: str,
) -> None:
    """
    Track user response time metrics if interrupt timestamp available.

    Args:
        interrupt_ts: ISO timestamp of interrupt (None if not available)
        decision: Classification decision (APPROVE, REJECT, EDIT, AMBIGUOUS)
        run_id: Run ID for logging
    """
    if not interrupt_ts:
        return

    from datetime import UTC, datetime

    from src.infrastructure.observability.metrics_agents import (
        hitl_user_response_time_seconds,
    )

    try:
        interrupt_time = datetime.fromisoformat(interrupt_ts)
        response_time = datetime.now(UTC)
        response_time_seconds = (response_time - interrupt_time).total_seconds()

        hitl_user_response_time_seconds.labels(
            decision=decision.lower(),
        ).observe(response_time_seconds)

        logger.info(
            "hitl_user_response_time_tracked",
            run_id=run_id,
            decision=decision,
            response_time_seconds=response_time_seconds,
        )
    except Exception as e:
        logger.warning(
            "hitl_response_time_tracking_failed",
            run_id=run_id,
            error=str(e),
            interrupt_ts=interrupt_ts,
        )


async def _handle_message_counting(
    decision: str,
    tracker: Any,
    run_id: str,
) -> None:
    """
    Handle message counting logic based on classification decision.

    Message counting rules (updated: count ALL HITL messages):
    - APPROVE: Counted (explicit confirmation)
    - REJECT: Counted (explicit refusal)
    - EDIT: Counted (user reformulation)
    - AMBIGUOUS: Counted (clarification request)

    All HITL messages are now counted and visible in conversation history
    for complete token/message tracking and accurate billing.

    Args:
        decision: Classification decision (APPROVE, REJECT, EDIT, AMBIGUOUS)
        tracker: TrackingContext for message counting
        run_id: Run ID for logging
    """
    # Count ALL HITL messages for complete tracking
    await tracker.increment_message_count()
    logger.debug(
        "hitl_message_counted",
        run_id=run_id,
        decision=decision,
        reason="all_hitl_messages_now_counted",
    )


def _find_last_ai_message_with_tool_calls(messages: list[Any]) -> Any | None:
    """
    Find the last AIMessage with tool_calls in message history.

    Args:
        messages: List of messages from state

    Returns:
        AIMessage with tool_calls, or None if not found
    """
    for msg in reversed(messages):
        if hasattr(msg, "type") and msg.type == "ai" and hasattr(msg, "tool_calls"):
            if msg.tool_calls:
                return msg
    return None


def _build_tool_call_mapping(
    ai_message: Any,
    action_requests: list[dict],
    validator: Any,
) -> dict[int, str]:
    """
    Build mapping {action_index: tool_call_id} by matching tool names.

    Args:
        ai_message: AIMessage with tool_calls
        action_requests: List of action dicts from HumanInTheLoopMiddleware
        validator: HitlValidator instance for tool extraction

    Returns:
        Mapping dict {action_index: tool_call_id}
    """
    mapping = {}

    for idx, action in enumerate(action_requests):
        try:
            action_name = validator.extract_tool_name(action)
        except ValueError:
            # Skip actions with missing tool names
            continue

        for tc in ai_message.tool_calls:
            # Extract tool call ID with null safety
            tc_id = validator.extract_tool_call_id(tc)
            if not tc_id:
                continue

            # Handle both dict and object formats
            if isinstance(tc, dict):
                tc_name = tc.get("name")
            elif hasattr(tc, "name"):
                tc_name = tc.name
            else:
                continue

            # Match by tool name
            if tc_name and str(tc_name) == action_name:
                mapping[idx] = tc_id
                break

    return mapping


async def _store_mapping_in_redis(
    mapping: dict[int, str],
    conversation_id: Any,
    run_id: str,
) -> None:
    """
    Store tool call mapping in Redis with 5min TTL.

    Args:
        mapping: Tool call mapping {action_index: tool_call_id}
        conversation_id: Conversation UUID
        run_id: Run ID for logging
    """
    import json

    from src.infrastructure.cache.redis import get_redis_cache

    redis = await get_redis_cache()
    await redis.set(
        f"hitl_tool_call_mapping:{conversation_id}",
        json.dumps(mapping),
        ex=300,  # 5 min TTL
    )
    logger.info(
        "hitl_mapping_stored",
        run_id=run_id,
        conversation_id=str(conversation_id),
        mapping=mapping,
    )


class HITLOrchestrator:
    """
    Service for orchestrating HITL (Human-in-the-Loop) flows.

    Responsibilities:
    - Classify user responses to HITL questions (LLM-based)
    - Build approval decisions from classification (approve/reject/edit)
    - Validate HITL security (DoS protection)
    - Store tool_call_id mappings in Redis for rejection handling
    - Handle classification errors with fallback logic
    - Generate clarification questions for ambiguous responses
    """

    def __init__(
        self,
        hitl_classifier: Any,
        hitl_question_generator: Any,
        hitl_store: "HITLStore",
        graph: Any,  # CompiledGraph
        agent_type: str = "generic",
    ):
        """
        Initialize HITL orchestrator with dependencies.

        Args:
            hitl_classifier: Service for LLM-based response classification
            hitl_question_generator: Service for generating clarification questions
            hitl_store: Redis store for HITL state (tool_call_id mappings)
            graph: Compiled LangGraph instance (for checkpointer access)
            agent_type: Agent type label for metrics (e.g., "contacts_agent")
        """
        self.hitl_classifier = hitl_classifier
        self.hitl_question_generator = hitl_question_generator
        self.hitl_store = hitl_store
        self.graph = graph
        self.agent_type = agent_type
        # Policy Classes (Phase 3 - Composition Pattern)
        self.approval_builder = ApprovalDecisionBuilder(agent_type=agent_type)

    # ============================================================================
    # CRITICAL METHODS - Classification and Decision Building
    # ============================================================================

    async def classify_hitl_response_with_metrics(
        self,
        user_response: str,
        action_requests: list[dict],
        tracker: "TrackingContext",
        run_id: str,
        interrupt_ts: str | None,
    ) -> Any:
        """
        Classify HITL user response and track metrics.

        Performs LLM classification of user's natural language response,
        tracks response time metrics, and handles message counting logic.

        Session 21: Refactored with 2 helpers (109 → 49 lines, -55%).

        Args:
            user_response: User's natural language response
            action_requests: Pending action requests from interrupt
            tracker: Unified TrackingContext for token aggregation
            run_id: Run ID for logging
            interrupt_ts: ISO timestamp of interrupt (for response time)

        Returns:
            ClassificationResult with decision, confidence, reasoning

        Note:
            - APPROVE responses are NOT counted in message history
            - Response time metrics tracked if interrupt_ts provided
            - Classification uses hitl_classifier with token tracking
        """
        from src.infrastructure.observability.callbacks import TokenTrackingCallback

        # Classify with token tracking
        classification = await self.hitl_classifier.classify(
            user_response=user_response,
            action_context=action_requests,
            tracker=TokenTrackingCallback(tracker, run_id),
        )

        logger.info(
            "hitl_response_classified",
            run_id=run_id,
            decision=classification.decision,
            confidence=classification.confidence,
            reasoning=classification.reasoning[:100] if classification.reasoning else "",
        )

        # Track user response time metrics (Session 21 - Helper #1)
        _track_response_time_metrics(interrupt_ts, classification.decision, run_id)

        # Handle message counting logic (Session 21 - Helper #2)
        await _handle_message_counting(classification.decision, tracker, run_id)

        return classification

    def build_approval_decision_from_draft_action(
        self,
        draft_action_json: dict[str, Any],
        action_requests: list[dict],
    ) -> ToolApprovalDecision:
        """Build ToolApprovalDecision from structured draft action JSON.

        LOT 6: Draft Critique HITL - Bypasses LLM classification for structured actions.

        Phase 3: Delegates to ApprovalDecisionBuilder Policy Class.

        Args:
            draft_action_json: Parsed JSON from frontend with action details.
            action_requests: List of action_requests from interrupt (contains draft_critique).

        Returns:
            ToolApprovalDecision with single decision matching the draft action.
        """
        return self.approval_builder.build_from_draft_action(
            draft_action_json=draft_action_json,
            action_requests=action_requests,
        )

    def build_approval_decision_from_classification(
        self,
        classification: Any,  # ClassificationResult or dict
        action_requests: list[dict],
        user_response: str = "",
        user_language: str = "en",
    ) -> ToolApprovalDecision:
        """Build ToolApprovalDecision from ClassificationResult.

        Converts natural language classification (APPROVE/REJECT/EDIT/AMBIGUOUS)
        into structured ToolApprovalDecision format expected by HumanInTheLoopMiddleware.

        Phase 3: Delegates to ApprovalDecisionBuilder Policy Class.

        Args:
            classification: ClassificationResult from HitlResponseClassifier (or dict for compatibility).
            action_requests: List of action_requests from interrupt.
            user_response: User's original natural language response (for rejection type inference).
            user_language: User's language code for i18n messages (e.g., "fr", "en"). Default: "en".

        Returns:
            ToolApprovalDecision with decisions list and action_indices.
        """
        return self.approval_builder.build_from_classification(
            classification=classification,
            action_requests=action_requests,
            user_response=user_response,
            user_language=user_language,
        )

    # ============================================================================
    # IMPORTANT METHODS - Tool Mapping and Security
    # ============================================================================

    async def store_tool_call_mapping(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        action_requests: list[dict],
        run_id: str,
    ) -> None:
        """
        Extract and store tool_call_id mapping for HITL REJECT handling.

        LangChain's HumanInTheLoopMiddleware doesn't include tool_call_id in action_requests,
        but we need it to inject ToolMessage on REJECT. This method:
        1. Fetches current state from checkpointer
        2. Finds last AIMessage with tool_calls
        3. Builds mapping {action_index: tool_call_id} by matching tool names
        4. Stores mapping in Redis with 5min TTL

        Session 21: Refactored with 3 helpers (113 → 51 lines, -55%).

        Args:
            conversation_id: Conversation UUID
            user_id: User UUID
            action_requests: List of action dicts from HumanInTheLoopMiddleware
            run_id: Current run ID for logging

        Note:
            - Silent failure (logged as warning) - HITL will work but REJECT may not inject ToolMessage
            - Handles both dict and object tool_call formats
        """
        try:
            # Fetch current state from checkpointer
            config = RunnableConfig(
                configurable={"thread_id": str(conversation_id), FIELD_USER_ID: user_id}
            )
            state = await self.graph.aget_state(config)

            if not state or not state.values:
                logger.warning(
                    "hitl_mapping_no_state",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                )
                return

            messages = state.values.get(STATE_KEY_MESSAGES, [])

            # Find last AIMessage with tool_calls (Session 21 - Helper #1)
            ai_message = _find_last_ai_message_with_tool_calls(messages)
            if not ai_message:
                logger.warning(
                    "hitl_mapping_empty",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    messages_count=len(messages),
                    actions_count=len(action_requests),
                )
                return

            # Build mapping by matching tool names (Session 21 - Helper #2)
            validator = HitlValidator()
            mapping = _build_tool_call_mapping(ai_message, action_requests, validator)

            if not mapping:
                logger.warning(
                    "hitl_mapping_empty",
                    run_id=run_id,
                    conversation_id=str(conversation_id),
                    messages_count=len(messages),
                    actions_count=len(action_requests),
                )
                return

            # Store in Redis (Session 21 - Helper #3)
            await _store_mapping_in_redis(mapping, conversation_id, run_id)

        except Exception as e:
            logger.warning(
                "hitl_mapping_failed",
                run_id=run_id,
                error=str(e),
                error_type=type(e).__name__,
            )

    def validate_hitl_security(
        self,
        action_requests: list[dict],
        max_actions: int = MAX_HITL_ACTIONS_PER_REQUEST,
    ) -> None:
        """
        Validate HITL action count for DoS protection.

        Prevents malicious/buggy agents from creating excessive tool calls
        that could exhaust system resources.

        Args:
            action_requests: List of pending action requests
            max_actions: Maximum allowed actions (default: 10)

        Raises:
            ValueError: If action count exceeds limit

        Example:
            >>> self.validate_hitl_security(action_requests)
            >>> # Raises ValueError if len(action_requests) > 10
        """
        if len(action_requests) > max_actions:
            logger.error(
                "hitl_dos_protection_triggered",
                action_count=len(action_requests),
                max_actions=max_actions,
            )
            raise ValueError(
                f"Too many HITL actions ({len(action_requests)}). "
                f"Maximum allowed: {max_actions}. "
                "This may indicate a misconfigured or malicious agent."
            )

    # ============================================================================
    # ERROR HANDLING METHODS
    # ============================================================================

    async def handle_classification_error(
        self,
        error: Exception,
        conversation_id: uuid.UUID,
        run_id: str,
        user_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Handle classification failure with fallback message.

        When HITL classifier fails (timeout, validation error, network error),
        emits user-friendly fallback message and allows resumption.

        Args:
            error: Exception that occurred during classification
            conversation_id: Conversation UUID
            run_id: Run ID for logging
            user_id: Optional user ID for logging

        Yields:
            ChatStreamChunk with fallback message

        Note:
            - Fallback message is i18n (supports 6 languages)
            - Logs error with full context for debugging
            - Metrics tracked for classification failures
        """
        logger.error(
            "hitl_classification_failed",
            run_id=run_id,
            conversation_id=str(conversation_id),
            user_id=str(user_id) if user_id else None,
            error=str(error),
            error_type=type(error).__name__,
        )

        # Emit fallback message
        yield ChatStreamChunk(
            type="error",
            content={
                "error": HITL_CLASSIFICATION_FALLBACK_MESSAGE,
                FIELD_ERROR_TYPE: "classification_error",
                "recoverable": True,
            },
        )

    async def handle_ambiguous_response(
        self,
        classification: Any,
        action_requests: list[dict],
        user_response: str,
        conversation_id: uuid.UUID,
        run_id: str,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Handle ambiguous HITL response with clarification question.

        When classifier determines user response is AMBIGUOUS (unclear intent),
        generates and streams clarification question to help user provide clearer response.

        Args:
            classification: ClassificationResult with decision=AMBIGUOUS
            action_requests: Pending action requests
            user_response: User's original ambiguous response
            conversation_id: Conversation UUID
            run_id: Run ID for logging

        Yields:
            ChatStreamChunk with clarification question (streamed token by token)

        Note:
            - Uses hitl_question_generator for intelligent question generation
            - Falls back to generic message if generation fails
            - Tracks metrics for ambiguous response handling
        """
        logger.info(
            "hitl_ambiguous_response_detected",
            run_id=run_id,
            conversation_id=str(conversation_id),
            user_response=user_response[:100],
            confidence=classification.confidence if hasattr(classification, "confidence") else None,
        )

        # Try to extract clarification_question from classification
        clarification_question = None
        if hasattr(classification, "clarification_question"):
            clarification_question = classification.clarification_question
        elif isinstance(classification, dict):
            clarification_question = classification.get("clarification_question")

        # If no question in classification, generate one
        if not clarification_question:
            try:
                clarification_question = await self.hitl_question_generator.generate_clarification(
                    user_response=user_response,
                    action_requests=action_requests,
                    conversation_id=conversation_id,
                )
            except Exception as e:
                logger.warning(
                    "hitl_clarification_generation_failed",
                    run_id=run_id,
                    error=str(e),
                )
                clarification_question = HITL_CLARIFICATION_GENERIC_MESSAGE

        # Stream clarification question token by token
        for token in clarification_question.split():
            yield ChatStreamChunk(
                type="hitl_clarification_token",
                content=token + " ",
                metadata={FIELD_RUN_ID: run_id},
            )

        # Signal clarification complete
        yield ChatStreamChunk(
            type="hitl_clarification_complete",
            content="",
            metadata={
                FIELD_RUN_ID: run_id,
                "requires_user_input": True,
            },
        )

    # ============================================================================
    # LEGACY METHODS - Kept for backward compatibility
    # ============================================================================

    async def handle_hitl_interrupt(
        self,
        graph_interrupt: GraphInterrupt,
        state: dict[str, Any],
        tracking_context: "TrackingContext",
    ) -> ChatStreamChunk:
        """
        Handle HITL interrupt and generate question for user.

        Args:
            graph_interrupt: GraphInterrupt exception from LangGraph
            state: Current graph state
            tracking_context: Token tracking context

        Returns:
            ChatStreamChunk with type="hitl_question"

        Example:
            >>> chunk = await orchestrator.handle_hitl_interrupt(interrupt, state, tracker)
            >>> print(chunk.content["question"])  # HITL question for user
        """
        interrupt_type = self._classify_interrupt(graph_interrupt)

        logger.info(
            "hitl_interrupt_detected",
            interrupt_type=interrupt_type,
            has_state=state is not None,
        )

        # Generate HITL question based on interrupt type
        if interrupt_type == "plan_approval":
            question = await self._generate_plan_approval_question(state)
        elif interrupt_type == "tool_approval":
            question = await self._generate_tool_approval_question(state, graph_interrupt)
        elif interrupt_type == "clarification":
            question = await self._generate_clarification_question(state)
        else:
            # Fallback - uses centralized i18n (6 languages)
            from src.domains.agents.api.error_messages import SSEErrorMessages

            user_language = state.get("user_language", "fr") if state else "fr"
            question = SSEErrorMessages.confirmation_required(
                language=user_language  # type: ignore[arg-type]
            )

        return ChatStreamChunk(
            type="hitl_question",
            content={
                "question": question,
                "interrupt_type": interrupt_type,
                "requires_approval": True,
            },
        )

    async def resume_after_hitl(
        self,
        hitl_response: HitlResponse,
        graph: Any,  # CompiledGraph
        conversation_id: uuid.UUID,
        tracking_context: "TrackingContext",
    ) -> AsyncGenerator["GraphChunk", None]:
        """
        Resume graph execution after HITL response.

        Args:
            hitl_response: User's response to HITL question
            graph: Compiled LangGraph instance
            conversation_id: Conversation UUID (thread_id)
            tracking_context: Token tracking context

        Yields:
            GraphChunk: Graph events after resumption

        Example:
            >>> response = HitlResponse(response_type="plan_approval", decision="approve")
            >>> async for chunk in orchestrator.resume_after_hitl(response, graph, conv_id, tracker):
            ...     print(chunk.type)
        """
        logger.info(
            "hitl_resumption_started",
            conversation_id=str(conversation_id),
            response_type=hitl_response.response_type,
            decision=hitl_response.decision,
        )

        # Build resumption input based on response type
        if hitl_response.response_type == "plan_approval":
            resume_input = self._build_plan_approval_input(hitl_response)
        elif hitl_response.response_type == "tool_approval":
            resume_input = self._build_tool_approval_input(hitl_response)
        elif hitl_response.response_type == "clarification":
            resume_input = self._build_clarification_input(hitl_response)
        else:
            raise ValueError(f"Unknown HITL response type: {hitl_response.response_type}")

        # Resume graph with user input
        # Use enriched config with Langfuse + TokenTracking callbacks for proper tracing continuity
        from src.infrastructure.observability.callbacks import TokenTrackingCallback

        runnable_config = RunnableConfig(configurable={"thread_id": str(conversation_id)})
        runnable_config = enrich_config_with_callbacks(
            runnable_config,
            llm_type="hitl_resumption",
            session_id=tracking_context.session_id,
            user_id=str(tracking_context.user_id),
            trace_name="hitl_resumption",
            metadata={
                "response_type": hitl_response.response_type,
                "decision": hitl_response.decision,
            },
        )

        # Add TokenTrackingCallback for token usage tracking after resumption
        existing_callbacks = runnable_config.get("callbacks")
        token_callback = TokenTrackingCallback(tracking_context, tracking_context.run_id)
        if existing_callbacks is None:
            runnable_config["callbacks"] = [token_callback]
        elif isinstance(existing_callbacks, list):
            runnable_config["callbacks"] = [*existing_callbacks, token_callback]
        else:
            # BaseCallbackManager - add handler to it
            existing_callbacks.add_handler(token_callback)
            runnable_config["callbacks"] = existing_callbacks

        try:
            from src.domains.agents.services.orchestration.service import GraphChunk

            async for event in graph.astream_events(resume_input, runnable_config, version="v2"):
                yield GraphChunk(event_type=event.get("event"), data=event.get("data", {}))

        except GraphInterrupt:
            # Another HITL interrupt - caller should handle it
            logger.info(
                "hitl_resumption_interrupted_again",
                conversation_id=str(conversation_id),
            )
            raise

    async def validate_hitl_response(
        self,
        response: HitlResponse,
        expected_type: str,
    ) -> ValidationResult:
        """
        Validate HITL response structure and content.

        Args:
            response: User's HITL response
            expected_type: Expected response type

        Returns:
            ValidationResult with is_valid and errors

        Example:
            >>> result = await orchestrator.validate_hitl_response(response, "plan_approval")
            >>> if not result.is_valid:
            ...     print(result.errors)
        """
        errors = []

        # Type validation
        if response.response_type != expected_type:
            errors.append(
                f"Expected response type '{expected_type}', got '{response.response_type}'"
            )

        # Decision validation
        if response.response_type == "plan_approval":
            valid_decisions = ["approve", "reject", "edit", HITL_DECISION_AMBIGUOUS]
            if response.decision not in valid_decisions:
                errors.append(f"Invalid decision: {response.decision}")

            if response.decision == HITL_DECISION_EDIT and not response.edited_plan:
                errors.append("Edited plan is required when decision is 'edit'")

        elif response.response_type == "tool_approval":
            # Valid decision types for tool approval (matching domain_schemas.py validation)
            valid_decisions = ["approve", "reject", "edit"]
            if response.decision not in valid_decisions:
                errors.append(f"Invalid decision: {response.decision}")

        elif response.response_type == "clarification":
            if not response.clarification_text:
                errors.append("Clarification text is required")

        return ValidationResult(is_valid=len(errors) == 0, errors=errors)

    # ============================================================================
    # PRIVATE METHODS - Question Generation (Legacy Stubs)
    # ============================================================================

    def _classify_interrupt(self, graph_interrupt: GraphInterrupt) -> str:
        """Classify HITL interrupt type."""
        # Simplified classification - in reality would use HITL classifier
        if "plan" in str(graph_interrupt).lower():
            return "plan_approval"
        elif "tool" in str(graph_interrupt).lower():
            return "tool_approval"
        else:
            return "clarification"

    async def _generate_plan_approval_question(self, state: dict[str, Any]) -> str:
        """Generate plan approval question."""
        # Simplified - in reality would use HITL question generator
        plan = state.get("plan", {})
        return f"Voulez-vous approuver ce plan ? {plan}"

    async def _generate_tool_approval_question(
        self, state: dict[str, Any], graph_interrupt: GraphInterrupt
    ) -> str:
        """Generate tool approval question."""
        # Simplified - in reality would use HITL question generator
        return "Veux-tu approuver l'exécution de cet outil ?"

    async def _generate_clarification_question(self, state: dict[str, Any]) -> str:
        """Generate clarification question."""
        # Simplified - in reality would use HITL question generator
        return "Peux-tu clarifier ta demande ?"

    # ============================================================================
    # PRIVATE METHODS - Resumption Input Building (Legacy Stubs)
    # ============================================================================

    def _build_plan_approval_input(self, response: HitlResponse) -> dict[str, Any]:
        """Build resumption input for plan approval."""
        return {
            "plan_approval": {
                "decision": response.decision,
                "edited_plan": response.edited_plan,
            }
        }

    def _build_tool_approval_input(self, response: HitlResponse) -> dict[str, Any]:
        """Build resumption input for tool approval."""
        return {"tool_approval": {"decision": response.decision}}

    def _build_clarification_input(self, response: HitlResponse) -> dict[str, Any]:
        """Build resumption input for clarification."""
        return {"clarification": {"text": response.clarification_text}}
