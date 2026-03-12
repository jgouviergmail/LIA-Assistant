"""
Unit tests for Tool Manifest Builder.

Tests for the fluent API ToolManifestBuilder that constructs ToolManifest objects.
"""

import pytest

from src.domains.agents.registry.manifest_builder import (
    CachingStrategy,
    RateLimit,
    ToolManifestBuilder,
    create_tool_manifest,
)


class TestRateLimit:
    """Tests for RateLimit dataclass."""

    def test_rate_limit_creation(self):
        """Test basic RateLimit creation."""
        rate_limit = RateLimit(requests=10, period_seconds=1.0)
        assert rate_limit.requests == 10
        assert rate_limit.period_seconds == 1.0
        assert rate_limit.burst_size is None

    def test_rate_limit_with_burst(self):
        """Test RateLimit with burst size."""
        rate_limit = RateLimit(requests=10, period_seconds=1.0, burst_size=20)
        assert rate_limit.burst_size == 20

    def test_rate_limit_is_frozen(self):
        """Test that RateLimit is immutable (frozen)."""
        rate_limit = RateLimit(requests=10, period_seconds=1.0)
        with pytest.raises(AttributeError):
            rate_limit.requests = 20  # type: ignore[misc]


class TestCachingStrategy:
    """Tests for CachingStrategy dataclass."""

    def test_caching_strategy_creation(self):
        """Test basic CachingStrategy creation."""
        strategy = CachingStrategy(ttl_seconds=300)
        assert strategy.ttl_seconds == 300
        assert strategy.invalidation_events == []
        assert strategy.cache_key_template is None

    def test_caching_strategy_with_events(self):
        """Test CachingStrategy with invalidation events."""
        strategy = CachingStrategy(
            ttl_seconds=300,
            invalidation_events=["create", "update"],
        )
        assert strategy.invalidation_events == ["create", "update"]

    def test_caching_strategy_with_key_template(self):
        """Test CachingStrategy with cache key template."""
        strategy = CachingStrategy(
            ttl_seconds=60,
            cache_key_template="user:{user_id}:contacts",
        )
        assert strategy.cache_key_template == "user:{user_id}:contacts"

    def test_caching_strategy_is_frozen(self):
        """Test that CachingStrategy is immutable."""
        strategy = CachingStrategy(ttl_seconds=300)
        with pytest.raises(AttributeError):
            strategy.ttl_seconds = 600  # type: ignore[misc]


class TestToolManifestBuilderInit:
    """Tests for ToolManifestBuilder initialization."""

    def test_builder_init_sets_name_and_agent(self):
        """Test that builder stores name and agent."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.name == "my_tool"
        assert manifest.agent == "my_agent"

    def test_builder_init_creates_placeholder_description(self):
        """Test that builder creates placeholder description."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.description == "__BUILDER_PLACEHOLDER__"

    def test_builder_init_sets_default_version(self):
        """Test that builder sets default version."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.version == "1.0.0"

    def test_builder_init_sets_default_maintainer(self):
        """Test that builder sets default maintainer."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.maintainer == "Team Agents"

    def test_builder_init_creates_empty_parameters(self):
        """Test that builder creates empty parameters list."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.parameters == []

    def test_builder_init_creates_empty_outputs(self):
        """Test that builder creates empty outputs list."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.outputs == []


