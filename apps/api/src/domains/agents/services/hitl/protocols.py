"""
HITL Interaction Protocol - Generic interface for HITL streaming interactions.

This module defines the Protocol and supporting types for Human-in-the-Loop
streaming interactions. It enables:
- True LLM token streaming (TTFT < 500ms vs 2-4s blocking)
- Extensibility for new interaction types (clarification, edit confirmation, etc.)
- Type-safe interface via Protocol (PEP 544)
- Data Registry integration: Registry IDs for rich item rendering (LOT 4)

Architecture:
    - HitlInteractionType: Enum of supported interaction types
    - HitlInteractionProtocol: Contract for interaction implementations
    - Each interaction type implements the protocol with domain-specific logic
    - Data Registry: Registry IDs included in metadata for frontend rendering

Design Patterns:
    - Strategy Pattern: Different strategies per interaction type
    - Protocol Pattern: Type-safe interface without inheritance coupling
    - Factory Pattern: Registry creates appropriate interaction instance

References:
    - LangGraph v1.0 Interrupt Pattern
    - LangChain v1.0 astream() for token streaming
    - Issue #56: Architecture Planning Agentique
    - Data Registry LOT 4: HITL Integration

Created: 2025-11-25
Updated: 2025-11-26 (Data Registry LOT 4 - registry_ids support)
"""

from collections.abc import AsyncGenerator
from enum import Enum
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from langchain_core.callbacks.base import BaseCallbackHandler


class HitlInteractionType(str, Enum):
    """
    Supported HITL interaction types.

    Each type corresponds to a different interrupt scenario in the LangGraph workflow.
    New types can be added without modifying existing code (Open/Closed Principle).

    Types:
        PLAN_APPROVAL: User approves/rejects entire execution plan
        TOOL_CONFIRMATION: User confirms individual tool execution
        CLARIFICATION: User provides clarification for ambiguous request (Issue #56)
        EDIT_CONFIRMATION: User confirms plan edits (Phase 3)
        DRAFT_CRITIQUE: User reviews draft before execution (Data Registry LOT 4.3)

    Data Registry Integration (LOT 4):
        All interaction types can include registry_ids in their metadata.
        Frontend uses these IDs to render rich <LARSCard> components
        alongside the HITL question.

    Usage:
        >>> interaction_type = HitlInteractionType.PLAN_APPROVAL
        >>> interaction = HitlInteractionRegistry.get(interaction_type)
    """

    PLAN_APPROVAL = "plan_approval"
    TOOL_CONFIRMATION = "tool_confirmation"
    CLARIFICATION = "clarification"
    EDIT_CONFIRMATION = "edit_confirmation"
    DRAFT_CRITIQUE = "draft_critique"  # Data Registry LOT 4.3: Draft review before execution
    ENTITY_DISAMBIGUATION = "entity_disambiguation"  # Entity resolution when multiple matches found
    DESTRUCTIVE_CONFIRM = "destructive_confirm"  # Phase 3: Enhanced confirmation for bulk deletions
    FOR_EACH_CONFIRMATION = (
        "for_each_confirmation"  # Bulk mutation confirmation (send/create/update N items)
    )

    @classmethod
    def from_action_type(cls, action_type: str) -> "HitlInteractionType":
        """
        Convert action_type string from interrupt payload to enum.

        Provides backward compatibility with existing interrupt formats.

        Args:
            action_type: String from interrupt payload (e.g., "plan_approval")

        Returns:
            Corresponding HitlInteractionType enum value

        Raises:
            ValueError: If action_type is not recognized

        Example:
            >>> HitlInteractionType.from_action_type("plan_approval")
            HitlInteractionType.PLAN_APPROVAL
        """
        try:
            return cls(action_type)
        except ValueError:
            # Fallback for backward compatibility
            # Unknown types default to PLAN_APPROVAL (safest option)
            return cls.PLAN_APPROVAL


