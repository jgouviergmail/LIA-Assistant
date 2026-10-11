"""The real tool bootstrap must load implementations before a planner selects them."""

import pytest

from src.domains.agents.tools.tool_registry import _import_tool_modules, get_tool

pytestmark = pytest.mark.unit


def test_native_source_tools_are_reachable_from_the_actual_bootstrap():
    _import_tool_modules()
    for name in (
        "get_lia_knowledge_source_options_tool",
        "link_lia_knowledge_source_tool",
        "unlink_lia_knowledge_source_tool",
        "sync_lia_knowledge_source_tool",
        "delete_lia_knowledge_source_tool",
    ):
        assert get_tool(name) is not None, name
