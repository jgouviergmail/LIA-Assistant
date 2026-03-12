"""
Orchestration schemas.
Pydantic models for agent orchestration, results, and execution plans.

Phase 3.2.5: Migrated AgentResult from TypedDict to BaseModel for runtime validation.
Legacy cleanup: Added StepResult and ExecutionResult (extracted from plan_executor.py).
"""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domains.agents.tools.common import ToolErrorCode


class AgentResultData(BaseModel):
    """
    Base class for agent result data.

    Extensible by inheritance for agent-specific result structures.
    Use this as a base for type-safe agent data models.

    **Type Safety Pattern (Phase 5.3):**
    - Subclasses SHOULD define `result_type: Literal["..."] = "..."` for explicit typing
    - `extra='forbid'` prevents silent Union coercion (critical for Pydantic v2)
    - Cannot use `Field(discriminator=...)` because Union includes `dict[str, Any]`

    **IMPORTANT**: Uses `extra='forbid'` to prevent Pydantic v2 Union coercion issues.
    Without this, a dict with arbitrary keys could be coerced to a domain-specific
    model (like PlacesResultData) when all its fields have default values, causing
    the dict's actual data (like step_results) to be silently discarded.

    Example:
        >>> class EmailResultData(AgentResultData):
        ...     result_type: Literal["emails"] = "emails"  # Explicit type marker
        ...     emails: list[dict]
        ...     unread_count: int
    """

    model_config = ConfigDict(extra="forbid")


class ContactsResultData(AgentResultData):
    """
    Result data structure for Contacts Agent.

    Attributes:
        result_type: Type discriminator for serialization.
        contacts: List of contact dictionaries from Google People API.
        total_count: Total number of contacts returned.
        has_more: Whether more contacts are available (pagination).
        query: Original search query (if applicable).
        data_source: Source of data ("api" for real-time, "cache" for Redis).
        timestamp: ISO 8601 timestamp when data was fetched.
        cache_age_seconds: Age of cached data in seconds (None if from API).
    """

    result_type: Literal["contacts"] = Field(
        default="contacts", description="Type discriminator for serialization"
    )
    contacts: list[dict[str, Any]] = Field(
        default_factory=list, description="List of contacts with name, email, phone, etc."
    )
    total_count: int = Field(description="Total number of contacts in results")
    has_more: bool = Field(default=False, description="Whether pagination has more results")
    query: str | None = Field(default=None, description="Original search query (if applicable)")

    # Freshness transparency metadata
    # Data Registry Mode (BugFix 2025-11-26): Added "data_registry" as valid data_source
    # for when data is extracted from data registry items instead of direct API/cache
    data_source: Literal["api", "cache", "data_registry"] = Field(
        default="api",
        description="Source of data: 'api' for real-time API fetch, 'cache' for Redis cache hit, 'data_registry' for Data Registry mode extraction",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp when data was fetched (UTC)",
    )
    cache_age_seconds: int | None = Field(
        default=None,
        description="Age of cached data in seconds (None if data_source='api')",
    )


class EmailsResultData(AgentResultData):
    """
    Result data structure for Gmail Agent.

    Attributes:
        result_type: Type discriminator for serialization.
        emails: List of email dictionaries from Gmail API.
        total: Total number of emails returned.
        query: Original search query (if applicable).
        data_source: Source of data ("api" for real-time, "cache" for Redis).
        timestamp: ISO 8601 timestamp when data was fetched.
        cache_age_seconds: Age of cached data in seconds (None if from API).
    """

    result_type: Literal["emails"] = Field(
        default="emails", description="Type discriminator for serialization"
    )
    emails: list[dict[str, Any]] = Field(
        default_factory=list, description="List of emails with subject, from, to, body, etc."
    )
    total: int = Field(description="Total number of emails in results")
    query: str | None = Field(default=None, description="Original search query (if applicable)")

    # Freshness transparency metadata
    # Data Registry Mode (BugFix 2025-11-26): Added "data_registry" as valid data_source
    data_source: Literal["api", "cache", "data_registry"] = Field(
        default="api",
        description="Source of data: 'api' for real-time API fetch, 'cache' for Redis cache hit, 'data_registry' for Data Registry mode extraction",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp when data was fetched (UTC)",
    )
    cache_age_seconds: int | None = Field(
        default=None,
        description="Age of cached data in seconds (None if data_source='api')",
    )


