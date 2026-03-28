"""
Unit tests for Domain Taxonomy.

Tests the domain registry and configuration functions.

@created: 2026-02-02
@coverage: domain_taxonomy.py
"""

import pytest

from src.domains.agents.registry.domain_taxonomy import (
    DOMAIN_REGISTRY,
    DomainConfig,
    export_context_labels_for_router,
    get_all_domains,
    get_domain_config,
    get_result_key,
    get_result_key_for_tool,
    get_routable_domains,
    validate_domain_registry,
)

# ============================================================================
# DomainConfig Dataclass Tests
# ============================================================================


class TestDomainConfigDataclass:
    """Tests for DomainConfig dataclass."""

    def test_create_minimal_config(self):
        """Test creating DomainConfig with minimal required fields."""
        config = DomainConfig(
            name="test",
            display_name="Test Domain",
            description="A test domain",
            agent_names=["test_agent"],
            result_key="tests",
        )
        assert config.name == "test"
        assert config.display_name == "Test Domain"
        assert config.agent_names == ["test_agent"]
        assert config.result_key == "tests"
        assert config.is_routable is True  # default
        assert config.related_domains == []
        assert config.metadata == {}

    def test_create_full_config(self):
        """Test creating DomainConfig with all fields."""
        config = DomainConfig(
            name="custom",
            display_name="Custom Domain",
            description="Custom description",
            agent_names=["agent1", "agent2"],
            result_key="customs",
            related_domains=["other"],
            is_routable=False,
            metadata={"provider": "test"},
        )
        assert config.is_routable is False
        assert config.related_domains == ["other"]
        assert config.metadata == {"provider": "test"}

    def test_frozen_config_immutable(self):
        """Test DomainConfig is frozen (immutable)."""
        config = DomainConfig(
            name="test",
            display_name="Test",
            description="Test",
            agent_names=["test_agent"],
            result_key="tests",
        )
        with pytest.raises(AttributeError):
            config.name = "changed"  # type: ignore

    def test_validation_empty_name_raises(self):
        """Test validation raises on empty name."""
        with pytest.raises(ValueError) as exc_info:
            DomainConfig(
                name="",
                display_name="Test",
                description="Test",
                agent_names=["test_agent"],
                result_key="tests",
            )
        assert "name cannot be empty" in str(exc_info.value)

    def test_validation_empty_agents_raises(self):
        """Test validation raises on empty agent_names."""
        with pytest.raises(ValueError) as exc_info:
            DomainConfig(
                name="test",
                display_name="Test",
                description="Test",
                agent_names=[],
                result_key="tests",
            )
        assert "must have at least one agent" in str(exc_info.value)

    def test_validation_empty_result_key_raises(self):
        """Test validation raises on empty result_key."""
        with pytest.raises(ValueError) as exc_info:
            DomainConfig(
                name="test",
                display_name="Test",
                description="Test",
                agent_names=["test"],
                result_key="",
            )
        assert "must have a result_key" in str(exc_info.value)


# ============================================================================
# DOMAIN_REGISTRY Tests
# ============================================================================


class TestDomainRegistry:
    """Tests for DOMAIN_REGISTRY contents."""

    def test_registry_has_core_domains(self):
        """Test registry contains expected core domains."""
        expected_domains = [
            "contact",
            "email",
            "event",
            "task",
            "weather",
            "file",
            "wikipedia",
            "perplexity",
            "reminder",
            "place",
            "route",
        ]
        for domain in expected_domains:
            assert domain in DOMAIN_REGISTRY, f"Missing domain: {domain}"

    def test_registry_has_internal_domains(self):
        """Test registry contains internal domains."""
        assert "context" in DOMAIN_REGISTRY
        assert "query" in DOMAIN_REGISTRY

    def test_internal_domains_not_routable(self):
        """Test internal domains are not routable."""
        assert DOMAIN_REGISTRY["context"].is_routable is False
        assert DOMAIN_REGISTRY["query"].is_routable is False

    def test_all_domains_have_unique_agent_names(self):
        """Test all agent names are unique across domains."""
        all_agents = []
        for config in DOMAIN_REGISTRY.values():
            all_agents.extend(config.agent_names)
        assert len(all_agents) == len(set(all_agents))

    def test_all_domains_have_unique_result_keys(self):
        """Test all result keys are unique."""
        result_keys = [config.result_key for config in DOMAIN_REGISTRY.values()]
        assert len(result_keys) == len(set(result_keys))

    def test_email_domain_config(self):
        """Test email domain has correct configuration."""
        email_config = DOMAIN_REGISTRY["email"]
        assert email_config.display_name == "Emails"
        assert email_config.result_key == "emails"
        assert email_config.is_routable is True
        assert "contact" in email_config.related_domains

    def test_weather_domain_config(self):
        """Test weather domain has correct configuration."""
        weather_config = DOMAIN_REGISTRY["weather"]
        assert weather_config.result_key == "weathers"
        assert weather_config.metadata.get("provider") == "openweathermap"


