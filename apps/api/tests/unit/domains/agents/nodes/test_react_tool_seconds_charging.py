"""The node that spends the most used to charge nothing (ADR-256).

Functional proof, not a source-string assertion: the node is driven with a real
(slow) tool and the returned state update is inspected. Before ADR-256,
``react_execute_tools_node`` returned no time key at all — measured by walking
every dict literal it writes, which is how the defect was found in the first
place.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from src.domains.agents.nodes import react_nodes

pytestmark = [pytest.mark.unit]

_SLEEP_SECONDS = 0.05


def _register_tool(name: str, *, delay: float = _SLEEP_SECONDS, fail: bool = False) -> None:
    from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

    if get_tool(name) is not None:
        return

    async def _fn() -> dict[str, Any]:
        await asyncio.sleep(delay)
        if fail:
            raise RuntimeError("boom")
        return {"success": True, "data": "ok"}

    register_external_tool(StructuredTool.from_function(coroutine=_fn, name=name, description="d"))


def _state(tool_names: list[str], calls: list[dict[str, Any]], **extra: Any) -> dict[str, Any]:
    return {
        "messages": [AIMessage(content="", tool_calls=calls)],
        "react_tool_names": tool_names,
        "react_hitl_map": dict.fromkeys(tool_names, False),
        "react_iteration": 1,
        "react_call_digests": {},
        **extra,
    }


def _call(name: str, cid: str) -> dict[str, Any]:
    return {"name": name, "args": {}, "id": cid, "type": "tool_call"}


@pytest.fixture(autouse=True)
def _no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """The context store needs PostgreSQL; the budget arithmetic does not."""

    async def _store() -> None:
        return None

    monkeypatch.setattr(
        "src.domains.agents.context.store.get_tool_context_store", _store, raising=True
    )


class TestToolTimeIsCharged:
    async def test_a_successful_call_charges_its_seconds(self) -> None:
        _register_tool("budget_probe_ok")

        result = await react_nodes.react_execute_tools_node(
            _state(["budget_probe_ok"], [_call("budget_probe_ok", "c1")]), {}
        )

        assert result["react_tool_seconds"] >= _SLEEP_SECONDS

    async def test_a_failing_call_still_charges_its_seconds(self) -> None:
        """The time was spent whether or not the call produced anything — the
        accumulator sits outside the try so no branch can forget it."""
        _register_tool("budget_probe_fail", fail=True)

        result = await react_nodes.react_execute_tools_node(
            _state(["budget_probe_fail"], [_call("budget_probe_fail", "c2")]), {}
        )

        assert result["react_tool_seconds"] >= _SLEEP_SECONDS

    async def test_seconds_accumulate_across_the_turn(self) -> None:
        """The budget bounds the WHOLE turn, not one node execution."""
        _register_tool("budget_probe_ok")

        result = await react_nodes.react_execute_tools_node(
            _state(
                ["budget_probe_ok"],
                [_call("budget_probe_ok", "c3")],
                react_tool_seconds=12.0,
            ),
            {},
        )

        assert result["react_tool_seconds"] >= 12.0 + _SLEEP_SECONDS

    async def test_several_calls_in_one_iteration_are_summed(self) -> None:
        _register_tool("budget_probe_ok")

        result = await react_nodes.react_execute_tools_node(
            _state(
                ["budget_probe_ok"],
                [_call("budget_probe_ok", "c4"), _call("budget_probe_ok", "c5")],
            ),
            {},
        )

        assert result["react_tool_seconds"] >= 2 * _SLEEP_SECONDS


class TestNothingSpentChargesNothing:
    async def test_an_unresolved_call_does_not_charge_time(self) -> None:
        """It also must not silently overwrite the turn's accumulated total."""
        result = await react_nodes.react_execute_tools_node(
            _state([], [_call("totally_invented_tool_xyz", "c6")]), {}
        )

        assert "react_tool_seconds" not in result

    async def test_an_unresolved_call_is_counted_by_reason(self) -> None:
        from src.infrastructure.observability.metrics_react import (
            react_unknown_tool_calls_total,
        )

        before = react_unknown_tool_calls_total.labels(reason="unknown")._value.get()

        await react_nodes.react_execute_tools_node(
            _state([], [_call("totally_invented_tool_xyz", "c7")]), {}
        )

        assert react_unknown_tool_calls_total.labels(reason="unknown")._value.get() == before + 1

    async def test_a_dropped_tool_is_counted_as_not_selected(self) -> None:
        """It exists in the registry but this turn did not bind it — the cap or
        the per-request filtering dropped it, which needs the opposite fix."""
        from src.infrastructure.observability.metrics_react import (
            react_unknown_tool_calls_total,
        )

        _register_tool("budget_probe_dropped")
        before = react_unknown_tool_calls_total.labels(reason="not_selected")._value.get()

        await react_nodes.react_execute_tools_node(
            _state([], [_call("budget_probe_dropped", "c8")]), {}
        )

        assert (
            react_unknown_tool_calls_total.labels(reason="not_selected")._value.get() == before + 1
        )


class TestTheTimeoutIsApplied:
    async def test_a_tool_that_overruns_is_stopped_and_reported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The pipeline bounds every family; ReAct bounded none (ADR-256)."""
        _register_tool("budget_probe_slow", delay=5.0)
        monkeypatch.setattr(
            "src.domains.agents.nodes.react_nodes.compute_step_timeout",
            lambda name, requested: 0.05,
            raising=True,
        )

        result = await react_nodes.react_execute_tools_node(
            _state(["budget_probe_slow"], [_call("budget_probe_slow", "c9")]), {}
        )

        message = result["messages"][0]
        assert "execution budget" in message.content
        # Recoverable: the loop keeps the turn and the model can choose another
        # route, exactly as a pipeline step timeout yields a failed StepResult.
        assert result["react_tool_seconds"] > 0


class TestTheTimeoutWrapperDoesNotSwallowSideChannels:
    """ADR-256 wraps every tool call in ``asyncio.wait_for``.

    A wrapper that ran the coroutine in a SEPARATE task would copy the context
    instead of sharing it, and every ContextVar an tool writes would be lost to
    the node — silently. ADR-249 depends on exactly that channel: the sandboxed
    scripts and the run budget are drained from ContextVars AFTER the loop, and
    they would have vanished from the admin debug panel with no error anywhere.

    Python 3.14's ``wait_for`` delegates to ``asyncio.timeouts.timeout`` and
    awaits in place, so the context IS shared. This pins that behaviour against
    a future runtime or refactor that changes it.
    """

    async def test_a_context_var_written_by_a_tool_reaches_the_node(self) -> None:
        from src.domains.agents.tools import python_sandbox_tools as sandbox

        sandbox.reset_turn_budget()
        script = {"purpose": "probe", "code": "1+1", "success": True, "output_head": "2"}

        def _register() -> None:
            from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

            if get_tool("budget_probe_ctxvar") is not None:
                return

            async def _fn() -> dict[str, Any]:
                await asyncio.sleep(0.01)
                sandbox._turn_scripts.set([script])
                sandbox._runs_this_turn.set(1)
                return {"success": True, "data": "ok"}

            register_external_tool(
                StructuredTool.from_function(
                    coroutine=_fn, name="budget_probe_ctxvar", description="d"
                )
            )

        _register()

        result = await react_nodes.react_execute_tools_node(
            _state(["budget_probe_ctxvar"], [_call("budget_probe_ctxvar", "cv1")]), {}
        )

        assert result["react_scripts"] == [
            script
        ], "the sandbox side-channel did not survive the timeout wrapper"
        assert result["react_script_runs"] == 1
