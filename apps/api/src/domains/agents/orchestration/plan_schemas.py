"""
DSL for multi-agent execution plans.

This module defines the Domain-Specific Language (DSL) of the execution plans
the LLM planner generates and the validator checks.

The DSL supports:
- Multi-step execution (sequential or conditional steps)
- Multiple agents (each step names its agent)
- Dependencies between steps ($steps.X.field references a result)
- Conditions (branching on results)
- HITL (Human-In-The-Loop) for the user's approval
- Error handling (on_fail actions)

Architecture:
- ExecutionStep: one step of the plan (TOOL, CONDITIONAL, REPLAN, HUMAN)
- ExecutionPlan: the whole plan with its metadata (version, cost, timeout)
- StepType: the supported step types
- PlanValidationError: a plan validation error

Usage:
    from .plan_schemas import ExecutionPlan, ExecutionStep, StepType

    plan = ExecutionPlan(
        plan_id="plan_123",
        user_id="user_456",
        steps=[
            ExecutionStep(
                step_id="step_1",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="search_contacts_tool",
                parameters={"query": "John"},
            ),
            ExecutionStep(
                step_id="step_2",
                step_type=StepType.TOOL,
                agent_name="contacts_agent",
                tool_name="get_contact_details_tool",
                parameters={"resource_name": "$steps.step_1.contacts[0].resource_name"},
                depends_on=["step_1"],
            ),
        ],
        execution_mode="sequential",
        max_cost_usd=1.0,
    )

Compliance: LangGraph v1.0 + Pydantic v2 validation
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.config import settings
from src.core.field_names import FIELD_AGENT_NAME, FIELD_STEP_ID, FIELD_TOOL_NAME

# ============================================================================
# Parameter Types (OpenAI Strict Mode Compatible)
# ============================================================================


class ParameterValue(BaseModel):
    """
    A single parameter value for tool execution.

    OpenAI strict mode requires all object types to have defined properties.
    This class provides a strict-compatible representation for dynamic parameter values.

    Uses ``extra="forbid"`` to generate ``additionalProperties: false``
    in JSON schema, required by OpenAI strict structured output mode.

    The value can be:
    - string: For text values, JSON references ($steps.X), dates, etc.
    - number: For numeric values
    - boolean: For true/false flags
    - null: For unset/optional values

    Complex values (arrays, nested objects) should be serialized as JSON strings
    in the string_value field with value_type="json".

    Attributes:
        string_value: String representation of the value (used for all types)
        value_type: Type hint for deserialization ("string", "number", "boolean", "null", "json")
    """

    model_config = ConfigDict(extra="forbid")

    string_value: str | None = Field(
        default=None,
        description="String representation of the value. For non-string types, "
        "this is the serialized form (e.g., '123' for numbers, 'true' for booleans, "
        '\'{"key": "value"}\' for JSON objects/arrays).',
    )
    value_type: str = Field(
        default="string",
        description="Type of the value: 'string', 'number', 'boolean', 'null', or 'json' "
        "(for complex objects/arrays serialized as JSON).",
    )

    def to_python_value(self) -> Any:
        """
        Convert to Python native value based on value_type.

        Returns:
            Deserialized Python value
        """
        import json

        if self.string_value is None or self.value_type == "null":
            return None
        if self.value_type == "string":
            return self.string_value
        if self.value_type == "number":
            # Try int first, then float
            try:
                return int(self.string_value)
            except ValueError:
                return float(self.string_value)
        if self.value_type == "boolean":
            return self.string_value.lower() in ("true", "1", "yes")
        if self.value_type == "json":
            return json.loads(self.string_value)
        return self.string_value


class ParameterItem(BaseModel):
    """
    A single named parameter for tool execution.

    OpenAI strict mode requires object types to have defined properties.
    Using a list of ParameterItem instead of dict[str, Any] ensures strict compatibility.

    Attributes:
        name: Parameter name (e.g., "query", "contact_id", "limit")
        value: Parameter value with type information
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="Parameter name (e.g., 'query', 'contact_id', 'limit')")
    value: ParameterValue = Field(
        default_factory=lambda: ParameterValue(string_value=None, value_type="null"),
        description="Parameter value with type information",
    )


def parameters_to_dict(parameters: list[ParameterItem]) -> dict[str, Any]:
    """
    Convert list of ParameterItem to dict for tool execution.

    Args:
        parameters: List of ParameterItem

    Returns:
        Dict mapping parameter names to Python values
    """
    return {p.name: p.value.to_python_value() for p in parameters}


# ============================================================================
# Step Types
# ============================================================================


