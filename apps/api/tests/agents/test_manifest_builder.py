"""
Tests for Tool Manifest Builder Pattern.

Test Strategy:
- Unit tests: Each builder method in isolation
- Integration tests: Complete manifest construction
- Parametrized tests: Generic validation across different agent types
- Contract tests: Builder produces valid ToolManifest

Best Practices:
- Test immutability (builder doesn't mutate)
- Test validation (fail-fast on invalid configuration)
- Test presets (generic configurations work)
- Test extensibility (custom validators)
"""

import pytest

from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.manifest_builder import (
    RateLimit,
    ToolManifestBuilder,
    ValidationRule,
    create_tool_manifest,
)

# ============================================================================
# Basic Builder Tests
# ============================================================================


def test_builder_initialization():
    """Test builder initializes with minimal required fields."""
    builder = ToolManifestBuilder("test_tool", "test_agent")

    manifest = builder.with_description("Test tool").build(validate=False)

    assert manifest.name == "test_tool"
    assert manifest.agent == "test_agent"
    assert manifest.version == "1.0.0"
    assert manifest.maintainer == "Team Agents"


def test_builder_immutability():
    """Test builder methods return new instances (immutable)."""
    builder1 = ToolManifestBuilder("test_tool", "test_agent")
    builder2 = builder1.with_description("Description 1")
    builder3 = builder2.with_description("Description 2")

    # Each builder should have different description
    assert builder1._manifest.description == "__BUILDER_PLACEHOLDER__"  # Initial placeholder
    assert builder2._manifest.description == "Description 1"
    assert builder3._manifest.description == "Description 2"

    # Verify true immutability - builder1 unchanged after builder2/builder3 created
    assert builder1._manifest.description == "__BUILDER_PLACEHOLDER__"


def test_builder_fluent_api():
    """Test fluent API chaining."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test description")
        .with_version("2.0.0")
        .with_maintainer("Team Test")
        .add_parameter("param1", "string", required=True)
        .add_output("output1", "string", "Output description")
        .build(validate=False)
    )

    assert manifest.description == "Test description"
    assert manifest.version == "2.0.0"
    assert manifest.maintainer == "Team Test"
    assert len(manifest.parameters) == 1
    assert len(manifest.outputs) == 1


# ============================================================================
# Parameter Configuration Tests
# ============================================================================


def test_add_parameter_basic():
    """Test adding basic parameter without constraints."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
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


def test_add_parameter_with_constraints():
    """Test parameter constraints are parsed correctly."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("age", "integer", required=True, description="User age", min=0, max=120)
        .add_parameter("email", "string", pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
        .add_parameter("status", "string", enum=["active", "inactive"])
        .build()
    )

    # Check integer constraints
    age_param = manifest.parameters[0]
    assert len(age_param.constraints) == 2
    assert any(c.kind == "minimum" and c.value == 0 for c in age_param.constraints)
    assert any(c.kind == "maximum" and c.value == 120 for c in age_param.constraints)

    # Check pattern constraint
    email_param = manifest.parameters[1]
    assert any(c.kind == "pattern" for c in email_param.constraints)

    # Check enum constraint
    status_param = manifest.parameters[2]
    assert any(
        c.kind == "enum" and c.value == ["active", "inactive"] for c in status_param.constraints
    )


@pytest.mark.parametrize(
    "constraint_kwargs,expected_kinds",
    [
        ({"min_length": 1, "max_length": 100}, ["min_length", "max_length"]),
        ({"min": 0, "max": 10}, ["minimum", "maximum"]),
        ({"minimum": 5, "maximum": 50}, ["minimum", "maximum"]),
        ({"enum": ["a", "b", "c"]}, ["enum"]),
        ({"pattern": r"^\d+$"}, ["pattern"]),
    ],
)
def test_parameter_constraints_parsing(constraint_kwargs, expected_kinds):
    """Test various constraint types are parsed correctly."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("param", "string", **constraint_kwargs)
        .build()
    )

    param = manifest.parameters[0]
    constraint_kinds = [c.kind for c in param.constraints]

    for expected_kind in expected_kinds:
        assert expected_kind in constraint_kinds


