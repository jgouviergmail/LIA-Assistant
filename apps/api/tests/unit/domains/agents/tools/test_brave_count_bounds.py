"""One bound on the Brave ``count``, published where it is enforced (prompt audit 2026-09-12, A.3).

Measured: the agent prompt said « max 20 / 50 », the catalogue manifest published
``maximum=20/50`` to the planner (so the ADR-184 repair let 20 through), the tool
docstring said « 1-10 » and the tool clamped to 10 in silence — a person asking for
twenty results got ten and nobody said so. Brave's own API maxima are 20 (web) and
50 (news); they are ONE constant each, read by the manifest, the tool, the parameter
description and the prompt.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.constants import BRAVE_NEWS_SEARCH_MAX_COUNT, BRAVE_WEB_SEARCH_MAX_COUNT
from src.domains.agents.brave.catalogue_manifests import (
    brave_news_catalogue_manifest,
    brave_search_catalogue_manifest,
)
from src.domains.agents.graphs.brave_agent_builder import render_brave_agent_prompt
from src.domains.agents.tools import brave_tools
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker
from tests.helpers.runtime_context import make_tool_runtime


def _count_maximum(manifest: Any) -> int | None:
    for parameter in manifest.parameters:
        if parameter.name == "count":
            for constraint in parameter.constraints:
                if constraint.kind == "maximum":
                    return int(constraint.value)
    return None


class TestOneBoundPerEndpoint:
    def test_manifest_publishes_the_enforced_maximum(self) -> None:
        assert _count_maximum(brave_search_catalogue_manifest) == BRAVE_WEB_SEARCH_MAX_COUNT
        assert _count_maximum(brave_news_catalogue_manifest) == BRAVE_NEWS_SEARCH_MAX_COUNT

    def test_parameter_description_names_the_same_number(self) -> None:
        web = brave_tools.brave_search_tool.args_schema.model_fields["count"].description or ""
        news = brave_tools.brave_news_tool.args_schema.model_fields["count"].description or ""
        assert str(BRAVE_WEB_SEARCH_MAX_COUNT) in web
        assert str(BRAVE_NEWS_SEARCH_MAX_COUNT) in news
        assert "1-10" not in web and "1-10" not in news

    def test_tool_description_does_not_contradict(self) -> None:
        assert "1-10" not in brave_tools.brave_search_tool.description
        assert "1-10" not in brave_tools.brave_news_tool.description

    def test_agent_prompt_reads_the_same_numbers(self) -> None:
        rendered = render_brave_agent_prompt()
        assert f"web: max {BRAVE_WEB_SEARCH_MAX_COUNT}" in rendered
        assert f"news: max {BRAVE_NEWS_SEARCH_MAX_COUNT}" in rendered
        assert "{brave_web_max_count}" not in rendered and "{brave_news_max_count}" not in rendered

    @pytest.mark.parametrize(
        ("tool", "impl_name", "maximum"),
        [
            ("brave_search_tool", "_brave_search_tool_impl", BRAVE_WEB_SEARCH_MAX_COUNT),
            ("brave_news_tool", "_brave_news_tool_impl", BRAVE_NEWS_SEARCH_MAX_COUNT),
        ],
    )
    async def test_tool_clamps_to_the_published_maximum(
        self, tool: str, impl_name: str, maximum: int
    ) -> None:
        impl = MagicMock()
        impl.execute = AsyncMock(return_value="{}")
        with patch.object(brave_tools, impl_name, impl):
            await getattr(brave_tools, tool).coroutine(query="q", count=maximum + 30, runtime=None)
        assert impl.execute.await_args.kwargs["count"] == maximum


class TestPaidApiIsRateLimited:
    """A tool hitting a paid API carries ``@rate_limit`` (systemic rule, tools)."""

    @pytest.fixture(autouse=True)
    def _reset_tracker(self) -> Any:
        _rate_limit_tracker.clear()
        yield
        _rate_limit_tracker.clear()

    async def test_exceeding_the_settings_ceiling_short_circuits(self) -> None:
        settings = MagicMock()  # what the decorator lambdas read (module-level)
        settings.brave_rate_limit_calls = 2
        settings.brave_rate_limit_window = 60
        wrapper_settings = MagicMock()  # what the wrapper's get_settings() reads
        wrapper_settings.rate_limit_enabled = True
        impl = MagicMock()
        impl.execute = AsyncMock(return_value="{}")
        runtime = make_tool_runtime()
        with (
            patch.object(brave_tools, "settings", settings),
            patch("src.core.config.get_settings", return_value=wrapper_settings),
            patch.object(brave_tools, "_brave_search_tool_impl", impl),
        ):
            results = [
                await brave_tools.brave_search_tool.coroutine(query="q", runtime=runtime)
                for _ in range(settings.brave_rate_limit_calls + 1)
            ]
        assert impl.execute.await_count == settings.brave_rate_limit_calls
        blocked = json.loads(results[-1])
        assert blocked["error"] == "rate_limit_exceeded"