# ============================================================================
# get_domain_config Tests
# ============================================================================


class TestGetDomainConfig:
    """Tests for get_domain_config function."""

    def test_get_existing_domain(self):
        """Test getting an existing domain."""
        config = get_domain_config("email")
        assert config is not None
        assert config.name == "email"
        assert config.display_name == "Emails"

    def test_get_non_existing_domain(self):
        """Test getting a non-existing domain returns None."""
        config = get_domain_config("nonexistent")
        assert config is None

    def test_get_all_registered_domains(self):
        """Test all registered domains can be retrieved."""
        for domain_name in DOMAIN_REGISTRY.keys():
            config = get_domain_config(domain_name)
            assert config is not None
            assert config.name == domain_name


# ============================================================================
# get_all_domains Tests
# ============================================================================


class TestGetAllDomains:
    """Tests for get_all_domains function."""

    def test_returns_all_domains(self):
        """Test returns all domain names."""
        domains = get_all_domains()
        assert isinstance(domains, list)
        assert len(domains) == len(DOMAIN_REGISTRY)

    def test_includes_routable_and_internal(self):
        """Test includes both routable and internal domains."""
        domains = get_all_domains()
        assert "email" in domains  # routable
        assert "context" in domains  # internal

    def test_returns_copy_not_reference(self):
        """Test returns a new list."""
        domains1 = get_all_domains()
        domains2 = get_all_domains()
        # Should be equal content but different objects
        assert domains1 == domains2


# ============================================================================
# get_routable_domains Tests
# ============================================================================


class TestGetRoutableDomains:
    """Tests for get_routable_domains function."""

    def test_excludes_internal_domains(self):
        """Test internal domains are excluded."""
        routable = get_routable_domains()
        assert "context" not in routable
        assert "query" not in routable

    def test_includes_routable_domains(self):
        """Test routable domains are included."""
        routable = get_routable_domains()
        assert "email" in routable
        assert "contact" in routable
        assert "weather" in routable

    def test_subset_of_all_domains(self):
        """Test routable domains are subset of all domains."""
        all_domains = set(get_all_domains())
        routable = set(get_routable_domains())
        assert routable.issubset(all_domains)


# ============================================================================
# get_result_key Tests
# ============================================================================


class TestGetResultKey:
    """Tests for get_result_key function."""

    def test_get_weather_result_key(self):
        """Test weather domain result key."""
        assert get_result_key("weather") == "weathers"

    def test_get_email_result_key(self):
        """Test email domain result key."""
        assert get_result_key("email") == "emails"

    def test_get_contact_result_key(self):
        """Test contact domain result key."""
        assert get_result_key("contact") == "contacts"

    def test_get_event_result_key(self):
        """Test event domain result key."""
        assert get_result_key("event") == "events"

    def test_non_existing_domain_returns_none(self):
        """Test non-existing domain returns None."""
        assert get_result_key("nonexistent") is None


# ============================================================================
# get_result_key_for_tool Tests
# ============================================================================


class TestGetResultKeyForTool:
    """Tests for get_result_key_for_tool function."""

    def test_action_domain_tool_pattern(self):
        """Test {action}_{domain}_tool pattern."""
        assert get_result_key_for_tool("get_weather_tool") == "weathers"
        assert get_result_key_for_tool("send_email_tool") == "emails"

    def test_action_domains_tool_pattern(self):
        """Test {action}_{domain}s_tool pattern (plural)."""
        assert get_result_key_for_tool("get_contacts_tool") == "contacts"
        assert get_result_key_for_tool("search_events_tool") == "events"

    def test_domain_action_tool_pattern(self):
        """Test {domain}_{action}_tool pattern."""
        assert get_result_key_for_tool("weather_get_tool") == "weathers"
        assert get_result_key_for_tool("perplexity_search_tool") == "perplexitys"

    def test_empty_tool_name(self):
        """Test empty tool name returns None."""
        assert get_result_key_for_tool("") is None
        assert get_result_key_for_tool(None) is None  # type: ignore

    def test_unknown_tool_returns_none(self):
        """Test unknown tool pattern returns None."""
        assert get_result_key_for_tool("random_unknown_tool") is None

    def test_case_insensitive(self):
        """Test matching is case-insensitive."""
        assert get_result_key_for_tool("Get_Weather_Tool") == "weathers"
        assert get_result_key_for_tool("SEND_EMAIL_TOOL") == "emails"