class TestToolManifestBuilderCoreConfig:
    """Tests for core configuration methods."""

    def test_with_description(self):
        """Test setting description."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("A useful tool")
            .build(validate=False)
        )
        assert manifest.description == "A useful tool"

    def test_with_version(self):
        """Test setting version."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent").with_version("2.0.0").build(validate=False)
        )
        assert manifest.version == "2.0.0"

    def test_with_maintainer(self):
        """Test setting maintainer."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_maintainer("Team Data")
            .build(validate=False)
        )
        assert manifest.maintainer == "Team Data"


class TestToolManifestBuilderParameters:
    """Tests for parameter configuration methods."""

    def test_add_simple_parameter(self):
        """Test adding a simple parameter."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("query", "string", required=True, description="Search query")
            .build()
        )
        assert len(manifest.parameters) == 1
        param = manifest.parameters[0]
        assert param.name == "query"
        assert param.type == "string"
        assert param.required is True
        assert param.description == "Search query"

    def test_add_multiple_parameters(self):
        """Test adding multiple parameters."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("query", "string", required=True, description="Query")
            .add_parameter("limit", "integer", required=False, description="Limit")
            .add_parameter("active", "boolean", required=False)
            .build()
        )
        assert len(manifest.parameters) == 3
        names = [p.name for p in manifest.parameters]
        assert names == ["query", "limit", "active"]

    def test_add_parameter_with_min_length_constraint(self):
        """Test parameter with min_length constraint."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("query", "string", required=True, description="Q", min_length=1)
            .build()
        )
        param = manifest.parameters[0]
        assert len(param.constraints) == 1
        assert param.constraints[0].kind == "min_length"
        assert param.constraints[0].value == 1

    def test_add_parameter_with_max_length_constraint(self):
        """Test parameter with max_length constraint."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("query", "string", required=True, description="Q", max_length=100)
            .build()
        )
        param = manifest.parameters[0]
        assert len(param.constraints) == 1
        assert param.constraints[0].kind == "max_length"
        assert param.constraints[0].value == 100

    def test_add_parameter_with_min_max_constraints(self):
        """Test parameter with min/max (number) constraints."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("limit", "integer", required=True, description="Limit", min=1, max=100)
            .build()
        )
        param = manifest.parameters[0]
        assert len(param.constraints) == 2
        kinds = {c.kind for c in param.constraints}
        assert "minimum" in kinds
        assert "maximum" in kinds

    def test_add_parameter_with_minimum_maximum_constraints(self):
        """Test parameter with minimum/maximum (alternative naming)."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter(
                "value", "number", required=True, description="V", minimum=0.0, maximum=1.0
            )
            .build()
        )
        param = manifest.parameters[0]
        kinds = {c.kind for c in param.constraints}
        assert "minimum" in kinds
        assert "maximum" in kinds

    def test_add_parameter_with_enum_constraint(self):
        """Test parameter with enum constraint."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter(
                "status",
                "string",
                required=True,
                description="S",
                enum=["active", "inactive", "pending"],
            )
            .build()
        )
        param = manifest.parameters[0]
        assert len(param.constraints) == 1
        assert param.constraints[0].kind == "enum"
        assert param.constraints[0].value == ["active", "inactive", "pending"]

    def test_add_parameter_with_pattern_constraint(self):
        """Test parameter with regex pattern constraint."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter(
                "email",
                "string",
                required=True,
                description="E",
                pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$",
            )
            .build()
        )
        param = manifest.parameters[0]
        assert len(param.constraints) == 1
        assert param.constraints[0].kind == "pattern"


class TestToolManifestBuilderOutputs:
    """Tests for output configuration methods."""

    def test_add_simple_output(self):
        """Test adding a simple output."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .add_output("items", "array", "List of items")
            .build()
        )
        assert len(manifest.outputs) == 1
        output = manifest.outputs[0]
        assert output.path == "items"
        assert output.type == "array"
        assert output.description == "List of items"
        assert output.nullable is False

    def test_add_nullable_output(self):
        """Test adding a nullable output."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .add_output("result", "object", "Result", nullable=True)
            .build()
        )
        assert manifest.outputs[0].nullable is True

    def test_add_multiple_outputs(self):
        """Test adding multiple outputs."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .add_output("items", "array", "Items")
            .add_output("total", "integer", "Total count")
            .add_output("items[].id", "string", "Item ID")
            .build()
        )
        assert len(manifest.outputs) == 3


