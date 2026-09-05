"""The gate must hold on the tools it was BUILT for (ADR-263).

Measured 2026-09-04, and it is the founding hole of this lot pointing back at
itself: ``confirm`` exists for third-party MCP tools, and MCP tools were the
one family the installer could not gate.

- ``MCPToolAdapter`` and ``UserMCPToolAdapter`` are ``BaseTool`` subclasses
  whose ``coroutine`` is a read-only ``@property``. Assigning the gate to it
  raised ``AttributeError`` — so registering ANY user's MCP server broke, and
  the tool would have been ungated anyway.
- They are reached through THREE doors, not one: ``.coroutine(...)`` (the
  pipeline's direct path), ``ainvoke(...)`` → ``_arun`` (the sub-agent runner),
  and ``_inner._arun(...)`` (``_MCPReActWrapper``, the ReAct loop). A gate on
  ``.coroutine`` alone would have left the last two open.

So these adapters gate THEMSELVES, in ``_arun``, where all three doors meet.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.runtime import EFFECT_GATED_ATTR
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.infrastructure.mcp.tool_adapter import MCPToolAdapter
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter

pytestmark = [pytest.mark.unit]

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"plan": {"type": "string"}}}


def _mcp_tool() -> MCPToolAdapter:
    return MCPToolAdapter.from_mcp_tool(
        server_name="era",
        tool_name="billing__cancel_subscription",
        description="Cancel a subscription",
        input_schema=_SCHEMA,
    )


def _user_mcp_tool() -> UserMCPToolAdapter:
    return UserMCPToolAdapter.from_discovered_tool(
        server_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        server_name="era",
        tool_name="billing__cancel_subscription",
        description="Cancel a subscription",
        input_schema=_SCHEMA,
    )


@pytest.fixture(autouse=True)
def _attended_user() -> Any:
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=uuid.uuid4(),
            thread_id="thread-mcp",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


class TestRegisteringAnMcpToolStillWorks:
    """The regression: a read-only property is not a place to install a gate."""

    def test_the_server_adapter_registers_and_is_gated(self) -> None:
        from src.domains.agents.tools.tool_registry import register_external_tool

        tool = _mcp_tool()
        register_external_tool(tool)  # must not raise

        assert getattr(tool.coroutine, EFFECT_GATED_ATTR, False) is True

    def test_the_user_adapter_registers_and_is_gated(self) -> None:
        from src.domains.agents.tools.tool_registry import register_external_tool

        tool = _user_mcp_tool()
        register_external_tool(tool)

        assert getattr(tool.coroutine, EFFECT_GATED_ATTR, False) is True


class TestARenamedAdapterActsUnderItsOwnName:
    """``model_copy`` carries private attributes — the memoised gate included."""

    def test_a_renamed_copy_rebuilds_its_gate(self) -> None:
        from src.domains.agents.effects.runtime import EFFECT_GATED_NAME_ATTR
        from src.domains.agents.tools.tool_registry import register_external_tool

        tool = _mcp_tool()
        register_external_tool(tool)
        assert getattr(tool.coroutine, EFFECT_GATED_NAME_ATTR, None) == tool.name

        renamed = tool.model_copy(update={"name": "mcp_other_billing__cancel_subscription"})

        assert (
            getattr(renamed.coroutine, EFFECT_GATED_NAME_ATTR, None)
            == "mcp_other_billing__cancel_subscription"
        )
        # And registering it must still not try to write the read-only property.
        register_external_tool(renamed)


class TestEveryDoorIsGated:
    """One capability, three call paths, one gate."""

    @staticmethod
    async def _refused_through(call: Any) -> Any:
        """Run ``call`` with a policy the gate must stop, and no authority."""
        with (
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
            patch.object(gate_runtime, "_LEDGER", _SilentLedger()),
            effect_scope(EffectScope(run_id="r", idempotency_key="step:s1", source="scheduled")),
        ):
            return await call()

    async def test_the_direct_coroutine_path_is_gated(self) -> None:
        tool = _mcp_tool()
        result = await self._refused_through(lambda: tool.coroutine(plan="premium"))
        assert result["success"] is False

    async def test_the_arun_path_is_gated(self) -> None:
        """``ainvoke`` and ``_MCPReActWrapper`` both land on ``_arun``."""
        tool = _mcp_tool()
        result = await self._refused_through(lambda: tool._arun(plan="premium"))
        assert result["success"] is False

    async def test_the_react_wrapper_path_is_gated(self) -> None:
        """The ReAct loop calls ``self._inner._arun(...)``, a door of its own.

        The wrapper stringifies whatever comes back, so the assertion is on
        what matters: the server was never reached.
        """
        from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper

        reached: list[dict[str, Any]] = []

        async def _record(self: Any, **kwargs: Any) -> Any:
            reached.append(kwargs)
            return None

        wrapper = _MCPReActWrapper(inner=_mcp_tool())
        with patch.object(MCPToolAdapter, "_call_server", new=_record):
            await self._refused_through(lambda: wrapper._arun(plan="premium"))

        assert reached == [], "the ReAct door reached the MCP server ungated"

    async def test_the_user_adapter_is_gated_on_arun_too(self) -> None:
        tool = _user_mcp_tool()
        result = await self._refused_through(lambda: tool._arun(plan="premium"))
        assert result["success"] is False


class TestTheGateResolvesTheRightIdentity:
    async def test_it_reads_the_policy_of_the_prefixed_name(self) -> None:
        """The ledger names the tool the user's catalogue names."""
        seen: list[str] = []
        tool = _mcp_tool()

        def _policy(name: str) -> str:
            seen.append(name)
            return "read"

        with (
            patch.object(gate_runtime, "resolve_policy", _policy),
            patch.object(MCPToolAdapter, "_call_server", new=_fake_server_call, create=False),
        ):
            await tool.coroutine(plan="premium")

        assert seen == ["mcp_era_billing__cancel_subscription"]


class _SilentLedger:
    async def claim(self, request: Any) -> Any:
        return None

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        return None


async def _fake_server_call(self: Any, **kwargs: Any) -> Any:
    from src.domains.agents.tools.output import UnifiedToolOutput

    return UnifiedToolOutput.action_success(message="ok")