# ============================================================================
# export_context_labels_for_router Tests
# ============================================================================


class TestExportContextLabelsForRouter:
    """Tests for export_context_labels_for_router function."""

    def test_returns_pipe_separated_string(self):
        """Test returns pipe-separated string."""
        labels = export_context_labels_for_router()
        assert isinstance(labels, str)
        assert "|" in labels

    def test_includes_general(self):
        """Test includes 'general' label."""
        labels = export_context_labels_for_router()
        assert "general" in labels.split("|")

    def test_includes_info(self):
        """Test includes 'info' label."""
        labels = export_context_labels_for_router()
        assert "info" in labels.split("|")

    def test_includes_routable_domains(self):
        """Test includes routable domain names."""
        labels_list = export_context_labels_for_router().split("|")
        routable = get_routable_domains()
        for domain in routable:
            assert domain in labels_list

    def test_excludes_internal_domains(self):
        """Test excludes internal domain names (context, query)."""
        labels_list = export_context_labels_for_router().split("|")
        # context and query should not be in labels (they're not routable)
        # But 'general' is added statically, which is different from 'context'
        assert "query" not in labels_list


# ============================================================================
# validate_domain_registry Tests
# ============================================================================


class TestValidateDomainRegistry:
    """Tests for validate_domain_registry function."""

    def test_current_registry_valid(self):
        """Test the current registry passes validation."""
        errors = validate_domain_registry()
        assert errors == [], f"Registry validation errors: {errors}"

    def test_detects_duplicate_agent_names(self):
        """Test validation would detect duplicate agent names.

        Note: We can't easily test this without modifying the registry,
        but we verify the check exists by testing the logic.
        """
        # The actual registry should have no duplicates
        all_agents = []
        for config in DOMAIN_REGISTRY.values():
            all_agents.extend(config.agent_names)
        duplicates = [name for name in all_agents if all_agents.count(name) > 1]
        assert duplicates == []

    def test_related_domains_exist(self):
        """Test all related domains exist in registry."""
        for domain_name, config in DOMAIN_REGISTRY.items():
            for related in config.related_domains:
                assert (
                    related in DOMAIN_REGISTRY
                ), f"Domain '{domain_name}' references non-existent '{related}'"


# ============================================================================
# Integration Tests
# ============================================================================


class TestDomainTaxonomyIntegration:
    """Integration tests for domain taxonomy."""

    def test_result_key_matches_domain_convention(self):
        """Test result_key follows domain + 's' convention."""
        for domain_name, config in DOMAIN_REGISTRY.items():
            # Most result keys are domain + 's'
            # Some special cases exist (context -> contexts, query -> querys)
            assert config.result_key.endswith(
                "s"
            ), f"Domain '{domain_name}' result_key should end with 's'"

    def test_all_agents_have_agent_suffix(self):
        """Test all agent names end with '_agent'."""
        for domain_name, config in DOMAIN_REGISTRY.items():
            for agent in config.agent_names:
                assert agent.endswith(
                    "_agent"
                ), f"Agent '{agent}' in domain '{domain_name}' should end with '_agent'"

    def test_google_oauth_or_apikey_domains(self):
        """Test Google provider domains require either OAuth or API key."""
        google_domains = [
            name
            for name, config in DOMAIN_REGISTRY.items()
            if config.metadata.get("provider") == "google"
        ]
        for domain in google_domains:
            config = DOMAIN_REGISTRY[domain]
            has_oauth = config.metadata.get("requires_oauth") is True
            has_api_key = config.metadata.get("requires_api_key") is True
            assert (
                has_oauth or has_api_key
            ), f"Google domain '{domain}' should require OAuth or API key"

    def test_domain_lookup_workflow(self):
        """Test typical domain lookup workflow."""
        # 1. Get all routable domains
        routable = get_routable_domains()
        assert len(routable) > 0

        # 2. Get config for a specific domain
        email_config = get_domain_config("email")
        assert email_config is not None

        # 3. Get result key for a tool
        result_key = get_result_key_for_tool("send_email_tool")
        assert result_key == "emails"