# ============================================================================
# Output Configuration Tests
# ============================================================================


def test_add_output():
    """Test adding output fields."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_output("items", "array", "List of items")
        .add_output("items[].id", "string", "Item ID")
        .add_output("total", "integer", "Total count", nullable=True)
        .build()
    )

    assert len(manifest.outputs) == 3

    items_output = manifest.outputs[0]
    assert items_output.path == "items"
    assert items_output.type == "array"
    assert items_output.nullable is False

    total_output = manifest.outputs[2]
    assert total_output.nullable is True


# ============================================================================
# Cost & Permissions Tests
# ============================================================================


def test_with_cost_profile():
    """Test cost profile configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_cost_profile(
            est_tokens_in=100,
            est_tokens_out=200,
            est_cost_usd=0.005,
            est_latency_ms=500,
        )
        .build()
    )

    assert manifest.cost is not None
    assert manifest.cost.est_tokens_in == 100
    assert manifest.cost.est_tokens_out == 200
    assert manifest.cost.est_cost_usd == 0.005
    assert manifest.cost.est_latency_ms == 500


def test_with_permissions():
    """Test permissions configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_permissions(
            required_scopes=["read:contacts"],
            allowed_roles=["admin"],
            hitl_required=True,
            data_classification="CONFIDENTIAL",
        )
        .build()
    )

    assert manifest.permissions is not None
    assert manifest.permissions.required_scopes == ["read:contacts"]
    assert manifest.permissions.allowed_roles == ["admin"]
    assert manifest.permissions.hitl_required is True
    assert manifest.permissions.data_classification == "CONFIDENTIAL"


def test_with_hitl_shorthand():
    """Test HITL shorthand method."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_hitl(data_classification="RESTRICTED")
        .build()
    )

    assert manifest.permissions is not None
    assert manifest.permissions.hitl_required is True
    assert manifest.permissions.data_classification == "RESTRICTED"


# ============================================================================
# Behavior Configuration Tests
# ============================================================================


def test_with_context_key():
    """Test context key configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_context_key("my_context")
        .build()
    )

    assert manifest.context_key == "my_context"


def test_with_reference_fields():
    """Test reference fields configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_reference_fields(["name", "email", "id"])
        .build()
    )

    assert manifest.reference_fields == ["name", "email", "id"]


def test_with_field_mappings():
    """Test field mappings configuration."""
    mappings = {"user_name": "names/displayName", "user_email": "emailAddresses/value"}

    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_field_mappings(mappings)
        .build()
    )

    assert manifest.field_mappings == mappings


def test_with_max_iterations():
    """Test max iterations configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_max_iterations(5)
        .build()
    )

    assert manifest.max_iterations == 5


def test_with_dry_run_support():
    """Test dry-run support configuration."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
        .with_dry_run_support(True)
        .build()
    )

    assert manifest.supports_dry_run is True


# ============================================================================
# Generic Presets Tests
# ============================================================================


def test_with_api_integration_preset():
    """Test generic API integration preset."""
    rate_limit = RateLimit(requests=10, period_seconds=1)

    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test API tool")
        .add_parameter("query", "string", required=True, description="Search query")
        .with_api_integration(
            provider="google",
            scopes=["https://www.googleapis.com/auth/contacts.readonly"],
            rate_limit=rate_limit,
            http2_enabled=True,
        )
        .build()
    )

    # Check permissions were set
    assert manifest.permissions is not None
    assert manifest.permissions.hitl_required is True
    assert manifest.permissions.data_classification == "CONFIDENTIAL"
    assert (
        "https://www.googleapis.com/auth/contacts.readonly" in manifest.permissions.required_scopes
    )

    # Check cost profile was set
    assert manifest.cost is not None
    assert manifest.cost.est_latency_ms == 500

    # Check metadata was stored in examples
    assert len(manifest.examples) > 0
    metadata = manifest.examples[0]["_metadata"]
    assert metadata["provider"] == "google"
    assert metadata["rate_limit"]["requests"] == 10


