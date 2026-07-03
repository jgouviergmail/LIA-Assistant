"""Unit tests for ReAct tool wrappers cancellation handling.

Regression coverage for the 2026-07 codebase audit (wave 1):
- Both ReAct wrappers caught ``BaseException`` and converted it to an
  "ERROR: ..." string for the LLM. That also swallowed
  ``asyncio.CancelledError``, so a user stop did NOT stop the ReAct loop —
  the agent kept iterating on a fake tool error instead of cancelling.
"""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper
from src.domains.agents.tools.react_tool_wrapper import ReactToolWrapper

# ============================================================================
# Test doubles
# ============================================================================


class _CancelledTool(BaseTool):
    """Inner tool whose execution is cancelled."""

    name: str = "cancelled_tool"
    description: str = "Simulates a cancelled coroutine"

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError

    async def _arun(self, **kwargs: Any) -> str:
        raise asyncio.CancelledError()


class _FailingTool(BaseTool):
    """Inner tool that raises a regular exception."""

    name: str = "failing_tool"
    description: str = "Simulates a tool failure"

    def _run(self, **kwargs: Any) -> str:
        raise NotImplementedError

    async def _arun(self, **kwargs: Any) -> str:
        raise ValueError("boom")


def _mcp_inner(delegate: BaseTool) -> SimpleNamespace:
    """Fake MCP adapter exposing the attributes _MCPReActWrapper reads."""
    return SimpleNamespace(
        mcp_tool_name=delegate.name,
        description=delegate.description,
        args_schema=None,
        _arun=delegate._arun,
    )


# ============================================================================
# REGRESSION: user cancellation must propagate (audit item 13)
# ============================================================================


@pytest.mark.unit
async def test_mcp_react_wrapper_propagates_cancellation():
    """CancelledError must escape the MCP ReAct wrapper, not become a string."""
    wrapper = _MCPReActWrapper(_mcp_inner(_CancelledTool()))

    with pytest.raises(asyncio.CancelledError):
        await wrapper._arun()


@pytest.mark.unit
async def test_react_tool_wrapper_propagates_cancellation():
    """CancelledError must escape the ReAct tool wrapper, not become a string."""
    wrapper = ReactToolWrapper(_CancelledTool())

    with pytest.raises(asyncio.CancelledError):
        await wrapper._arun()


@pytest.mark.unit
async def test_mcp_react_wrapper_still_stringifies_regular_errors():
    """Regular exceptions keep the reason-and-retry behavior for the LLM."""
    wrapper = _MCPReActWrapper(_mcp_inner(_FailingTool()))

    result = await wrapper._arun()

    assert result == "ERROR: boom"


@pytest.mark.unit
async def test_react_tool_wrapper_still_stringifies_regular_errors():
    """Regular exceptions keep the reason-and-retry behavior for the LLM."""
    wrapper = ReactToolWrapper(_FailingTool())

    result = await wrapper._arun()

    assert result == "ERROR: boom"
