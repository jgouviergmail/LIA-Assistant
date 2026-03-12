"""
Plan Approval Interaction - HITL streaming for plan-level approval.

This module implements HitlInteractionProtocol for plan_approval type.
It provides true LLM streaming for plan approval questions, achieving
TTFT < 500ms instead of the previous 2-4s blocking approach.

Features:
    - True LLM token streaming via astream()
    - Fallback to static question on error
    - Multi-language support (fr, en, es, de, it, zh-CN) via i18n_hitl
    - Prometheus metrics for TTFT and fallback tracking
    - Langfuse instrumentation for observability
    - Data Registry integration: registry_ids for rich item rendering (LOT 4)

Data Registry LOT 4 Integration:
    Plan approval can reference registry items from previous tool executions
    (e.g., contacts found in search). The registry_ids are included in
    metadata so frontend can render <LARSCard> components.

Architecture:
    StreamingService detects plan_approval interrupt
    → Creates PlanApprovalInteraction via Registry
    → Calls generate_question_stream() with context
    → Yields tokens to client in real-time

References:
    - protocols.py: HitlInteractionProtocol definition
    - registry.py: Registration decorator
    - OPTIMPLAN/PLAN.md: Section 3 - Phase 1 HITL Streaming
    - Data Registry LOT 4: HITL Integration docs

Created: 2025-11-25
Updated: 2025-11-26 (Data Registry LOT 4 - registry_ids support)
Updated: 2025-12-06 (i18n centralization - 6 languages support)
"""

import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from src.core.field_names import FIELD_CONVERSATION_ID
from src.core.i18n_hitl import HitlMessages, HitlMessageType
from src.infrastructure.observability.logging import get_logger

from ..protocols import HitlInteractionType
from ..registry import HitlInteractionRegistry

if TYPE_CHECKING:
    from ..question_generator import HitlQuestionGenerator

logger = get_logger(__name__)


