"""
Unit tests for catalogue dataclasses and exceptions.

Phase: Session 15 - Registry Modules (registry/catalogue)
Created: 2025-11-20

Focus: Validation logic in __post_init__ methods and exception constructors
Target Coverage: 81% → 100% (25 missing lines)
"""

from datetime import datetime

import pytest

from src.core.constants import CONTACTS_AGENT_PROMPT_VERSION_DEFAULT
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    AgentManifestAlreadyRegistered,
    AgentManifestNotFound,
    CatalogueError,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
    ToolManifestAlreadyRegistered,
    ToolManifestNotFound,
)


class TestCostProfile:
    """Tests for CostProfile dataclass validation."""

    def test_cost_profile_valid_values(self):
        """Test CostProfile with valid values."""
        profile = CostProfile(
            est_tokens_in=150,
            est_tokens_out=400,
            est_cost_usd=0.005,
            est_latency_ms=1200,
        )

        assert profile.est_tokens_in == 150
        assert profile.est_tokens_out == 400
        assert profile.est_cost_usd == 0.005
        assert profile.est_latency_ms == 1200

    def test_cost_profile_zero_values(self):
        """Test CostProfile with zero values (valid)."""
        profile = CostProfile(est_tokens_in=0, est_tokens_out=0, est_cost_usd=0.0, est_latency_ms=0)

        assert profile.est_tokens_in == 0
        assert profile.est_tokens_out == 0
        assert profile.est_cost_usd == 0.0
        assert profile.est_latency_ms == 0

    def test_cost_profile_negative_tokens_in_raises(self):
        """Test that negative est_tokens_in raises ValueError (Line 71)."""
        with pytest.raises(ValueError) as exc_info:
            CostProfile(est_tokens_in=-1)

        assert "est_tokens_in must be >= 0" in str(exc_info.value)

    def test_cost_profile_negative_tokens_out_raises(self):
        """Test that negative est_tokens_out raises ValueError (Line 73)."""
        with pytest.raises(ValueError) as exc_info:
            CostProfile(est_tokens_out=-1)

        assert "est_tokens_out must be >= 0" in str(exc_info.value)

    def test_cost_profile_negative_cost_raises(self):
        """Test that negative est_cost_usd raises ValueError (Line 75)."""
        with pytest.raises(ValueError) as exc_info:
            CostProfile(est_cost_usd=-0.001)

        assert "est_cost_usd must be >= 0" in str(exc_info.value)

    def test_cost_profile_negative_latency_raises(self):
        """Test that negative est_latency_ms raises ValueError (Line 77)."""
        with pytest.raises(ValueError) as exc_info:
            CostProfile(est_latency_ms=-100)

        assert "est_latency_ms must be >= 0" in str(exc_info.value)

    def test_cost_profile_is_frozen(self):
        """Test that CostProfile is immutable (frozen=True)."""
        profile = CostProfile(est_tokens_in=100)

        with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
            profile.est_tokens_in = 200


class TestPermissionProfile:
    """Tests for PermissionProfile dataclass."""

    def test_permission_profile_defaults(self):
        """Test PermissionProfile with default values."""
        profile = PermissionProfile()

        assert profile.required_scopes == []
        assert profile.allowed_roles == []
        assert profile.data_classification == "CONFIDENTIAL"
        assert profile.hitl_required is False

    def test_permission_profile_with_scopes(self):
        """Test PermissionProfile with custom scopes."""
        profile = PermissionProfile(
            required_scopes=["google_contacts.read", "google_contacts.write"],
            data_classification="SENSITIVE",
            hitl_required=True,
        )

        assert len(profile.required_scopes) == 2
        assert "google_contacts.read" in profile.required_scopes
        assert profile.data_classification == "SENSITIVE"
        assert profile.hitl_required is True

    def test_permission_profile_is_frozen(self):
        """Test that PermissionProfile is immutable."""
        profile = PermissionProfile()

        with pytest.raises((AttributeError, TypeError)):  # FrozenInstanceError
            profile.hitl_required = True


