"""
DSL pour plans d'exécution multi-agents.

Ce module définit le Domain-Specific Language (DSL) pour les plans d'exécution
générés par le planner LLM et validés par le validator.

Le DSL supporte:
- Exécution multi-étapes (steps séquentiels ou conditionnels)
- Multi-agents (chaque step spécifie son agent)
- Dépendances entre steps ($steps.X.field pour référencer résultats)
- Conditions (branching basé sur résultats)
- HITL (Human-In-The-Loop) pour approbation utilisateur
- Gestion d'erreurs (on_fail actions)

Architecture:
- ExecutionStep: Une étape du plan (TOOL, CONDITIONAL, REPLAN, HUMAN)
- ExecutionPlan: Plan complet avec métadonnées (version, coût, timeout)
- StepType: Types d'étapes supportées
- PlanValidationError: Erreur de validation de plan

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
                parameters={"resource_name": "$steps.0.contacts[0].resource_name"},
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

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from src.core.config import settings
from src.core.field_names import FIELD_AGENT_NAME, FIELD_STEP_ID

# ============================================================================
# Parameter Types (OpenAI Strict Mode Compatible)
# ============================================================================


class ParameterValue(BaseModel):
    """
    A single parameter value for tool execution.

    OpenAI strict mode requires all object types to have defined properties.
    This class provides a strict-compatible representation for dynamic parameter values.

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

    @classmethod
    def from_python_value(cls, value: Any) -> ParameterValue:
        """
        Create ParameterValue from Python native value.

        Args:
            value: Any Python value

        Returns:
            ParameterValue instance
        """
        import json

        if value is None:
            return cls(string_value=None, value_type="null")
        if isinstance(value, bool):
            return cls(string_value=str(value).lower(), value_type="boolean")
        if isinstance(value, int | float):
            return cls(string_value=str(value), value_type="number")
        if isinstance(value, str):
            return cls(string_value=value, value_type="string")
        # Complex types -> JSON
        return cls(string_value=json.dumps(value), value_type="json")


class ParameterItem(BaseModel):
    """
    A single named parameter for tool execution.

    OpenAI strict mode requires object types to have defined properties.
    Using a list of ParameterItem instead of dict[str, Any] ensures strict compatibility.

    Attributes:
        name: Parameter name (e.g., "query", "contact_id", "limit")
        value: Parameter value with type information
    """

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


def dict_to_parameters(params: dict[str, Any]) -> list[ParameterItem]:
    """
    Convert dict to list of ParameterItem for LLM output.

    Args:
        params: Dict of parameter name -> value

    Returns:
        List of ParameterItem
    """
    return [
        ParameterItem(name=k, value=ParameterValue.from_python_value(v)) for k, v in params.items()
    ]


# ============================================================================
# Step Types
# ============================================================================


class StepType(str, Enum):
    """
    Types d'étapes supportées dans un ExecutionPlan.

    MVP (Phase 1):
    - TOOL: Exécution d'un tool via agent
    - CONDITIONAL: Branchement conditionnel basé sur résultats

    Future (Phase 2):
    - REPLAN: Regénération de plan par le planner LLM
    - HUMAN: Demande d'approbation HITL (Human-In-The-Loop)

    Attributes:
        TOOL: Appel d'un tool via un agent
        CONDITIONAL: Évaluation d'une condition pour branching
        REPLAN: Demande de re-planification (future)
        HUMAN: Interruption pour approbation humaine (future)
    """

    TOOL = "TOOL"
    CONDITIONAL = "CONDITIONAL"
    REPLAN = "REPLAN"  # Phase 2
    HUMAN = "HUMAN"  # Phase 2


# ============================================================================
# Execution Step
# ============================================================================