class StepType(str, Enum):
    """
    Step types an ExecutionPlan supports.

    MVP (Phase 1):
    - TOOL: runs a tool through an agent
    - CONDITIONAL: branches on results

    Future (Phase 2):
    - REPLAN: the LLM planner regenerates the plan
    - HUMAN: asks for a HITL (Human-In-The-Loop) approval

    Attributes:
        TOOL: a tool call through an agent
        CONDITIONAL: evaluates a condition to branch
        REPLAN: asks for a new plan (future)
        HUMAN: interrupts for a human approval (future)
    """

    TOOL = "TOOL"
    CONDITIONAL = "CONDITIONAL"
    REPLAN = "REPLAN"  # Phase 2
    HUMAN = "HUMAN"  # Phase 2


# ============================================================================
# Execution Step
# ============================================================================

#: Fields without which a step of a given type cannot be executed.
#:
#: Every ``StepType`` is listed, including those requiring nothing: an empty
#: entry is a decision, an absent one is an oversight (ADR-085 doctrine). The
#: assert below refuses to import the module if a type is added without one, so
#: the question gets asked at the moment the type is created rather than the
#: first time a plan carrying it fails somewhere else.
_REQUIRED_FIELDS_BY_STEP_TYPE: dict[StepType, frozenset[str]] = {
    StepType.TOOL: frozenset({FIELD_AGENT_NAME, FIELD_TOOL_NAME}),
    StepType.CONDITIONAL: frozenset({"condition"}),
    StepType.REPLAN: frozenset(),
    StepType.HUMAN: frozenset(),
}

assert set(_REQUIRED_FIELDS_BY_STEP_TYPE) == set(StepType), (
    "_REQUIRED_FIELDS_BY_STEP_TYPE must list every StepType — missing: "
    f"{sorted(t.value for t in StepType if t not in _REQUIRED_FIELDS_BY_STEP_TYPE)}. "
    "Use frozenset() to declare that a type requires nothing."
)