class TestToolManifestBuilderCostProfile:
    """Tests for cost profile configuration."""

    def test_with_cost_profile(self):
        """Test setting cost profile."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_cost_profile(
                est_tokens_in=100,
                est_tokens_out=200,
                est_cost_usd=0.01,
                est_latency_ms=500,
            )
            .build()
        )
        assert manifest.cost.est_tokens_in == 100
        assert manifest.cost.est_tokens_out == 200
        assert manifest.cost.est_cost_usd == 0.01
        assert manifest.cost.est_latency_ms == 500


class TestToolManifestBuilderPermissions:
    """Tests for permissions configuration."""

    def test_with_permissions(self):
        """Test setting permissions."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_permissions(
                required_scopes=["read:contacts", "write:contacts"],
                allowed_roles=["admin", "editor"],
                hitl_required=True,
                data_classification="CONFIDENTIAL",
            )
            .build()
        )
        assert manifest.permissions.required_scopes == ["read:contacts", "write:contacts"]
        assert manifest.permissions.allowed_roles == ["admin", "editor"]
        assert manifest.permissions.hitl_required is True
        assert manifest.permissions.data_classification == "CONFIDENTIAL"

    def test_with_permissions_defaults(self):
        """Test permissions with default values."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_permissions()
            .build()
        )
        assert manifest.permissions.required_scopes == []
        assert manifest.permissions.allowed_roles == []
        assert manifest.permissions.hitl_required is False
        assert manifest.permissions.data_classification == "CONFIDENTIAL"

    def test_with_hitl(self):
        """Test enabling HITL shorthand."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_hitl(data_classification="RESTRICTED")
            .build()
        )
        assert manifest.permissions.hitl_required is True
        assert manifest.permissions.data_classification == "RESTRICTED"

    def test_with_hitl_preserves_existing_permissions(self):
        """Test that with_hitl preserves existing permission settings."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_permissions(required_scopes=["read:contacts"])
            .with_hitl()
            .build()
        )
        assert manifest.permissions.hitl_required is True
        assert manifest.permissions.required_scopes == ["read:contacts"]


class TestToolManifestBuilderBehavior:
    """Tests for behavior configuration."""

    def test_with_context_key(self):
        """Test setting context key."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_context_key("contacts")
            .build()
        )
        assert manifest.context_key == "contacts"

    def test_with_reference_fields(self):
        """Test setting reference fields."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_reference_fields(["name", "email"])
            .build()
        )
        assert manifest.reference_fields == ["name", "email"]

    def test_with_field_mappings(self):
        """Test setting field mappings."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_field_mappings({"name": "names/displayName", "email": "emailAddresses[0]/value"})
            .build()
        )
        assert manifest.field_mappings == {
            "name": "names/displayName",
            "email": "emailAddresses[0]/value",
        }

    def test_with_max_iterations(self):
        """Test setting max iterations."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_max_iterations(5)
            .build()
        )
        assert manifest.max_iterations == 5

    def test_with_dry_run_support(self):
        """Test enabling dry-run support."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_dry_run_support()
            .build()
        )
        assert manifest.supports_dry_run is True


class TestToolManifestBuilderPresets:
    """Tests for generic presets."""

    def test_with_api_integration(self):
        """Test API integration preset."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_api_integration(
                provider="google",
                scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            )
            .build()
        )
        # API integration sets HITL and scopes
        assert manifest.permissions.hitl_required is True
        assert manifest.permissions.required_scopes == [
            "https://www.googleapis.com/auth/contacts.readonly"
        ]
        # Sets default cost profile
        assert manifest.cost.est_latency_ms == 500

    def test_with_api_integration_and_rate_limit(self):
        """Test API integration preset with rate limit."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_api_integration(
                provider="google",
                scopes=["scope"],
                rate_limit=RateLimit(requests=10, period_seconds=1.0),
            )
            .build()
        )
        # Rate limit stored in examples metadata
        assert manifest.examples is not None
        assert len(manifest.examples) > 0

    def test_with_rest_api_integration(self):
        """Test REST API integration preset."""
        manifest = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("q", "string", required=True, description="Q")
            .with_rest_api_integration(
                base_url="https://api.example.com",
                auth_type="bearer",
            )
            .build()
        )
        # REST API defaults to no HITL
        assert manifest.permissions.hitl_required is False
        assert manifest.permissions.data_classification == "INTERNAL"


class TestToolManifestBuilderValidation:
    """Tests for validation functionality."""

    def test_validate_fails_without_description(self):
        """Test validation fails without description."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        errors = builder.validate()
        assert len(errors) > 0
        assert any("description" in e.lower() for e in errors)

    def test_validate_fails_without_parameters_or_outputs(self):
        """Test validation fails without parameters or outputs."""
        builder = ToolManifestBuilder("my_tool", "my_agent").with_description("Test")
        errors = builder.validate()
        assert len(errors) > 0
        assert any("parameters or outputs" in e.lower() for e in errors)

    def test_validate_fails_for_required_param_without_description(self):
        """Test validation fails for required param without description."""
        builder = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("Test")
            .add_parameter("query", "string", required=True)  # No description
        )
        errors = builder.validate()
        assert len(errors) > 0
        assert any("description" in e.lower() for e in errors)

    def test_validate_passes_for_valid_manifest(self):
        """Test validation passes for valid manifest."""
        builder = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("A useful tool")
            .add_parameter("query", "string", required=True, description="Search query")
        )
        errors = builder.validate()
        assert errors == []

    def test_validate_accepts_outputs_only(self):
        """Test validation accepts manifest with only outputs."""
        builder = (
            ToolManifestBuilder("my_tool", "my_agent")
            .with_description("A useful tool")
            .add_output("result", "object", "The result")
        )
        errors = builder.validate()
        assert errors == []

    def test_build_raises_on_invalid(self):
        """Test build() raises ValueError for invalid manifest."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        with pytest.raises(ValueError) as exc_info:
            builder.build()
        assert "validation failed" in str(exc_info.value).lower()

    def test_build_with_validate_false_bypasses_validation(self):
        """Test build(validate=False) bypasses validation."""
        builder = ToolManifestBuilder("my_tool", "my_agent")
        manifest = builder.build(validate=False)
        assert manifest.name == "my_tool"


