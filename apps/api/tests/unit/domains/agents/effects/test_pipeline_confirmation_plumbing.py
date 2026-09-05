"""The asked-for confirmation must actually REACH the user (ADR-263).

The gate hands an unconfirmed ``confirm`` call back as a draft. That is only
half a feature: between the gate and the card the user answers there are two
pieces of pre-existing plumbing that know nothing about ADR-263, and both fail
SILENTLY — no exception, no red test, just a turn where nothing happens.

  1. ``_execute_tool`` only builds a ``draft_info`` when the result is a
     ``StandardToolOutput | UnifiedToolOutput`` carrying the four keys it reads
     (``requires_confirmation``, ``draft_id``, ``draft_type`` and the payload
     under ``registry_updates[draft_id].payload["content"]``).
  2. ``_handle_execution_plan`` routes drafts by type, and its chain has a
     branch — ``tool_confirmation`` — pointing at ``pending_tool_confirmation``,
     a state key NOTHING produces (``DraftType`` has no such member). A future
     edit adding ``tool_call`` to that branch, or renaming the fall-through,
     would send our draft to a queue no card reads.

Everything else was verified by calling the gated coroutine directly, which
jumps over both. These tests exercise the real functions.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.tools import StructuredTool

from src.domains.agents.drafts.models import DraftType
from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo

pytestmark = [pytest.mark.unit]


class _SilentLedger:
    """Records nothing, refuses nothing — the ledger is not what is under test."""

    async def claim(self, request: Any) -> Any:
        return None

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        return None


@pytest.fixture(autouse=True)
def _attended_user() -> Any:
    """A live turn with a user who can answer — otherwise the gate refuses."""
    gate_runtime.reset_policy_cache()
    with patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=uuid.uuid4(),
            thread_id="thread-pipeline",
            execution_mode="pipeline",
            is_automated_source=False,
        ),
    ):
        yield


class TestTheExecutorTurnsTheGatesAnswerIntoADraft:
    """Layer 1: ``_execute_tool`` must recognise what the gate returns."""

    async def test_a_confirm_call_produces_a_tool_call_draft(self) -> None:
        from src.domains.agents.orchestration.parallel_executor import _execute_tool
        from src.domains.agents.tools import tool_registry

        performed: list[dict[str, Any]] = []

        async def _cancel(plan: str = "premium") -> dict[str, Any]:
            performed.append({"plan": plan})
            return {"success": True, "data": {"cancelled": True}}

        tool = StructuredTool.from_function(
            coroutine=_cancel, name="plumbing_probe_cancel_tool", description="p"
        )
        tool_registry.register_external_tool(tool)

        with (
            patch.object(gate_runtime, "_LEDGER", _SilentLedger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "confirm"),
        ):
            outcome = await _execute_tool(
                tool_name="plumbing_probe_cancel_tool",
                args={"plan": "premium"},
                config={"configurable": {"thread_id": "thread-pipeline", "run_id": "run-1"}},
                store=None,
                step_id="s1",
            )

        assert performed == [], "the effect must wait for the user's answer"
        assert outcome.draft_info is not None, (
            "the executor did not recognise the gate's answer as a draft — "
            "the confirmation would never reach a card"
        )
        assert outcome.draft_info["draft_type"] == DraftType.TOOL_CALL.value
        assert outcome.draft_info["draft_content"] == {
            "tool_name": "plumbing_probe_cancel_tool",
            "tool_label": "plumbing probe cancel",
            "tool_args": {"plan": "premium"},
        }
        # The id the card answers is the id the replay names.
        assert outcome.draft_info["draft_id"] in outcome.draft_info["registry_ids"]

    async def test_a_read_produces_no_draft(self) -> None:
        """Anti-vacuity: the detection above is not something every call trips."""
        from src.domains.agents.orchestration.parallel_executor import _execute_tool
        from src.domains.agents.tools import tool_registry

        async def _look(q: str = "x") -> dict[str, Any]:
            return {"success": True, "data": {"found": 0}}

        tool = StructuredTool.from_function(
            coroutine=_look, name="plumbing_probe_read_tool", description="p"
        )
        tool_registry.register_external_tool(tool)

        with (
            patch.object(gate_runtime, "_LEDGER", _SilentLedger()),
            patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
        ):
            outcome = await _execute_tool(
                tool_name="plumbing_probe_read_tool",
                args={"q": "x"},
                config={"configurable": {"thread_id": "thread-pipeline", "run_id": "run-1"}},
                store=None,
                step_id="s1",
            )

        assert outcome.draft_info is None


class TestTheDraftIsRoutedToTheCardTheUserAnswers:
    """Layer 2: ``_handle_execution_plan`` must not divert the new type."""

    @staticmethod
    def _plan() -> Any:
        from src.domains.agents.orchestration.plan_schemas import (
            ExecutionPlan,
            ExecutionStep,
            StepType,
        )

        return ExecutionPlan(
            plan_id="plan_tool_call_routing",
            user_id="u",
            session_id="s",
            steps=[
                ExecutionStep(
                    step_id="s1",
                    step_type=StepType.TOOL,
                    agent_name="a",
                    tool_name="plumbing_probe_cancel_tool",
                    parameters={},
                )
            ],
        )

    @staticmethod
    def _draft(draft_type: str) -> PendingDraftInfo:
        return PendingDraftInfo(
            draft_id="draft_1",
            draft_type=draft_type,
            draft_content={"tool_name": "t", "tool_args": {}},
            draft_summary="summary",
            registry_ids=["draft_1"],
            tool_name="plumbing_probe_cancel_tool",
            step_id="s1",
        )

    async def _route(self, draft: PendingDraftInfo) -> dict[str, Any]:
        from src.domains.agents.nodes.task_orchestrator_node import _handle_execution_plan
        from src.domains.agents.orchestration.parallel_executor import ParallelExecutionResult

        outcome = ParallelExecutionResult(
            completed_steps={"s1": {"success": True}},
            registry={},
            pending_draft=draft,
            pending_drafts=[draft],
        )
        with patch(
            "src.domains.agents.orchestration.parallel_executor.execute_plan_parallel",
            new=AsyncMock(return_value=outcome),
        ):
            return await _handle_execution_plan(
                execution_plan=self._plan(),
                state={"messages": []},  # type: ignore[arg-type]
                run_id="run-1",
                config={"configurable": {"thread_id": "thread-pipeline"}},
            )

    async def test_a_tool_call_draft_lands_in_the_draft_critique_card(self) -> None:
        result = await self._route(self._draft(DraftType.TOOL_CALL.value))

        assert result.get("pending_draft_critique") is not None, (
            "the tool_call draft was diverted — the card the user answers is "
            "fed by pending_draft_critique alone"
        )
        assert result["pending_draft_critique"]["draft_type"] == DraftType.TOOL_CALL.value
        assert "pending_tool_confirmation" not in result, (
            "pending_tool_confirmation is read by graph.py but produced by nothing; "
            "routing there would hang the turn on a card no node renders"
        )

    async def test_the_older_types_still_route_where_they_did(self) -> None:
        """No regression for the 25 draft-producing tools."""
        result = await self._route(self._draft(DraftType.EMAIL.value))

        assert result["pending_draft_critique"]["draft_type"] == DraftType.EMAIL.value

    async def test_disambiguation_is_still_diverted(self) -> None:
        """Anti-vacuity: the chain really does route by type."""
        result = await self._route(self._draft("entity_disambiguation"))

        assert result.get("pending_entity_disambiguation") is not None
        assert result.get("pending_draft_critique") is None
