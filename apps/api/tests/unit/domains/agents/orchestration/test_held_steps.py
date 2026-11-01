"""A step needing a pending act waits for the person's answer (spec D7, amended 2026-10-30).

Measured 2026-10-29 (probe « dependents »): a step whose parameters read the
result of a step awaiting the person's approval ran on the draft's preview — or
the plan logged a dependency DEADLOCK. Such a step is now HELD: excluded from the
waves, never run on a placeholder, never reported failed, resumed once its
blockers are confirmed.

Measured 2026-10-30 on Docker dev (full turn): « supprime la note n2, puis
montre-moi la liste à jour » was planned ``list → delete → list`` with the second
read ORDERED after the deletion (``depends_on``) without reading its result. It
ran at once, on the notes before the act, and after « oui » the answer showed the
card alone. A step the planner explicitly orders after a pending act now waits for
the DECISION too; reading no placeholder, it then runs whatever the answer was.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.orchestration.held_steps import (
    held_by_order_only,
    held_steps,
    told_after_the_answer,
)
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

pytestmark = [pytest.mark.unit]


def _step(step_id: str, **fields: Any) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=fields.pop("step_type", StepType.TOOL),
        agent_name="probe_agent",
        tool_name=fields.pop("tool_name", "probe_notify_tool"),
        **fields,
    )


def _plan(*steps: ExecutionStep, mode: str = "parallel") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-held",
        user_id="u",
        session_id="s",
        steps=list(steps),
        execution_mode=mode,
    )


class TestWhatWaits:
    def test_a_data_reference_and_an_explicit_order_both_hold(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool", parameters={"note_id": "n-42"}),
            _step("s2", parameters={"text": "$steps.s1.deleted_id"}),
            _step("s3", parameters={"text": "done"}, depends_on=["s1"]),
            _step("s4", parameters={"text": "$steps.s2.sent"}),
            _step("s5", parameters={"text": "{{ steps.s1.deleted_id }}"}),
        )

        assert held_steps(plan, {"s1": ["d1"]}) == {
            "s2": ["d1"],
            "s3": ["d1"],
            "s4": ["d1"],
            "s5": ["d1"],
        }
        assert held_by_order_only(plan, {"s1": ["d1"]}) == {"s3"}

    def test_reading_again_after_a_pending_act_waits_for_the_decision(self) -> None:
        """The measured shape: the re-read reads nothing of the act, it comes AFTER it."""
        plan = _plan(
            _step("s1", tool_name="probe_list_notes_tool"),
            _step("s2", tool_name="probe_delete_note_tool", depends_on=["s1"]),
            _step("s3", tool_name="probe_list_notes_tool", depends_on=["s2"]),
        )

        assert held_steps(plan, {"s2": ["d1"]}) == {"s3": ["d1"]}
        assert held_by_order_only(plan, {"s2": ["d1"]}) == {"s3"}

    def test_the_order_class_follows_what_the_step_waits_on(self) -> None:
        """After an order-held step, still order; after a data-held one, data."""
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", parameters={"text": "listed"}, depends_on=["s1"]),
            _step("s3", parameters={"text": "$steps.s2.notes"}),
            _step("s4", parameters={"text": "$steps.s1.deleted_id"}),
            _step("s5", parameters={"text": "after"}, depends_on=["s4"]),
            _step("s6", parameters={"a": "$steps.s2.notes", "b": "$steps.s4.sent"}),
        )

        held = held_steps(plan, {"s1": ["d1"]})

        assert set(held) == {"s2", "s3", "s4", "s5", "s6"}
        assert held_by_order_only(plan, {"s1": ["d1"]}) == {"s2", "s3"}

    def test_nothing_pending_orders_nothing(self) -> None:
        plan = _plan(_step("s1"), _step("s2", depends_on=["s1"]))

        assert held_by_order_only(plan, {}) == set()

    def test_a_step_ordered_after_a_held_step_waits_with_it(self) -> None:
        """It cannot run before the step it follows, which runs only on the resume."""
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", parameters={"text": "$steps.s1.deleted_id"}),
            _step("s3", parameters={"text": "then"}, depends_on=["s2"]),
        )

        assert held_steps(plan, {"s1": ["d1"]}) == {"s2": ["d1"], "s3": ["d1"]}

    def test_sequential_chaining_after_a_pending_step_runs(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", parameters={"text": "next in the list"}),
            mode="sequential",
        )

        assert held_steps(plan, {"s1": ["d1"]}) == {}

    def test_a_for_each_over_a_pending_result_waits(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", parameters={"text": "$item.title"}, for_each="$steps.s1.notes"),
        )

        assert held_steps(plan, {"s1": ["d1"]}) == {"s2": ["d1"]}

    def test_a_condition_on_a_pending_result_waits(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step(
                "c1",
                step_type=StepType.CONDITIONAL,
                tool_name=None,
                condition="$steps.s1.deleted_id != ''",
                on_success="s3",
            ),
            _step("s3", parameters={"text": "ok"}),
        )

        held = held_steps(plan, {"s1": ["d1"]})

        assert held["c1"] == ["d1"]
        assert held["s3"] == ["d1"], "a branch runs only once its condition did"

    def test_every_blocker_is_named_once(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", tool_name="probe_delete_note_tool"),
            _step("s3", parameters={"a": "$steps.s1.x", "b": "$steps.s2.y"}),
            _step("s4", parameters={"text": "$steps.s3.z"}),
        )

        held = held_steps(plan, {"s1": ["d1"], "s2": ["d2", "d3"]})

        assert held == {"s3": ["d1", "d2", "d3"], "s4": ["d1", "d2", "d3"]}

    def test_nothing_pending_holds_nothing(self) -> None:
        plan = _plan(_step("s1"), _step("s2", parameters={"text": "$steps.s1.x"}))

        assert held_steps(plan, {}) == {}

    def test_a_step_named_like_an_item_is_no_item(self) -> None:
        """``get_item_details`` is a plain step: its draft is never its « parent's »."""
        plan = _plan(
            _step("get", parameters={"text": "x"}),
            _step("get_item_details", tool_name="probe_delete_note_tool"),
            _step("tell", parameters={"text": "$steps.get.x"}),
        )

        assert held_steps(plan, {"get_item_details": ["d1"]}) == {}


