"""ADR-083: the Sub-Agent LLM type label reflects its new ReAct-loop nature.

The internal `llm_type` id "subagent" is preserved (DB rows, config overrides,
code references all keep working). Only the human-facing display name changes,
mirroring the existing `mcp_react_agent` → "MCP Iterative (ReAct)" pattern.
"""

import pytest


@pytest.mark.unit
def test_subagent_display_name_signals_react():
    """The admin LLM panel must show 'Sub-Agent (ReAct)' for the subagent type."""
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

    meta = LLM_TYPES_REGISTRY["subagent"]
    assert meta.display_name == "Sub-Agent (ReAct)"


@pytest.mark.unit
def test_subagent_llm_type_id_is_unchanged():
    """Critical: the internal id MUST stay 'subagent' — renaming it breaks
    every existing DB row, env override, and code reference to get_llm('subagent').
    """
    from src.domains.llm_config.constants import LLM_TYPES_REGISTRY

    assert "subagent" in LLM_TYPES_REGISTRY
    meta = LLM_TYPES_REGISTRY["subagent"]
    assert meta.llm_type == "subagent"
    # description_key must also stay the same so the 6 locale files keep working.
    assert meta.description_key == "settings.admin.llmConfig.types.subagent"
