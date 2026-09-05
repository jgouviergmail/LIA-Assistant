"""
Declarative catalogue for agents and tools.

This module defines manifests that exhaustively describe agents and tools
available in the system. These manifests serve as a single source of truth for:
- The LLM planner (plan generation)
- The validator (permission, cost, and parameter validation)
- The orchestrator (plan execution)
- Documentation (automatic inventory)

Architecture:
- AgentManifest: Agent description (name, tools, version)
- ToolManifest: Complete tool description (params, outputs, cost, permissions)
- CostProfile: Cost and latency estimation
- PermissionProfile: Scopes, roles, data classification, HITL
- ParameterSchema: Pydantic validation for input parameters
- OutputFieldSchema: Output field documentation

Usage:
    from .catalogue import ToolManifest, AgentManifest, CostProfile

    manifest = ToolManifest(
        name="get_contacts_tool",
        agent="contact_agent",
        description="Search Google contacts",
        parameters=[...],
        cost=CostProfile(est_tokens_in=150, est_tokens_out=400),
        permissions=PermissionProfile(required_scopes=["google_contacts.read"]),
        version="1.0.0",
    )
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, Literal

from src.core.constants import (
    DEFAULT_TOOL_TIMEOUT_MS,
    EXECUTION_MODE_PIPELINE,
    EXECUTION_MODE_REACT,
    MCP_TOOL_NAME_PREFIX,
)
from src.domains.agents.context.schemas import ContextSaveMode

# =============================================================================
# Tool Category for Strategy-Based Filtering
# =============================================================================

ToolCategory = Literal[
    "search",  # Search/get tools - unified category (get_emails, get_contacts, etc.)
    "create",  # Create/add tools (create_event, create_task)
    "update",  # Update/modify tools (update_event, update_contact)
    "delete",  # Delete/remove tools (delete_event, delete_task)
    "send",  # Send/communicate tools (send_email, send_notification)
    "readonly",  # Read-only external tools (get_weather, search_wikipedia)
    "system",  # System/context tools (resolve_reference, get_context_list)
    # NOTE: "list" and "details" categories removed (2026-01 simplification)
    # - All get/search/list operations are now unified under "search"
    # - Use get_*_tool pattern for unified data retrieval
]

# =============================================================================
# Mutation Policy — what confirmation a non-read-only tool owes (ADR-263)
# =============================================================================
#
# The category says WHAT a tool does; the policy says WHAT THE USER IS ASKED
# before it does it. Measured 2026-09-03: 13 native tools classified as
# mutations had no confirmation gate in either execution mode, and nothing said
# whether that was a decision or an omission.
#
# Owner rule (2026-09-03): a confirmation is owed by a mutation that MODIFIES,
# DELETES or COMMUNICATES TO A THIRD PARTY; never by a read; and never out of
# paranoia — a card the user did not need is a card they stop reading.
#
# ``permissions.hitl_required`` answers a DIFFERENT question: does ReAct pause
# before this call? A tool may be paused on for its COST rather than its effect
# — ``delegate_to_sub_agent_tool`` opens a whole read-only research loop, asks
# the user because that is expensive, and changes nothing in the world. Deriving
# the policy from the flag would have classified it as a mutation and, once the
# gate refused unconfirmed ones, made it unusable in pipeline mode. The two
# questions stay separate.

MutationPolicy = Literal[
    "read",  # acts on nothing: the explicit "no confirmation is owed"
    "draft",  # the tool returns a draft; the draft IS the confirmation
    "confirm",  # pre-execution confirmation card, in BOTH execution modes
    "reversible",  # executes and is journaled; one call undoes it
    "artefact",  # produces a local artefact for the user, no third-party effect
    "sandboxed",  # runs inside the throwaway container (SEC-001)
]

MUTATION_POLICIES: frozenset[str] = frozenset(
    {"read", "draft", "confirm", "reversible", "artefact", "sandboxed"}
)

#: The policies of a tool that ACTS. ``read`` is the only value that claims the
#: tool changes nothing.
ACTING_POLICIES: frozenset[str] = MUTATION_POLICIES - {"read"}

#: Policies under which the user is ASKED before the effect happens. ``draft``
#: builds what they confirm; ``confirm`` asks for the call itself. Published to
#: the planner, so a plan never presents as silent an action a card interrupts.
ASKING_POLICIES: frozenset[str] = frozenset({"draft", "confirm"})

#: Policies that EXEMPT an acting tool from a confirmation. ``draft`` and
#: ``confirm`` ask the user, so they justify themselves; the other three must
#: say in writing why the user is not asked.
POLICIES_REQUIRING_REASON: frozenset[str] = frozenset({"reversible", "artefact", "sandboxed"})

#: The ONLY category exempt from declaring a policy — and the exemption is
#: measured, not comfortable. ``infer_tool_category`` assigns ``search`` only
#: from an explicit ``get_*``/``search_*``/``list_*`` name, whereas
#: ``"readonly"`` is its FALLBACK when no convention applies. That fallback is
#: where the dangerous tools landed: ``claude_server_task_tool`` (drives the
#: production server), ``run_python_tool`` (runs model-authored code) and
#: ``delegate_to_sub_agent_tool`` (a whole ReAct loop) are all declared
#: read-only — deliberately, to keep the semantic validator from rerouting them
#: (ADR-256 §C) — so exempting "read-only" would have exempted exactly them.
#: ``readonly`` and ``system`` tools therefore declare ``read`` explicitly: one
#: cheap true statement instead of an inherited silence.
POLICY_EXEMPT_CATEGORIES: frozenset[str] = frozenset({"search"})

#: Categories whose very name says the tool acts — declaring ``read`` there is
#: a contradiction, not a decision.
MUTATING_CATEGORIES: frozenset[str] = frozenset({"create", "update", "delete", "send"})

# Shared justifications for the policies that skip a confirmation. Factored
# here because they are DOCTRINE, not per-tool data: the same sentence covers
# three lights and two label tools, and a doctrine that is retyped drifts.
REASON_UNDONE_BY_ONE_CALL: Final[str] = (
    "Undone by one more call of the same tool; the owner refused a card per action."
)
REASON_REOPENED_BY_AN_UPDATE: Final[str] = (
    "Reopened by an ordinary update; nothing leaves the account."
)
REASON_ADDITIVE_METADATA: Final[str] = (
    "Additive metadata on the user's own items; the opposite call restores them."
)
REASON_LOCAL_ARTEFACT: Final[str] = (
    "Produces a local artefact for the user; no effect at a third party."
)
REASON_SANDBOXED_CONTAINER: Final[str] = (
    "Runs in the throwaway container (SEC-001): no network, no host filesystem."
)
REASON_USER_VISIBLE_CONTROL: Final[str] = (
    "Navigation under the user's visible control; a submission to a third party "
    "would need its own draft tool."
)
REASON_INTERNAL_CONTEXT: Final[str] = (
    "Changes only LIA's own conversation context: no user data, no third party."
)
REASON_OWN_LIBRARY: Final[str] = (
    "Installs into the user's own library and is removable from the settings."
)

# System tools that should ALWAYS be included regardless of strategy
SYSTEM_TOOL_NAMES = frozenset(
    {
        "resolve_reference",
        "get_context_list",
        "get_context_state",
        "list_active_domains",
        "set_current_item",
        "local_query_engine_tool",
    }
)

# ============================================================================
# Cost & Performance
# ============================================================================


@dataclass(frozen=True)
class CostProfile:
    """
    Cost and performance profile for a tool.

    Used for:
    - Total plan cost estimation (validation before execution)
    - Observability metrics (estimated vs actual comparison)
    - Optimization (identifying expensive tools)

    Attributes:
        est_tokens_in: Estimated number of input tokens (prompt + params)
        est_tokens_out: Estimated number of output tokens (response)
        est_cost_usd: Estimated cost in USD (based on model pricing)
        est_latency_ms: Estimated latency in milliseconds
    """

    est_tokens_in: int = 0
    est_tokens_out: int = 0
    est_cost_usd: float = 0.0
    est_latency_ms: int = 0

    def __post_init__(self) -> None:
        """Validate profile values."""
        if self.est_tokens_in < 0:
            raise ValueError("est_tokens_in must be >= 0")
        if self.est_tokens_out < 0:
            raise ValueError("est_tokens_out must be >= 0")
        if self.est_cost_usd < 0:
            raise ValueError("est_cost_usd must be >= 0")
        if self.est_latency_ms < 0:
            raise ValueError("est_latency_ms must be >= 0")


# ============================================================================
# Security & Permissions
# ============================================================================


@dataclass(frozen=True)
class PermissionProfile:
    """
    Permission and security profile for a tool.

    Defines security requirements:
    - Required OAuth scopes (e.g., google_contacts.read)
    - Authorized user roles (if restricted)
    - Data classification (PUBLIC, CONFIDENTIAL, SENSITIVE)
    - HITL (Human-In-The-Loop) approval requirement

    Attributes:
        required_scopes: List of required OAuth scopes
        allowed_roles: Authorized roles (empty = all roles allowed)
        data_classification: Data sensitivity level
        hitl_required: If True, requires user approval before execution
    """

    required_scopes: list[str] = field(default_factory=list)
    allowed_roles: list[str] = field(default_factory=list)
    data_classification: Literal[
        "PUBLIC", "INTERNAL", "CONFIDENTIAL", "SENSITIVE", "RESTRICTED"
    ] = "CONFIDENTIAL"
    hitl_required: bool = False


# ============================================================================
# Parameters & Validation
# ============================================================================


@dataclass(frozen=True)
class ParameterConstraint:
    r"""
    Validation constraint for a parameter.

    Supports standard Pydantic constraints:
    - min_length / max_length (strings)
    - minimum / maximum (numbers)
    - pattern (regex)
    - enum (allowed values)

    Attributes:
        kind: Constraint type
        value: Constraint value (type depends on kind)

    Examples:
        >>> ParameterConstraint(kind="min_length", value=1)
        >>> ParameterConstraint(kind="maximum", value=100)
        >>> ParameterConstraint(kind="pattern", value=r"^people/c\d+$")
        >>> ParameterConstraint(kind="enum", value=["ASC", "DESC"])
    """

    kind: Literal["min_length", "max_length", "minimum", "maximum", "pattern", "enum"]
    value: Any


@dataclass(frozen=True)
class ParameterSchema:
    """
    Validation schema for a tool parameter.

    Fully describes an input parameter:
    - Type (string, integer, number, boolean, array, object)
    - Required or optional
    - Description for documentation
    - Validation constraints
    - Full JSON schema (optional, for complex types)
    - Semantic type (for cross-domain LLM reasoning)

    Attributes:
        name: Parameter name (e.g., "query", "max_results")
        type: Pydantic type (string, integer, boolean, array, object)
        required: If True, parameter is mandatory
        description: Description for LLM and documentation
        constraints: List of validation constraints
        schema: Full JSON Schema (for complex types)
        semantic_type: Semantic type for cross-domain LLM reasoning.
                      Enables the planner to automatically understand dependencies
                      between tools. E.g., routes.destination (semantic_type="physical_address")
                      cannot receive a person name - the planner must first
                      call contacts to obtain the physical address.
                      Common types: "physical_address", "person_name", "email_address",
                      "phone_number", "event_id", "datetime", "coordinate".
                      Must reference a type registered in the semantic TypeRegistry
                      (enforced by tests/unit/domains/agents/semantic/
                      test_semantic_registry_integrity.py).

    Examples:
        >>> ParameterSchema(
        ...     name="query",
        ...     type="string",
        ...     required=True,
        ...     description="Search text",
        ...     constraints=[ParameterConstraint(kind="min_length", value=1)]
        ... )
        >>> ParameterSchema(
        ...     name="destination",
        ...     type="string",
        ...     required=True,
        ...     description="Physical address or coordinates",
        ...     semantic_type="physical_address"  # NOT a person name!
        ... )
    """

    name: str
    type: str  # "string", "integer", "boolean", "array", "object", etc.
    required: bool
    description: str
    constraints: list[ParameterConstraint] = field(default_factory=list)
    schema: dict[str, Any] | None = None  # Full JSON Schema if needed
    semantic_type: str | None = None  # Semantic type for cross-domain LLM reasoning
    # Optional search-reset role, read by the plan validator to neutralize params
    # the planner over-constrains on a search. Declared per tool (opt-in) instead
    # of guessing from param names. Currently supported value:
    #   "range_end" — an end-of-window date bound (e.g. time_max) that is emptied
    #     for open/relative queries carrying no user temporal reference, so the
    #     tool's own default window applies instead of a hallucinated narrow one.
    # Typed as a Literal so a typo in a manifest annotation fails MyPy rather than
    # silently disabling the reset.
    search_role: Literal["range_end"] | None = None


# ============================================================================
# Outputs & Documentation
# ============================================================================


@dataclass(frozen=True)
class OutputFieldSchema:
    """
    Schema for a tool output field.

    Documents the structure of returned data.
    Uses JSONPath to describe nested fields.

    Attributes:
        path: JSONPath to the field (e.g., "contacts[].name.display")
        type: Field type (string, integer, boolean, array, object)
        description: Field description
        nullable: If True, field can be null
        semantic_type: Semantic type of the output field.
                      Enables the LLM planner to understand that this field can
                      be used as input for another tool that requires
                      this semantic type. E.g., contacts[].addresses[].formattedValue
                      (semantic_type="physical_address") can feed routes.destination.

    Examples:
        >>> OutputFieldSchema(
        ...     path="contacts[].resource_name",
        ...     type="string",
        ...     description="Google contact identifier"
        ... )
        >>> OutputFieldSchema(
        ...     path="contacts[].addresses[].formattedValue",
        ...     type="string",
        ...     description="Formatted postal address",
        ...     semantic_type="physical_address"  # Can feed routes.destination
        ... )
    """

    path: str
    type: str
    description: str
    nullable: bool = False
    semantic_type: str | None = None  # Semantic type for cross-domain LLM reasoning


# ============================================================================
# Voice Weight (for dynamic voice trigger threshold estimation)
# ============================================================================


@dataclass(frozen=True)
class VoiceWeight:
    """
    Weight for dynamic voice trigger threshold estimation.

    Used to estimate result context size per domain/operation.
    Formula: estimated_chars = base_chars * operation_multiplier + (result_count * per_result_chars)

    Attributes:
        base_chars: Base character estimate for this domain (e.g., weather=100, emails=350)
        search_multiplier: Multiplier for search operations (default: 1.0)
        detail_multiplier: Multiplier for detail operations (default: 2.0)
        per_result_chars: Additional characters per returned result

    Examples:
        >>> VoiceWeight(base_chars=150, per_result_chars=50)  # contacts
        >>> VoiceWeight(base_chars=100, detail_multiplier=1.5)  # weather (simple)
        >>> VoiceWeight(base_chars=400, per_result_chars=100)  # wikipedia (verbose)
    """

    base_chars: int = 200
    search_multiplier: float = 1.0
    detail_multiplier: float = 2.0
    per_result_chars: int = 30

    def __post_init__(self) -> None:
        """Validate voice weights."""
        if self.base_chars < 0:
            raise ValueError("base_chars must be >= 0")
        if self.search_multiplier <= 0:
            raise ValueError("search_multiplier must be > 0")
        if self.detail_multiplier <= 0:
            raise ValueError("detail_multiplier must be > 0")
        if self.per_result_chars < 0:
            raise ValueError("per_result_chars must be >= 0")

    def estimate_chars(
        self,
        operation_type: str = "search",
        result_count: int = 1,
    ) -> int:
        """
        Estimate the number of characters produced by this operation.

        Args:
            operation_type: Operation type ("search", "detail", "list", etc.)
            result_count: Number of returned results

        Returns:
            Estimate in characters
        """
        # Determine the multiplier based on operation type
        if "detail" in operation_type.lower() or "get" in operation_type.lower():
            multiplier = self.detail_multiplier
        else:
            multiplier = self.search_multiplier

        # Calculate the estimate
        base = int(self.base_chars * multiplier)
        results_contribution = result_count * self.per_result_chars

        return base + results_contribution


# ============================================================================
# Display Metadata (for UI rendering of execution steps)
# ============================================================================


@dataclass(frozen=True)
class DisplayMetadata:
    """
    Display metadata for UI rendering of execution steps.

    Used for progressive display of execution steps in the interface:
    - Visual emoji for quick recognition
    - i18n key for translation (namespace: execution.steps.*)
    - Visibility (hide certain technical steps if needed)
    - Category for visual grouping

    Attributes:
        emoji: Emoji visually representing the action (e.g., "🔍", "📝", "✉️")
        i18n_key: Key for translation in namespace execution.steps
                  (e.g., "search_contacts" → "execution.steps.search_contacts")
        visible: If False, the step is not displayed in the UI (default: True)
        category: Category for visual grouping
                  - "system": Internal system operations (router, planner)
                  - "agent": Specialized agent execution
                  - "tool": External tool calls (Google API, etc.)
                  - "context": Context operations (save, get, clear)

    Examples:
        >>> DisplayMetadata(
        ...     emoji="🔍",
        ...     i18n_key="search_contacts",
        ...     visible=True,
        ...     category="tool"
        ... )
        >>> DisplayMetadata(
        ...     emoji="🧭",
        ...     i18n_key="router_decision",
        ...     visible=True,
        ...     category="system"
        ... )
    """

    emoji: str
    i18n_key: str
    visible: bool = True
    category: Literal["system", "agent", "tool", "context"] = "tool"

    def __post_init__(self) -> None:
        """Validate display metadata."""
        if not self.emoji:
            raise ValueError("emoji cannot be empty")
        if not self.i18n_key:
            raise ValueError("i18n_key cannot be empty")
        # Validate emoji is a single emoji character (basic check)
        if len(self.emoji) > 4:  # Allow for multi-codepoint emojis
            raise ValueError(f"emoji should be a single emoji character: {self.emoji}")


# ============================================================================
# Tool Manifest
# ============================================================================


@dataclass
class ToolManifest:
    """
    Complete tool manifest.

    Single source of truth exhaustively describing a tool:
    - Identity (name, agent, version)
    - Documentation (description, examples)
    - Contract (parameters, outputs)
    - Cost (tokens, latency)
    - Security (permissions, HITL)
    - Behavior (iterations, dry-run, context)

    This manifest is used by:
    - Planner: plan generation (via export_for_prompt)
    - Validator: parameter, permission, and cost validation
    - Orchestrator: execution and context management
    - Documentation: automatic docs generation

    Attributes:
        name: Unique tool name (e.g., "search_contacts_tool")
        agent: Owning agent name
        description: Complete description for LLM
        parameters: Parameter list with validation
        outputs: Output field documentation
        cost: Cost and performance profile
        permissions: Permission and security profile
        max_iterations: Max iterations (for iterative tools)
        supports_dry_run: If True, tool supports simulation mode
        reference_fields: Fields usable as contextual references
        context_key: Key for auto-save in Store (if applicable)
        field_mappings: Optional mapping of user-friendly names to API names (e.g., {"name": "names", "emails": "emailAddresses"})
        serves_domains: Extra domains this tool is reachable from, beyond its
            owning agent's domain (cross-domain tools only)
        examples: Input/output examples for documentation and tests
        version: Semver version of the tool
        updated_at: Last modification date
        maintainer: Responsible team

    Examples:
        >>> ToolManifest(
        ...     name="get_contacts_tool",
        ...     agent="contact_agent",
        ...     description="Search Google contacts by name, email, or phone",
        ...     parameters=[
        ...         ParameterSchema(name="query", type="string", required=True, ...)
        ...     ],
        ...     cost=CostProfile(est_tokens_in=150, est_tokens_out=400, ...),
        ...     permissions=PermissionProfile(required_scopes=["google_contacts.read"]),
        ...     context_key="contacts",
        ...     version="1.0.0"
        ... )
    """

    # Identity
    name: str
    agent: str
    description: str

    # Contract
    parameters: list[ParameterSchema]
    outputs: list[OutputFieldSchema]

    # Cost & Performance
    cost: CostProfile

    # Security
    permissions: PermissionProfile

    # Behavior
    #: Execution modes this tool may run in (ADR-249). Both by default; a
    #: restriction is a CONTRACT the planner catalogue reads, not a convention.
    execution_modes: frozenset[str] = field(
        default_factory=lambda: frozenset({EXECUTION_MODE_PIPELINE, EXECUTION_MODE_REACT})
    )
    max_iterations: int = 1
    supports_dry_run: bool = False
    reference_fields: list[str] = field(default_factory=list)
    context_key: str | None = None
    context_save_mode: ContextSaveMode | None = None  # Explicit LIST/DETAILS override for auto-save
    field_mappings: dict[str, str] | None = (
        None  # Maps user-friendly names to API-specific field names
    )

    # Documentation
    examples: list[dict[str, Any]] = field(default_factory=list)
    examples_in_prompt: bool = (
        True  # If False, examples excluded from planner prompt (use description instead)
    )

    # Semantic Search Optimization (LLM-Native Architecture)
    # Natural language phrases that describe user intents for this tool.
    # Used by SemanticToolSelector for embedding-based matching.
    # Include variations in English for optimal embedding performance.
    # Example: ["get my emails", "fetch recent messages", "read inbox", "list received mails"]
    semantic_keywords: list[str] = field(default_factory=list)

    # Reference examples for Planner guidance (Phase 5.1 - Multi-Domain Architecture)
    # Documents valid $steps.STEP_ID.PATH patterns for this tool's output
    # This enables the Planner LLM to generate correct references without guessing
    # Example: ["contacts[0].resource_name", "contacts[*].emails", "total"]
    reference_examples: list[str] = field(default_factory=list)

    # Extra domains this tool is REACHABLE from, beyond its owning agent's own
    # domain (ADR-191). Catalogue filtering drops out-of-domain manifests BEFORE
    # consulting any semantic score, so a genuinely cross-domain tool is
    # invisible to every query the analyzer classifies elsewhere — however well
    # it scores. Measured 2026-08-01: get_person_overview_tool (domain
    # `contact`, score 0.853, the catalogue's best) was absent from the planner
    # catalogue for a `peer` query, where the analyzer prompt sends every
    # question about a connected user.
    # Declare ONLY domains the tool genuinely serves: each extra domain widens
    # the candidate set for every query in it. Validated at registration against
    # DOMAIN_REGISTRY — an unknown domain is a boot failure, never a silent
    # no-op.
    serves_domains: list[str] = field(default_factory=list)

    # Versioning
    version: str = "1.0.0"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    maintainer: str = "Team AI"

    # Display (optional - for UI rendering of execution steps)
    display: DisplayMetadata | None = None

    # Voice (optional - for dynamic voice trigger threshold estimation)
    # Provides domain-specific weights for estimating result context size
    voice_weight: VoiceWeight | None = None

    # Tool Category for Strategy-Based Filtering
    # Used to filter tools based on user intent (action, detail, search, list)
    # If None, category is inferred from tool name using infer_tool_category()
    tool_category: ToolCategory | None = None

    # ADR-263: the confirmation this tool owes before it acts. None on a
    # read-only tool (a read owes nothing); mandatory on every other NATIVE
    # tool, enforced at boot by assert_mutation_policy_completeness(). A
    # third-party MCP tool never declares it — its policy is DERIVED from what
    # the server declares (derive_mcp_mutation_policy), never asserted.
    mutation_policy: MutationPolicy | None = None

    # Mandatory for the policies that exempt a mutation from a confirmation
    # (POLICIES_REQUIRING_REASON): one English sentence saying why the user is
    # not asked. An exemption nobody wrote down is an omission nobody can audit.
    mutation_policy_reason: str | None = None

    # Initiative eligibility: whether this tool can be used during the initiative phase.
    # The initiative phase performs proactive cross-domain enrichment after plan execution.
    # Default: None → auto-determined from category (search/readonly = True, system = False).
    # Set explicitly to False on tools that are read-only but not useful for proactive
    # enrichment (e.g., list_calendars, get_hourly_forecast, get_route_matrix).
    initiative_eligible: bool | None = None

    # Text-search mode for the tool's free-text query parameter (if any).
    # - "literal" (default): the store matches the query as a literal text in
    #   titles/subjects/names. Passing a semantic qualifier ("medical", "urgent")
    #   would return 0 hits or false positives — see smart_planner_prompt.txt
    #   "INDEXABLE vs SEMANTIC CRITERIA" and the validator semantic-leak check.
    # - "semantic": the store performs semantic/vector search and can match
    #   conceptual qualifiers. Validator skips the semantic-leak check.
    # - "hybrid": both modes are supported. Validator skips the check.
    # Default "literal" preserves current behavior for every existing tool.
    text_search_mode: Literal["literal", "semantic", "hybrid"] = "literal"

    def __post_init__(self) -> None:
        """Validate the manifest."""
        if not self.name:
            raise ValueError("Tool name cannot be empty")
        if not self.agent:
            raise ValueError("Agent name cannot be empty")
        if not self.description:
            raise ValueError("Tool description cannot be empty")
        # Validate semver version (simple check)
        if not self.version or len(self.version.split(".")) != 3:
            raise ValueError(f"Invalid semver version: {self.version}")


# ============================================================================
# Agent Manifest
# ============================================================================


@dataclass
class AgentManifest:
    """
    Agent manifest.

    Describes an agent and its capabilities:
    - Identity (name, description)
    - Available tools
    - Execution constraints (parallelism, timeout)
    - System prompt version

    Attributes:
        name: Unique agent name (e.g., "contact_agent")
        description: Complete description of capabilities
        tools: List of available tool names
        max_parallel_runs: Max parallel instances (1 = sequential)
        default_timeout_ms: Default timeout in milliseconds
        prompt_version: System prompt version (e.g., "v1", "v2")
        owner_team: Owning team
        version: Semver version of the agent
        updated_at: Last modification date

    Examples:
        >>> AgentManifest(
        ...     name="contact_agent",
        ...     description="Specialized Google Contacts agent",
        ...     tools=["get_contacts_tool", "create_contact_tool"],
        ...     max_parallel_runs=1,
        ...     prompt_version="v1",
        ...     version="1.0.0"
        ... )
    """

    # Identity
    name: str
    description: str
    tools: list[str]  # Tool names

    # Execution constraints
    max_parallel_runs: int = 1
    default_timeout_ms: int = DEFAULT_TOOL_TIMEOUT_MS

    # Prompt
    prompt_version: str = "v1"

    # Ownership
    owner_team: str = "Team AI"

    # Versioning
    version: str = "1.0.0"
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # Display (optional - for UI rendering of execution steps)
    display: DisplayMetadata | None = None

    def __post_init__(self) -> None:
        """Validate the manifest."""
        if not self.name:
            raise ValueError("Agent name cannot be empty")
        if not self.description:
            raise ValueError("Agent description cannot be empty")
        if not self.tools:
            raise ValueError("Agent must have at least one tool")
        if self.max_parallel_runs < 1:
            raise ValueError("max_parallel_runs must be >= 1")
        if self.default_timeout_ms < 1:
            raise ValueError("default_timeout_ms must be >= 1")
        # Validate semver version
        if not self.version or len(self.version.split(".")) != 3:
            raise ValueError(f"Invalid semver version: {self.version}")


# ============================================================================
# Tool Category Inference
# ============================================================================


def infer_tool_category(tool_name: str) -> ToolCategory:
    """Infer a tool category from its name, falling back to ``"readonly"``.

    Public contract, unchanged: a THIRD-PARTY tool names itself however it
    likes, and the safe default is the right answer there — ADR-255 keeps the
    server's own annotations able to TIGHTEN this, never to loosen it.

    For the NATIVE catalogue the fallback is a different matter: it invents an
    intention rather than reading a convention, so
    :func:`assert_tool_category_completeness` refuses to boot when a native
    manifest would rely on it. See :func:`infer_tool_category_or_none` for the
    distinction.

    Args:
        tool_name: Tool name to analyse.

    Returns:
        The inferred category, or ``"readonly"`` when no convention applies.
    """
    return infer_tool_category_or_none(tool_name) or "readonly"


def infer_tool_category_or_none(tool_name: str) -> ToolCategory | None:
    """
    Infer tool category from tool name using naming conventions.

    Returns ``None`` — rather than a safe-looking default — when no convention
    applies. That is the whole point of this function: *guessing from a
    convention is legitimate, inventing an intention is not* (ADR-184's
    distinction, applied to tool safety in ADR-256). Measured on the native
    catalogue before the guard existed: 17 manifests out of 96 landed on the
    default, and four of them wrote data.

    Convention-based inference (2026-01 unified architecture):
    - get_* → search (unified data retrieval with full details)
    - search_* → search (legacy, same behavior)
    - list_* → search (legacy, same behavior)
    - *_details* → search (legacy, same behavior)
    - create_* → create
    - update_* → update
    - delete_* → delete
    - send_* → send
    - System tools → system
    - External readonly tools (weather, wikipedia) → readonly

    Args:
        tool_name: Tool name to analyze

    Returns:
        Inferred ToolCategory

    Examples:
        >>> infer_tool_category("get_emails_tool")
        'search'
        >>> infer_tool_category("get_contacts_tool")
        'search'
        >>> infer_tool_category("create_event_tool")
        'create'
        >>> infer_tool_category("get_weather_tool")
        'readonly'
    """
    name_lower = tool_name.lower()

    # Strip MCP prefix before analysis (mcp_{server}_{real_tool_name})
    # Server names can contain underscores (e.g., "google_flights").
    # Strategy: try matching known action prefixes from the end of the name.
    if name_lower.startswith("mcp_"):
        # Remove "mcp_" prefix, then check if remainder contains an action prefix
        without_mcp = name_lower[4:]  # "excalidraw_create_view", "google_flights_search_flights"
        for prefix in (
            "create_",
            "update_",
            "modify_",
            "delete_",
            "remove_",
            "send_",
            "reply_",
            "forward_",
            "get_",
            "search_",
            "list_",
        ):
            idx = without_mcp.find(f"_{prefix}")
            if idx >= 0:
                name_lower = without_mcp[idx + 1 :]  # "create_view", "search_flights"
                break
        else:
            # No known action prefix found — use last segment after server name
            parts = without_mcp.split("_", 1)
            if len(parts) >= 2:
                name_lower = parts[1]  # Best effort

    # System tools (check first - highest priority)
    if tool_name in SYSTEM_TOOL_NAMES:
        return "system"

    # CRUD tools (check before get_* to avoid confusion)
    if name_lower.startswith("create_") or name_lower.startswith("add_"):
        return "create"

    if name_lower.startswith("update_") or name_lower.startswith("modify_"):
        return "update"

    if name_lower.startswith("delete_") or name_lower.startswith("remove_"):
        return "delete"

    # Send tools (send, reply, forward)
    if (
        name_lower.startswith("send_")
        or name_lower.startswith("reply_")
        or name_lower.startswith("forward_")
    ):
        return "send"

    # External readonly tools (weather, wikipedia, perplexity - no user data)
    external_readonly_patterns = ("weather", "wikipedia", "perplexity")
    if any(pattern in name_lower for pattern in external_readonly_patterns):
        return "readonly"

    # Unified search category: get_*, search_*, list_*, *_details*
    # All data retrieval operations are now unified under "search"
    if (
        name_lower.startswith("get_")
        or name_lower.startswith("search_")
        or name_lower.startswith("list_")
        or "_details" in name_lower
    ):
        return "search"

    # No convention applies. Saying so is the contribution: the caller decides
    # whether to fall back (third-party names) or to refuse (native manifests).
    return None


def assert_tool_category_completeness(manifests: Iterable[Any]) -> None:
    """Assert every NATIVE manifest declares or implies a safety category.

    Called from ``init_agent_registry`` right after ``initialize_catalogue`` —
    not from ``run_failfast_validations``, which runs before any manifest is
    registered and would therefore validate an empty registry and pass forever.
    A unit test calls it over the loaded catalogue so CI catches it before boot
    (ADR-085 pattern, same placement as ``assert_registry_completeness``).

    Third-party MCP tools are exempt by construction: they are registered
    dynamically, outside the catalogue this runs over, and ADR-255 already
    governs what their own declaration may say.

    Args:
        manifests: Tool manifests currently registered in the catalogue.

    Raises:
        AssertionError: If any manifest has no ``tool_category`` and no naming
            convention that implies one, listing the offending names.
    """
    undeclared = sorted(
        str(getattr(m, "name", "<unnamed>"))
        for m in manifests
        if getattr(m, "tool_category", None) is None
        and infer_tool_category_or_none(str(getattr(m, "name", ""))) is None
    )
    if undeclared:
        names = ", ".join(undeclared)
        raise AssertionError(
            f"{len(undeclared)} tool manifest(s) declare no tool_category and follow "
            f"no naming convention: {names}. The category decides whether the tool "
            "counts as a mutation (semantic-validator safety net) and whether the "
            "read-only initiative phase may run it — inferring 'readonly' there "
            "invents an intention. Declare tool_category on the manifest; see "
            "src/domains/agents/registry/catalogue.py."
        )


def _policy_contradiction_problems(name: str, policy: Any, hitl_required: bool) -> list[str]:
    """Problems visible from the policy VALUE alone, before any exemption.

    Checked first and for every manifest, because a tool that already asks the
    user cannot be a read whatever its category says — which is exactly
    ``delegate_to_sub_agent_tool``, declared read-only and carrying
    ``hitl_required=True``.

    Args:
        name: Tool name, for the message.
        policy: Declared ``mutation_policy`` (may be None or unknown).
        hitl_required: The manifest's pre-execution HITL flag.

    Returns:
        Zero or more problem descriptions.
    """
    if policy is not None and policy not in MUTATION_POLICIES:
        return [f"{name}: unknown mutation_policy {policy!r}"]
    if hitl_required and policy == "draft":
        # The measured invariant (test_hitl_required_consistency): the draft IS
        # the confirmation, so a pre-execution card asks the user twice.
        return [f"{name}: draft policy with hitl_required=True (asks the user twice)"]
    return []


def _policy_declaration_problems(name: str, policy: Any, reason: Any, category: str) -> list[str]:
    """Problems in what the manifest declares for its category.

    Args:
        name: Tool name, for the message.
        policy: Declared ``mutation_policy`` (already known to be valid or None).
        reason: Declared ``mutation_policy_reason``.
        category: Effective tool category.

    Returns:
        Zero or more problem descriptions.
    """
    if category in POLICY_EXEMPT_CATEGORIES:
        if policy in ACTING_POLICIES:
            return [f"{name}: search tool declares an acting policy ({policy})"]
        return []
    if policy is None:
        return [f"declare no mutation_policy: {name}"]
    problems: list[str] = []
    if policy == "read" and category in MUTATING_CATEGORIES:
        problems.append(f"{name}: declares read but its category ({category}) acts")
    if policy in POLICIES_REQUIRING_REASON and not str(reason or "").strip():
        problems.append(f"{name}: policy {policy} without a reason")
    return problems


def requires_user_approval(manifest: Any) -> bool:
    """Will the user be asked before this tool acts? (ADR-263)

    The planner is told this, so it must be the TRUTH the system enforces, not
    a permission flag that happens to sit nearby: ``permissions.hitl_required``
    is ``False`` for the 24 draft-building tools, and a draft is precisely the
    case where the user IS asked. What enforces the confirmation is the declared
    policy, so that is what is published (ADR-184: what a system enforces, it
    must publish to whoever produces the value).

    Args:
        manifest: A tool manifest, native or third-party.

    Returns:
        True when the user will be asked — a draft to confirm, a policy
        demanding confirmation, or an explicit operator requirement.
    """
    if getattr(manifest, "mutation_policy", None) in ASKING_POLICIES:
        return True
    permissions = getattr(manifest, "permissions", None)
    return bool(getattr(permissions, "hitl_required", False))


def assert_mutation_policy_completeness(manifests: Iterable[Any]) -> None:
    """Assert every NATIVE manifest carries the confirmation it owes (ADR-263).

    The rules live in :func:`_policy_contradiction_problems` and
    :func:`_policy_declaration_problems`; this function walks the catalogue and
    reports EVERY offender at once, so an operator facing a boot refusal sees
    the whole list rather than the first line of it.

    Called from ``init_agent_registry`` right after the catalogue is loaded,
    like :func:`assert_tool_category_completeness` — never from
    ``run_failfast_validations``, which runs before any manifest is registered
    and would validate an empty registry and pass forever (ADR-085 placement).

    Third-party MCP tools are exempt BY CONSTRUCTION: their policy is derived
    from what the server declares (``derive_mcp_mutation_policy``), never
    asserted, because a third party names and annotates its tools as it wants
    (ADR-255). They are recognised by the ``mcp_`` prefix their adapters carry.

    Args:
        manifests: Tool manifests currently registered in the catalogue.

    Raises:
        AssertionError: Listing every offending manifest and rule.
    """
    problems: list[str] = []
    for manifest in manifests:
        name = str(getattr(manifest, "name", "<unnamed>"))
        # Same idiom as ``step_timeouts.py``: the prefix constant is "mcp", so
        # the separator is spelled out — otherwise a native "mcpsomething_tool"
        # would silently escape the guard.
        if name.startswith(f"{MCP_TOOL_NAME_PREFIX}_"):
            continue
        policy = getattr(manifest, "mutation_policy", None)
        hitl_required = bool(
            getattr(getattr(manifest, "permissions", None), "hitl_required", False)
        )
        problems.extend(_policy_contradiction_problems(name, policy, hitl_required))
        if policy is not None and policy not in MUTATION_POLICIES:
            # Vocabulary already reported; the declaration rules below would
            # only add noise about a value that means nothing.
            continue
        # Defensive like its sibling assert: this runs at boot over whatever
        # the catalogue holds, and a guard that raises on an odd shape reports
        # nothing at all.
        declared_category = getattr(manifest, "tool_category", None)
        category = declared_category or infer_tool_category(name)
        problems.extend(
            _policy_declaration_problems(
                name,
                policy,
                getattr(manifest, "mutation_policy_reason", None),
                category,
            )
        )

    if problems:
        raise AssertionError(
            f"{len(problems)} mutation policy problem(s): "
            + "; ".join(sorted(problems))
            + ". A non-read-only tool must SAY what confirmation it owes — declaring "
            "nothing is how 13 tools came to run unconfirmed in both execution modes. "
            "See MutationPolicy in src/domains/agents/registry/catalogue.py."
        )


def get_tool_category(manifest: ToolManifest) -> ToolCategory:
    """
    Get the tool category, using explicit value or inferring from name.

    Args:
        manifest: Tool manifest

    Returns:
        Tool category (explicit or inferred)
    """
    if manifest.tool_category is not None:
        return manifest.tool_category
    return infer_tool_category(manifest.name)


def is_system_tool(tool_name: str) -> bool:
    """Check if tool is a system tool that should always be included."""
    return tool_name in SYSTEM_TOOL_NAMES


# Categories that are safe for initiative phase (read-only actions)
READ_ONLY_CATEGORIES: frozenset[ToolCategory] = frozenset({"search", "readonly", "system"})


def is_initiative_eligible(manifest: ToolManifest) -> bool:
    """Check if a tool is eligible for the initiative phase.

    Initiative performs proactive cross-domain enrichment. Eligible tools are
    read-only AND useful for proactive enrichment (not structural/utility tools).

    Resolution order:
    1. Explicit ``manifest.initiative_eligible`` (if set) — highest priority
    2. Category-based default: search/readonly → True, system → False

    Args:
        manifest: Tool manifest to check.

    Returns:
        True if the tool can be used during initiative phase.
    """
    # Explicit override takes priority
    if manifest.initiative_eligible is not None:
        return manifest.initiative_eligible
    # Auto-determine from category: system tools are never initiative-eligible
    category = get_tool_category(manifest)
    return category in ("search", "readonly")


def is_read_only_tool(manifest: ToolManifest) -> bool:
    """Check if a tool is read-only (safe for initiative phase).

    Read-only tools cannot modify user data. They include:
    - search: get_emails, get_contacts, get_events, etc.
    - readonly: weather, wikipedia, perplexity
    - system: context tools

    Write tools (create, update, delete, send) are excluded.

    Args:
        manifest: Tool manifest to check.

    Returns:
        True if the tool only reads data.
    """
    return get_tool_category(manifest) in READ_ONLY_CATEGORIES


# ============================================================================
# Exceptions
# ============================================================================


class CatalogueError(Exception):
    """Base exception for catalogue errors."""

    pass


class AgentManifestNotFound(CatalogueError):
    """Agent manifest not found."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__(f"Agent manifest not found: {agent_name}")


