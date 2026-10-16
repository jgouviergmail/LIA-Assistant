"""The browser task reads how its loop ended, never its text (ADR-303).

A browser run acts on a page: when it ends without an answer, its steps may
already have clicked or filled something. The failure therefore says how far it
got and where the page is, instead of reading as « nothing ran »; an answer the
budget cut says so in its structured data.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.agents.tools.browser_tools import browser_task_tool
from src.domains.agents.tools.react_runner import (
    BUDGET_EXHAUSTED_FIELD,
    ReactSubAgentResult,
    SubAgentOutcome,
)

_MODULE = "src.domains.agents.tools.browser_tools"


async def _browse(result: ReactSubAgentResult) -> Any:
    page = MagicMock()
    page.url = "https://shop.example/cart"
    page.is_closed.return_value = False
    page.title = AsyncMock(return_value="Cart")
    pool = MagicMock(update_session_redis=AsyncMock())
    runner = MagicMock(run=AsyncMock(return_value=result))
    config = SimpleNamespace(user_id=str(uuid4()), session_id="thread-1")
    with (
        patch(f"{_MODULE}.validate_runtime_config", return_value=config),
        patch(f"{_MODULE}._get_session", AsyncMock(return_value=(pool, MagicMock(page=page)))),
        patch("src.domains.agents.tools.react_runner.ReactSubAgentRunner", return_value=runner),
    ):
        return await browser_task_tool.coroutine(task="Add the blue shirt to the cart")


@pytest.mark.unit
async def test_a_failed_run_says_how_far_it_got_and_where_the_page_is() -> None:
    output = await _browse(
        ReactSubAgentResult(
            final_message="",
            messages=[],
            iteration_count=3,
            outcome=SubAgentOutcome.ERROR,
            failure_kind="timeout",
        )
    )

    assert output.success is False
    assert output.error_code == "TIMEOUT"
    assert "after 3 step(s)" in output.message
    assert "https://shop.example/cart" in output.message


@pytest.mark.unit
async def test_a_closed_run_reports_and_says_its_budget_ended() -> None:
    output = await _browse(
        ReactSubAgentResult(
            final_message="The shirt is in the cart; checkout was not reached.",
            messages=[],
            iteration_count=6,
            closed_on_budget=True,
        )
    )

    assert output.success is True
    assert "checkout was not reached" in output.message
    assert output.structured_data[BUDGET_EXHAUSTED_FIELD] is True
    assert output.structured_data["url"] == "https://shop.example/cart"
