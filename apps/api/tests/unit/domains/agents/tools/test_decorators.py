"""Unit tests for tools/decorators.py (connector_tool presets).

Rewritten for the 2026-07 audit (value-blind remediation): every test in this
file previously asserted only ``tool_func is not None`` — always true for a
decorator, verifying nothing (the file's own docstring said "Focus on COVERAGE
of missing lines, not behavior testing"). A decorator could apply the wrong
description branch, drop the async wrapping, or fail to produce a LangChain
tool and every test would still pass.

The decorators compose sub-decorators (@track_tool_metrics, @rate_limit,
@auto_save_context, @tool); the one piece of branching logic they own is
description resolution (explicit description vs docstring). These tests assert
the introspectable contract of the produced tool: it is a LangChain BaseTool,
carries the wrapped function's name, resolves its description correctly, and
preserves the async coroutine. Rate-limit ENFORCEMENT is covered separately in
test_rate_limiting.py.
"""

from langchain_core.tools import BaseTool

from src.domains.agents.tools.decorators import (
    connector_tool,
    expensive_tool,
    read_tool,
    write_tool,
)


class TestConnectorToolContract:
    """connector_tool produces a well-formed LangChain tool."""

    def test_explicit_description_wins_over_docstring(self):
        """description= overrides the docstring (the branch at decorators.py:213)."""

        @connector_tool(name="with_desc", agent_name="test", description="Custom description")
        async def tool_func() -> str:
            """Ignored docstring."""
            return "ok"

        assert isinstance(tool_func, BaseTool)
        assert tool_func.description == "Custom description"

    def test_docstring_is_used_when_no_description(self):
        """Without description=, the docstring becomes the tool description (else branch)."""

        @connector_tool(name="no_desc", agent_name="test")
        async def tool_func() -> str:
            """Docstring description."""
            return "ok"

        assert isinstance(tool_func, BaseTool)
        assert tool_func.description == "Docstring description."

    def test_tool_name_is_the_wrapped_function_name(self):
        """@tool derives the tool name from the wrapped function."""

        @connector_tool(name="metrics_name", agent_name="test")
        async def my_search_tool() -> str:
            """Search."""
            return "ok"

        assert my_search_tool.name == "my_search_tool"

    def test_async_coroutine_is_preserved(self):
        """The async implementation survives the decorator stack."""

        @connector_tool(name="async_t", agent_name="test")
        async def tool_func() -> str:
            """Async tool."""
            return "ok"

        assert tool_func.coroutine is not None

    def test_custom_rate_limits_still_produce_a_tool(self):
        """Custom rate-limit overrides (decorators.py:191-194) build a valid tool."""

        @connector_tool(
            name="custom_limits",
            agent_name="test",
            rate_limit_max_calls=10,
            rate_limit_window_seconds=30,
        )
        async def tool_func() -> str:
            """Custom limits."""
            return "ok"

        assert isinstance(tool_func, BaseTool)
        assert tool_func.description == "Custom limits."

    def test_context_domain_still_produces_a_tool(self):
        """The auto-save-context branch (decorators.py:208) builds a valid tool."""

        @connector_tool(name="with_context", agent_name="test", context_domain="test_domain")
        async def tool_func() -> str:
            """With context."""
            return "ok"

        assert isinstance(tool_func, BaseTool)
        assert tool_func.description == "With context."

    def test_no_context_domain_still_produces_a_tool(self):
        """Skipping context saving (context_domain=None) builds a valid tool."""

        @connector_tool(name="no_context", agent_name="test", context_domain=None)
        async def tool_func() -> str:
            """No context."""
            return "ok"

        assert isinstance(tool_func, BaseTool)


class TestPresets:
    """read_tool / write_tool / expensive_tool delegate to connector_tool."""

    def test_read_tool_produces_named_tool_with_docstring(self):
        @read_tool(name="read_test", agent_name="test", context_domain="test")
        async def read_func() -> str:
            """Read tool docstring."""
            return "ok"

        assert isinstance(read_func, BaseTool)
        assert read_func.name == "read_func"
        assert read_func.description == "Read tool docstring."

    def test_write_tool_produces_named_tool_with_docstring(self):
        @write_tool(name="write_test", agent_name="test")
        async def write_func() -> str:
            """Write tool docstring."""
            return "ok"

        assert isinstance(write_func, BaseTool)
        assert write_func.name == "write_func"
        assert write_func.description == "Write tool docstring."

    def test_expensive_tool_produces_named_tool_with_docstring(self):
        @expensive_tool(name="expensive_test", agent_name="test")
        async def expensive_func() -> str:
            """Expensive tool docstring."""
            return "ok"

        assert isinstance(expensive_func, BaseTool)
        assert expensive_func.name == "expensive_func"
        assert expensive_func.description == "Expensive tool docstring."

    def test_expensive_tool_with_custom_limits(self):
        @expensive_tool(
            name="expensive_custom",
            agent_name="test",
            max_calls=1,
            window_seconds=3600,
        )
        async def tool_func() -> str:
            """Expensive with custom limits."""
            return "ok"

        assert isinstance(tool_func, BaseTool)
        assert tool_func.description == "Expensive with custom limits."

    def test_presets_produce_distinct_tools(self):
        """Each preset yields its own independent tool instance."""

        @read_tool(name="r", agent_name="a")
        async def read_func() -> str:
            """R."""
            return "r"

        @write_tool(name="w", agent_name="a")
        async def write_func() -> str:
            """W."""
            return "w"

        @expensive_tool(name="e", agent_name="a")
        async def expensive_func() -> str:
            """E."""
            return "e"

        tools = [read_func, write_func, expensive_func]
        assert all(isinstance(t, BaseTool) for t in tools)
        assert {t.name for t in tools} == {"read_func", "write_func", "expensive_func"}

    def test_connector_tool_all_categories_build(self):
        """All three rate-limit categories produce valid, distinctly-named tools."""

        @connector_tool(name="r", agent_name="a", category="read")
        async def read_cat() -> str:
            """R."""
            return "r"

        @connector_tool(name="w", agent_name="a", category="write")
        async def write_cat() -> str:
            """W."""
            return "w"

        @connector_tool(name="e", agent_name="a", category="expensive")
        async def exp_cat() -> str:
            """E."""
            return "e"

        assert {read_cat.name, write_cat.name, exp_cat.name} == {
            "read_cat",
            "write_cat",
            "exp_cat",
        }

    def test_connector_tool_rate_limit_scopes_build(self):
        """Both rate-limit scopes produce valid tools."""

        @connector_tool(name="user", agent_name="a", rate_limit_scope="user")
        async def user_scope() -> str:
            """User."""
            return "user"

        @connector_tool(name="global", agent_name="a", rate_limit_scope="global")
        async def global_scope() -> str:
            """Global."""
            return "global"

        assert isinstance(user_scope, BaseTool)
        assert isinstance(global_scope, BaseTool)
