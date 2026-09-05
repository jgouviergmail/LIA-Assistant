"""The gate is installed on the capability, not asked of its callers (ADR-263).

Measured 2026-09-03: the same tool is reached three different ways — the
pipeline executor and the ReAct loop both call ``tool.coroutine(**args)``
directly, the sub-agent runner goes through ``tool.ainvoke(...)`` — and a
fourth caller is one refactor away. A gate a caller must remember to invoke is
a gate that will be forgotten, and an AST guard over call sites goes stale the
day someone adds a call site it does not recognise.

So the gate is installed once, at REGISTRATION, on the coroutine itself. These
tests pin that it is installed in place (every reference sees it), that both
call paths go through it, and that nothing registered escapes it.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.tools import StructuredTool

from src.domains.agents.effects.runtime import EFFECT_GATED_ATTR
from src.domains.agents.tools import tool_registry

pytestmark = [pytest.mark.unit]


async def _plain(x: int = 1) -> dict[str, Any]:
    """A tool coroutine with no gate of its own."""
    return {"success": True, "data": {"x": x}}


def _tool(name: str) -> StructuredTool:
    return StructuredTool.from_function(coroutine=_plain, name=name, description="t")


class TestRegistrationInstallsTheGate:
    def test_an_externally_registered_tool_is_gated(self) -> None:
        tool = _tool("gate_probe_external_tool")
        assert not getattr(tool.coroutine, EFFECT_GATED_ATTR, False)

        tool_registry.register_external_tool(tool)

        assert getattr(tool.coroutine, EFFECT_GATED_ATTR, False) is True

    def test_the_instance_is_mutated_in_place_not_copied(self) -> None:
        """Modules hold their own references (``skills_tools``); a copy would leak."""
        tool = _tool("gate_probe_inplace_tool")
        kept_by_a_module = tool

        tool_registry.register_external_tool(tool)

        assert tool_registry.get_tool("gate_probe_inplace_tool") is kept_by_a_module
        assert getattr(kept_by_a_module.coroutine, EFFECT_GATED_ATTR, False) is True

    def test_registering_twice_does_not_nest_two_gates(self) -> None:
        tool = _tool("gate_probe_twice_tool")
        tool_registry.register_external_tool(tool)
        once = tool.coroutine
        tool_registry.register_external_tool(tool)
        assert tool.coroutine is once


class TestTheWholeRegistryIsGated:
    def test_every_registered_tool_carries_the_gate(self) -> None:
        """The property the boot assert checks, verified over the real catalogue."""
        tool_registry.ensure_tools_loaded()
        ungated = [
            name
            for name, tool in tool_registry.get_all_tools().items()
            if not getattr(getattr(tool, "coroutine", None), EFFECT_GATED_ATTR, False)
        ]
        assert not ungated, (
            f"{len(ungated)} registered tools bypass the effect gate: {ungated}. "
            "They were registered through a path that does not install it."
        )

    def test_the_registry_is_not_empty(self) -> None:
        """Anti-vacuity: an empty registry would make the check above meaningless."""
        tool_registry.ensure_tools_loaded()
        assert len(tool_registry.get_all_tools()) > 100


class TestTheExecutorExemptionIsHonouredAndBounded:
    """The one declared exemption, and the proof it is the only one.

    Found by the boot assert itself: it flagged ``tool_call`` — the executor
    whose effect is recorded by the tool it replays — because it did not know
    about the exemption its own registration declares. An exemption that only
    one of the two sides knows about is how a guard becomes a nuisance and
    then gets weakened.
    """

    def test_the_boot_assert_accepts_the_declared_exemption(self) -> None:
        from src.domains.agents.effects.runtime import assert_effect_gate_completeness
        from src.domains.agents.services.draft_executor_registry import (
            ensure_executors_registered,
        )
        from src.domains.agents.services.draft_executor_types import EXECUTOR_REGISTRY

        EXECUTOR_REGISTRY.clear()
        ensure_executors_registered()
        tool_registry.ensure_tools_loaded()

        assert_effect_gate_completeness()

    def test_every_other_executor_is_gated(self) -> None:
        from src.domains.agents.effects.runtime import EFFECT_GATED_ATTR
        from src.domains.agents.services.draft_executor_registry import (
            ensure_executors_registered,
        )
        from src.domains.agents.services.draft_executor_types import (
            EXECUTOR_REGISTRY,
            EXECUTORS_GATED_BY_THEIR_TOOL,
        )

        EXECUTOR_REGISTRY.clear()
        ensure_executors_registered()

        ungated = sorted(
            draft_type
            for draft_type, executor in EXECUTOR_REGISTRY.items()
            if not getattr(executor, EFFECT_GATED_ATTR, False)
        )
        assert ungated == sorted(EXECUTORS_GATED_BY_THEIR_TOOL)
        assert len(EXECUTOR_REGISTRY) > 15, "anti-vacuity: the registry must be populated"
