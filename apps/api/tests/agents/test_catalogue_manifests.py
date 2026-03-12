"""
Tests pour le système de catalogue déclaratif (manifestes agents et tools).

Ce module teste:
- Dataclasses catalogue (CostProfile, PermissionProfile, ParameterSchema, etc.)
- AgentRegistry extensions (manifest registration, retrieval, export)
- catalogue_loader initialization

Coverage target: 95% sur nouveau code (catalogue.py, agent_registry.py extensions, catalogue_loader.py)
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from src.core.constants import CONTACTS_AGENT_PROMPT_VERSION_DEFAULT
from src.domains.agents.google_contacts.catalogue_manifests import (
    get_contacts_catalogue_manifest as GET_CONTACTS_MANIFEST,
)
from src.domains.agents.registry.agent_registry import AgentRegistry
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    AgentManifestAlreadyRegistered,
    AgentManifestNotFound,
    CostProfile,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
    ToolManifestAlreadyRegistered,
    ToolManifestNotFound,
)
from src.domains.agents.registry.catalogue_loader import (
    CONTACT_AGENT_MANIFEST,
    initialize_catalogue,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_checkpointer():
    """Mock checkpointer for AgentRegistry"""
    return MagicMock()


@pytest.fixture
def mock_store():
    """Mock store for AgentRegistry"""
    return MagicMock()


@pytest.fixture
def registry(mock_checkpointer, mock_store):
    """Fixture providing a clean AgentRegistry instance"""
    return AgentRegistry(checkpointer=mock_checkpointer, store=mock_store)


@pytest.fixture
def sample_cost_profile():
    """Fixture providing a valid CostProfile"""
    return CostProfile(
        est_tokens_in=150,
        est_tokens_out=400,
        est_cost_usd=0.0004,
        est_latency_ms=400,
    )


@pytest.fixture
def sample_permission_profile():
    """Fixture providing a valid PermissionProfile"""
    return PermissionProfile(
        required_scopes=["google_contacts.read"],
        allowed_roles=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    )


@pytest.fixture
def sample_parameter_schema():
    """Fixture providing a valid ParameterSchema"""
    return ParameterSchema(
        name="query",
        type="string",
        required=True,
        description="Search query",
        constraints=[ParameterConstraint(kind="min_length", value=1)],
    )


@pytest.fixture
def sample_output_field_schema():
    """Fixture providing a valid OutputFieldSchema"""
    return OutputFieldSchema(
        path="contacts[].resource_name",
        type="string",
        description="Google unique identifier",
        nullable=False,
    )


@pytest.fixture
def sample_tool_manifest(
    sample_cost_profile,
    sample_permission_profile,
    sample_parameter_schema,
    sample_output_field_schema,
):
    """Fixture providing a valid ToolManifest"""
    return ToolManifest(
        name="test_tool",
        agent="test_agent",
        description="Test tool for unit tests",
        parameters=[sample_parameter_schema],
        outputs=[sample_output_field_schema],
        cost=sample_cost_profile,
        permissions=sample_permission_profile,
        max_iterations=1,
        supports_dry_run=False,
        reference_fields=["contacts[].name.display"],
        context_key="test_context",
        examples=[{"input": {"query": "test"}, "output": {"result": "ok"}}],
        version="1.0.0",
        maintainer="Team AI",
    )


@pytest.fixture
def sample_agent_manifest():
    """Fixture providing a valid AgentManifest"""
    return AgentManifest(
        name="test_agent",
        description="Test agent for unit tests",
        tools=["test_tool"],
        max_parallel_runs=1,
        default_timeout_ms=30000,
        prompt_version=CONTACTS_AGENT_PROMPT_VERSION_DEFAULT,
        owner_team="Team AI",
        version="1.0.0",
    )


# ============================================================================
# Tests CostProfile
# ============================================================================


class TestCostProfile:
    """Tests pour CostProfile dataclass"""

    def test_cost_profile_valid(self):
        """Test création CostProfile valide"""
        profile = CostProfile(
            est_tokens_in=100,
            est_tokens_out=200,
            est_cost_usd=0.0005,
            est_latency_ms=500,
        )
        assert profile.est_tokens_in == 100
        assert profile.est_tokens_out == 200
        assert profile.est_cost_usd == 0.0005
        assert profile.est_latency_ms == 500

    def test_cost_profile_defaults(self):
        """Test valeurs par défaut CostProfile"""
        profile = CostProfile()
        assert profile.est_tokens_in == 0
        assert profile.est_tokens_out == 0
        assert profile.est_cost_usd == 0.0
        assert profile.est_latency_ms == 0

    def test_cost_profile_negative_tokens_in_raises(self):
        """Test validation: negative est_tokens_in must raise."""
        with pytest.raises(ValueError, match="est_tokens_in must be >= 0"):
            CostProfile(est_tokens_in=-10)

    def test_cost_profile_negative_tokens_out_raises(self):
        """Test validation: negative est_tokens_out must raise."""
        with pytest.raises(ValueError, match="est_tokens_out must be >= 0"):
            CostProfile(est_tokens_out=-10)

    def test_cost_profile_negative_cost_raises(self):
        """Test validation: negative est_cost_usd must raise."""
        with pytest.raises(ValueError, match="est_cost_usd must be >= 0"):
            CostProfile(est_cost_usd=-0.001)

    def test_cost_profile_negative_latency_raises(self):
        """Test validation: negative est_latency_ms must raise."""
        with pytest.raises(ValueError, match="est_latency_ms must be >= 0"):
            CostProfile(est_latency_ms=-100)

    def test_cost_profile_immutable(self, sample_cost_profile):
        """Test immutabilité (frozen=True)"""
        with pytest.raises(
            (AttributeError, TypeError)
        ):  # FrozenInstanceError is subclass of TypeError
            sample_cost_profile.est_tokens_in = 999


# ============================================================================
# Tests PermissionProfile
# ============================================================================


class TestPermissionProfile:
    """Tests pour PermissionProfile dataclass"""

    def test_permission_profile_valid(self):
        """Test création PermissionProfile valide"""
        profile = PermissionProfile(
            required_scopes=["scope1", "scope2"],
            allowed_roles=["admin", "user"],
            data_classification="SENSITIVE",
            hitl_required=True,
        )
        assert profile.required_scopes == ["scope1", "scope2"]
        assert profile.allowed_roles == ["admin", "user"]
        assert profile.data_classification == "SENSITIVE"
        assert profile.hitl_required is True

    def test_permission_profile_defaults(self):
        """Test valeurs par défaut PermissionProfile"""
        profile = PermissionProfile()
        assert profile.required_scopes == []
        assert profile.allowed_roles == []
        assert profile.data_classification == "CONFIDENTIAL"
        assert profile.hitl_required is False

    def test_permission_profile_immutable(self, sample_permission_profile):
        """Test immutabilité (frozen=True)"""
        with pytest.raises(
            (AttributeError, TypeError)
        ):  # FrozenInstanceError is subclass of TypeError
            sample_permission_profile.hitl_required = True


# ============================================================================
# Tests ParameterSchema
# ============================================================================


class TestParameterSchema:
    """Tests pour ParameterSchema dataclass"""

    def test_parameter_schema_valid(self):
        """Test création ParameterSchema valide"""
        param = ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Maximum number of results",
            constraints=[
                ParameterConstraint(kind="minimum", value=1),
                ParameterConstraint(kind="maximum", value=100),
            ],
        )
        assert param.name == "max_results"
        assert param.type == "integer"
        assert param.required is False
        assert len(param.constraints) == 2

    def test_parameter_schema_no_constraints(self):
        """Test ParameterSchema sans contraintes"""
        param = ParameterSchema(
            name="description",
            type="string",
            required=False,
            description="Optional description",
        )
        assert param.constraints == []

    def test_parameter_constraint_pattern(self):
        """Test ParameterConstraint avec regex pattern"""
        constraint = ParameterConstraint(kind="pattern", value=r"^people/c\d+$")
        assert constraint.kind == "pattern"
        assert constraint.value == r"^people/c\d+$"

    def test_parameter_constraint_enum(self):
        """Test ParameterConstraint avec enum"""
        constraint = ParameterConstraint(kind="enum", value=["ASC", "DESC"])
        assert constraint.kind == "enum"
        assert constraint.value == ["ASC", "DESC"]


# ============================================================================
# Tests OutputFieldSchema
# ============================================================================


class TestOutputFieldSchema:
    """Tests pour OutputFieldSchema dataclass"""

    def test_output_field_schema_valid(self):
        """Test création OutputFieldSchema valide"""
        field = OutputFieldSchema(
            path="contacts[].emails",
            type="array",
            description="List of email addresses",
            nullable=True,
        )
        assert field.path == "contacts[].emails"
        assert field.type == "array"
        assert field.nullable is True

    def test_output_field_schema_defaults(self):
        """Test valeurs par défaut OutputFieldSchema"""
        field = OutputFieldSchema(
            path="contact.name",
            type="string",
            description="Contact name",
        )
        assert field.nullable is False


# ============================================================================
# Tests ToolManifest
# ============================================================================


class TestToolManifest:
    """Tests pour ToolManifest dataclass"""

    def test_tool_manifest_valid(self, sample_tool_manifest):
        """Test création ToolManifest valide"""
        assert sample_tool_manifest.name == "test_tool"
        assert sample_tool_manifest.agent == "test_agent"
        assert sample_tool_manifest.version == "1.0.0"
        assert len(sample_tool_manifest.parameters) == 1
        assert len(sample_tool_manifest.outputs) == 1

    def test_tool_manifest_empty_name_raises(self, sample_cost_profile, sample_permission_profile):
        """Test validation: nom vide doit raise"""
        with pytest.raises(ValueError, match="Tool name cannot be empty"):
            ToolManifest(
                name="",
                agent="test_agent",
                description="Test",
                parameters=[],
                outputs=[],
                cost=sample_cost_profile,
                permissions=sample_permission_profile,
            )

    def test_tool_manifest_empty_agent_raises(self, sample_cost_profile, sample_permission_profile):
        """Test validation: agent vide doit raise"""
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            ToolManifest(
                name="test_tool",
                agent="",
                description="Test",
                parameters=[],
                outputs=[],
                cost=sample_cost_profile,
                permissions=sample_permission_profile,
            )

    def test_tool_manifest_empty_description_raises(
        self, sample_cost_profile, sample_permission_profile
    ):
        """Test validation: description vide doit raise"""
        with pytest.raises(ValueError, match="Tool description cannot be empty"):
            ToolManifest(
                name="test_tool",
                agent="test_agent",
                description="",
                parameters=[],
                outputs=[],
                cost=sample_cost_profile,
                permissions=sample_permission_profile,
            )

    def test_tool_manifest_invalid_semver_raises(
        self, sample_cost_profile, sample_permission_profile
    ):
        """Test validation: version semver invalide doit raise"""
        with pytest.raises(ValueError, match="Invalid semver version"):
            ToolManifest(
                name="test_tool",
                agent="test_agent",
                description="Test",
                parameters=[],
                outputs=[],
                cost=sample_cost_profile,
                permissions=sample_permission_profile,
                version="1.0",  # Invalid: should be X.Y.Z
            )

    def test_tool_manifest_defaults(self, sample_cost_profile, sample_permission_profile):
        """Test valeurs par défaut ToolManifest"""
        manifest = ToolManifest(
            name="test_tool",
            agent="test_agent",
            description="Test tool",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )
        assert manifest.max_iterations == 1
        assert manifest.supports_dry_run is False
        assert manifest.reference_fields == []
        assert manifest.context_key is None
        assert manifest.examples == []
        assert manifest.version == "1.0.0"
        assert manifest.maintainer == "Team AI"
        assert isinstance(manifest.updated_at, datetime)


# ============================================================================
# Tests AgentManifest
# ============================================================================


class TestAgentManifest:
    """Tests pour AgentManifest dataclass"""

    def test_agent_manifest_valid(self, sample_agent_manifest):
        """Test création AgentManifest valide"""
        assert sample_agent_manifest.name == "test_agent"
        assert sample_agent_manifest.description == "Test agent for unit tests"
        assert sample_agent_manifest.tools == ["test_tool"]
        assert sample_agent_manifest.version == "1.0.0"

    def test_agent_manifest_empty_name_raises(self):
        """Test validation: nom vide doit raise"""
        with pytest.raises(ValueError, match="Agent name cannot be empty"):
            AgentManifest(
                name="",
                description="Test",
                tools=["tool1"],
            )

    def test_agent_manifest_empty_description_raises(self):
        """Test validation: description vide doit raise"""
        with pytest.raises(ValueError, match="Agent description cannot be empty"):
            AgentManifest(
                name="test_agent",
                description="",
                tools=["tool1"],
            )

    def test_agent_manifest_empty_tools_raises(self):
        """Test validation: aucun tool doit raise"""
        with pytest.raises(ValueError, match="Agent must have at least one tool"):
            AgentManifest(
                name="test_agent",
                description="Test",
                tools=[],
            )

    def test_agent_manifest_invalid_max_parallel_runs_raises(self):
        """Test validation: max_parallel_runs < 1 doit raise"""
        with pytest.raises(ValueError, match="max_parallel_runs must be >= 1"):
            AgentManifest(
                name="test_agent",
                description="Test",
                tools=["tool1"],
                max_parallel_runs=0,
            )

    def test_agent_manifest_invalid_timeout_raises(self):
        """Test validation: default_timeout_ms < 1 doit raise"""
        with pytest.raises(ValueError, match="default_timeout_ms must be >= 1"):
            AgentManifest(
                name="test_agent",
                description="Test",
                tools=["tool1"],
                default_timeout_ms=0,
            )

    def test_agent_manifest_invalid_semver_raises(self):
        """Test validation: version semver invalide doit raise"""
        with pytest.raises(ValueError, match="Invalid semver version"):
            AgentManifest(
                name="test_agent",
                description="Test",
                tools=["tool1"],
                version="1.0",  # Invalid
            )

    def test_agent_manifest_defaults(self):
        """Test valeurs par défaut AgentManifest"""
        manifest = AgentManifest(
            name="test_agent",
            description="Test agent",
            tools=["tool1"],
        )
        assert manifest.max_parallel_runs == 1
        assert manifest.default_timeout_ms == 30000
        assert manifest.prompt_version == CONTACTS_AGENT_PROMPT_VERSION_DEFAULT
        assert manifest.owner_team == "Team AI"
        assert manifest.version == "1.0.0"
        assert isinstance(manifest.updated_at, datetime)


# ============================================================================
# Tests AgentRegistry - Manifest Registration
# ============================================================================


class TestAgentRegistryManifestRegistration:
    """Tests pour l'enregistrement de manifestes dans AgentRegistry"""

    def test_register_agent_manifest_success(self, registry, sample_agent_manifest):
        """Test enregistrement agent manifest réussi"""
        registry.register_agent_manifest(sample_agent_manifest)

        retrieved = registry.get_agent_manifest("test_agent")
        assert retrieved.name == "test_agent"
        assert retrieved.description == sample_agent_manifest.description

    def test_register_agent_manifest_duplicate_raises(self, registry, sample_agent_manifest):
        """Test enregistrement duplicate agent manifest doit raise"""
        registry.register_agent_manifest(sample_agent_manifest)

        with pytest.raises(AgentManifestAlreadyRegistered, match="test_agent"):
            registry.register_agent_manifest(sample_agent_manifest)

    def test_register_agent_manifest_override(self, registry, sample_agent_manifest):
        """Test override d'un agent manifest existant"""
        registry.register_agent_manifest(sample_agent_manifest)

        # Create modified manifest
        modified = AgentManifest(
            name="test_agent",
            description="Modified description",
            tools=["tool1", "tool2"],
            version="2.0.0",
        )

        registry.register_agent_manifest(modified, override=True)
        retrieved = registry.get_agent_manifest("test_agent")
        assert retrieved.description == "Modified description"
        assert retrieved.version == "2.0.0"

    def test_register_tool_manifest_success(
        self, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test enregistrement tool manifest réussi"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        retrieved = registry.get_tool_manifest("test_tool")
        assert retrieved.name == "test_tool"
        assert retrieved.agent == "test_agent"

    def test_register_tool_manifest_duplicate_raises(
        self, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test enregistrement duplicate tool manifest doit raise"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        with pytest.raises(ToolManifestAlreadyRegistered, match="test_tool"):
            registry.register_tool_manifest(sample_tool_manifest)

    def test_register_tool_manifest_override(
        self,
        registry,
        sample_agent_manifest,
        sample_tool_manifest,
        sample_cost_profile,
        sample_permission_profile,
    ):
        """Test override d'un tool manifest existant"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        # Create modified manifest
        modified = ToolManifest(
            name="test_tool",
            agent="test_agent",
            description="Modified tool description",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
            version="2.0.0",
        )

        registry.register_tool_manifest(modified, override=True)
        retrieved = registry.get_tool_manifest("test_tool")
        assert retrieved.description == "Modified tool description"
        assert retrieved.version == "2.0.0"

    def test_register_tool_without_agent_warning(self, registry, sample_tool_manifest, caplog):
        """Test enregistrement tool sans agent doit logger warning"""
        import logging

        # Register tool without registering agent first
        with caplog.at_level(logging.WARNING):
            registry.register_tool_manifest(sample_tool_manifest)

        # Verify warning was logged
        assert any("catalogue_tool_orphan" in record.message for record in caplog.records)


# ============================================================================
# Tests AgentRegistry - Manifest Retrieval
# ============================================================================


class TestAgentRegistryManifestRetrieval:
    """Tests pour la récupération de manifestes depuis AgentRegistry"""

    def test_get_agent_manifest_success(self, registry, sample_agent_manifest):
        """Test récupération agent manifest existant"""
        registry.register_agent_manifest(sample_agent_manifest)
        retrieved = registry.get_agent_manifest("test_agent")
        assert retrieved == sample_agent_manifest

    def test_get_agent_manifest_not_found_raises(self, registry):
        """Test récupération agent manifest inexistant doit raise"""
        with pytest.raises(AgentManifestNotFound, match="nonexistent_agent"):
            registry.get_agent_manifest("nonexistent_agent")

    def test_get_tool_manifest_success(self, registry, sample_agent_manifest, sample_tool_manifest):
        """Test récupération tool manifest existant"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)
        retrieved = registry.get_tool_manifest("test_tool")
        assert retrieved == sample_tool_manifest

    def test_get_tool_manifest_not_found_raises(self, registry):
        """Test récupération tool manifest inexistant doit raise"""
        with pytest.raises(ToolManifestNotFound, match="nonexistent_tool"):
            registry.get_tool_manifest("nonexistent_tool")

    def test_list_agent_manifests_empty(self, registry):
        """Test liste agent manifests quand vide"""
        manifests = registry.list_agent_manifests()
        assert manifests == []

    def test_list_agent_manifests_multiple(self, registry):
        """Test liste tous les agent manifests"""
        agent1 = AgentManifest(name="agent1", description="Agent 1", tools=["tool1"])
        agent2 = AgentManifest(name="agent2", description="Agent 2", tools=["tool2"])

        registry.register_agent_manifest(agent1)
        registry.register_agent_manifest(agent2)

        manifests = registry.list_agent_manifests()
        assert len(manifests) == 2
        names = [m.name for m in manifests]
        assert "agent1" in names
        assert "agent2" in names

    def test_list_tool_manifests_empty(self, registry):
        """Test liste tool manifests quand vide"""
        manifests = registry.list_tool_manifests()
        assert manifests == []

    def test_list_tool_manifests_all(
        self, registry, sample_cost_profile, sample_permission_profile
    ):
        """Test liste tous les tool manifests"""
        agent1 = AgentManifest(name="agent1", description="Agent 1", tools=["tool1", "tool2"])
        agent2 = AgentManifest(name="agent2", description="Agent 2", tools=["tool3"])

        tool1 = ToolManifest(
            name="tool1",
            agent="agent1",
            description="Tool 1",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )
        tool2 = ToolManifest(
            name="tool2",
            agent="agent1",
            description="Tool 2",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )
        tool3 = ToolManifest(
            name="tool3",
            agent="agent2",
            description="Tool 3",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )

        registry.register_agent_manifest(agent1)
        registry.register_agent_manifest(agent2)
        registry.register_tool_manifest(tool1)
        registry.register_tool_manifest(tool2)
        registry.register_tool_manifest(tool3)

        manifests = registry.list_tool_manifests()
        assert len(manifests) == 3

    def test_list_tool_manifests_filtered_by_agent(
        self, registry, sample_cost_profile, sample_permission_profile
    ):
        """Test liste tool manifests filtrés par agent"""
        agent1 = AgentManifest(name="agent1", description="Agent 1", tools=["tool1", "tool2"])
        agent2 = AgentManifest(name="agent2", description="Agent 2", tools=["tool3"])

        tool1 = ToolManifest(
            name="tool1",
            agent="agent1",
            description="Tool 1",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )
        tool2 = ToolManifest(
            name="tool2",
            agent="agent1",
            description="Tool 2",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )
        tool3 = ToolManifest(
            name="tool3",
            agent="agent2",
            description="Tool 3",
            parameters=[],
            outputs=[],
            cost=sample_cost_profile,
            permissions=sample_permission_profile,
        )

        registry.register_agent_manifest(agent1)
        registry.register_agent_manifest(agent2)
        registry.register_tool_manifest(tool1)
        registry.register_tool_manifest(tool2)
        registry.register_tool_manifest(tool3)

        manifests = registry.list_tool_manifests(agent="agent1")
        assert len(manifests) == 2
        names = [m.name for m in manifests]
        assert "tool1" in names
        assert "tool2" in names
        assert "tool3" not in names


# ============================================================================
# Tests AgentRegistry - Export Methods
# ============================================================================


class TestAgentRegistryExport:
    """Tests pour les méthodes d'export de AgentRegistry"""

    def test_export_catalogue_structure(
        self, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test structure de export_catalogue"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        exported = registry.export_catalogue()

        assert "agents" in exported
        assert "tools" in exported
        assert "exported_at" in exported
        assert "version" in exported
        assert len(exported["agents"]) == 1
        assert len(exported["tools"]) == 1

        # Exported as dict[str, dict], not list
        assert "test_agent" in exported["agents"]
        agent = exported["agents"]["test_agent"]
        assert agent["name"] == "test_agent"
        assert agent["version"] == "1.0.0"

        assert "test_tool" in exported["tools"]
        tool = exported["tools"]["test_tool"]
        assert tool["name"] == "test_tool"
        assert tool["agent"] == "test_agent"

    @patch("src.core.config.get_settings")
    def test_export_for_prompt_format(
        self, mock_get_settings, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test format optimisé de export_for_prompt"""
        mock_settings = MagicMock()
        mock_settings.planner_max_cost_usd = 0.1
        mock_settings.planner_max_steps = 10
        mock_get_settings.return_value = mock_settings

        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        exported = registry.export_for_prompt()

        assert "agents" in exported
        assert "max_plan_cost_usd" in exported
        assert "max_plan_steps" in exported
        assert exported["max_plan_cost_usd"] == 0.1
        assert exported["max_plan_steps"] == 10

        assert len(exported["agents"]) == 1
        agent = exported["agents"][0]
        assert agent["agent"] == "test_agent"
        assert "tools" in agent
        assert len(agent["tools"]) == 1

        tool = agent["tools"][0]
        assert "name" in tool
        assert "description" in tool
        assert "parameters" in tool
        assert "cost_estimate" in tool
        assert "requires_approval" in tool

    @patch("src.core.config.get_settings")
    def test_export_for_prompt_cost_estimate_structure(
        self, mock_get_settings, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test structure cost_estimate dans export_for_prompt"""
        mock_settings = MagicMock()
        mock_settings.planner_max_cost_usd = 0.1
        mock_settings.planner_max_steps = 10
        mock_get_settings.return_value = mock_settings

        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        exported = registry.export_for_prompt()
        tool = exported["agents"][0]["tools"][0]

        cost = tool["cost_estimate"]
        # Check actual format: tokens (combined) and latency_ms
        assert "tokens" in cost
        assert "latency_ms" in cost
        assert cost["tokens"] == 150 + 400  # est_tokens_in + est_tokens_out
        assert cost["latency_ms"] == 400

    def test_get_stats_includes_catalogue(
        self, registry, sample_agent_manifest, sample_tool_manifest
    ):
        """Test get_stats inclut les stats catalogue"""
        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        stats = registry.get_stats()

        assert "catalogue" in stats
        catalogue_stats = stats["catalogue"]
        assert catalogue_stats["agent_manifests"] == 1
        assert catalogue_stats["tool_manifests"] == 1
        assert "test_agent" in catalogue_stats["agents"]
        assert "test_tool" in catalogue_stats["tools"]


# ============================================================================
# Tests catalogue_loader
# ============================================================================


class TestCatalogueLoader:
    """Tests pour catalogue_loader initialization"""

    def test_loader_manifests_valid(self):
        """Test que tous les manifestes du loader sont valides"""
        # Should not raise
        assert CONTACT_AGENT_MANIFEST.name == "contact_agent"
        # Unified tool (v2.0 - replaces search + list + details)
        assert GET_CONTACTS_MANIFEST.name == "get_contacts_tool"

    def test_loader_manifests_relationships(self):
        """Test que les manifestes sont correctement liés"""
        agent_tools = CONTACT_AGENT_MANIFEST.tools
        # Unified tool (v2.0 - replaces search + list + details)
        assert "get_contacts_tool" in agent_tools
        assert "create_contact_tool" in agent_tools
        assert "update_contact_tool" in agent_tools
        assert "delete_contact_tool" in agent_tools

        assert GET_CONTACTS_MANIFEST.agent == "contact_agent"

    def test_initialize_catalogue_success(self, registry, caplog):
        """Test initialize_catalogue enregistre tous les manifestes"""
        import logging

        with caplog.at_level(logging.INFO):
            initialize_catalogue(registry)

        # Verify all manifests registered
        agent = registry.get_agent_manifest("contact_agent")
        assert agent.name == "contact_agent"

        # Unified tool (v2.0 - replaces search + list + details)
        tool = registry.get_tool_manifest("get_contacts_tool")
        assert tool.name == "get_contacts_tool"

        # Verify logger was called
        assert any("catalogue_initialized" in record.message for record in caplog.records)

    def test_get_contacts_manifest_parameters(self):
        """Test paramètres de get_contacts_tool manifest (unified v2.0)"""
        params = {p.name: p for p in GET_CONTACTS_MANIFEST.parameters}

        # Query mode parameter (optional - empty for all contacts)
        assert "query" in params
        assert params["query"].required is False
        assert params["query"].type == "string"

        # ID mode parameters
        assert "resource_name" in params
        assert params["resource_name"].required is False

        assert "max_results" in params
        assert params["max_results"].required is False
        assert params["max_results"].type == "integer"

    def test_get_contacts_manifest_pattern_constraint(self):
        """Test contrainte pattern de get_contacts_tool

        Note: resource_name is NOT required because it's optional.
        Query mode or ID mode can be used.
        """
        params = {p.name: p for p in GET_CONTACTS_MANIFEST.parameters}

        resource_name = params["resource_name"]
        # resource_name is NOT required (optional - ID mode)
        assert resource_name.required is False

        # Find pattern constraint
        pattern_constraints = [c for c in resource_name.constraints if c.kind == "pattern"]
        assert len(pattern_constraints) == 1
        # Pattern validates the people/ prefix format
        assert pattern_constraints[0].value == r"^people/"


# ============================================================================
# Tests Thread Safety
# ============================================================================


class TestThreadSafety:
    """Tests pour la sécurité thread du catalogue"""

    def test_concurrent_manifest_registration(
        self, registry, sample_cost_profile, sample_permission_profile
    ):
        """Test enregistrements concurrents de manifestes"""
        import threading

        def register_agent(i):
            manifest = AgentManifest(
                name=f"agent_{i}",
                description=f"Agent {i}",
                tools=[f"tool_{i}"],
            )
            registry.register_agent_manifest(manifest)

        def register_tool(i):
            manifest = ToolManifest(
                name=f"tool_{i}",
                agent=f"agent_{i}",
                description=f"Tool {i}",
                parameters=[],
                outputs=[],
                cost=sample_cost_profile,
                permissions=sample_permission_profile,
            )
            registry.register_tool_manifest(manifest)

        # First register agents
        threads = [threading.Thread(target=register_agent, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Then register tools
        threads = [threading.Thread(target=register_tool, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verify all registered
        assert len(registry.list_agent_manifests()) == 10
        assert len(registry.list_tool_manifests()) == 10

    def test_concurrent_reads(self, registry, sample_agent_manifest, sample_tool_manifest):
        """Test lectures concurrentes de manifestes"""
        import threading

        registry.register_agent_manifest(sample_agent_manifest)
        registry.register_tool_manifest(sample_tool_manifest)

        results = []

        def read_manifests():
            try:
                agent = registry.get_agent_manifest("test_agent")
                tool = registry.get_tool_manifest("test_tool")
                results.append((agent.name, tool.name))
            except Exception as e:
                results.append(e)

        threads = [threading.Thread(target=read_manifests) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All reads should succeed
        assert len(results) == 20
        for result in results:
            assert result == ("test_agent", "test_tool")