def test_with_database_integration_preset():
    """Test generic database integration preset."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test DB tool")
        .add_parameter("query", "string", required=True, description="SQL query")
        .with_database_integration(db_type="postgresql", read_only=True, max_rows=500)
        .build()
    )

    # Check permissions for read-only
    assert manifest.permissions is not None
    assert "data_reader" in manifest.permissions.allowed_roles
    assert manifest.permissions.hitl_required is False

    # Check cost profile (cheaper than API)
    assert manifest.cost is not None
    assert manifest.cost.est_latency_ms == 100


def test_with_rest_api_integration_preset():
    """Test generic REST API integration preset."""
    rate_limit = RateLimit(requests=100, period_seconds=60)

    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test REST API tool")
        .add_parameter("endpoint", "string", required=True, description="API endpoint")
        .with_rest_api_integration(
            base_url="https://api.example.com",
            auth_type="bearer",
            rate_limit=rate_limit,
        )
        .build()
    )

    # Check metadata
    assert len(manifest.examples) > 0
    metadata = manifest.examples[0]["_metadata"]
    assert metadata["base_url"] == "https://api.example.com"
    assert metadata["auth_type"] == "bearer"


# ============================================================================
# Validation Tests
# ============================================================================


def test_validation_requires_description():
    """Test validation fails without description."""
    builder = ToolManifestBuilder("test_tool", "test_agent")

    with pytest.raises(ValueError, match="Description is required"):
        builder.build(validate=True)


def test_validation_requires_parameters_or_outputs():
    """Test validation fails without parameters or outputs."""
    builder = ToolManifestBuilder("test_tool", "test_agent").with_description("Test")

    with pytest.raises(ValueError, match="must have at least parameters or outputs"):
        builder.build(validate=True)


def test_validation_required_parameters_need_description():
    """Test required parameters must have descriptions."""
    builder = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("param1", "string", required=True)  # No description
    )

    with pytest.raises(ValueError, match="must have description"):
        builder.build(validate=True)


def test_custom_validation_rule():
    """Test custom validation rules can be added."""

    class CustomRule(ValidationRule):
        def validate(self, manifest: ToolManifest) -> list[str]:
            if manifest.name.startswith("test_"):
                return ["Tool name should not start with 'test_'"]
            return []

    builder = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_output("output", "string", "Output")
    )

    errors = builder.validate(rules=[CustomRule()])
    assert len(errors) == 1
    assert "should not start with 'test_'" in errors[0]


def test_build_skip_validation():
    """Test build can skip validation if needed."""
    manifest = ToolManifestBuilder("test_tool", "test_agent").build(validate=False)

    # Should succeed even without description
    assert manifest.name == "test_tool"


# ============================================================================
# Complete Manifest Construction Tests
# ============================================================================


def test_complete_manifest_construction():
    """Test building a complete, realistic manifest."""
    manifest = (
        ToolManifestBuilder("search_items_tool", "items_agent")
        .with_description("Search items by query with filters")
        .with_version("1.2.0")
        .with_maintainer("Team Data")
        # Parameters
        .add_parameter("query", "string", required=True, description="Search query", min_length=1)
        .add_parameter(
            "category",
            "string",
            description="Filter by category",
            enum=["all", "active", "archived"],
        )
        .add_parameter("limit", "integer", description="Max results", min=1, max=100)
        # Outputs
        .add_output("items", "array", "List of items found")
        .add_output("items[].id", "string", "Item ID")
        .add_output("items[].name", "string", "Item name")
        .add_output("total", "integer", "Total count")
        # Cost & Permissions
        .with_cost_profile(est_cost_usd=0.001, est_latency_ms=300)
        .with_hitl(data_classification="INTERNAL")
        # Behavior
        .with_context_key("items")
        .with_reference_fields(["name", "id"])
        .with_max_iterations(1)
        .build()
    )

    # Validate structure
    assert manifest.name == "search_items_tool"
    assert manifest.agent == "items_agent"
    assert manifest.version == "1.2.0"
    assert len(manifest.parameters) == 3
    assert len(manifest.outputs) == 4
    assert manifest.permissions.hitl_required is True
    assert manifest.context_key == "items"


# ============================================================================
# Config-Based Construction Tests
# ============================================================================


def test_create_tool_manifest_from_config():
    """Test creating manifest from configuration dictionary."""
    config = {
        "description": "Test tool from config",
        "parameters": [
            {"name": "param1", "type": "string", "required": True, "description": "Param 1"},
            {"name": "param2", "type": "integer", "min": 0, "max": 10},
        ],
        "outputs": [
            {"path": "result", "type": "string", "description": "Result"},
        ],
        "with_hitl": {"data_classification": "CONFIDENTIAL"},
        "with_context_key": "test_context",
    }

    manifest = create_tool_manifest("test_tool", "test_agent", config)

    assert manifest.name == "test_tool"
    assert manifest.description == "Test tool from config"
    assert len(manifest.parameters) == 2
    assert manifest.permissions.hitl_required is True
    assert manifest.context_key == "test_context"


# ============================================================================
# Parametrized Tests (Generic Validation)
# ============================================================================


@pytest.mark.parametrize(
    "preset_method,preset_kwargs",
    [
        ("with_api_integration", {"provider": "google", "scopes": ["read"]}),
        ("with_database_integration", {"db_type": "postgresql", "read_only": True}),
        ("with_rest_api_integration", {"base_url": "https://api.test.com"}),
    ],
)
def test_presets_produce_valid_manifests(preset_method, preset_kwargs):
    """Test all presets produce valid manifests (parametrized)."""
    builder = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Test input")
    )

    # Apply preset
    preset_fn = getattr(builder, preset_method)
    builder = preset_fn(**preset_kwargs)

    # Should build successfully
    manifest = builder.build()

    assert manifest.name == "test_tool"
    assert manifest.permissions is not None
    assert manifest.cost is not None


@pytest.mark.parametrize(
    "tool_name,agent_name",
    [
        ("search_contacts_tool", "contacts_agent"),
        ("send_email_tool", "emails_agent"),
        ("create_event_tool", "calendar_agent"),
        ("query_database_tool", "database_agent"),
    ],
)
def test_builder_works_for_any_agent_type(tool_name, agent_name):
    """Test builder is truly generic across agent types (parametrized)."""
    manifest = (
        ToolManifestBuilder(tool_name, agent_name)
        .with_description(f"Generic tool for {agent_name}")
        .add_parameter("input", "string", required=True, description="Input parameter")
        .add_output("output", "string", "Output result")
        .build()
    )

    assert manifest.name == tool_name
    assert manifest.agent == agent_name
    assert len(manifest.parameters) == 1
    assert len(manifest.outputs) == 1


# ============================================================================
# Edge Cases & Error Handling
# ============================================================================


def test_empty_parameter_list():
    """Test manifest with no parameters (only outputs)."""
    manifest = (
        ToolManifestBuilder("list_all_tool", "test_agent")
        .with_description("List all items")
        .add_output("items", "array", "All items")
        .build()
    )

    assert len(manifest.parameters) == 0
    assert len(manifest.outputs) == 1


def test_negative_number_constraints():
    """Test constraints with negative numbers (e.g., temperature range)."""
    manifest = (
        ToolManifestBuilder("weather_tool", "test_agent")
        .with_description("Weather query")
        .add_parameter(
            "min_temp", "integer", required=True, description="Min temperature", min=-50, max=50
        )
        .build()
    )

    param = manifest.parameters[0]
    constraints_dict = {c.kind: c.value for c in param.constraints}
    assert constraints_dict["minimum"] == -50
    assert constraints_dict["maximum"] == 50


def test_zero_value_constraints():
    """Test that zero values in constraints are preserved (not treated as falsy)."""
    manifest = (
        ToolManifestBuilder("offset_tool", "test_agent")
        .with_description("Offset query")
        .add_parameter("offset", "integer", required=True, description="Offset", min=0, max=100)
        .add_parameter("limit", "integer", required=False, description="Limit", min=0, max=1000)
        .build()
    )

    offset_param = manifest.parameters[0]
    offset_constraints = {c.kind: c.value for c in offset_param.constraints}
    assert offset_constraints["minimum"] == 0  # Critical: 0 should not become None


def test_multiple_presets_composition():
    """Test composing multiple presets (API + HITL + Context)."""
    manifest = (
        ToolManifestBuilder("complex_tool", "test_agent")
        .with_description("Complex multi-preset tool")
        .add_parameter("query", "string", required=True, description="Query")
        .with_api_integration(provider="google", scopes=["read"])
        .with_hitl(data_classification="RESTRICTED")
        .with_context_key("complex_context")
        .with_max_iterations(3)
        .build()
    )

    # All presets should be applied
    assert manifest.permissions.hitl_required is True
    assert manifest.permissions.data_classification == "RESTRICTED"
    assert manifest.context_key == "complex_context"
    assert manifest.max_iterations == 3


def test_optional_parameter_without_description():
    """Test that optional parameters don't require description (only required ones do)."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("required_param", "string", required=True, description="Required param")
        .add_parameter("optional_param", "string", required=False)  # No description
        .build()
    )

    assert len(manifest.parameters) == 2
    assert manifest.parameters[1].description is None or manifest.parameters[1].description == ""


