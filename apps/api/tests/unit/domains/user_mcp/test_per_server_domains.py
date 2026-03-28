"""Tests for per-server MCP domain routing (F2.2).

Covers: slugify, deduplication, is_mcp_domain, dynamic DomainConfig fallback,
get_result_key fallback, manifest per-server agent, and removesuffix bugfix.
"""

import pytest

from src.domains.agents.constants import MCP_DOMAIN_PREFIX
from src.domains.agents.registry.domain_taxonomy import (
    DomainConfig,
    deduplicate_mcp_slugs,
    get_domain_config,
    get_result_key,
    is_mcp_domain,
    slugify_mcp_server_name,
)


class TestSlugifyMCPServerName:
    """Tests for slugify_mcp_server_name()."""

    def test_basic(self) -> None:
        """Basic server name slugification."""
        assert slugify_mcp_server_name("HuggingFace Hub") == "mcp_huggingface_hub"

    def test_special_chars(self) -> None:
        """Special characters are replaced with underscores and collapsed."""
        assert slugify_mcp_server_name("My-Server.v2!") == "mcp_my_server_v2"

    def test_empty_string(self) -> None:
        """Empty string returns fallback."""
        assert slugify_mcp_server_name("") == "mcp_unnamed"

    def test_only_special_chars(self) -> None:
        """String with only special chars returns fallback."""
        assert slugify_mcp_server_name("---!!!") == "mcp_unnamed"

    def test_unicode(self) -> None:
        """Unicode characters are replaced with underscores."""
        result = slugify_mcp_server_name("Serveur Météo")
        assert result.startswith(MCP_DOMAIN_PREFIX)
        # Unicode chars replaced, collapsed underscores
        assert "mcp_serveur_m" in result

    def test_long_name_truncated(self) -> None:
        """Names longer than 40 chars are truncated."""
        long_name = "A" * 60
        result = slugify_mcp_server_name(long_name)
        # mcp_ prefix (4 chars) + 40 chars max slug = 44 chars max
        slug_part = result.removeprefix(MCP_DOMAIN_PREFIX)
        assert len(slug_part) <= 40

    def test_agent_in_name(self) -> None:
        """Server named 'Agent Smith' produces correct slug (not corrupted by replace)."""
        result = slugify_mcp_server_name("Agent Smith")
        assert result == "mcp_agent_smith"

    def test_preserves_numbers(self) -> None:
        """Numbers are preserved in slugs."""
        assert slugify_mcp_server_name("GPT4 API v2") == "mcp_gpt4_api_v2"

    def test_leading_trailing_underscores_stripped(self) -> None:
        """Leading/trailing underscores from special chars are stripped."""
        assert slugify_mcp_server_name("__test__") == "mcp_test"


class TestDeduplicateMCPSlugs:
    """Tests for deduplicate_mcp_slugs()."""

    def test_no_collision(self) -> None:
        """No collision returns simple mapping."""
        result = deduplicate_mcp_slugs(["HuggingFace", "GitHub"])
        assert result == {
            "HuggingFace": "mcp_huggingface",
            "GitHub": "mcp_github",
        }

    def test_collision_appends_suffix(self) -> None:
        """Colliding slugs get _2, _3 suffixes."""
        result = deduplicate_mcp_slugs(["Test Server", "test-server", "test_server"])
        slugs = list(result.values())
        assert slugs[0] == "mcp_test_server"
        assert slugs[1] == "mcp_test_server_2"
        assert slugs[2] == "mcp_test_server_3"

    def test_empty_list(self) -> None:
        """Empty list returns empty dict."""
        assert deduplicate_mcp_slugs([]) == {}

    def test_single_server(self) -> None:
        """Single server returns single entry."""
        result = deduplicate_mcp_slugs(["My Server"])
        assert result == {"My Server": "mcp_my_server"}


class TestIsMCPDomain:
    """Tests for is_mcp_domain()."""

    def test_per_server_domain(self) -> None:
        """Per-server MCP domains return True."""
        assert is_mcp_domain("mcp_huggingface_hub") is True

    def test_base_mcp_domain(self) -> None:
        """Base 'mcp' domain returns False (it's the admin fallback, not per-server)."""
        assert is_mcp_domain("mcp") is False

    def test_non_mcp_domain(self) -> None:
        """Non-MCP domains return False."""
        assert is_mcp_domain("email") is False
        assert is_mcp_domain("contact") is False
        assert is_mcp_domain("weather") is False

    def test_empty_string(self) -> None:
        """Empty string returns False."""
        assert is_mcp_domain("") is False


