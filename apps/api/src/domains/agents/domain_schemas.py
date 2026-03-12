"""
Domain schemas for agents.
Core domain models used by LangGraph nodes and orchestration logic.

These schemas represent domain concepts and are used across the domain layer.
They are separate from API schemas (api/schemas.py) which are HTTP contract models.

Architecture v3.2 (2026-01):
- Confidence thresholds are handled by QueryAnalyzerService
- No legacy validator fallback needed (removed - was redundant and caused bugs)
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Type-safe node names for routing
NextNodeType = Literal[
    "response",
    "task_orchestrator",
    "planner",  # Phase 5: Multi-agent orchestration with LLM planner
]


class RouterOutput(BaseModel):
    """
    Router node output with Pydantic Literal validation.
    Ensures type-safe routing to prevent invalid next_node values.

    This is a DOMAIN model used by:
    - nodes/router_node.py (produces this)
    - orchestration/orchestrator.py (consumes this for plan creation)
    - graph.py (routing decisions)

    Attributes:
        intention: Detected user intention (conversation, contacts_search, etc.).
        confidence: Confidence score (0.0-1.0) for the routing decision.
        context_label: Context label for enrichment (general, unknown, contact, etc.).
        next_node: Next node to route to (validated by Literal).
        domains: Detected domains relevant to user query (Phase 3 - Dynamic Filtering).
                 Examples: ["contacts"], ["contacts", "email"], []
                 Used by Planner to load only relevant tool catalogues.
        reasoning: Optional debug/audit explanation of routing decision.
    """

    intention: str = Field(
        description=(
            "Detected user intention (conversation, contacts_search, "
            "contacts_list, contacts_details)"
        )
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score (0.0-1.0) for routing decision",
    )
    context_label: str = Field(
        description=("Context label for enrichment (general, unknown, contact, email, calendar)")
    )
    next_node: NextNodeType = Field(description="Next node to route to")
    domains: list[str] = Field(
        default_factory=list,
        description=(
            "Phase 3 - Multi-Domain Architecture: Detected domains relevant to user query. "
            "Examples: ['contacts'], ['contacts', 'email'], [] for conversational queries. "
            "Used by Planner node to load filtered catalogue (export_for_prompt_filtered). "
            "Enables 80-90% token reduction for single/dual-domain queries."
        ),
    )
    reasoning: str | None = Field(
        default=None,
        description="Debug/audit: why this routing decision?",
    )

    # Architecture v3.2: No validator needed
    # QueryAnalyzerService._decide_routing() already ensures:
    # - confidence >= V3_ROUTING_MIN_CONFIDENCE (0.6) for planner routes
    # - chat detection via V3_ROUTING_CHAT_SEMANTIC_THRESHOLD (0.4)
    # - high confidence routing via V3_ROUTING_HIGH_SEMANTIC_THRESHOLD (0.7)
    # The legacy validator was REMOVED because it caused bugs (conflicting thresholds)

    model_config = {"frozen": True}  # Immutable after creation


class RouterMetadata(BaseModel):
    """
    Metadata about router decision for debugging/observability.

    Used by api/service.py to construct SSE metadata chunk.
    This is a DOMAIN model representing router decision metadata.

    Attributes:
        intention: Detected intention.
        confidence: Confidence score.
        context_label: Context label.
        next_node: Node routed to.
        reasoning: Optional reasoning (if debug enabled).
    """

    intention: str
    confidence: float
    context_label: str
    next_node: str
    reasoning: str | None = None


# === Human-in-the-Loop (HITL) Tool Approval Schemas ===


class ToolApprovalRequest(BaseModel):
    """
    Request sent to user for tool execution approval.

    This is a DOMAIN model emitted by HumanInTheLoopMiddleware when a tool
    requires human approval before execution. It is sent via SSE stream to
    the frontend and stored in the graph state during interruption.

    Architecture note: Tool approval uses LangChain v1.0 HumanInTheLoopMiddleware
    pattern (see graphs/contacts_agent_builder.py), not custom hooks or nodes.

    Attributes:
        tool_call_id: Unique ID of the tool call (from AIMessage.tool_calls).
        tool_name: Name of the tool to execute (e.g., "delete_contact").
        tool_args: Arguments to pass to the tool (dict of parameter: value).
        tool_description: Human-readable description of what the tool does.
        timestamp: ISO 8601 timestamp of when approval was requested.
        conversation_id: ID of the conversation (for context).
        thread_id: LangGraph thread ID (for resumption via Command).
    """

    tool_call_id: str = Field(description="Unique ID of the tool call (from AIMessage)")
    tool_name: str = Field(description="Name of the tool to execute")
    tool_args: dict[str, Any] = Field(description="Arguments to pass to the tool")
    tool_description: str | None = Field(
        default=None, description="Human-readable description of what the tool does"
    )
    timestamp: str = Field(description="ISO 8601 timestamp of approval request")
    conversation_id: str = Field(description="ID of the conversation")
    thread_id: str = Field(description="LangGraph thread ID for resumption")


class ToolApprovalDecision(BaseModel):
    """
    User's decision(s) on tool approval - LangChain v1.0.1 HITL format.

    This is a DOMAIN model sent from the frontend (via POST /approve-tool)
    to resume graph execution after user reviews tool call(s).

    **LangChain v1.0.1 Requirement:**
    The HumanInTheLoopMiddleware expects a list of decisions, with **one decision
    per action_request** in the interrupt. The order must match the action_requests
    order from the interrupt payload.

    **Supported Patterns:**
    1. Single tool approval:
       - decisions = [{"type": "approve"}]
       - action_indices = [0]

    2. Multiple tools (all same decision):
       - decisions = [{"type": "approve"}, {"type": "approve"}]
       - action_indices = [0, 1]

    3. Multiple tools (granular decisions):
       - decisions = [{"type": "approve"}, {"type": "reject"}]
       - action_indices = [0, 1]

    4. Edited tool call:
       - decisions = [{"type": "edit", "edited_action": {"name": "tool_name", "args": {"param": "new_value"}}}]
       - action_indices = [0]

    **Format for Command(resume=...):**
    ```python
    Command(resume={
        "decisions": [
            {"type": "approve"},
            {"type": "reject", "message": "Reason"},
            {"type": "edit", "edited_action": {"name": "tool_name", "args": {...}}}
        ]
    })
    ```

    Attributes:
        decisions: List of decision objects (1 per tool), each with "type" and optional fields.
        action_indices: Indices of actions being decided (matches action_requests order).
        rejection_messages: Optional rejection messages (same length as decisions, None if not rejected).
    """

    decisions: list[dict[str, Any]] = Field(
        description="List of decision objects matching LangChain v1.0.1 format",
        min_length=1,
    )
    action_indices: list[int] = Field(
        description="Indices of actions being decided (0-based, matches interrupt order)",
        min_length=1,
    )
    rejection_messages: list[str | None] | None = Field(
        default=None,
        description="Optional rejection messages (one per decision, None if not rejected)",
    )

    @field_validator("decisions")
    @classmethod
    def validate_decisions_format(cls, v: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate each decision has required 'type' field and correct structure.

        Args:
            v: List of decision objects.

        Returns:
            Validated decisions.

        Raises:
            ValueError: If any decision is invalid.
        """
        for idx, decision in enumerate(v):
            if not isinstance(decision, dict):
                raise ValueError(f"Decision at index {idx} must be a dict, got {type(decision)}")

            if "type" not in decision:
                raise ValueError(f"Decision at index {idx} missing required 'type' field")

            decision_type = decision["type"]
            if decision_type not in ("approve", "reject", "edit"):
                raise ValueError(
                    f"Decision at index {idx} has invalid type '{decision_type}'. "
                    f"Must be 'approve', 'reject', or 'edit'"
                )

            # Validate 'edit' decision has 'edited_action'
            if decision_type == "edit" and "edited_action" not in decision:
                raise ValueError(
                    f"Decision at index {idx} with type='edit' must include 'edited_action' field"
                )

        return v

    @field_validator("action_indices")
    @classmethod
    def validate_action_indices(cls, v: list[int], info: Any) -> list[int]:
        """
        Validate action_indices match decisions length and are valid indices.

        Args:
            v: List of action indices.
            info: Validation context.

        Returns:
            Validated action indices.

        Raises:
            ValueError: If indices are invalid.
        """
        decisions = info.data.get("decisions", [])

        # Must have same length as decisions
        if len(v) != len(decisions):
            raise ValueError(
                f"action_indices length ({len(v)}) must match decisions length ({len(decisions)})"
            )

        # All indices must be non-negative
        for idx, action_idx in enumerate(v):
            if action_idx < 0:
                raise ValueError(f"action_indices[{idx}] = {action_idx} is negative (must be >= 0)")

        return v

    @field_validator("rejection_messages")
    @classmethod
    def validate_rejection_messages(
        cls, v: list[str | None] | None, info: Any
    ) -> list[str | None] | None:
        """
        Validate rejection_messages length matches decisions if provided.

        Args:
            v: Optional list of rejection messages.
            info: Validation context.

        Returns:
            Validated rejection messages or None.

        Raises:
            ValueError: If length doesn't match decisions.
        """
        if v is None:
            return None

        decisions = info.data.get("decisions", [])
        if len(v) != len(decisions):
            raise ValueError(
                f"rejection_messages length ({len(v)}) must match decisions length ({len(decisions)})"
            )

        return v
