"""Sanity tests for sub-agent settings introduced by the ReAct delegation redesign (ADR-083).

NOTE: Default-value tests read ``AgentsSettings.model_fields[...].default``
(the code-level default) instead of instantiating settings. Instantiation
(``get_settings()`` / ``AgentsSettings()``) resolves environment variables —
and the Taskfile exports the developer's root ``.env`` via ``dotenv:``, so any
locally overridden SUBAGENT_* value would make a hardcoded-default assertion
fail under ``task test:backend:*`` while passing under bare pytest.
"""

import pytest
from pydantic import ValidationError

from src.core.config.agents import AgentsSettings


@pytest.mark.unit
def test_instruction_cap_default_is_10000():
    """SUBAGENT_INSTRUCTION_MAX_TOKENS_RESOLVED defaults to 10000 tokens.

    Aligned on the proven production value (2026-08-06).
    """
    field = AgentsSettings.model_fields["subagent_instruction_max_tokens_resolved"]
    assert field.default == 10000


@pytest.mark.unit
def test_subagent_tool_timeout_default_is_300():
    """SUBAGENT_TOOL_TIMEOUT_SECONDS defaults to 180 seconds (3 minutes)."""
    field = AgentsSettings.model_fields["subagent_tool_timeout_seconds"]
    assert field.default == 300.0


@pytest.mark.unit
def test_subagent_tool_max_timeout_default_is_300():
    """SUBAGENT_TOOL_MAX_TIMEOUT_SECONDS defaults to 300 seconds (5 minutes)."""
    field = AgentsSettings.model_fields["subagent_tool_max_timeout_seconds"]
    assert field.default == 300.0


@pytest.mark.unit
def test_subagent_default_max_iterations_default_is_20():
    """SUBAGENT_DEFAULT_MAX_ITERATIONS defaults to 10 (post-bump from 5)."""
    field = AgentsSettings.model_fields["subagent_default_max_iterations"]
    assert field.default == 20


@pytest.mark.unit
def test_subagent_tool_timeout_range_rejects_below_30():
    """sub_agent_tool_timeout_seconds must be >= 30 (Pydantic constraint)."""
    with pytest.raises(ValidationError) as exc_info:
        AgentsSettings(subagent_tool_timeout_seconds=29.0)
    assert "greater than or equal to 30" in str(exc_info.value)


@pytest.mark.unit
def test_subagent_tool_timeout_range_rejects_above_600():
    """sub_agent_tool_timeout_seconds must be <= 600 (Pydantic constraint)."""
    with pytest.raises(ValidationError) as exc_info:
        AgentsSettings(subagent_tool_timeout_seconds=601.0)
    assert "less than or equal to 600" in str(exc_info.value)


@pytest.mark.unit
def test_subagent_tool_max_timeout_range_rejects_below_60():
    """sub_agent_tool_max_timeout_seconds must be >= 60 (Pydantic constraint)."""
    with pytest.raises(ValidationError) as exc_info:
        AgentsSettings(subagent_tool_max_timeout_seconds=59.0)
    assert "greater than or equal to 60" in str(exc_info.value)


@pytest.mark.unit
def test_subagent_tool_max_timeout_range_rejects_above_900():
    """sub_agent_tool_max_timeout_seconds must be <= 900 (Pydantic constraint)."""
    with pytest.raises(ValidationError) as exc_info:
        AgentsSettings(subagent_tool_max_timeout_seconds=901.0)
    assert "less than or equal to 900" in str(exc_info.value)


@pytest.mark.unit
def test_subagent_default_max_iterations_ceiling_30():
    """subagent_default_max_iterations ceiling is 30 (was 15, bumped to allow 20+)."""
    # Boundary: 30 is accepted
    s = AgentsSettings(subagent_default_max_iterations=30)
    assert s.subagent_default_max_iterations == 30
    # Beyond: rejected
    with pytest.raises(ValidationError) as exc_info:
        AgentsSettings(subagent_default_max_iterations=31)
    assert "less than or equal to 30" in str(exc_info.value)