@HitlInteractionRegistry.register(HitlInteractionType.PLAN_APPROVAL)
class PlanApprovalInteraction:
    """
    HITL interaction implementation for plan-level approval.

    Generates contextual approval questions for execution plans using
    LLM streaming. Achieves TTFT < 500ms by generating the question
    AFTER the interrupt, in the StreamingService.

    Attributes:
        question_generator: HitlQuestionGenerator instance for LLM calls

    Example:
        >>> generator = HitlQuestionGenerator()
        >>> interaction = PlanApprovalInteraction(question_generator=generator)
        >>> async for token in interaction.generate_question_stream(
        ...     context={"plan_summary": {...}, "approval_reasons": [...]},
        ...     user_language="fr",
        ... ):
        ...     print(token, end="", flush=True)

    See Also:
        - HitlInteractionProtocol: Contract this class implements
        - HitlQuestionGenerator: LLM question generation
        - approval_gate_node: Where interrupt is triggered
    """

    def __init__(self, question_generator: "HitlQuestionGenerator") -> None:
        """
        Initialize PlanApprovalInteraction.

        Args:
            question_generator: HitlQuestionGenerator instance for LLM calls
        """
        self._question_generator = question_generator

    @property
    def interaction_type(self) -> HitlInteractionType:
        """Get the interaction type."""
        return HitlInteractionType.PLAN_APPROVAL

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker: Any | None = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate plan approval question via LLM streaming.

        Extracts plan_summary and approval_reasons from context,
        then streams the question token by token.

        Args:
            context: Interrupt context with:
                - plan_summary: dict with plan details
                - approval_reasons: list of reason strings
                - strategies_triggered: list of strategy names
            user_language: Language code (fr, en, es)
            user_timezone: User's IANA timezone for datetime context
            tracker: Optional TokenTrackingCallback

        Yields:
            str: Individual tokens from LLM

        Raises:
            Exception: If LLM streaming fails (caught by caller)

        Performance:
            - TTFT target: < 500ms
            - Total duration: 1-3 seconds
        """
        # Import metrics locally to avoid circular imports
        from src.infrastructure.observability.metrics_agents import (
            hitl_question_tokens_per_second,
            hitl_question_ttft_seconds,
        )

        # Extract data from context
        plan_summary = context.get("plan_summary", {})
        approval_reasons = context.get("approval_reasons", [])
        personality_instruction = context.get("personality_instruction")

        # Convert dict back to PlanSummary if needed
        from src.domains.agents.orchestration.approval_schemas import PlanSummary

        if isinstance(plan_summary, dict):
            try:
                plan_summary_obj = PlanSummary.model_validate(plan_summary)
            except Exception as e:
                logger.warning(
                    "plan_summary_validation_failed_using_dict",
                    error=str(e),
                    plan_summary_keys=list(plan_summary.keys()),
                )
                # Create minimal PlanSummary for fallback
                plan_summary_obj = self._create_minimal_plan_summary(plan_summary)
        else:
            plan_summary_obj = plan_summary

        # Stream question tokens
        start_time = time.time()
        first_token_received = False
        token_count = 0

        logger.info(
            "plan_approval_question_streaming_started",
            plan_id=plan_summary_obj.plan_id,
            total_steps=plan_summary_obj.total_steps,
            user_language=user_language,
        )

        async for token in self._question_generator.generate_plan_approval_question_stream(
            plan_summary=plan_summary_obj,
            approval_reasons=approval_reasons,
            user_language=user_language,
            user_timezone=user_timezone,
            tracker=tracker,
            personality_instruction=personality_instruction,
        ):
            # Track TTFT on first token
            if not first_token_received:
                ttft = time.time() - start_time
                hitl_question_ttft_seconds.labels(type="plan_approval").observe(ttft)
                first_token_received = True
                logger.debug(
                    "plan_approval_question_first_token",
                    ttft_seconds=ttft,
                    plan_id=plan_summary_obj.plan_id,
                )

            token_count += 1
            yield token

        # Track completion metrics
        total_duration = time.time() - start_time
        if total_duration > 0:
            tokens_per_second = token_count / total_duration
            hitl_question_tokens_per_second.labels(type="plan_approval").observe(tokens_per_second)

        logger.info(
            "plan_approval_question_streaming_complete",
            plan_id=plan_summary_obj.plan_id,
            token_count=token_count,
            duration_seconds=total_duration,
            tokens_per_second=tokens_per_second if total_duration > 0 else 0,
        )

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the initial HITL chunk.

        Creates metadata dict with plan approval specific fields.

        Data Registry LOT 4 Integration:
            When registry_ids is provided, includes them in metadata so
            frontend can render <LARSCard> components for items referenced
            in the plan (e.g., contacts to email, events to modify).

        Args:
            context: Interrupt context with plan_summary, etc.
            message_id: Unique message ID
            conversation_id: Conversation UUID string
            registry_ids: data registry IDs for items referenced in plan
                          (e.g., ["contact_abc123"] from previous search)

        Returns:
            Metadata dict for hitl_interrupt_metadata chunk with:
                - action_requests: Plan approval action
                - registry_ids: Registry IDs for rich rendering
                - plan_id: Plan identifier
        """
        plan_summary = context.get("plan_summary", {})
        approval_reasons = context.get("approval_reasons", [])
        strategies_triggered = context.get("strategies_triggered", [])

        # Data Registry LOT 4: Extract registry_ids from context if not explicitly provided
        # Plans can reference items from previous steps
        if registry_ids is None:
            registry_ids = context.get("registry_ids", [])

        # Build action_requests in expected format
        action_requests = [
            {
                "type": "plan_approval",
                "plan_summary": plan_summary,
                "approval_reasons": approval_reasons,
                "strategies_triggered": strategies_triggered,
                # Data Registry LOT 4: Include registry_ids in action_request
                "registry_ids": registry_ids,
            }
        ]

        return {
            "message_id": message_id,
            FIELD_CONVERSATION_ID: conversation_id,
            "action_requests": action_requests,
            "count": 1,
            "is_plan_approval": True,
            # Additional plan-specific metadata
            "plan_id": plan_summary.get("plan_id", "unknown"),
            "total_steps": plan_summary.get("total_steps", 0),
            "hitl_steps_count": plan_summary.get("hitl_steps_count", 0),
            # Data Registry LOT 4: Registry IDs at top level for easy access
            "registry_ids": registry_ids,
            "has_registry_items": len(registry_ids) > 0,
        }

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios.

        Returns a static, pre-defined question when LLM streaming fails.

        Args:
            user_language: Language code (fr, en, es, de, it, zh-CN)

        Returns:
            Static fallback question string
        """
        return HitlMessages.get_fallback(HitlMessageType.PLAN_APPROVAL, user_language)

    def _create_minimal_plan_summary(self, plan_dict: dict[str, Any]) -> Any:
        """
        Create minimal PlanSummary from dict for fallback scenarios.

        Args:
            plan_dict: Raw plan summary dict

        Returns:
            PlanSummary object with minimal required fields
        """
        from datetime import UTC, datetime

        from src.domains.agents.orchestration.approval_schemas import PlanSummary

        return PlanSummary(
            plan_id=plan_dict.get("plan_id", "unknown"),
            total_steps=plan_dict.get("total_steps", 0),
            total_cost_usd=plan_dict.get("total_cost_usd", 0.0),
            hitl_steps_count=plan_dict.get("hitl_steps_count", 0),
            steps=[],  # Empty steps for fallback
            generated_at=datetime.now(UTC),
        )