class TestParameterConstraint:
    """Tests for ParameterConstraint dataclass."""

    def test_parameter_constraint_min_length(self):
        """Test ParameterConstraint with min_length."""
        constraint = ParameterConstraint(kind="min_length", value=1)

        assert constraint.kind == "min_length"
        assert constraint.value == 1

    def test_parameter_constraint_pattern(self):
        """Test ParameterConstraint with regex pattern."""
        constraint = ParameterConstraint(kind="pattern", value=r"^people/c\d+$")

        assert constraint.kind == "pattern"
        assert constraint.value == r"^people/c\d+$"

    def test_parameter_constraint_enum(self):
        """Test ParameterConstraint with enum values."""
        constraint = ParameterConstraint(kind="enum", value=["ASC", "DESC"])

        assert constraint.kind == "enum"
        assert constraint.value == ["ASC", "DESC"]


class TestParameterSchema:
    """Tests for ParameterSchema dataclass."""

    def test_parameter_schema_required(self):
        """Test ParameterSchema for required parameter."""
        schema = ParameterSchema(
            name="query",
            type="string",
            required=True,
            description="Search query",
            constraints=[ParameterConstraint(kind="min_length", value=1)],
        )

        assert schema.name == "query"
        assert schema.type == "string"
        assert schema.required is True
        assert len(schema.constraints) == 1

    def test_parameter_schema_optional_with_json_schema(self):
        """Test ParameterSchema with JSON Schema."""
        json_schema = {"type": "array", "items": {"type": "string"}}
        schema = ParameterSchema(
            name="tags",
            type="array",
            required=False,
            description="List of tags",
            schema=json_schema,
        )

        assert schema.required is False
        assert schema.schema == json_schema


class TestOutputFieldSchema:
    """Tests for OutputFieldSchema dataclass."""

    def test_output_field_schema_basic(self):
        """Test OutputFieldSchema for basic field."""
        schema = OutputFieldSchema(
            path="contacts[].resource_name", type="string", description="Contact ID"
        )

        assert schema.path == "contacts[].resource_name"
        assert schema.type == "string"
        assert schema.nullable is False

    def test_output_field_schema_nullable(self):
        """Test OutputFieldSchema with nullable field."""
        schema = OutputFieldSchema(
            path="contacts[].emails", type="array", description="Email addresses", nullable=True
        )

        assert schema.nullable is True


class TestDisplayMetadata:
    """Tests for DisplayMetadata dataclass validation."""

    def test_display_metadata_valid(self):
        """Test DisplayMetadata with valid values."""
        metadata = DisplayMetadata(
            emoji="🔍", i18n_key="search_contacts", visible=True, category="tool"
        )

        assert metadata.emoji == "🔍"
        assert metadata.i18n_key == "search_contacts"
        assert metadata.visible is True
        assert metadata.category == "tool"

    def test_display_metadata_empty_emoji_raises(self):
        """Test that empty emoji raises ValueError (Line 269)."""
        with pytest.raises(ValueError) as exc_info:
            DisplayMetadata(emoji="", i18n_key="test")

        assert "emoji cannot be empty" in str(exc_info.value)

    def test_display_metadata_empty_i18n_key_raises(self):
        """Test that empty i18n_key raises ValueError (Line 271)."""
        with pytest.raises(ValueError) as exc_info:
            DisplayMetadata(emoji="🔍", i18n_key="")

        assert "i18n_key cannot be empty" in str(exc_info.value)

    def test_display_metadata_long_emoji_raises(self):
        """Test that long emoji string raises ValueError (Line 274)."""
        with pytest.raises(ValueError) as exc_info:
            DisplayMetadata(emoji="🔍🔍🔍🔍🔍", i18n_key="test")  # 5 emojis

        assert "emoji should be a single emoji character" in str(exc_info.value)

    def test_display_metadata_multi_codepoint_emoji_allowed(self):
        """Test that multi-codepoint emoji (up to 4 chars) is allowed."""
        # Some emojis use multiple codepoints (e.g., skin tone modifiers)
        metadata = DisplayMetadata(emoji="👨‍💻", i18n_key="developer")

        assert metadata.emoji == "👨‍💻"

    def test_display_metadata_category_types(self):
        """Test all valid category types."""
        categories = ["system", "agent", "tool", "context"]

        for category in categories:
            metadata = DisplayMetadata(emoji="📝", i18n_key="test", category=category)
            assert metadata.category == category