@runtime_checkable
class HitlInteractionProtocol(Protocol):
    """
    Protocol for HITL interaction streaming.

    This protocol defines the contract for generating HITL questions in streaming mode.
    Implementations provide domain-specific logic for different interaction types.

    Design:
        - Protocol (PEP 544) for structural subtyping
        - @runtime_checkable for isinstance() checks
        - Async generators for true LLM streaming

    Benefits:
        - Type-safe interface without inheritance coupling
        - Testable via mocking (no base class required)
        - Extensible for new interaction types

    Example Implementation:
        >>> class PlanApprovalInteraction:
        ...     @property
        ...     def interaction_type(self) -> HitlInteractionType:
        ...         return HitlInteractionType.PLAN_APPROVAL
        ...
        ...     async def generate_question_stream(
        ...         self, context: dict, user_language: str
        ...     ) -> AsyncGenerator[str, None]:
        ...         async for token in self.llm.astream(prompt):
        ...             yield token.content

    See Also:
        - HitlInteractionRegistry: Factory for creating interaction instances
        - PlanApprovalInteraction: Plan-level approval implementation
        - ToolConfirmationInteraction: Tool-level confirmation implementation
    """

    @property
    def interaction_type(self) -> HitlInteractionType:
        """
        Get the type of this interaction.

        Returns:
            HitlInteractionType enum value identifying this interaction

        Implementation Notes:
            - MUST return a constant value (same for all calls)
            - Used by registry for routing
        """
        ...

    async def generate_question_stream(
        self,
        context: dict[str, Any],
        user_language: str,
        user_timezone: str = "Europe/Paris",
        tracker: "BaseCallbackHandler | None" = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate HITL question tokens via LLM streaming.

        This is the core method for true HITL streaming. It uses LLM astream()
        to yield tokens progressively, achieving TTFT < 500ms.

        Args:
            context: Interaction-specific context from interrupt payload
                - For PLAN_APPROVAL: plan_summary, approval_reasons, strategies
                - For TOOL_CONFIRMATION: tool_name, tool_args
                - For CLARIFICATION: questions, semantic_issues
            user_language: Language code for question generation (fr, en, es)
            user_timezone: User's IANA timezone for datetime context in prompts
            tracker: Optional TokenTrackingCallback for cost accounting

        Yields:
            str: Individual tokens as generated by the LLM

        Raises:
            Exception: If LLM streaming fails (caller should handle gracefully)

        Performance Targets:
            - TTFT (Time To First Token): < 500ms
            - Total generation: 1-3 seconds
            - Fallback on error: immediate with static message

        Example:
            >>> interaction = PlanApprovalInteraction(question_generator)
            >>> tokens = []
            >>> async for token in interaction.generate_question_stream(
            ...     context={"plan_summary": {...}},
            ...     user_language="fr",
            ... ):
            ...     tokens.append(token)
            ...     print(token, end="", flush=True)
        """
        ...
        # This is a protocol method stub
        # Implementations yield tokens
        yield ""  # noqa: B901 - Protocol stub

    def build_metadata_chunk(
        self,
        context: dict[str, Any],
        message_id: str,
        conversation_id: str,
        registry_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Build metadata for the initial HITL chunk.

        Creates the metadata dict sent with hitl_interrupt_metadata chunk.
        Contains action_requests and interaction-specific data.

        Data Registry LOT 4 Integration:
            When registry_ids is provided, the metadata includes these IDs
            so frontend can render <LARSCard> components alongside the HITL
            question. This enables rich visualization of items being confirmed.

        Args:
            context: Interaction context from interrupt payload
            message_id: Unique message identifier for this HITL session
            conversation_id: Conversation UUID string
            registry_ids: data registry IDs related to this HITL action
                          (e.g., ["contact_abc123"] for tool confirmation)

        Returns:
            Metadata dict with:
                - message_id: str
                - conversation_id: str
                - action_requests: list[dict]
                - count: int
                - is_plan_approval: bool
                - registry_ids: list[str] (Data Registry LOT 4)
                - Additional interaction-specific fields

        Example:
            >>> metadata = interaction.build_metadata_chunk(
            ...     context={"plan_summary": {...}},
            ...     message_id="hitl_123_abc",
            ...     conversation_id="550e8400-e29b-41d4-a716-446655440000",
            ...     registry_ids=["contact_abc123", "contact_def456"],
            ... )
            >>> print(metadata["is_plan_approval"])
            True
            >>> print(metadata["registry_ids"])
            ['contact_abc123', 'contact_def456']
        """
        ...

    def get_fallback_question(self, user_language: str) -> str:
        """
        Get fallback question for error scenarios.

        Called when LLM streaming fails. Returns a static, pre-defined
        question appropriate for this interaction type.

        Args:
            user_language: Language code (fr, en, es)

        Returns:
            Static fallback question string

        Example:
            >>> interaction.get_fallback_question("fr")
            "Ce plan nécessite ton approbation. Valides-tu pour continuer ?"
        """
        ...