class ExecutionStep(BaseModel):
    """
    One execution step of a multi-agent plan.

    An atomic action to run:
    - a tool call through an agent (TOOL)
    - a conditional branch (CONDITIONAL)
    - a new plan (REPLAN, future)
    - a human approval (HUMAN, future)

    Mutable on purpose (``frozen=False``): steps may be adjusted during execution.

    Attributes:
        step_id: Unique step identifier (e.g. "step_1", "step_2")
        step_type: Step type (TOOL, CONDITIONAL, etc.)
        agent_name: The agent in charge (e.g. "contacts_agent")
        tool_name: The tool to run (when step_type=TOOL)
        parameters: Tool parameters (may contain $steps.X references)
        depends_on: The step_ids this step depends on
        condition: Conditional expression (when step_type=CONDITIONAL)
        on_success: Step_id to run on success (for CONDITIONAL)
        on_fail: Step_id to run on failure (for CONDITIONAL)
        timeout_seconds: Execution timeout (None = no timeout)
        approvals_required: When True, HITL approval is required
        description: Text description of the step (for UI/logs)

    Examples:
        >>> # TOOL step
        >>> step1 = ExecutionStep(
        ...     step_id="step_1",
        ...     step_type=StepType.TOOL,
        ...     agent_name="contacts_agent",
        ...     tool_name="search_contacts_tool",
        ...     parameters={"query": "John"},
        ...     description="Search contacts named John"
        ... )

        >>> # TOOL step with reference
        >>> step2 = ExecutionStep(
        ...     step_id="step_2",
        ...     step_type=StepType.TOOL,
        ...     agent_name="contacts_agent",
        ...     tool_name="get_contact_details_tool",
        ...     parameters={"resource_name": "$steps.step_1.contacts[0].resource_name"},
        ...     depends_on=["step_1"],
        ...     description="Get the details of the first contact found"
        ... )

        >>> # CONDITIONAL step
        >>> step3 = ExecutionStep(
        ...     step_id="step_3",
        ...     step_type=StepType.CONDITIONAL,
        ...     condition="len($steps.step_1.contacts) > 1",
        ...     on_success="step_4",
        ...     on_fail="step_5",
        ...     depends_on=["step_1"],
        ...     description="Check whether several contacts were found"
        ... )
    """

    # Note: frozen=False because steps may need modification during execution
    # (e.g., resolved parameters, execution metadata)

    step_id: str = Field(description="Unique step identifier (e.g. 'step_1', 'search_contacts')")
    step_type: StepType = Field(description="Step type (TOOL, CONDITIONAL, etc.)")
    agent_name: str | None = Field(default=None, description="Agent name (required for TOOL)")
    tool_name: str | None = Field(default=None, description="Tool name (required for TOOL)")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Tool parameters (may contain $steps.X references)",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="The step_ids this step depends on",
    )
    condition: str | None = Field(
        default=None,
        description="Safe Python conditional expression (required for CONDITIONAL)",
    )
    on_success: str | None = Field(
        default=None, description="Step_id to run when the condition is True"
    )
    on_fail: str | None = Field(
        default=None, description="Step_id to run when the condition is False or fails"
    )
    timeout_seconds: int | None = Field(
        default=None, description="Execution timeout in seconds (None = no timeout)"
    )
    approvals_required: bool = Field(
        default=False,
        description="When True, HITL approval is required before execution",
    )
    description: str = Field(default="", description="Text description of the step (for UI/logs)")

    # =========================================================================
    # FOR_EACH PATTERN SUPPORT (Phase: plan_planner.md Section 4.1)
    # =========================================================================
    # Enables dynamic iteration over results from previous steps.
    # When for_each is set, the step is expanded at runtime into N steps,
    # one for each item in the referenced collection.
    # =========================================================================
    for_each: str | None = Field(
        default=None,
        description="Reference to array to iterate over. E.g., '$steps.get_hotels.places'. "
        "When set, this step is expanded at runtime into N parallel steps.",
    )
    for_each_max: int = Field(
        default_factory=lambda: settings.for_each_max_default,
        ge=1,
        le=settings.for_each_max_hard_limit,
        description=f"Maximum items to process (safety limit). Default {settings.for_each_max_default}, max {settings.for_each_max_hard_limit}.",
    )
    on_item_error: Literal["continue", "stop", "collect_errors"] = Field(
        default="continue",
        description="Behavior on item error during for_each iteration: "
        "'continue' (skip failed, continue others), "
        "'stop' (abort all on first failure), "
        "'collect_errors' (continue but collect all errors).",
    )
    delay_between_items_ms: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Delay in milliseconds between items for API rate limiting. "
        "0 = parallel execution, >0 = sequential with delay.",
    )

    @property
    def is_for_each_step(self) -> bool:
        """Check if this step uses for_each pattern."""
        return self.for_each is not None

    @field_validator(FIELD_STEP_ID)
    @classmethod
    def validate_step_id(cls, v: str) -> str:
        """Validate that step_id is non-empty and has no spaces."""
        if not v or not v.strip():
            raise ValueError("step_id cannot be empty")
        if " " in v:
            raise ValueError("step_id cannot contain spaces")
        return v.strip()

    @model_validator(mode="after")
    def validate_fields_required_by_step_type(self) -> ExecutionStep:
        """Enforce the fields each step type cannot work without.

        Deliberately a MODEL validator, not three field validators. Pydantic
        does not validate default values, so a field validator on an optional
        field never runs when the field is simply omitted — which is how a TOOL
        step without ``agent_name`` used to be accepted, at step level AND at
        plan level (measured; the previous test called it "by design").

        It was not harmless. Serialized, the field is written explicitly as
        None; on the way back the validator DOES fire, the constructor raises,
        and the serializer falls back to handing out a plain ``dict`` — with no
        error anywhere. ``parallel_executor`` then reads ``step.step_id`` on a
        mapping and dies far from the cause. Refusing the object here turns a
        silent corruption into an immediate, located failure (ADR-195).

        Returns:
            The validated step.

        Raises:
            ValueError: A field required by this step type is missing or empty.
        """
        missing = sorted(
            field
            for field in _REQUIRED_FIELDS_BY_STEP_TYPE[self.step_type]
            if not getattr(self, field, None)
        )
        if missing:
            raise ValueError(
                f"{', '.join(missing)} required for {self.step_type.value} steps "
                f"(step_id={self.step_id!r})"
            )
        return self

    model_config = {"frozen": False}  # Allow modification during execution


