"""
Tool Manifest Builder Pattern - Generic & Extensible Architecture.

This module provides a fluent API for constructing ToolManifest objects with
zero domain coupling. All presets and configurations are abstract and reusable
across any type of agent (Google, Microsoft, Database, Filesystem, etc.).

Best Practices (LangGraph v1.0 / LangChain v1.0):
- Composition over Inheritance
- Protocol-based interfaces for extensibility
- Configuration over code (external YAML/JSON support)
- Immutability where possible (builder pattern)
- Zero hardcoded domain logic (contacts, gmail, etc.)

Usage:
    >>> from src.domains.agents.registry.manifest_builder import ToolManifestBuilder
    >>>
    >>> manifest = (
    ...     ToolManifestBuilder("search_items_tool", "my_agent")
    ...     .with_description("Search items by query")
    ...     .add_parameter("query", "string", required=True, min_length=1)
    ...     .with_api_integration(provider="google", scopes=["..."])
    ...     .with_hitl(data_classification="CONFIDENTIAL")
    ...     .build()
    ... )

Architecture:
- Builder: Fluent API with immutable steps
- Presets: Reusable configurations (not domain-specific)
- Validators: Extensible validation pipeline
- Serializers: JSON/YAML/Python output formats
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Literal, Protocol, Self

from src.core.field_names import FIELD_PARAMETERS
from src.domains.agents.registry.catalogue import (
    CostProfile,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# Configuration Protocols (Extensibility)
# ============================================================================


class ValidationRule(Protocol):
    """Protocol for extensible validation rules."""

    def validate(self, manifest: ToolManifest) -> list[str]:
        """
        Validate manifest and return list of error messages.

        Args:
            manifest: ToolManifest to validate

        Returns:
            List of error messages (empty if valid)
        """
        ...


@dataclass(frozen=True)
class RateLimit:
    """
    Generic rate limit configuration (not tied to specific provider).

    Examples:
        - Google API: RateLimit(requests=10, period_seconds=1)
        - Database: RateLimit(queries=100, period_seconds=60)
        - File I/O: RateLimit(operations=50, period_seconds=1)
    """

    requests: int
    period_seconds: float
    burst_size: int | None = None  # Optional burst allowance


@dataclass(frozen=True)
class CachingStrategy:
    """
    Generic caching configuration (agnostic of cache backend).

    Examples:
        - API responses: CachingStrategy(ttl_seconds=300, invalidate_on=["create", "update"])
        - Database queries: CachingStrategy(ttl_seconds=60, invalidate_on=["write"])
    """

    ttl_seconds: int
    invalidation_events: list[str] = field(default_factory=list)
    cache_key_template: str | None = None  # Template for cache key generation


# ============================================================================
# Tool Manifest Builder - Fluent API
# ============================================================================


class ToolManifestBuilder:
    """
    Fluent builder for ToolManifest with generic presets.

    Design Principles:
    - Immutable: Each method returns new builder instance
    - Composable: Chain methods in any order
    - Validating: Errors raised at build() time (fail-fast)
    - Generic: Zero coupling to specific domains (contacts, gmail, etc.)

    Example:
        >>> builder = (
        ...     ToolManifestBuilder("my_tool", "my_agent")
        ...     .with_description("Tool description")
        ...     .add_parameter("param1", "string", required=True)
        ...     .with_api_integration(provider="google")
        ...     .build()
        ... )
    """

    def __init__(
        self,
        name: str,
        agent: str,
        *,
        _manifest: ToolManifest | None = None,
    ) -> None:
        """
        Initialize builder with tool name and agent.

        Args:
            name: Tool name (e.g., "search_items_tool")
            agent: Agent name (e.g., "my_agent")
            _manifest: Internal parameter for immutable chaining
        """
        if _manifest is not None:
            self._manifest = _manifest
        else:
            # Initialize with minimal required fields + defaults
            # NOTE: We use a placeholder description to pass ToolManifest.__post_init__ validation
            # The builder.build() method will validate that a proper description was set
            self._manifest = ToolManifest(
                name=name,
                agent=agent,
                description="__BUILDER_PLACEHOLDER__",  # Placeholder - must call with_description()
                parameters=[],
                outputs=[],
                cost=CostProfile(),  # Default empty cost profile
                permissions=PermissionProfile(),  # Default empty permissions
                version="1.0.0",
                maintainer="Team Agents",
            )

    def _clone(self, **updates: Any) -> Self:
        """Create new builder with updated manifest (immutability)."""
        new_manifest = replace(self._manifest, **updates)
        return self.__class__(
            name=self._manifest.name,
            agent=self._manifest.agent,
            _manifest=new_manifest,
        )

    # ========================================================================
    # Core Configuration
    # ========================================================================

    def with_description(self, description: str) -> Self:
        """
        Set tool description.

        Args:
            description: Human-readable description of tool purpose

        Returns:
            New builder instance
        """
        return self._clone(description=description)

    def with_version(self, version: str) -> Self:
        """
        Set semantic version.

        Args:
            version: Semantic version string (e.g., "1.2.3")

        Returns:
            New builder instance
        """
        return self._clone(version=version)

    def with_maintainer(self, maintainer: str) -> Self:
        """
        Set maintainer identifier.

        Args:
            maintainer: Team or person responsible (e.g., "Team Data")

        Returns:
            New builder instance
        """
        return self._clone(maintainer=maintainer)

    # ========================================================================
    # Parameters Configuration
    # ========================================================================

    def add_parameter(
        self,
        name: str,
        type: str,
        required: bool = False,
        description: str = "",
        **constraints: Any,
    ) -> Self:
        """
        Add parameter with automatic constraint detection.

        Args:
            name: Parameter name
            type: Parameter type ("string", "integer", "boolean", "array", "object")
            required: Whether parameter is required
            description: Parameter description
            **constraints: Constraint kwargs (min_length, maximum, enum, pattern, etc.)

        Returns:
            New builder instance

        Examples:
            >>> .add_parameter("query", "string", required=True, min_length=1)
            >>> .add_parameter("limit", "integer", min=1, max=100)
            >>> .add_parameter("status", "string", enum=["active", "inactive"])
        """
        # Parse constraints from kwargs
        constraint_list = self._parse_constraints(**constraints)

        param = ParameterSchema(
            name=name,
            type=type,
            required=required,
            description=description,
            constraints=constraint_list,
        )

        new_params = [*self._manifest.parameters, param]
        return self._clone(parameters=new_params)

    def _parse_constraints(self, **kwargs: Any) -> list[ParameterConstraint]:
        """
        Parse constraint kwargs into ParameterConstraint list.

        Supported constraints:
        - min_length, max_length (string)
        - minimum, maximum (number)
        - enum (array of allowed values)
        - pattern (regex string)
        """
        constraints = []

        # String constraints
        if "min_length" in kwargs:
            constraints.append(ParameterConstraint(kind="min_length", value=kwargs["min_length"]))
        if "max_length" in kwargs:
            constraints.append(ParameterConstraint(kind="max_length", value=kwargs["max_length"]))

        # Number constraints
        if "min" in kwargs or "minimum" in kwargs:
            value = kwargs.get("min") if "min" in kwargs else kwargs.get("minimum")
            constraints.append(ParameterConstraint(kind="minimum", value=value))
        if "max" in kwargs or "maximum" in kwargs:
            value = kwargs.get("max") if "max" in kwargs else kwargs.get("maximum")
            constraints.append(ParameterConstraint(kind="maximum", value=value))

        # Enum constraint
        if "enum" in kwargs:
            constraints.append(ParameterConstraint(kind="enum", value=kwargs["enum"]))

        # Regex pattern
        if "pattern" in kwargs:
            constraints.append(ParameterConstraint(kind="pattern", value=kwargs["pattern"]))

        return constraints

    # ========================================================================
    # Outputs Configuration
    # ========================================================================

    def add_output(
        self,
        path: str,
        type: str,
        description: str = "",
        nullable: bool = False,
    ) -> Self:
        """
        Add output field schema.

        Args:
            path: JSONPath to output field (e.g., "items", "items[].id")
            type: Output type ("string", "integer", "array", "object", etc.)
            description: Field description
            nullable: Whether field can be null

        Returns:
            New builder instance

        Examples:
            >>> .add_output("items", "array", "List of items found")
            >>> .add_output("items[].id", "string", "Item unique identifier")
            >>> .add_output("total", "integer", "Total count")
        """
        output = OutputFieldSchema(
            path=path,
            type=type,
            description=description,
            nullable=nullable,
        )

        new_outputs = [*self._manifest.outputs, output]
        return self._clone(outputs=new_outputs)

    # ========================================================================
    # Cost & Performance Configuration
    # ========================================================================

    def with_cost_profile(
        self,
        est_tokens_in: int = 0,
        est_tokens_out: int = 0,
        est_cost_usd: float = 0.0,
        est_latency_ms: int = 0,
    ) -> Self:
        """
        Set cost and performance estimates.

        Args:
            est_tokens_in: Estimated input tokens
            est_tokens_out: Estimated output tokens
            est_cost_usd: Estimated cost in USD
            est_latency_ms: Estimated latency in milliseconds

        Returns:
            New builder instance
        """
        cost = CostProfile(
            est_tokens_in=est_tokens_in,
            est_tokens_out=est_tokens_out,
            est_cost_usd=est_cost_usd,
            est_latency_ms=est_latency_ms,
        )
        return self._clone(cost=cost)

    # ========================================================================
    # Security & Permissions Configuration
    # ========================================================================

    def with_permissions(
        self,
        required_scopes: list[str] | None = None,
        allowed_roles: list[str] | None = None,
        hitl_required: bool = False,
        data_classification: (
            Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL", "SENSITIVE", "RESTRICTED"] | None
        ) = None,
    ) -> Self:
        """
        Set security and permission requirements.

        Args:
            required_scopes: OAuth scopes required (e.g., ["read:contacts"])
            allowed_roles: User roles allowed (e.g., ["admin", "editor"]) - empty means all roles
            hitl_required: Whether human-in-the-loop confirmation required
            data_classification: Data sensitivity ("PUBLIC", "CONFIDENTIAL", etc.)

        Returns:
            New builder instance
        """
        permissions = PermissionProfile(
            required_scopes=required_scopes or [],
            allowed_roles=allowed_roles or [],
            hitl_required=hitl_required,
            data_classification=data_classification or "CONFIDENTIAL",
        )
        return self._clone(permissions=permissions)

    def with_hitl(
        self,
        data_classification: Literal[
            "PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"
        ] = "CONFIDENTIAL",
    ) -> Self:
        """
        Enable HITL (Human-in-the-Loop) with data classification.

        Shorthand for with_permissions(hitl_required=True, ...).

        Args:
            data_classification: Data sensitivity level

        Returns:
            New builder instance
        """
        # Merge with existing permissions if any
        existing_perms = self._manifest.permissions or PermissionProfile()

        new_perms = PermissionProfile(
            required_scopes=existing_perms.required_scopes or [],
            allowed_roles=existing_perms.allowed_roles or [],
            hitl_required=True,
            data_classification=data_classification,
        )

        return self._clone(permissions=new_perms)

    # ========================================================================
    # Behavior Configuration
    # ========================================================================

    def with_context_key(self, context_key: str) -> Self:
        """
        Set context key for Store persistence.

        Args:
            context_key: Key for LangGraph Store (e.g., "contacts", "emails")

        Returns:
            New builder instance
        """
        return self._clone(context_key=context_key)

    def with_reference_fields(self, fields: list[str]) -> Self:
        """
        Set reference fields for context resolution.

        Args:
            fields: Fields used for reference resolution (e.g., ["name", "email"])

        Returns:
            New builder instance
        """
        return self._clone(reference_fields=fields)

    def with_field_mappings(self, mappings: dict[str, str]) -> Self:
        """
        Set field mappings (user-friendly name -> API field).

        Args:
            mappings: Mapping dictionary (e.g., {"name": "names/displayName"})

        Returns:
            New builder instance
        """
        return self._clone(field_mappings=mappings)

    def with_max_iterations(self, max_iterations: int) -> Self:
        """
        Set maximum iterations for tool execution.

        Args:
            max_iterations: Max number of times tool can be called

        Returns:
            New builder instance
        """
        return self._clone(max_iterations=max_iterations)

    def with_dry_run_support(self, supports_dry_run: bool = True) -> Self:
        """
        Enable dry-run mode support.

        Args:
            supports_dry_run: Whether tool supports dry-run

        Returns:
            New builder instance
        """
        return self._clone(supports_dry_run=supports_dry_run)

    # ========================================================================
    # Generic Presets (Domain-Agnostic)
    # ========================================================================

    def with_api_integration(
        self,
        provider: str,
        scopes: list[str],
        rate_limit: RateLimit | None = None,
        http2_enabled: bool = False,
    ) -> Self:
        """
        Generic preset for OAuth API integration.

        Works with ANY OAuth provider (Google, Microsoft, Salesforce, etc.).

        Args:
            provider: Provider name (for documentation/metrics)
            scopes: OAuth scopes required
            rate_limit: Optional rate limit configuration
            http2_enabled: Whether HTTP/2 should be used

        Returns:
            New builder instance

        Examples:
            >>> .with_api_integration(
            ...     provider="google",
            ...     scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            ...     rate_limit=RateLimit(requests=10, period_seconds=1)
            ... )
        """
        # Set permissions with scopes
        builder = self.with_permissions(
            required_scopes=scopes,
            hitl_required=True,  # API integrations default to HITL
            data_classification="CONFIDENTIAL",
        )

        # Set cost estimates (typical API call)
        builder = builder.with_cost_profile(
            est_tokens_in=150,
            est_tokens_out=400,
            est_cost_usd=0.001,
            est_latency_ms=500,
        )

        # Store rate limit in examples metadata (for documentation)
        if rate_limit:
            examples = self._manifest.examples or []
            examples.append(
                {
                    "_metadata": {
                        "provider": provider,
                        "rate_limit": {
                            "requests": rate_limit.requests,
                            "period_seconds": rate_limit.period_seconds,
                        },
                        "http2_enabled": http2_enabled,
                    }
                }
            )
            builder = builder._clone(examples=examples)

        return builder

    def with_rest_api_integration(
        self,
        base_url: str,
        auth_type: Literal["bearer", "api_key", "basic", "none"] = "bearer",
        rate_limit: RateLimit | None = None,
    ) -> Self:
        """
        Generic preset for REST API integration.

        Args:
            base_url: API base URL
            auth_type: Authentication type
            rate_limit: Optional rate limit

        Returns:
            New builder instance

        Examples:
            >>> .with_rest_api_integration(
            ...     base_url="https://api.example.com",
            ...     auth_type="bearer",
            ...     rate_limit=RateLimit(requests=100, period_seconds=60)
            ... )
        """
        # REST APIs may or may not need HITL (depends on sensitivity)
        builder = self.with_permissions(
            hitl_required=False,  # Default to no HITL (caller can override)
            data_classification="INTERNAL",
        )

        # REST APIs vary widely in cost/latency
        builder = builder.with_cost_profile(
            est_cost_usd=0.0005,
            est_latency_ms=300,
        )

        # Store metadata
        examples = self._manifest.examples or []
        examples.append(
            {
                "_metadata": {
                    "base_url": base_url,
                    "auth_type": auth_type,
                    "rate_limit": rate_limit.__dict__ if rate_limit else None,
                }
            }
        )
        return builder._clone(examples=examples)

    # ========================================================================
    # Validation & Build
    # ========================================================================

    def validate(self, rules: list[ValidationRule] | None = None) -> list[str]:
        """
        Validate manifest against rules.

        Args:
            rules: Optional custom validation rules (extends defaults)

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Default validations
        if (
            not self._manifest.description
            or self._manifest.description == "__BUILDER_PLACEHOLDER__"
        ):
            errors.append("Description is required (must call .with_description())")

        if not self._manifest.parameters and not self._manifest.outputs:
            errors.append("Tool must have at least parameters or outputs defined")

        # Check required parameters have descriptions
        for param in self._manifest.parameters:
            if param.required and not param.description:
                errors.append(f"Required parameter '{param.name}' must have description")

        # Custom rules
        if rules:
            for rule in rules:
                errors.extend(rule.validate(self._manifest))

        return errors

    def build(self, validate: bool = True) -> ToolManifest:
        """
        Build and return ToolManifest.

        Args:
            validate: Whether to run validation before building

        Returns:
            Constructed ToolManifest

        Raises:
            ValueError: If validation fails
        """
        if validate:
            errors = self.validate()
            if errors:
                error_msg = "Manifest validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
                raise ValueError(error_msg)

        return self._manifest