class ExecutionStep(BaseModel):
    """
    Une étape d'exécution dans un plan multi-agents.

    Représente une action atomique à exécuter :
    - Appel d'un tool via un agent (TOOL)
    - Branchement conditionnel (CONDITIONAL)
    - Re-planification (REPLAN, future)
    - Approbation humaine (HUMAN, future)

    Phase 3.2.8.2: Frozen model for performance (immutable after creation).

    Attributes:
        step_id: Identifiant unique du step (ex: "step_1", "step_2")
        step_type: Type de step (TOOL, CONDITIONAL, etc.)
        agent_name: Nom de l'agent responsable (ex: "contacts_agent")
        tool_name: Nom du tool à exécuter (si step_type=TOOL)
        parameters: Paramètres du tool (peut contenir références $steps.X)
        depends_on: Liste des step_ids dont dépend ce step
        condition: Expression conditionnelle (si step_type=CONDITIONAL)
        on_success: Step_id à exécuter si succès (pour CONDITIONAL)
        on_fail: Step_id à exécuter si échec (pour CONDITIONAL)
        timeout_seconds: Timeout d'exécution (None = pas de timeout)
        approvals_required: Si True, nécessite approbation HITL
        description: Description textuelle du step (pour UI/logs)

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
        ...     parameters={"resource_name": "$steps.0.contacts[0].resource_name"},
        ...     depends_on=["step_1"],
        ...     description="Récupérer détails du premier contact trouvé"
        ... )

        >>> # CONDITIONAL step
        >>> step3 = ExecutionStep(
        ...     step_id="step_3",
        ...     step_type=StepType.CONDITIONAL,
        ...     condition="len($steps.0.contacts) > 1",
        ...     on_success="step_4",
        ...     on_fail="step_5",
        ...     depends_on=["step_1"],
        ...     description="Vérifier si plusieurs contacts trouvés"
        ... )
    """

    # Note: frozen=False because steps may need modification during execution
    # (e.g., resolved parameters, execution metadata)

    step_id: str = Field(description="Identifiant unique du step (ex: 'step_1', 'search_contacts')")
    step_type: StepType = Field(description="Type de step (TOOL, CONDITIONAL, etc.)")
    agent_name: str | None = Field(default=None, description="Nom de l'agent (requis pour TOOL)")
    tool_name: str | None = Field(default=None, description="Nom du tool (requis pour TOOL)")
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Paramètres du tool (peut contenir références $steps.X)",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Liste des step_ids dont dépend ce step",
    )
    condition: str | None = Field(
        default=None,
        description="Expression conditionnelle Python safe (requis pour CONDITIONAL)",
    )
    on_success: str | None = Field(
        default=None, description="Step_id à exécuter si condition = True"
    )
    on_fail: str | None = Field(
        default=None, description="Step_id à exécuter si condition = False ou erreur"
    )
    timeout_seconds: int | None = Field(
        default=None, description="Timeout d'exécution en secondes (None = pas de timeout)"
    )
    approvals_required: bool = Field(
        default=False,
        description="Si True, nécessite approbation HITL avant exécution",
    )
    description: str = Field(default="", description="Description textuelle du step (pour UI/logs)")

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

    @field_validator(FIELD_AGENT_NAME)
    @classmethod
    def validate_agent_name(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that agent_name is required for TOOL steps."""
        if info.data.get("step_type") == StepType.TOOL and not v:
            raise ValueError("agent_name is required for TOOL steps")
        return v

    @field_validator("tool_name")
    @classmethod
    def validate_tool_name(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that tool_name is required for TOOL steps."""
        if info.data.get("step_type") == StepType.TOOL and not v:
            raise ValueError("tool_name is required for TOOL steps")
        return v

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate that condition is required for CONDITIONAL steps."""
        if info.data.get("step_type") == StepType.CONDITIONAL and not v:
            raise ValueError("condition is required for CONDITIONAL steps")
        return v

    model_config = {"frozen": False}  # Allow modification during execution


# ============================================================================
# LLM-Compatible Step Schema (OpenAI Strict Mode)
# ============================================================================


class ExecutionStepLLM(BaseModel):
    """
    OpenAI Strict Mode compatible version of ExecutionStep for LLM output.

    This schema replaces `dict[str, Any]` fields with `list[ParameterItem]`
    to ensure compatibility with OpenAI's structured output strict mode.

    The main difference from ExecutionStep:
    - `parameters` is `list[ParameterItem]` instead of `dict[str, Any]`

    Use `to_execution_step()` to convert to internal ExecutionStep format.

    Attributes:
        step_id: Unique step identifier
        step_type: Type of step (TOOL, CONDITIONAL, etc.)
        agent_name: Agent name (required for TOOL)
        tool_name: Tool name (required for TOOL)
        parameters: List of parameter items (strict-compatible)
        depends_on: List of step_ids this step depends on
        condition: Conditional expression (for CONDITIONAL)
        on_success: Step_id to execute on success (for CONDITIONAL)
        on_fail: Step_id to execute on failure (for CONDITIONAL)
        timeout_seconds: Execution timeout
        approvals_required: Whether HITL approval is required
        description: Human-readable description
    """

    step_id: str = Field(description="Identifiant unique du step (ex: 'step_1', 'search_contacts')")
    step_type: StepType = Field(description="Type de step (TOOL, CONDITIONAL, etc.)")
    agent_name: str | None = Field(default=None, description="Nom de l'agent (requis pour TOOL)")
    tool_name: str | None = Field(default=None, description="Nom du tool (requis pour TOOL)")
    parameters: list[ParameterItem] = Field(
        default_factory=list,
        description="Liste des paramètres du tool. Chaque paramètre a un 'name' et une 'value' "
        "(avec 'string_value' et 'value_type'). Peut contenir références $steps.X dans string_value.",
    )
    depends_on: list[str] = Field(
        default_factory=list,
        description="Liste des step_ids dont dépend ce step",
    )
    condition: str | None = Field(
        default=None,
        description="Expression conditionnelle Python safe (requis pour CONDITIONAL)",
    )
    on_success: str | None = Field(
        default=None,
        description="Step_id à exécuter si condition = True",
    )
    on_fail: str | None = Field(
        default=None,
        description="Step_id à exécuter si condition = False ou erreur",
    )
    timeout_seconds: int | None = Field(
        default=None,
        description="Timeout d'exécution en secondes (None = pas de timeout)",
    )
    approvals_required: bool = Field(
        default=False,
        description="Si True, nécessite approbation HITL avant exécution",
    )
    description: str = Field(
        default="",
        description="Description textuelle du step (pour UI/logs)",
    )

    # FOR_EACH PATTERN SUPPORT (must mirror ExecutionStep for LLM compatibility)
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
        description="Behavior on item error during for_each iteration.",
    )
    delay_between_items_ms: int = Field(
        default=0,
        ge=0,
        le=10000,
        description="Delay in milliseconds between items for API rate limiting.",
    )

    def to_execution_step(self) -> ExecutionStep:
        """
        Convert to internal ExecutionStep format.

        Converts `list[ParameterItem]` to `dict[str, Any]` for internal use.

        Returns:
            ExecutionStep: Internal format with dict parameters
        """
        return ExecutionStep(
            step_id=self.step_id,
            step_type=self.step_type,
            agent_name=self.agent_name,
            tool_name=self.tool_name,
            parameters=parameters_to_dict(self.parameters),
            depends_on=self.depends_on,
            condition=self.condition,
            on_success=self.on_success,
            on_fail=self.on_fail,
            timeout_seconds=self.timeout_seconds,
            approvals_required=self.approvals_required,
            description=self.description,
            # FOR_EACH fields
            for_each=self.for_each,
            for_each_max=self.for_each_max,
            on_item_error=self.on_item_error,
            delay_between_items_ms=self.delay_between_items_ms,
        )


# ============================================================================
# Execution Plan
# ============================================================================


class ExecutionPlan(BaseModel):
    """
    Plan d'exécution multi-agents complet.

    Généré par le planner LLM, validé par le validator, exécuté par l'orchestrateur.

    Phase 3.2.8.2: Frozen model for performance (immutable after creation).

    Attributes:
        plan_id: Identifiant unique du plan (UUID)
        user_id: ID de l'utilisateur (pour permissions et context)
        session_id: ID de session (pour continuité conversationnelle)
        steps: Liste ordonnée des steps à exécuter
        execution_mode: Mode d'exécution ("sequential" pour MVP, "parallel" future)
        max_cost_usd: Coût maximum autorisé (validation)
        estimated_cost_usd: Coût estimé basé sur manifests
        max_timeout_seconds: Timeout global du plan
        version: Version du format DSL (semver)
        created_at: Timestamp de création
        metadata: Métadonnées additionnelles (query, intention, etc.)

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
        description="Identifiant unique du plan (UUID)",
    )
    user_id: str = Field(description="ID utilisateur (pour permissions et context)")
    session_id: str = Field(
        default="", description="ID session (pour continuité conversationnelle)"
    )
    steps: list[ExecutionStep] = Field(
        default_factory=list,
        description="Liste ordonnée des steps à exécuter. VIDE si needs_clarification=True dans metadata.",
    )
    execution_mode: Literal["sequential", "parallel"] = Field(
        default="sequential",
        description="Mode d'exécution (sequential pour MVP, parallel future)",
    )
    max_cost_usd: float | None = Field(
        default=None, description="Coût maximum autorisé (None = pas de limite)"
    )
    estimated_cost_usd: float = Field(default=0.0, description="Coût estimé basé sur manifests")
    max_timeout_seconds: int | None = Field(
        default=None, description="Timeout global du plan (None = pas de timeout)"
    )
    version: str = Field(default="1.0.0", description="Version du format DSL (semver)")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timestamp de création (UTC)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Métadonnées additionnelles (query, intention, router_output, etc.)",
        json_schema_extra={"additionalProperties": True},
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_not_empty(cls, v: list[ExecutionStep]) -> list[ExecutionStep]:
        """
        Valide qu'il y a au moins un step.

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
        Validate that plan has steps OR needs_clarification=True.

        A plan must either:
        - Have at least one step (normal execution), OR
        - Have metadata.needs_clarification=True (awaiting user clarification)

        This allows the planner to return an empty plan when it needs to ask
        the user for missing required parameters.
        """
        if not self.steps:
            needs_clarification = self.metadata.get("needs_clarification", False)
            if not needs_clarification:
                raise ValueError(
                    "Plan must contain at least one step, or metadata.needs_clarification must be True"
                )
        return self

    model_config = {"frozen": False}  # Allow modification during execution