class ExecutionPlan(BaseModel):
    """
    A complete multi-agent execution plan.

    Generated by the LLM planner, checked by the validator, run by the orchestrator.

    Mutable on purpose (``frozen=False``): steps may be adjusted during execution.

    Attributes:
        plan_id: Unique plan identifier (UUID)
        user_id: The user's ID (for permissions and context)
        session_id: Session ID (for conversational continuity)
        steps: Ordered steps to run
        execution_mode: Execution mode ("sequential" for the MVP, "parallel" in future)
        max_cost_usd: Maximum allowed cost (validation)
        estimated_cost_usd: Estimated cost, from the manifests
        max_timeout_seconds: Global plan timeout
        version: DSL format version (semver)
        created_at: Creation timestamp
        metadata: Additional metadata (query, intention, etc.)

    Examples:
        >>> plan = ExecutionPlan(
        ...     plan_id=str(uuid4()),
        ...     user_id="user_123",
        ...     session_id="sess_456",
        ...     steps=[
        ...         ExecutionStep(step_id="step_1", step_type=StepType.TOOL, ...),
        ...         ExecutionStep(step_id="step_2", step_type=StepType.TOOL, ...),
        ...     ],
        ...     execution_mode="sequential",
        ...     max_cost_usd=1.0,
        ...     estimated_cost_usd=0.002,
        ... )
    """

    # Note: frozen=False because plans may need modification during execution
    # (e.g., tracking execution state, adding results)

    plan_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique plan identifier (UUID)",
    )
    user_id: str = Field(description="User ID (for permissions and context)")
    session_id: str = Field(default="", description="Session ID (for conversational continuity)")
    steps: list[ExecutionStep] = Field(
        default_factory=list,
        description="Ordered steps to run. EMPTY when metadata has needs_clarification=True.",
    )
    execution_mode: Literal["sequential", "parallel"] = Field(
        default="sequential",
        description="Execution mode (sequential for the MVP, parallel in future)",
    )
    max_cost_usd: float | None = Field(
        default=None, description="Maximum allowed cost (None = no limit)"
    )
    estimated_cost_usd: float = Field(default=0.0, description="Estimated cost, from the manifests")
    max_timeout_seconds: int | None = Field(
        default=None, description="Global plan timeout (None = no timeout)"
    )
    version: str = Field(default="1.0.0", description="DSL format version (semver)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Creation timestamp (UTC)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (query, intention, router_output, etc.)",
        json_schema_extra={"additionalProperties": True},
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_not_empty(cls, v: list[ExecutionStep]) -> list[ExecutionStep]:
        """
        Check there is at least one step.

        Note: Empty steps allowed if needs_clarification=True in metadata.
        This is validated in model_validator below since metadata comes after steps.
        """
        # Defer to model_validator for cross-field validation
        return v

    @field_validator("steps")
    @classmethod
    def validate_step_ids_unique(cls, v: list[ExecutionStep]) -> list[ExecutionStep]:
        """Validate that step_ids are unique."""
        step_ids = [step.step_id for step in v]
        if len(step_ids) != len(set(step_ids)):
            duplicates = [sid for sid in step_ids if step_ids.count(sid) > 1]
            raise ValueError(f"Duplicate step_ids found: {duplicates}")
        return v

    @field_validator("max_cost_usd")
    @classmethod
    def validate_max_cost_positive(cls, v: float | None) -> float | None:
        """Validate that max_cost_usd is positive if provided."""
        if v is not None and v < 0:
            raise ValueError("max_cost_usd must be >= 0")
        return v

    @field_validator("estimated_cost_usd")
    @classmethod
    def validate_estimated_cost_positive(cls, v: float) -> float:
        """Validate that estimated_cost_usd is positive."""
        if v < 0:
            raise ValueError("estimated_cost_usd must be >= 0")
        return v

    @model_validator(mode="after")
    def validate_steps_or_clarification(self) -> ExecutionPlan:
        """
        Validate that plan has steps OR a documented reason for being empty.

        A plan must either:
        - Have at least one step (normal execution), OR
        - Have metadata.needs_clarification=True (awaiting user clarification), OR
        - Have metadata.skill_bypass_noop=True (execution delegated to the
          ReactSubAgentRunner for a script-only skill; the planner intentionally
          returns an empty plan so the task_orchestrator short-circuits and the
          response_node takes over).
        """
        if not self.steps:
            needs_clarification = self.metadata.get("needs_clarification", False)
            skill_bypass_noop = self.metadata.get("skill_bypass_noop", False)
            if not (needs_clarification or skill_bypass_noop):
                raise ValueError(
                    "Plan must contain at least one step, or metadata.needs_clarification "
                    "or metadata.skill_bypass_noop must be True"
                )
        return self

    model_config = {"frozen": False}  # Allow modification during execution


# ============================================================================
# Validation Errors
# ============================================================================


class PlanValidationError(Exception):
    """
    Validation error of an ExecutionPlan.

    Raised by the validator when a plan breaks a constraint:
    - invalid structure
    - cyclic dependencies
    - missing permissions
    - cost exceeded
    - dangerous conditions

    Attributes:
        message: Descriptive error message
        code: Standardised error code
        details: Additional details (dict)
    """

    def __init__(
        self, message: str, code: str | None = None, details: dict[str, Any] | None = None
    ) -> None:
        """
        Initialize the validation error.

        Args:
            message: Descriptive error message
            code: Standardized error code (e.g., "INVALID_STRUCTURE")
            details: Additional details for debugging
        """
        self.message = message
        self.code = code or "VALIDATION_ERROR"
        self.details = details or {}
        super().__init__(self.message)


__all__ = [
    "ExecutionPlan",
    "ExecutionStep",
    "PlanValidationError",
    "StepType",
]