# ============================================================================
# Helper Functions
# ============================================================================


def create_tool_manifest(
    name: str,
    agent: str,
    config: dict[str, Any],
) -> ToolManifest:
    """
    Create ToolManifest from configuration dictionary.

    Useful for loading manifests from YAML/JSON files.

    Args:
        name: Tool name
        agent: Agent name
        config: Configuration dictionary matching builder methods

    Returns:
        Built ToolManifest

    Example:
        >>> config = {
        ...     "description": "Search items",
        ...     "parameters": [
        ...         {"name": "query", "type": "string", "required": True}
        ...     ],
        ...     "with_api_integration": {
        ...         "provider": "google",
        ...         "scopes": ["..."]
        ...     }
        ... }
        >>> manifest = create_tool_manifest("search_tool", "my_agent", config)
    """
    builder = ToolManifestBuilder(name, agent)

    # Apply configuration
    if "description" in config:
        builder = builder.with_description(config["description"])

    if FIELD_PARAMETERS in config:
        for param_config in config[FIELD_PARAMETERS]:
            builder = builder.add_parameter(**param_config)

    if "outputs" in config:
        for output_config in config["outputs"]:
            builder = builder.add_output(**output_config)

    # Apply presets
    for key, value in config.items():
        if key.startswith("with_") and hasattr(builder, key):
            method = getattr(builder, key)
            if isinstance(value, dict):
                builder = method(**value)
            else:
                builder = method(value)

    return builder.build()