class TestGetDomainConfigDynamicMCP:
    """Tests for get_domain_config() fallback for dynamic mcp_* domains."""

    def test_static_domain_unchanged(self) -> None:
        """Static domains still work as before."""
        config = get_domain_config("contact")
        assert config is not None
        assert config.name == "contact"

    def test_dynamic_mcp_domain(self) -> None:
        """Dynamic mcp_* domains return synthesized DomainConfig."""
        config = get_domain_config("mcp_huggingface_hub")
        assert config is not None
        assert isinstance(config, DomainConfig)
        assert config.name == "mcp_huggingface_hub"
        assert config.result_key == "mcps"
        assert config.is_routable is True
        assert config.metadata.get("dynamic") is True

    def test_unknown_domain_returns_none(self) -> None:
        """Unknown non-MCP domain returns None."""
        assert get_domain_config("nonexistent_domain") is None

    def test_base_mcp_domain_from_registry(self) -> None:
        """Base 'mcp' domain comes from static registry, not fallback."""
        config = get_domain_config("mcp")
        assert config is not None
        assert config.name == "mcp"
        assert config.result_key == "mcps"


class TestGetResultKeyDynamicMCP:
    """Tests for get_result_key() fallback for dynamic mcp_* domains."""

    def test_static_domain(self) -> None:
        """Static domains return correct result_key."""
        assert get_result_key("weather") == "weathers"

    def test_dynamic_mcp_domain(self) -> None:
        """Dynamic mcp_* domains return 'mcps'."""
        assert get_result_key("mcp_huggingface_hub") == "mcps"
        assert get_result_key("mcp_github") == "mcps"

    def test_unknown_domain(self) -> None:
        """Unknown non-MCP domain returns None."""
        assert get_result_key("nonexistent") is None


class TestManifestAgentPerServer:
    """Tests for per-server agent naming in _build_user_tool_manifest."""

    def test_manifest_agent_uses_server_domain(self) -> None:
        """Manifest agent should be '{server_domain}_agent', not 'mcp_agent'."""
        from src.infrastructure.mcp.user_context import _build_user_tool_manifest

        manifest = _build_user_tool_manifest(
            adapter_name="mcp_user_abc123_search_models",
            tool_name="search_models",
            description="Search ML models on HuggingFace",
            input_schema={"properties": {"query": {"type": "string"}}, "required": ["query"]},
            server_name="HuggingFace Hub",
            server_domain="mcp_huggingface_hub",
            hitl_required=True,
        )
        assert manifest.agent == "mcp_huggingface_hub_agent"

    def test_manifest_semantic_keywords_include_domain(self) -> None:
        """Manifest semantic_keywords should include server_domain."""
        from src.infrastructure.mcp.user_context import _build_user_tool_manifest

        manifest = _build_user_tool_manifest(
            adapter_name="mcp_user_abc123_search",
            tool_name="search",
            description="Search repositories",
            input_schema={},
            server_name="GitHub",
            server_domain="mcp_github",
            hitl_required=False,
        )
        assert "mcp_github" in manifest.semantic_keywords


class TestRemovesuffixVsReplace:
    """Tests verifying removesuffix correctness vs the old replace approach."""

    @pytest.mark.parametrize(
        "agent_name,expected_domain",
        [
            # Standard agents (both approaches give same result)
            ("contact_agent", "contact"),
            ("email_agent", "email"),
            ("weather_agent", "weather"),
            ("web_search_agent", "web_search"),
            # MCP per-server agents (removesuffix correct, replace would break)
            ("mcp_huggingface_hub_agent", "mcp_huggingface_hub"),
            ("mcp_github_agent", "mcp_github"),
            # Edge case: "agent" in server name
            ("mcp_agent_smith_agent", "mcp_agent_smith"),
            ("mcp_my_agent_server_agent", "mcp_my_agent_server"),
        ],
    )
    def test_removesuffix_extracts_correct_domain(
        self, agent_name: str, expected_domain: str
    ) -> None:
        """removesuffix('_agent') extracts the correct domain in all cases."""
        assert agent_name.removesuffix("_agent") == expected_domain

    @pytest.mark.parametrize(
        "agent_name",
        [
            "mcp_agent_smith_agent",
            "mcp_my_agent_server_agent",
        ],
    )
    def test_replace_would_break_agent_in_name(self, agent_name: str) -> None:
        """Demonstrates that replace('_agent', '') gives wrong results for names containing 'agent'."""
        # replace removes ALL occurrences, corrupting the domain
        wrong_result = agent_name.replace("_agent", "")
        correct_result = agent_name.removesuffix("_agent")
        assert (
            wrong_result != correct_result
        ), f"Expected replace to differ from removesuffix for '{agent_name}'"