def test_nullable_outputs():
    """Test outputs marked as nullable."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Input")
        .add_output("result", "string", "Main result", nullable=False)
        .add_output("optional_data", "object", "Optional data", nullable=True)
        .build()
    )

    assert manifest.outputs[0].nullable is False
    assert manifest.outputs[1].nullable is True


def test_nested_output_paths():
    """Test complex JSONPath output paths."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("input", "string", required=True, description="Input")
        .add_output("contacts[].name.displayName", "string", "Contact display name")
        .add_output("contacts[].emails[0].value", "string", "Primary email")
        .build()
    )

    assert manifest.outputs[0].path == "contacts[].name.displayName"
    assert manifest.outputs[1].path == "contacts[].emails[0].value"


def test_build_without_validation():
    """Test building manifest without validation (bypass checks)."""
    # This should NOT raise even without description
    manifest = ToolManifestBuilder("incomplete_tool", "test_agent").build(validate=False)

    assert manifest.name == "incomplete_tool"
    assert manifest.description == "__BUILDER_PLACEHOLDER__"  # Invalid but allowed


def test_long_enum_constraint():
    """Test enum constraint with many values."""
    statuses = ["pending", "active", "suspended", "archived", "deleted", "banned", "frozen"]

    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("status", "string", required=True, description="Status", enum=statuses)
        .build()
    )

    param = manifest.parameters[0]
    enum_constraint = next((c for c in param.constraints if c.kind == "enum"), None)
    assert enum_constraint is not None
    assert enum_constraint.value == statuses