class PlacesResultData(AgentResultData):
    """
    Result data structure for Places Agent.

    Attributes:
        result_type: Type discriminator for serialization.
        places: List of place dictionaries from Google Places API.
        total_count: Total number of places returned.
        query: Original search query (if applicable).
        location: Location used for the search (if applicable).
        data_source: Source of data ("api" for real-time, "cache" for Redis).
        timestamp: ISO 8601 timestamp when data was fetched.
        cache_age_seconds: Age of cached data in seconds (None if from API).
    """

    result_type: Literal["places"] = Field(
        default="places", description="Type discriminator for serialization"
    )
    places: list[dict[str, Any]] = Field(
        default_factory=list, description="List of places with name, address, rating, etc."
    )
    total_count: int = Field(default=0, description="Total number of places in results")
    query: str | None = Field(default=None, description="Original search query (if applicable)")
    location: str | None = Field(default=None, description="Location used for search")

    # Freshness transparency metadata
    data_source: Literal["api", "cache", "data_registry"] = Field(
        default="api",
        description="Source of data: 'api' for real-time API fetch, 'cache' for Redis cache hit, 'data_registry' for Data Registry mode extraction",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp when data was fetched (UTC)",
    )
    cache_age_seconds: int | None = Field(
        default=None,
        description="Age of cached data in seconds (None if data_source='api')",
    )


class MultiDomainResultData(AgentResultData):
    """
    Result data structure for multi-domain planner results.

    Used when a plan returns results from multiple domains (e.g., contacts + emails + places).
    Keeps all data in a generic format for response_node to format intelligently.

    Attributes:
        result_type: Type discriminator for serialization.
        contacts: List of contact dictionaries.
        contacts_total: Total number of contacts.
        emails: List of email dictionaries.
        emails_total: Total number of emails.
        places: List of place dictionaries.
        places_total: Total number of places.
        completed_steps: Map of step_id -> step result data.
        step_results: Raw list of all step results.
    """

    result_type: Literal["multi_domain"] = Field(
        default="multi_domain", description="Type discriminator for serialization"
    )

    # Contacts data
    contacts: list[dict[str, Any]] = Field(
        default_factory=list, description="List of contacts from contacts domain"
    )
    contacts_total: int = Field(default=0, description="Total number of contacts")

    # Emails data
    emails: list[dict[str, Any]] = Field(
        default_factory=list, description="List of emails from emails domain"
    )
    emails_total: int = Field(default=0, description="Total number of emails")

    # Places data
    places: list[dict[str, Any]] = Field(
        default_factory=list, description="List of places from places domain"
    )
    places_total: int = Field(default=0, description="Total number of places")

    # Metadata
    plan_id: str | None = Field(default=None, description="Execution plan ID")
    completed_steps: dict[str, Any] = Field(
        default_factory=dict, description="Map of step_id -> step result"
    )
    total_steps: int = Field(default=0, description="Total steps executed")
    execution_time_ms: int = Field(default=0, description="Total execution time")

    # Freshness transparency metadata
    # Data Registry Mode (BugFix 2025-11-26): Added "data_registry" as valid data_source
    data_source: Literal["api", "cache", "data_registry"] = Field(
        default="api",
        description="Source of data: 'api' for real-time API fetch, 'cache' for Redis cache hit, 'data_registry' for Data Registry mode extraction",
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO 8601 timestamp when data was fetched (UTC)",
    )


class AgentResult(BaseModel):
    """
    Standardized result structure for all agents.

    Phase 3.2.5: Migrated from TypedDict to BaseModel for runtime validation.

    Used to maintain consistent result format across different agent types.
    Stored in MessagesState.agent_results dictionary.

    Attributes:
        agent_name: Name of the agent (e.g., contacts_agent, emails_agent).
        status: Execution status (success, error, connector_disabled, pending, failed).
        data: Agent-specific result data (ContactsResultData, dict, or None).
        error: Error message if status is error or connector_disabled.
        tokens_in: Input tokens consumed by agent LLM (for cost tracking).
        tokens_out: Output tokens generated by agent LLM.
        duration_ms: Execution duration in milliseconds.

    Example:
        >>> result = AgentResult(
        ...     agent_name="contacts_agent",
        ...     status="success",
        ...     data=ContactsResultData(contacts=[...], total_count=5, has_more=False),
        ...     error=None,
        ...     tokens_in=150,
        ...     tokens_out=300,
        ...     duration_ms=1250
        ... )
    """

    agent_name: str = Field(description="Agent name (e.g., contacts_agent, emails_agent)")
    status: Literal["success", "error", "connector_disabled", "pending", "failed"] = Field(
        description="Execution status"
    )
    data: (
        ContactsResultData
        | EmailsResultData
        | PlacesResultData
        | MultiDomainResultData
        | dict[str, Any]
        | None
    ) = Field(default=None, description="Agent-specific result data")
    error: str | None = Field(default=None, description="Error message if failed")
    tokens_in: int = Field(default=0, description="Input tokens consumed")
    tokens_out: int = Field(default=0, description="Output tokens generated")
    duration_ms: int = Field(default=0, description="Execution duration in ms")
    # Data Registry LOT 5.2: Registry updates from tool executions
    # Used by response_node to filter registry items by current turn
    registry_updates: dict[str, Any] | None = Field(
        default=None,
        description="Registry updates from tool executions (item_id → RegistryItem dict)",
    )

    model_config = {"frozen": False}  # Allow modification if needed