class TestWhatTheAnswerTells:
    """Spec D5 (2026-10-30): the work done BESIDE a pending act, for the answer to tell.

    Measured on Docker dev: « archive la note n3 et supprime la note n2 » archived
    n3 before the card, and after « non » the answer was « OK, c'est annulé » —
    the archiving was never told. What the act reads or follows served the act
    alone: its card says it.
    """

    def test_work_beside_the_act_is_told(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_archive_note_tool"),
            _step("s2", tool_name="probe_delete_note_tool"),
        )

        assert told_after_the_answer(plan, {"s2": ["d1"]}, {"s1", "s2"}) == ["s1"]

    def test_what_an_act_reads_or_follows_is_not_told(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_list_notes_tool"),
            _step("s2", tool_name="probe_delete_note_tool", parameters={"id": "$steps.s1.id"}),
            _step("s3", tool_name="probe_list_notes_tool"),
            _step("s4", tool_name="probe_delete_note_tool", depends_on=["s3"]),
            _step("s0", tool_name="probe_list_notes_tool"),
            _step("s5", parameters={"text": "$steps.s0.x"}, depends_on=["s1"]),
        )

        ran = {step.step_id for step in plan.steps}

        assert told_after_the_answer(plan, {"s2": ["d1"], "s4": ["d2"]}, ran) == [
            "s0",
            "s5",
        ], "what the acts read or follow is theirs; a step merely beside them is not"

    def test_a_for_each_act_is_its_own_step(self) -> None:
        plan = _plan(
            _step("list", tool_name="probe_list_notes_tool"),
            _step("drop", tool_name="probe_delete_note_tool", for_each="$steps.list.notes"),
            _step("tell", parameters={"text": "beside"}),
        )

        told = told_after_the_answer(
            plan, {"drop_item_0": ["d1"]}, {"list", "drop_item_0", "drop", "tell"}
        )

        assert told == ["tell"]

    def test_a_step_that_did_not_run_is_not_told(self) -> None:
        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool"),
            _step("s2", parameters={"text": "$steps.s1.deleted_id"}),
        )

        assert told_after_the_answer(plan, {"s1": ["d1"]}, {"s1"}) == []

    def test_nothing_pending_tells_nothing(self) -> None:
        plan = _plan(_step("s1"), _step("s2"))

        assert told_after_the_answer(plan, {}, {"s1", "s2"}) == []


# ---------------------------------------------------------------------------
# On the real executor
# ---------------------------------------------------------------------------

RECEIVED: list[dict[str, Any]] = []
PERFORMED: list[str] = []


class _SilentLedger:
    async def claim(self, request: Any) -> Any:
        return None

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, request: Any, *, error_code: str) -> None:
        return None


