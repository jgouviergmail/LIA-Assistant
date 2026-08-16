"""Tests for per-tool call limits (ToolCallLimitMiddleware wiring).

ModelCallLimitMiddleware bounds LLM calls and ``@rate_limit`` bounds calls in
time, but nothing bounded how many times a single run could invoke one paid
tool (image generation, Perplexity, Brave): an agent looping on a paid tool
was only stopped by the global model-call ceiling. The middleware stack now
adds one ``ToolCallLimitMiddleware(tool_name=…)`` per configured entry, parsed
from the settings-driven ``tool_call_run_limits`` string.

Format: ``"tool_a:2,tool_b:4"`` — tool name to max calls per run. Empty string
disables the feature. Malformed entries fail at settings validation (boot),
never silently at stack-build time.
"""

from __future__ import annotations

import pytest

from src.infrastructure.llm.middleware_config import parse_tool_call_run_limits

pytestmark = pytest.mark.unit


class TestParseToolCallRunLimits:
    def test_nominal_mapping(self) -> None:
        assert parse_tool_call_run_limits("generate_image:2,brave_search_tool:6") == {
            "generate_image": 2,
            "brave_search_tool": 6,
        }

    def test_spaces_are_tolerated(self) -> None:
        assert parse_tool_call_run_limits(" generate_image : 2 , brave_search_tool : 6 ") == {
            "generate_image": 2,
            "brave_search_tool": 6,
        }

    def test_empty_string_disables(self) -> None:
        assert parse_tool_call_run_limits("") == {}
        assert parse_tool_call_run_limits("   ") == {}

    @pytest.mark.parametrize(
        "raw",
        [
            "generate_image",  # missing limit
            "generate_image:abc",  # non-integer limit
            "generate_image:0",  # zero forbidden (use empty string to disable)
            "generate_image:-1",  # negative forbidden
            ":3",  # missing tool name
            "a:1,a:2",  # duplicate tool
        ],
    )
    def test_malformed_entries_raise(self, raw: str) -> None:
        with pytest.raises(ValueError):
            parse_tool_call_run_limits(raw)


class TestStackWiring:
    def test_stack_contains_one_limiter_per_configured_tool(self, monkeypatch) -> None:
        from langchain.agents.middleware import ToolCallLimitMiddleware

        from src.core.config import settings
        from src.infrastructure.llm.middleware_config import create_agent_middleware_stack

        monkeypatch.setattr(
            settings, "tool_call_run_limits", "generate_image:2,perplexity_search_tool:4"
        )
        stack = create_agent_middleware_stack("contacts_agent")

        limiters = [m for m in stack if isinstance(m, ToolCallLimitMiddleware)]
        assert len(limiters) == 2

    def test_stack_has_no_limiter_when_disabled(self, monkeypatch) -> None:
        from langchain.agents.middleware import ToolCallLimitMiddleware

        from src.core.config import settings
        from src.infrastructure.llm.middleware_config import create_agent_middleware_stack

        monkeypatch.setattr(settings, "tool_call_run_limits", "")
        stack = create_agent_middleware_stack("contacts_agent")

        limiters = [m for m in stack if isinstance(m, ToolCallLimitMiddleware)]
        assert limiters == []

    PAID_TOOLS = (
        "generate_image",
        "edit_image",
        "perplexity_search_tool",
        "perplexity_ask_tool",
        "brave_search_tool",
        "brave_news_tool",
    )

    def test_default_setting_covers_the_paid_tools(self) -> None:
        """The shipped default must bound every paid external-API tool."""
        from src.core.config import settings

        parsed = parse_tool_call_run_limits(settings.tool_call_run_limits)
        for paid_tool in self.PAID_TOOLS:
            assert paid_tool in parsed, f"{paid_tool} missing from default tool_call_run_limits"
            assert parsed[paid_tool] >= 1

    def test_default_tool_names_exist_in_the_registry(self) -> None:
        """A limit on a misspelled tool is a protection that silently does not
        exist (ADR-085 doctrine) — every default-limited name must be a real
        tool. Names absent from the runtime registry (their family may be
        feature-flag-gated OFF in this environment, e.g. image generation) are
        verified against their canonical module instead: the import always
        works, only registration is flag-gated.
        """
        import importlib

        from langchain_core.tools import BaseTool

        from src.core.constants import TOOL_CALL_RUN_LIMITS_DEFAULT
        from src.domains.agents.tools.tool_registry import ensure_tools_loaded, get_all_tools

        ensure_tools_loaded()
        registered = set(get_all_tools())
        parsed = parse_tool_call_run_limits(TOOL_CALL_RUN_LIMITS_DEFAULT)

        flagged_tool_modules = {
            "generate_image": "src.domains.agents.tools.image_generation_tools",
            "edit_image": "src.domains.agents.tools.image_generation_tools",
        }

        missing: list[str] = []
        for name in parsed:
            if name in registered:
                continue
            module_path = flagged_tool_modules.get(name)
            if module_path is None:
                missing.append(name)
                continue
            module = importlib.import_module(module_path)
            tool = getattr(module, name, None)
            if not isinstance(tool, BaseTool) or tool.name != name:
                missing.append(name)

        assert not missing, f"tool_call_run_limits names not backed by a real tool: {missing}"


class TestBootValidation:
    """bootstrap.validate_tool_call_run_limits — malformed setting refuses boot."""

    def test_passes_on_current_setting(self) -> None:
        from src.core.bootstrap import validate_tool_call_run_limits

        validate_tool_call_run_limits()  # must not raise on the shipped default

    def test_raises_runtime_error_on_malformed_setting(self, monkeypatch) -> None:
        from src.core.bootstrap import validate_tool_call_run_limits
        from src.core.config import settings

        monkeypatch.setattr(settings, "tool_call_run_limits", "generate_image:abc")
        with pytest.raises(RuntimeError, match="tool_call_run_limits"):
            validate_tool_call_run_limits()
