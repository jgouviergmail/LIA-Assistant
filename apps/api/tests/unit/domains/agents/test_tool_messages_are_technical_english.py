"""Tool-facing messages are technical English for the model (ADR-256 doctrine).

Prompt audit 2026-09-12 (lot B): three tool payloads and the rate limiter's default
refusal were inline French — a language in Python, in a message the model
reformulates for a person who may not speak it.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

from src.domains.agents.context.resolver import ReferenceResolver
from src.domains.agents.formatters.resolved_context import format_resolved_context_for_prompt
from src.domains.agents.utils.rate_limiting import _rate_limit_tracker, rate_limit
from tests.helpers.runtime_context import make_tool_runtime


def test_resolver_without_context_says_so_in_english() -> None:
    result = ReferenceResolver(MagicMock(name="definition")).resolve("2", [])
    assert result.error == "no_context"
    assert result.message == "No item in the current context."


def test_resolved_context_formatter_without_items_is_english() -> None:
    assert (
        format_resolved_context_for_prompt({"items": []}, "fr")
        == "No item resolved for this reference."
    )


async def test_rate_limiter_default_refusal_is_english() -> None:
    _rate_limit_tracker.clear()
    wrapper_settings = MagicMock()
    wrapper_settings.rate_limit_enabled = True

    @rate_limit(max_calls=1, window_seconds=60, scope="user")
    async def probe_tool(*, runtime: Any) -> str:
        return "ran"

    runtime = make_tool_runtime()
    with patch("src.core.config.get_settings", return_value=wrapper_settings):
        assert await probe_tool(runtime=runtime) == "ran"
        blocked = json.loads(await probe_tool(runtime=runtime))
    _rate_limit_tracker.clear()
    assert blocked["error"] == "rate_limit_exceeded"
    assert blocked["message"].startswith("Rate limit exceeded for probe_tool")
    assert "seconds" in blocked["message"]
    assert "Veuillez" not in blocked["message"]