class TestToolManifestBuilderImmutability:
    """Tests for builder immutability."""

    def test_builder_returns_new_instance(self):
        """Test that builder methods return new instances."""
        builder1 = ToolManifestBuilder("my_tool", "my_agent")
        builder2 = builder1.with_description("Test")
        assert builder1 is not builder2

    def test_chained_methods_dont_modify_original(self):
        """Test that chaining doesn't modify original builder."""
        builder1 = ToolManifestBuilder("my_tool", "my_agent")
        builder2 = builder1.with_description("Test")

        manifest1 = builder1.build(validate=False)
        manifest2 = builder2.build(validate=False)

        assert manifest1.description == "__BUILDER_PLACEHOLDER__"
        assert manifest2.description == "Test"


class TestToolManifestBuilderChaining:
    """Tests for fluent API chaining."""

    def test_full_fluent_chain(self):
        """Test complete fluent API chain."""
        manifest = (
            ToolManifestBuilder("search_contacts", "contacts")
            .with_description("Search contacts by query")
            .with_version("1.0.0")
            .with_maintainer("Team Contacts")
            .add_parameter(
                "query", "string", required=True, description="Search query", min_length=1
            )
            .add_parameter(
                "limit", "integer", required=False, description="Max results", min=1, max=100
            )
            .add_output("contacts", "array", "List of contacts")
            .add_output("total", "integer", "Total count")
            .with_cost_profile(est_tokens_in=150, est_tokens_out=400, est_latency_ms=300)
            .with_permissions(required_scopes=["read:contacts"], hitl_required=True)
            .with_context_key("contacts")
            .with_reference_fields(["name", "email"])
            .build()
        )

        assert manifest.name == "search_contacts"
        assert manifest.agent == "contacts"
        assert manifest.description == "Search contacts by query"
        assert len(manifest.parameters) == 2
        assert len(manifest.outputs) == 2
        assert manifest.cost.est_latency_ms == 300
        assert manifest.permissions.hitl_required is True
        assert manifest.context_key == "contacts"


class TestCreateToolManifest:
    """Tests for create_tool_manifest() helper function."""

    def test_create_from_config(self):
        """Test creating manifest from config dict."""
        config = {
            "description": "Search items",
            "parameters": [
                {"name": "query", "type": "string", "required": True, "description": "Q"},
            ],
        }
        manifest = create_tool_manifest("search_tool", "my_agent", config)
        assert manifest.name == "search_tool"
        assert manifest.description == "Search items"
        assert len(manifest.parameters) == 1

    def test_create_with_outputs(self):
        """Test creating manifest with outputs in config."""
        config = {
            "description": "Fetch data",
            "parameters": [{"name": "id", "type": "string", "required": True, "description": "ID"}],
            "outputs": [
                {"path": "data", "type": "object", "description": "The data"},
            ],
        }
        manifest = create_tool_manifest("fetch_tool", "my_agent", config)
        assert len(manifest.outputs) == 1
        assert manifest.outputs[0].path == "data"

    def test_create_with_preset_methods(self):
        """Test creating manifest with preset method in config."""
        config = {
            "description": "API tool",
            "parameters": [{"name": "q", "type": "string", "required": True, "description": "Q"}],
            "with_context_key": "items",
            "with_max_iterations": 5,
        }
        manifest = create_tool_manifest("api_tool", "my_agent", config)
        assert manifest.context_key == "items"
        assert manifest.max_iterations == 5
