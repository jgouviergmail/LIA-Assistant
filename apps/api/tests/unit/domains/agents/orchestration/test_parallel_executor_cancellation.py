"""Cancellation propagation and FOR_EACH "stop" semantics (F18/F17, 2026-07).

- F18: ``asyncio.CancelledError`` used to be swallowed by ``_execute_tool``'s
  broad except tuple (converted into a failed ToolExecutionResult), so an SSE
  disconnect no longer stopped the remaining steps. It must PROPAGATE — at
  the tool level AND at the wave level (in Python 3.12 CancelledError derives
  from BaseException, so ``gather(return_exceptions=True)`` hands it back as
  a result that an ``isinstance(x, Exception)`` conversion would miss).

- F17: in parallel FOR_EACH execution, ``on_item_error="stop"`` fired its
  break only AFTER gather() had already executed every item. It now forces
  the sequential path (``FOR_EACH_STOP_FORCES_SEQUENTIAL``, default true).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.orchestration import parallel_executor as pe


def _fake_tool(coroutine: Any) -> SimpleNamespace:
    """Minimal StructuredTool stand-in: _execute_tool only needs .coroutine."""
    return SimpleNamespace(coroutine=coroutine, args_schema=None, name="fake_tool")


def _registry_returning(tool: Any) -> MagicMock:
    registry = MagicMock()
    registry.get_tool.return_value = tool
    return registry


@pytest.mark.unit
@pytest.mark.asyncio
class TestExecuteToolCancellation:
    """_execute_tool re-raises CancelledError instead of swallowing it."""

    async def test_cancelled_error_propagates(self) -> None:
        async def _cancelled_coroutine(**kwargs: Any) -> None:
            raise asyncio.CancelledError()

        tool = _fake_tool(_cancelled_coroutine)
        with (
            patch.object(pe.ToolRegistry, "get_instance", return_value=_registry_returning(tool)),
            patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
        ):
            with pytest.raises(asyncio.CancelledError):
                await pe._execute_tool(
                    tool_name="fake_tool",
                    args={},
                    config={"configurable": {}},
                    store=None,
                )

    async def test_regular_exception_still_converted(self) -> None:
        """Non-cancellation errors keep the historical failed-result contract."""

        async def _boom_coroutine(**kwargs: Any) -> None:
            raise RuntimeError("boom")

        tool = _fake_tool(_boom_coroutine)
        with (
            patch.object(pe.ToolRegistry, "get_instance", return_value=_registry_returning(tool)),
            patch.object(pe, "_build_tool_runtime", side_effect=lambda t, a, c, s: a),
        ):
            result = await pe._execute_tool(
                tool_name="fake_tool",
                args={},
                config={"configurable": {}},
                store=None,
            )

        assert result.result["success"] is False
        assert "boom" in result.result["error"]


@pytest.mark.unit
class TestForEachStopForcesSequential:
    """on_item_error='stop' must not run items in parallel (setting-gated)."""

    def test_setting_exists_and_defaults_true(self) -> None:
        from src.core.constants import FOR_EACH_STOP_FORCES_SEQUENTIAL_DEFAULT

        assert FOR_EACH_STOP_FORCES_SEQUENTIAL_DEFAULT is True

    def test_settings_field_wired(self) -> None:
        from src.core.config import settings

        assert isinstance(settings.for_each_stop_forces_sequential, bool)