def manifests_for_mode(manifests: Iterable[Any], mode: str) -> list[Any]:
    """Keep the manifests allowed in one execution mode (ADR-249).

    A restriction that lived only in the tool's own refusal would let the
    planner SEE a tool it cannot run, plan a step with it, and be refused at
    execution — an invented dead end. Every reader of the manifest list applies
    this filter, which is why it has exactly one implementation.

    Fails OPEN: a manifest with no declared modes (older, third-party) is kept.

    Args:
        manifests: Tool manifests to filter.
        mode: ``EXECUTION_MODE_PIPELINE`` or ``EXECUTION_MODE_REACT``.

    Returns:
        The manifests this mode may use, in order.
    """
    kept: list[Any] = []
    for manifest in manifests:
        modes = getattr(manifest, "execution_modes", None)
        if not modes or mode in modes:
            kept.append(manifest)
    return kept


class ToolManifestNotFound(CatalogueError):
    """Tool manifest not found."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool manifest not found: {tool_name}")


class ToolManifestAlreadyRegistered(CatalogueError):
    """Tool manifest already registered."""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        super().__init__(f"Tool manifest already registered: {tool_name}")


class AgentManifestAlreadyRegistered(CatalogueError):
    """Agent manifest already registered."""

    def __init__(self, agent_name: str) -> None:
        self.agent_name = agent_name
        super().__init__(f"Agent manifest already registered: {agent_name}")