class TestToolManifest:
    """Tests for ToolManifest dataclass validation."""

    def test_tool_manifest_valid(self):
        """Test ToolManifest with valid values."""
        manifest = ToolManifest(
            name="search_contacts_tool",
            agent="contacts_agent",
            description="Search Google contacts",
            parameters=[
                ParameterSchema(
                    name="query", type="string", required=True, description="Search query"
                )
            ],
            outputs=[
                OutputFieldSchema(path="contacts[]", type="array", description="Contact list")
            ],
            cost=CostProfile(est_tokens_in=150, est_tokens_out=400),
            permissions=PermissionProfile(required_scopes=["google_contacts.read"]),
            version="1.2.3",
        )

        assert manifest.name == "search_contacts_tool"
        assert manifest.agent == "contacts_agent"
        assert len(manifest.parameters) == 1
        assert manifest.version == "1.2.3"

    def test_tool_manifest_empty_name_raises(self):
        """Test that empty name raises ValueError (Line 381)."""
        with pytest.raises(ValueError) as exc_info:
            ToolManifest(
                name="",
                agent="test_agent",
                description="Test",
                parameters=[],
                outputs=[],
                cost=CostProfile(),
                permissions=PermissionProfile(),
            )

        assert "Tool name cannot be empty" in str(exc_info.value)

    def test_tool_manifest_empty_agent_raises(self):
        """Test that empty agent raises ValueError (Line 383)."""
        with pytest.raises(ValueError) as exc_info:
            ToolManifest(
                name="test_tool",
                agent="",
                description="Test",
                parameters=[],
                outputs=[],
                cost=CostProfile(),
                permissions=PermissionProfile(),
            )

        assert "Agent name cannot be empty" in str(exc_info.value)

    def test_tool_manifest_empty_description_raises(self):
        """Test that empty description raises ValueError (Line 385)."""
        with pytest.raises(ValueError) as exc_info:
            ToolManifest(
                name="test_tool",
                agent="test_agent",
                description="",
                parameters=[],
                outputs=[],
                cost=CostProfile(),
                permissions=PermissionProfile(),
            )

        assert "Tool description cannot be empty" in str(exc_info.value)

    def test_tool_manifest_invalid_version_raises(self):
        """Test that invalid semver version raises ValueError (Line 388)."""
        with pytest.raises(ValueError) as exc_info:
            ToolManifest(
                name="test_tool",
                agent="test_agent",
                description="Test",
                parameters=[],
                outputs=[],
                cost=CostProfile(),
                permissions=PermissionProfile(),
                version="1.0",  # Invalid: should be 1.0.0
            )

        assert "Invalid semver version" in str(exc_info.value)

    def test_tool_manifest_with_display_metadata(self):
        """Test ToolManifest with DisplayMetadata."""
        display = DisplayMetadata(emoji="🔍", i18n_key="search")
        manifest = ToolManifest(
            name="test_tool",
            agent="test_agent",
            description="Test",
            parameters=[],
            outputs=[],
            cost=CostProfile(),
            permissions=PermissionProfile(),
            display=display,
        )

        assert manifest.display is not None
        assert manifest.display.emoji == "🔍"

    def test_tool_manifest_defaults(self):
        """Test ToolManifest default values."""
        manifest = ToolManifest(
            name="test_tool",
            agent="test_agent",
            description="Test",
            parameters=[],
            outputs=[],
            cost=CostProfile(),
            permissions=PermissionProfile(),
        )

        assert manifest.max_iterations == 1
        assert manifest.supports_dry_run is False
        assert manifest.reference_fields == []
        assert manifest.context_key is None
        assert manifest.examples == []
        assert manifest.examples_in_prompt is True
        assert manifest.version == "1.0.0"
        assert manifest.maintainer == "Team AI"
        assert isinstance(manifest.updated_at, datetime)