def test_pattern_with_special_characters():
    """Test regex pattern with special characters (escaped properly)."""
    # Email pattern with backslashes
    email_pattern = r"^[\w\.-]+@[\w\.-]+\.\w+$"

    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter("email", "string", required=True, description="Email", pattern=email_pattern)
        .build()
    )

    param = manifest.parameters[0]
    pattern_constraint = next((c for c in param.constraints if c.kind == "pattern"), None)
    assert pattern_constraint is not None
    assert pattern_constraint.value == email_pattern


def test_empty_output_list():
    """Test manifest with no outputs (only parameters)."""
    manifest = (
        ToolManifestBuilder("delete_tool", "test_agent")
        .with_description("Delete item")
        .add_parameter("id", "string", required=True, description="Item ID")
        .build()
    )

    assert len(manifest.parameters) == 1
    assert len(manifest.outputs) == 0


def test_multiple_constraint_types_on_same_parameter():
    """Test parameter with multiple constraint types."""
    manifest = (
        ToolManifestBuilder("test_tool", "test_agent")
        .with_description("Test")
        .add_parameter(
            "username",
            "string",
            required=True,
            description="Username",
            min_length=3,
            max_length=20,
            pattern=r"^[a-zA-Z0-9_]+$",
        )
        .build()
    )

    param = manifest.parameters[0]
    assert len(param.constraints) == 3
    constraint_kinds = [c.kind for c in param.constraints]
    assert "min_length" in constraint_kinds
    assert "max_length" in constraint_kinds
    assert "pattern" in constraint_kinds
