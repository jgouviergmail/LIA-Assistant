"""
Base protocol for HITL resumption strategies.

Follows same pattern as:
- OAuthProvider (src/core/oauth/providers/base.py)
- LLMProvider (src/infrastructure/llm/base.py)

This enables swapping HITL strategies without code changes:
- Conversational HITL (natural language: "oui", "non")
- Button-based HITL (admin inspection mode)
- Future: Voice-based HITL, Multi-step approval, etc.
"""

from collections.abc import AsyncGenerator
from typing import Any, Protocol
from uuid import UUID

from langchain_core.runnables.config import RunnableConfig
from langgraph.graph.state import CompiledStateGraph

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.domain_schemas import ToolApprovalDecision


class HitlResumptionStrategy(Protocol):
    """
    Protocol for HITL graph resumption strategies.

    This protocol defines the contract for resuming graph execution after
    Human-in-the-Loop approval. Different strategies can be swapped without
    modifying consuming code.

    Design pattern: Strategy pattern via Protocol
    - Enables runtime strategy selection
    - Type-safe via Protocol (PEP 544)
    - Testable via mocking

    Examples:
        >>> strategy = ConversationalHitlResumption()
        >>> async for chunk in strategy.resume_and_stream(...):
        ...     print(chunk.type, chunk.content)

    See Also:
        - ConversationalHitlResumption: Natural language approval
    """

    async def resume_and_stream(
        self,
        graph: CompiledStateGraph,
        approval_decision: ToolApprovalDecision,
        conversation_id: UUID,
        user_id: UUID,
        run_id: str,
        config: RunnableConfig | None = None,
        context: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> AsyncGenerator[ChatStreamChunk, None]:
        """
        Resume graph execution after HITL approval and stream results.

        This method is called after user approves/rejects/edits a tool call.
        It resumes the graph from the interrupt point and streams tokens back.

        Args:
            graph: Compiled LangGraph StateGraph to resume.
            approval_decision: User's approval decision (approve/reject/edit).
            conversation_id: Conversation UUID (thread_id for checkpoint).
            user_id: User UUID (for tracking and context).
            run_id: Unique run ID for this execution.
            config: Optional RunnableConfig for graph execution.
            context: Optional context dict for ToolRuntime.
            **kwargs: Additional strategy-specific parameters.

        Yields:
            ChatStreamChunk: Stream chunks (tokens, metadata, done/error).

        Raises:
            Exception: If graph execution fails or resumption fails.

        Implementation Notes:
            - MUST use TrackingContext for token tracking
            - MUST yield "done" chunk with token metadata
            - MUST handle nested interrupts (multi-action HITL)
            - MUST archive messages to database
            - MUST update conversation stats

        Example Flow:
            1. Extract decisions from approval_decision
            2. Build Command(resume={"decisions": [...]})
            3. Create TrackingContext for token tracking
            4. Stream graph.astream(command, config)
            5. Yield tokens to frontend
            6. Archive response + update stats
            7. Yield "done" chunk with metrics
        """
        ...