class TestAgentManifest:
    """Tests for AgentManifest dataclass validation."""

    def test_agent_manifest_valid(self):
        """Test AgentManifest with valid values."""
        manifest = AgentManifest(
            name="contacts_agent",
            description="Agent for Google Contacts",
            tools=["search_contacts_tool", "list_contacts_tool"],
            version="2.1.0",
        )

        assert manifest.name == "contacts_agent"
        assert manifest.description == "Agent for Google Contacts"
        assert len(manifest.tools) == 2
        assert manifest.version == "2.1.0"

    def test_agent_manifest_empty_name_raises(self):
        """Test that empty name raises ValueError (Line 454)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(name="", description="Test", tools=["tool1"])

        assert "Agent name cannot be empty" in str(exc_info.value)

    def test_agent_manifest_empty_description_raises(self):
        """Test that empty description raises ValueError (Line 456)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(name="test_agent", description="", tools=["tool1"])

        assert "Agent description cannot be empty" in str(exc_info.value)

    def test_agent_manifest_empty_tools_raises(self):
        """Test that empty tools list raises ValueError (Line 458)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(name="test_agent", description="Test", tools=[])

        assert "Agent must have at least one tool" in str(exc_info.value)

    def test_agent_manifest_zero_parallel_runs_raises(self):
        """Test that max_parallel_runs < 1 raises ValueError (Line 460)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(
                name="test_agent", description="Test", tools=["tool1"], max_parallel_runs=0
            )

        assert "max_parallel_runs must be >= 1" in str(exc_info.value)

    def test_agent_manifest_zero_timeout_raises(self):
        """Test that default_timeout_ms < 1 raises ValueError (Line 462)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(
                name="test_agent", description="Test", tools=["tool1"], default_timeout_ms=0
            )

        assert "default_timeout_ms must be >= 1" in str(exc_info.value)

    def test_agent_manifest_invalid_version_raises(self):
        """Test that invalid semver version raises ValueError (Line 465)."""
        with pytest.raises(ValueError) as exc_info:
            AgentManifest(
                name="test_agent",
                description="Test",
                tools=["tool1"],
                version="v2",  # Invalid
            )

        assert "Invalid semver version" in str(exc_info.value)

    def test_agent_manifest_defaults(self):
        """Test AgentManifest default values."""
        manifest = AgentManifest(name="test_agent", description="Test agent", tools=["tool1"])

        assert manifest.max_parallel_runs == 1
        assert manifest.default_timeout_ms > 0
        assert manifest.prompt_version == CONTACTS_AGENT_PROMPT_VERSION_DEFAULT
        assert manifest.owner_team == "Team AI"
        assert manifest.version == "1.0.0"
        assert isinstance(manifest.updated_at, datetime)


class TestCatalogueExceptions:
    """Tests for Catalogue exception classes."""

    def test_catalogue_error_base(self):
        """Test CatalogueError base exception."""
        error = CatalogueError("Test error message")

        assert isinstance(error, Exception)
        assert str(error) == "Test error message"

    def test_agent_manifest_not_found(self):
        """Test AgentManifestNotFound exception (Lines 483-484)."""
        error = AgentManifestNotFound("contacts_agent")

        assert isinstance(error, CatalogueError)
        assert error.agent_name == "contacts_agent"
        assert "Agent manifest not found: contacts_agent" in str(error)

    def test_tool_manifest_not_found(self):
        """Test ToolManifestNotFound exception (Lines 491-492)."""
        error = ToolManifestNotFound("search_contacts_tool")

        assert isinstance(error, CatalogueError)
        assert error.tool_name == "search_contacts_tool"
        assert "Tool manifest not found: search_contacts_tool" in str(error)

    def test_tool_manifest_already_registered(self):
        """Test ToolManifestAlreadyRegistered exception (Lines 499-500)."""
        error = ToolManifestAlreadyRegistered("search_contacts_tool")

        assert isinstance(error, CatalogueError)
        assert error.tool_name == "search_contacts_tool"
        assert "Tool manifest already registered: search_contacts_tool" in str(error)

    def test_agent_manifest_already_registered(self):
        """Test AgentManifestAlreadyRegistered exception (Lines 507-508)."""
        error = AgentManifestAlreadyRegistered("contacts_agent")

        assert isinstance(error, CatalogueError)
        assert error.agent_name == "contacts_agent"
        assert "Agent manifest already registered: contacts_agent" in str(error)

    def test_exceptions_can_be_caught_as_catalogue_error(self):
        """Test that all custom exceptions can be caught as CatalogueError."""
        exceptions = [
            AgentManifestNotFound("test"),
            ToolManifestNotFound("test"),
            ToolManifestAlreadyRegistered("test"),
            AgentManifestAlreadyRegistered("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, CatalogueError)

    def test_exceptions_can_be_caught_as_base_exception(self):
        """Test that all exceptions inherit from Exception."""
        exceptions = [
            CatalogueError("test"),
            AgentManifestNotFound("test"),
            ToolManifestNotFound("test"),
            ToolManifestAlreadyRegistered("test"),
            AgentManifestAlreadyRegistered("test"),
        ]

        for exc in exceptions:
            assert isinstance(exc, Exception)