@pytest.mark.unit
class TestSubagentResearchToolsWhitelistParsed:
    """Tests for the `subagent_research_tools_whitelist_parsed` derived list."""

    def test_default_parses_to_the_three_production_tools(self):
        """Default whitelist parses to the three production tools.

        Pins the CODE default explicitly (environment-hermetic): passing the
        field default as a constructor kwarg overrides any SUBAGENT_* env var
        exported by the Taskfile's dotenv from the developer's local .env.
        """
        default_whitelist = AgentsSettings.model_fields["subagent_research_tools_whitelist"].default
        s = AgentsSettings(subagent_research_tools_whitelist=default_whitelist)
        assert s.subagent_research_tools_whitelist_parsed == [
            "perplexity_search_tool",
            "brave_search_tool",
            "fetch_web_page_tool",
        ]

    def test_custom_csv_parses_correctly(self):
        """A custom CSV with extra spaces is trimmed and split."""
        s = AgentsSettings(
            subagent_research_tools_whitelist="  brave_search_tool , perplexity_search_tool ,fetch_web_page_tool"
        )
        assert s.subagent_research_tools_whitelist_parsed == [
            "brave_search_tool",
            "perplexity_search_tool",
            "fetch_web_page_tool",
        ]

    def test_empty_string_parses_to_empty_list(self):
        """An empty whitelist disables allowlist mode (resolve_tools_for_subagent falls back to blocklist-only)."""
        s = AgentsSettings(subagent_research_tools_whitelist="")
        assert s.subagent_research_tools_whitelist_parsed == []

    def test_single_value_parses_to_single_item_list(self):
        """A single tool name (no comma) parses to a one-element list."""
        s = AgentsSettings(subagent_research_tools_whitelist="brave_search_tool")
        assert s.subagent_research_tools_whitelist_parsed == ["brave_search_tool"]

    def test_trailing_comma_does_not_produce_empty_item(self):
        """Trailing commas are tolerated and do not produce empty strings in the list."""
        s = AgentsSettings(
            subagent_research_tools_whitelist="brave_search_tool,fetch_web_page_tool,"
        )
        assert s.subagent_research_tools_whitelist_parsed == [
            "brave_search_tool",
            "fetch_web_page_tool",
        ]

    def test_whitespace_only_entries_are_skipped(self):
        """CSV entries that are pure whitespace are filtered out."""
        s = AgentsSettings(
            subagent_research_tools_whitelist="brave_search_tool,   ,fetch_web_page_tool"
        )
        assert s.subagent_research_tools_whitelist_parsed == [
            "brave_search_tool",
            "fetch_web_page_tool",
        ]


@pytest.mark.unit
class TestSubagentResearchToolsWhitelistValidation:
    """Tests for `_validate_research_tools_whitelist_format` field_validator."""

    def test_dashes_instead_of_underscores_rejected(self):
        """A tool name with dashes (operator typo) is rejected at config-load."""
        with pytest.raises(ValidationError) as exc_info:
            AgentsSettings(
                subagent_research_tools_whitelist="brave-search-tool,fetch_web_page_tool"
            )
        assert "brave-search-tool" in str(exc_info.value)
        assert "snake_case" in str(exc_info.value)

    def test_semicolon_separator_rejected(self):
        """A semicolon-separated list (instead of commas) is rejected — the whole string is one invalid identifier."""
        with pytest.raises(ValidationError) as exc_info:
            AgentsSettings(
                subagent_research_tools_whitelist="brave_search_tool;fetch_web_page_tool"
            )
        assert "semicolons" in str(exc_info.value) or "snake_case" in str(exc_info.value)

    def test_uppercase_rejected(self):
        """A camelCase or PascalCase name is rejected (must be snake_case)."""
        with pytest.raises(ValidationError):
            AgentsSettings(subagent_research_tools_whitelist="BraveSearchTool")

    def test_leading_digit_rejected(self):
        """A name starting with a digit is rejected (must start with letter or underscore)."""
        with pytest.raises(ValidationError):
            AgentsSettings(subagent_research_tools_whitelist="1_brave_search_tool")

    def test_empty_string_accepted(self):
        """An empty string is accepted (disables allowlist mode)."""
        s = AgentsSettings(subagent_research_tools_whitelist="")
        assert s.subagent_research_tools_whitelist == ""

    def test_default_value_passes_validation(self):
        """The codebase default value passes its own validator."""
        # Should not raise
        AgentsSettings()