@pytest.fixture
def probe_tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A confirm tool and a read tool, registered for real (the probe's own pair)."""
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        ParameterSchema,
        PermissionProfile,
        ToolManifest,
    )
    from src.domains.agents.tools import tool_registry

    # A registry of this test's own: the probe tools of another module share these names.
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)

    RECEIVED.clear()
    PERFORMED.clear()
    gate_runtime.reset_policy_cache()

    async def _delete(note_id: str) -> dict[str, Any]:
        PERFORMED.append(note_id)
        return {"success": True, "data": {"deleted_id": note_id}}

    async def _notify(text: str = "") -> dict[str, Any]:
        RECEIVED.append({"text": text})
        return {"success": True, "data": {"sent": True}}

    params = {"probe_delete_note_tool": "note_id", "probe_notify_tool": "text"}
    for name, fn in (("probe_delete_note_tool", _delete), ("probe_notify_tool", _notify)):
        tool_registry.register_external_tool(
            StructuredTool.from_function(coroutine=fn, name=name, description=name)
        )
        get_global_registry().register_tool_manifest(
            ToolManifest(
                name=name,
                agent="probe_agent",
                description=name,
                parameters=[
                    ParameterSchema(
                        name=params[name], type="string", required=True, description="p"
                    )
                ],
                outputs=[],
                cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
                permissions=PermissionProfile(required_scopes=[]),
                mutation_policy="confirm" if name == "probe_delete_note_tool" else "read",
            ),
            override=True,
        )
    sink = AsyncMock()
    with (
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=uuid.uuid4(),
                thread_id="thread-held",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        patch.object(gate_runtime, "_LEDGER", _SilentLedger()),
        patch(
            "src.domains.agents.context.store.get_tool_context_store",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.orchestration.parallel_executor._load_execution_contexts",
            new=AsyncMock(return_value={}),
        ),
        treatment_collector(run_id="held"),
    ):
        yield
    gate_runtime.reset_policy_cache()


_CONFIG: RunnableConfig = {
    "configurable": {"thread_id": "thread-held"},
    "metadata": {"run_id": "run-held"},
}


class TestOnTheRealExecutor:
    async def test_held_step_never_runs_on_a_placeholder(self, probe_tools: None) -> None:
        from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

        plan = _plan(
            _step("s1", tool_name="probe_delete_note_tool", parameters={"note_id": "n-42"}),
            _step("s2", parameters={"text": "$steps.s1.deleted_id"}, depends_on=["s1"]),
            _step("s3", parameters={"text": "independent"}),
        )
        with patch("src.domains.agents.orchestration.parallel_executor.logger") as log:
            outcome = await execute_plan_parallel(plan, _CONFIG, "run-held")

        assert PERFORMED == [], "the delete waits for the person"
        assert RECEIVED == [{"text": "independent"}], "s2 never ran on a placeholder"
        assert "s2" not in outcome.completed_steps, "neither run nor failed"
        assert outcome.held_steps == {"s2": [outcome.pending_drafts[0].draft_id]}
        deadlocks = [
            c for c in log.error.call_args_list if c.args[:1] == ("parallel_execution_deadlock",)
        ]
        assert deadlocks == [], "a held step is not a deadlock"

    async def test_held_step_inside_an_expanded_for_each_branch(self, probe_tools: None) -> None:
        """A FOR_EACH child reading its drafted parent waits under its EXPANDED id."""
        from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

        async def _list(text: str = "") -> dict[str, Any]:
            return {"success": True, "data": {"notes": [{"id": "n1"}, {"id": "n2"}]}}

        from src.domains.agents.registry import get_global_registry
        from src.domains.agents.registry.catalogue import (
            CostProfile,
            PermissionProfile,
            ToolManifest,
        )
        from src.domains.agents.tools import tool_registry

        tool_registry.register_external_tool(
            StructuredTool.from_function(
                coroutine=_list, name="probe_list_notes_tool", description="l"
            )
        )
        get_global_registry().register_tool_manifest(
            ToolManifest(
                name="probe_list_notes_tool",
                agent="probe_agent",
                description="l",
                parameters=[],
                outputs=[],
                cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
                permissions=PermissionProfile(required_scopes=[]),
                mutation_policy="read",
            ),
            override=True,
        )
        plan = _plan(
            _step("list", tool_name="probe_list_notes_tool"),
            _step(
                "drop",
                tool_name="probe_delete_note_tool",
                parameters={"note_id": "$item.id"},
                for_each="$steps.list.notes",
                depends_on=["list"],
            ),
            _step("tell", parameters={"text": "$steps.drop.deleted_id"}),
        )

        outcome = await execute_plan_parallel(plan, _CONFIG, "run-held")

        assert PERFORMED == []
        assert len(outcome.pending_drafts) == 2, "one question per item"
        assert "tell" in outcome.held_steps, "the step reading the drafted items waits"
        assert RECEIVED == []