# ============================================================================
# Validation Errors
# ============================================================================


class PlanValidationError(Exception):
    """
    Erreur de validation d'un ExecutionPlan.

    Levée par le validator lorsqu'un plan ne respecte pas les contraintes:
    - Structure invalide
    - Dépendances cycliques
    - Permissions manquantes
    - Coût dépassé
    - Conditions dangereuses

    Attributes:
        message: Message d'erreur descriptif
        code: Code d'erreur standardisé
        details: Détails additionnels (dict)
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


# ============================================================================
# LLM Output Schema (Structured Output - Phase 2)
# ============================================================================


class ExecutionPlanLLMOutput(BaseModel):
    """
    Schema for LLM-generated execution plan output.

    This schema is specifically designed for use with `with_structured_output()`.
    It contains ONLY the fields that the LLM should generate, excluding runtime
    fields like `user_id`, `session_id`, `created_at`, etc.

    Phase 2 - Structured Output Migration:
    - Replaces manual json.loads() + model_validate() pattern
    - Enables native LangChain structured output with automatic retry
    - Multi-provider support (OpenAI, Anthropic, DeepSeek, Ollama)

    After parsing, use `to_execution_plan()` to convert to full `ExecutionPlan`
    with runtime fields injected.

    Usage:
        >>> from src.infrastructure.llm.structured_output import get_structured_output
        >>>
        >>> # Get LLM output with automatic parsing
        >>> llm_output = await get_structured_output(
        ...     llm=llm,
        ...     messages=prompt_messages,
        ...     schema=ExecutionPlanLLMOutput,
        ...     provider="openai",
        ...     node_name="planner",
        ... )
        >>>
        >>> # Convert to full ExecutionPlan with runtime fields
        >>> execution_plan = llm_output.to_execution_plan(
        ...     user_id="user_123",
        ...     session_id="session_456",
        ... )

    Attributes:
        steps: List of execution steps (REQUIRED - LLM must generate)
        execution_mode: Sequential or parallel execution (optional, default: "sequential")
        estimated_cost_usd: Estimated cost (optional, default: 0.0)

    Note:
        Fields NOT included (injected at runtime):
        - plan_id: Generated at conversion (uuid4)
        - user_id: Injected from request context
        - session_id: Injected from request context
        - created_at: Generated at conversion
        - max_cost_usd: Set by system configuration
        - max_timeout_seconds: Set by system configuration
        - version: Set by system
        - metadata: Injected from request context
    """

    steps: list[ExecutionStepLLM] = Field(
        default_factory=list,
        description="Liste ordonnée des steps à exécuter. "
        "Chaque step doit avoir un step_id unique, step_type, et les champs requis selon son type. "
        "Les paramètres utilisent list[ParameterItem] pour compatibilité OpenAI strict mode. "
        "VIDE si needs_clarification=True dans metadata.",
    )
    execution_mode: Literal["sequential", "parallel"] = Field(
        default="sequential",
        description="Mode d'exécution: 'sequential' (défaut) ou 'parallel' (future)",
    )
    estimated_cost_usd: float = Field(
        default=0.0,
        description="Coût estimé en USD basé sur les manifests des tools (optionnel)",
    )
    metadata: list[ParameterItem] = Field(
        default_factory=list,
        description="Métadonnées du plan sous forme de liste de paires nom/valeur. "
        "Inclure un item avec name='needs_clarification' et value.string_value='true' "
        "si un paramètre requis est manquant. "
        "Inclure un item avec name='missing_parameters' pour lister les paramètres manquants.",
    )

    @field_validator("steps")
    @classmethod
    def validate_steps_not_empty(
        cls, v: list[ExecutionStepLLM], info: ValidationInfo
    ) -> list[ExecutionStepLLM]:
        """
        Validate that at least one step is provided.

        Exception: Empty steps is allowed if metadata.needs_clarification=True
        (plan requires clarification from user before generating steps).
        """
        if not v:
            # Check if needs_clarification is True in metadata
            # ValidationInfo.data contains already-validated fields (metadata comes before steps in Pydantic)
            # But metadata is after steps in our definition, so we can't access it here
            # Solution: Use model_validator instead (see below)
            pass  # Defer to model_validator
        return v

    @model_validator(mode="after")
    def validate_steps_or_clarification(self) -> ExecutionPlanLLMOutput:
        """
        Validate that plan has steps OR needs_clarification=True.

        A plan must either:
        - Have at least one step (normal execution), OR
        - Have metadata item with name='needs_clarification' and value='true' (awaiting user clarification)
        """
        if not self.steps:
            # Check if needs_clarification is True in metadata list
            needs_clarification = False
            for item in self.metadata:
                if item.name == "needs_clarification":
                    val = item.value.to_python_value()
                    needs_clarification = val is True or val == "true" or val == "True"
                    break
            if not needs_clarification:
                raise ValueError(
                    "Plan must contain at least one step, or metadata must include "
                    "item with name='needs_clarification' and value.string_value='true'"
                )
        return self

    @field_validator("steps")
    @classmethod
    def validate_step_ids_unique(cls, v: list[ExecutionStepLLM]) -> list[ExecutionStepLLM]:
        """Validate that step_ids are unique."""
        step_ids = [step.step_id for step in v]
        if len(step_ids) != len(set(step_ids)):
            duplicates = [sid for sid in step_ids if step_ids.count(sid) > 1]
            raise ValueError(f"Duplicate step_ids found: {duplicates}")
        return v

    @field_validator("estimated_cost_usd")
    @classmethod
    def validate_estimated_cost_positive(cls, v: float) -> float:
        """Validate that estimated_cost_usd is non-negative."""
        if v < 0:
            raise ValueError("estimated_cost_usd must be >= 0")
        return v

    def to_execution_plan(
        self,
        user_id: str,
        session_id: str = "",
        max_cost_usd: float | None = None,
        max_timeout_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionPlan:
        """
        Convert LLM output to full ExecutionPlan with runtime fields.

        This method injects runtime context (user_id, session_id, timestamps)
        that cannot be generated by the LLM.

        Also converts:
        - ExecutionStepLLM (list[ParameterItem]) → ExecutionStep (dict[str, Any])
        - metadata list[ParameterItem] → dict[str, Any]

        Args:
            user_id: User identifier (from request context)
            session_id: Session identifier (from request context)
            max_cost_usd: Maximum allowed cost (from system settings)
            max_timeout_seconds: Maximum timeout (from system settings)
            metadata: Additional metadata (query, intention, etc.)

        Returns:
            ExecutionPlan: Complete execution plan ready for validation and execution
        """
        # Convert LLM metadata from list[ParameterItem] to dict
        llm_metadata_dict = parameters_to_dict(self.metadata) if self.metadata else {}

        # Merge LLM-generated metadata with runtime metadata
        # LLM metadata (needs_clarification, missing_parameters) takes precedence
        merged_metadata = metadata or {}
        if llm_metadata_dict:
            merged_metadata = {**merged_metadata, **llm_metadata_dict}

        # Convert ExecutionStepLLM (list[ParameterItem]) → ExecutionStep (dict[str, Any])
        converted_steps = [step.to_execution_step() for step in self.steps]

        return ExecutionPlan(
            plan_id=str(uuid4()),
            user_id=user_id,
            session_id=session_id,
            steps=converted_steps,
            execution_mode=self.execution_mode,
            max_cost_usd=max_cost_usd,
            estimated_cost_usd=self.estimated_cost_usd,
            max_timeout_seconds=max_timeout_seconds,
            version="1.0.0",
            created_at=datetime.now(UTC),
            metadata=merged_metadata,
        )

    model_config = {"frozen": True}  # Immutable after LLM generation


__all__ = [
    "ExecutionPlan",
    "ExecutionPlanLLMOutput",
    "ExecutionStep",
    "PlanValidationError",
    "StepType",
]