class OrchestratorPlan(BaseModel):
    """
    Execution plan created by TaskOrchestrator.

    Defines which agents to call and how to execute them (sequential vs parallel).

    Version 1 (current): Sequential execution only.
    Version 2 (future): Parallel execution with dependency management.

    Attributes:
        agents_to_call: List of agent names to execute (e.g., ["contacts_agent", "emails_agent"]).
        execution_mode: Mode of execution (sequential for V1, parallel planned for V2).
        metadata: Additional context (version, intention, confidence, etc.).

    Example V1 (sequential):
        >>> plan = OrchestratorPlan(
        ...     agents_to_call=["contacts_agent"],
        ...     execution_mode="sequential",
        ...     metadata={"version": "v1_sequential", "intention": "contacts_search"}
        ... )

    Example V2 (future - parallel):
        >>> plan = OrchestratorPlan(
        ...     agents_to_call=["contacts_agent", "emails_agent"],
        ...     execution_mode="parallel",
        ...     metadata={
        ...         "version": "v2_parallel",
        ...         "dependencies": {"emails_agent": []}  # No dependencies
        ...     }
        ... )
    """

    agents_to_call: list[str] = Field(
        description="List of agent names to execute in order (V1) or parallel (V2)"
    )
    execution_mode: Literal["sequential", "parallel"] = Field(
        description="Execution mode: sequential (V1) or parallel (V2 future)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context: version, intention, confidence, dependencies (V2)",
    )

    model_config = {"frozen": False}  # Allow modification during execution


# ============================================================================
# Step Execution Results (extracted from plan_executor.py)
# ============================================================================


class StepResult(BaseModel):
    """
    Result of executing a single step.

    Extracted from plan_executor.py during legacy cleanup.

    Attributes:
        step_index: Step index in plan
        tool_name: Name of executed tool
        args: Resolved arguments used
        result: Tool response dict
        success: True if step succeeded
        error: Error message if failed
        error_code: Error code if failed
        execution_time_ms: Execution time in milliseconds
        hitl_approved: True if HITL approved (None if no HITL)
    """

    step_index: int
    tool_name: str
    args: dict[str, Any]
    result: dict[str, Any] | None = None
    success: bool = True
    error: str | None = None
    error_code: ToolErrorCode | None = None
    execution_time_ms: int = 0
    hitl_approved: bool | None = None

    model_config = {"frozen": False}


class ExecutionResult(BaseModel):
    """
    Result of executing a complete plan.

    Extracted from plan_executor.py during legacy cleanup.

    Attributes:
        success: True if plan executed successfully
        step_results: List of step results
        total_steps: Total number of steps
        completed_steps: Number of completed steps
        failed_step_index: Index of failed step (None if success)
        error: Global error message if failed
        error_code: Error code if failed
        total_execution_time_ms: Total execution time
        executed_at: Execution timestamp
    """

    success: bool
    step_results: list[StepResult] = Field(default_factory=list)
    total_steps: int = 0
    completed_steps: int = 0
    failed_step_index: int | None = None
    error: str | None = None
    error_code: ToolErrorCode | None = None
    total_execution_time_ms: int = 0
    executed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"frozen": False}


# ============================================================================
# Helper Functions
# ============================================================================


# Helper function for creating empty AgentResult (pending state)
def create_pending_agent_result(agent_name: str) -> AgentResult:
    """
    Create an AgentResult in pending state.

    Phase 3.2.5: Updated to work with Pydantic BaseModel.

    Args:
        agent_name: Name of the agent.

    Returns:
        AgentResult with status="pending" and zero metrics.
    """
    return AgentResult(
        agent_name=agent_name,
        status="pending",
        data=None,
        error=None,
        tokens_in=0,
        tokens_out=0,
        duration_ms=0,
    )
