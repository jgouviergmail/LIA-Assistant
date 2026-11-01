"""After the person's answers, the plan resumes with the REAL results (spec D7).

A step that read a result awaiting approval waited (``test_held_steps``). Once
the confirmation sequence settles, the graph comes back to the orchestrator: the
confirmed drafts are executed once, their real results become their steps'
results, and the waiting steps run on them — never on a placeholder. A refused
or failed blocker leaves its waiting steps unrun, and says so.
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
from src.domains.agents.nodes.draft_sequence import decision_entry
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType
from src.domains.agents.orchestration.tool_data_projection import without_tool_data
from src.domains.agents.services.runtime_failure_directive import held_not_run_block
from src.domains.agents.tools.output import UnifiedToolOutput

pytestmark = [pytest.mark.unit]

PERFORMED: list[tuple[str, str]] = []
RECEIVED: list[str] = []
FAIL_ON_REPLAY: set[str] = set()


class _WinningLedger:
    def __init__(self) -> None:
        self.keys: list[str] = []

    async def claim(self, request: Any) -> Any:
        if request.idempotency_key in self.keys:
            return gate_runtime.ClaimTicket(
                effect_id=uuid.uuid4(),
                claim_token=None,
                served_result={"success": True, "data": {"served": True}},
            )
        self.keys.append(request.idempotency_key)
        return gate_runtime.ClaimTicket(
            effect_id=uuid.uuid4(), claim_token=uuid.uuid4(), served_result=None
        )

    async def close(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def abandon(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def refuse(self, *args: Any, **kwargs: Any) -> None:
        return None


def _register(name: str, coroutine: Any, parameter: str, policy: str) -> None:
    from src.domains.agents.registry import get_global_registry
    from src.domains.agents.registry.catalogue import (
        CostProfile,
        ParameterSchema,
        PermissionProfile,
        ToolManifest,
    )
    from src.domains.agents.tools import tool_registry

    tool_registry.register_external_tool(
        StructuredTool.from_function(coroutine=coroutine, name=name, description=name)
    )
    get_global_registry().register_tool_manifest(
        ToolManifest(
            name=name,
            agent="probe_agent",
            description=name,
            parameters=[
                ParameterSchema(name=parameter, type="string", required=True, description="p")
            ],
            outputs=[],
            cost=CostProfile(est_tokens_in=10, est_tokens_out=10),
            permissions=PermissionProfile(required_scopes=[]),
            mutation_policy=policy,  # type: ignore[arg-type]
        ),
        override=True,
    )


async def _delete(note_id: str) -> Any:
    if note_id in FAIL_ON_REPLAY:
        return {"success": False, "error": "The server refused", "error_code": "EXTERNAL_API_ERROR"}
    PERFORMED.append(("delete", note_id))
    return {"success": True, "data": {"deleted_id": note_id}}


async def _archive(note_id: str) -> Any:
    """An MCP-like answer: a UnifiedToolOutput, not a dict."""
    PERFORMED.append(("archive", note_id))
    return UnifiedToolOutput.data_success(
        message=f"archived {note_id}", structured_data={"archived_id": f"{note_id}-archived"}
    )


async def _notify(text: str = "") -> Any:
    RECEIVED.append(text)
    return {"success": True, "data": {"sent": True}}


async def _create_task(title: str) -> Any:
    """A tool that builds its OWN draft (a native one): its card says the act."""
    from src.domains.agents.drafts.models import DraftType
    from src.domains.agents.drafts.service import DraftService

    return DraftService().create_draft(
        DraftType.TASK, content={"title": title}, source_tool="probe_create_task_tool"
    )


@pytest.fixture(autouse=True)
def _turn(monkeypatch: pytest.MonkeyPatch) -> Iterator[_WinningLedger]:
    from src.domains.agents.tools import tool_registry

    # A registry of this test's own: the probe tools of another module share these names.
    monkeypatch.setattr(tool_registry, "_TOOL_REGISTRY", {})
    monkeypatch.setattr(tool_registry, "_INITIALIZED", True)
    PERFORMED.clear()
    RECEIVED.clear()
    FAIL_ON_REPLAY.clear()
    gate_runtime.reset_policy_cache()
    _register("probe_delete_note_tool", _delete, "note_id", "confirm")
    _register("probe_archive_note_tool", _archive, "note_id", "confirm")
    _register("probe_notify_tool", _notify, "text", "read")
    _register("probe_create_task_tool", _create_task, "title", "draft")
    ledger = _WinningLedger()
    sink = AsyncMock()
    run = SimpleNamespace(
        user_id=uuid.uuid4(),
        thread_id="thread-resume",
        execution_mode="pipeline",
        is_automated_source=False,
        deps=object(),
        side_channel_queue=None,
    )
    with (
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=run,
        ),
        patch(
            "src.domains.agents.services.draft_executor.runtime_context_if_running",
            return_value=run,
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        patch.object(gate_runtime, "_LEDGER", ledger),
        patch(
            "src.domains.agents.context.store.get_tool_context_store",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.domains.agents.orchestration.parallel_executor._load_execution_contexts",
            new=AsyncMock(return_value={}),
        ),
        treatment_collector(run_id="resume"),
    ):
        yield ledger
    gate_runtime.reset_policy_cache()


_CONFIG: RunnableConfig = {
    "configurable": {"thread_id": "thread-resume"},
    "metadata": {"run_id": "run-resume"},
}


def _step(step_id: str, tool: str, **parameters: Any) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="probe_agent",
        tool_name=tool,
        parameters=parameters,
    )


def _after(step_id: str, tool: str, after: list[str], **parameters: Any) -> ExecutionStep:
    """A step the planner ORDERED after others, reading none of their results."""
    return _step(step_id, tool, **parameters).model_copy(update={"depends_on": after})


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="plan-resume",
        user_id="u",
        session_id="s",
        steps=list(steps),
        execution_mode="parallel",
    )


async def _first_pass(plan: ExecutionPlan) -> dict[str, Any]:
    """The orchestrator's first pass, as the state carries it into the resume."""
    from src.domains.agents.nodes.plan_resume import held_plan_of
    from src.domains.agents.orchestration.parallel_executor import execute_plan_parallel

    outcome = await execute_plan_parallel(plan, _CONFIG, "run-resume", turn_id=3)
    return {
        "execution_plan": plan,
        "completed_steps": without_tool_data(outcome.completed_steps),
        "held_plan": held_plan_of(plan, outcome, previous=None),
        "pending_drafts": [draft.model_dump() for draft in outcome.pending_drafts],
        "current_turn_id": 3,
        "user_language": "en",
        "registry": dict(outcome.registry),
        "agent_results": {},
        "messages": [],
    }


def _decide(state: dict[str, Any], *actions: str) -> dict[str, Any]:
    """What the confirmation sequence settles: one decision, or a batch."""
    entries = [
        decision_entry(draft, action)
        for draft, action in zip(state["pending_drafts"], actions, strict=True)
    ]
    decision = entries[0] if len(entries) == 1 else {"action": "confirm_batch", "batch": entries}
    return {**state, "draft_action_result": decision}


def _due(state: dict[str, Any]) -> bool:
    from src.domains.agents.nodes.plan_resume import resume_due

    return resume_due(state)  # type: ignore[arg-type]


async def _resume(state: dict[str, Any]) -> dict[str, Any]:
    from src.domains.agents.nodes.plan_resume import resume_held_steps

    update: dict[str, Any] = await resume_held_steps(state, _CONFIG, "run-resume")  # type: ignore[arg-type]
    return update


class TestAConfirmedBlockerResumesThePlan:
    @pytest.mark.parametrize("reference", ["$steps.s1.deleted_id", "{{ steps.s1.deleted_id }}"])
    async def test_confirmed_blocker_resumes_with_the_real_result(self, reference: str) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-42"),
            _step("s2", "probe_notify_tool", text=reference),
        )
        state = await _first_pass(plan)
        assert PERFORMED == [] and RECEIVED == [], "nothing before the answer"

        update = await _resume(_decide(state, "confirm"))

        assert PERFORMED == [("delete", "n-42")], "the confirmed act ran once"
        assert RECEIVED == ["n-42"], "the waiting step read the REAL result"
        assert update["draft_action_result"] is None, "the response executes nothing again"
        assert list(update["executed_drafts"]) == [state["pending_drafts"][0]["draft_id"]]
        assert update["held_plan"]["resumed"] == ["s2"]
        assert update["held_plan"]["held"] == {}

    async def test_a_tool_answering_with_a_model_feeds_the_waiting_step(self) -> None:
        """An MCP-like answer is projected like a step's own call (Task 3's projection)."""
        plan = _plan(
            _step("s1", "probe_archive_note_tool", note_id="n-7"),
            _step("s2", "probe_notify_tool", text="$steps.s1.archived_id"),
        )
        state = await _first_pass(plan)

        await _resume(_decide(state, "confirm"))

        assert PERFORMED == [("archive", "n-7")]
        assert RECEIVED == ["n-7-archived"]


class TestARefusedOrFailedBlockerIsSaid:
    async def test_refused_or_failed_blocker_leaves_the_step_unrun_and_said(self) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-1"),
            _step("s2", "probe_notify_tool", text="$steps.s1.deleted_id"),
            _step("s3", "probe_delete_note_tool", note_id="n-2"),
            _step("s4", "probe_notify_tool", text="$steps.s3.deleted_id"),
        )
        FAIL_ON_REPLAY.add("n-2")
        state = await _first_pass(plan)

        update = await _resume(_decide(state, "cancel", "confirm"))

        assert RECEIVED == [], "neither waiting step ran"
        assert update["held_plan"]["not_run"] == {"s2": "refused", "s4": "failed"}
        assert update["held_plan"]["resumed"] == []
        assert PERFORMED == [], "the refused act never ran; the failed one did not happen"
        block = held_not_run_block({**state, **update})
        assert "- probe_notify_tool: refused" in block, "the answer names what was not done"
        assert "- probe_notify_tool: failed" in block


class TestAStepOrderedAfterAnActRunsOnTheDecision:
    """Spec D7, amended 2026-10-30: it waits for the answer, then runs whatever it was."""

    async def test_it_runs_after_the_act_once_confirmed(self) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-1"),
            _after("s2", "probe_notify_tool", ["s1"], text="listed after"),
        )
        state = await _first_pass(plan)
        assert RECEIVED == [], "it waited for the answer"
        assert state["held_plan"]["ordered"] == ["s2"]

        update = await _resume(_decide(state, "confirm"))

        assert PERFORMED == [("delete", "n-1")]
        assert RECEIVED == ["listed after"], "it ran AFTER the act"
        assert update["held_plan"]["resumed"] == ["s2"]
        assert update["held_plan"]["not_run"] == {}

    @pytest.mark.parametrize("failing", [False, True], ids=["refused", "failed"])
    async def test_it_runs_after_a_refused_or_failed_act_too(self, failing: bool) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-1"),
            _after("s2", "probe_notify_tool", ["s1"], text="listed after"),
        )
        if failing:
            FAIL_ON_REPLAY.add("n-1")
        state = await _first_pass(plan)

        update = await _resume(_decide(state, "confirm" if failing else "cancel"))

        assert PERFORMED == []
        assert RECEIVED == ["listed after"], "nothing it reads was missing: it ran"
        assert update["held_plan"]["resumed"] == ["s2"]
        assert update["held_plan"]["not_run"] == {}

    def test_it_keeps_waiting_while_the_approved_act_waits(self) -> None:
        from src.domains.agents.nodes.plan_resume import WAITING, _unrunnable

        records = {"d1": {"status": "waiting"}}

        assert _unrunnable({"s2": ["d1"]}, records, ordered={"s2"}) == {"s2": WAITING}

    @pytest.mark.parametrize("status", ["success", "cancelled", "error", None])
    def test_it_is_never_refused_nor_failed(self, status: str | None) -> None:
        from src.domains.agents.nodes.plan_resume import _unrunnable

        records = {"d1": {"status": status}} if status else {}

        assert _unrunnable({"s2": ["d1"]}, records, ordered={"s2"}) == {}


class TestWorkBesideTheActIsToldAfterTheAnswer:
    """Spec D5 (2026-10-30): the decision comes back to the plan when work ran beside it."""

    async def test_the_first_pass_keeps_what_to_tell(self) -> None:
        plan = _plan(
            _step("s1", "probe_notify_tool", text="beside"),
            _step("s2", "probe_delete_note_tool", note_id="n-1"),
        )
        state = await _first_pass(plan)

        assert RECEIVED == ["beside"], "the work ran before the card"
        assert state["held_plan"]["told"] == ["s1"]
        assert state["held_plan"]["held"] == {}
        assert _due(_decide(state, "confirm"))

    @pytest.mark.parametrize("action", ["confirm", "cancel"])
    async def test_the_answer_reads_it_after_either_decision(self, action: str) -> None:
        plan = _plan(
            _step("s1", "probe_notify_tool", text="beside"),
            _step("s2", "probe_delete_note_tool", note_id="n-1"),
        )
        state = await _first_pass(plan)

        update = await _resume(_decide(state, action))

        assert RECEIVED == ["beside"], "nothing ran twice"
        assert PERFORMED == ([("delete", "n-1")] if action == "confirm" else [])
        assert update["held_plan"]["told"] == ["s1"], "the answer tells it"
        assert len(update["executed_drafts"]) == 1, "the decision is the answer's account"
        assert update["draft_action_result"] is None

    async def test_work_told_again_is_never_counted_again(self) -> None:
        """The first pass counted its steps' failures; a resume counts what IT ran only."""
        plan = _plan(
            _step("s1", "probe_notify_tool", text="beside"),
            _step("s2", "probe_delete_note_tool", note_id="n-1"),
        )
        state = await _first_pass(plan)

        with patch(
            "src.domains.agents.nodes.execution_state.record_pipeline_step_failures"
        ) as counted:
            await _resume(_decide(state, "confirm"))

        (steps,) = counted.call_args.args
        assert steps == {}, "nothing ran in this resume: nothing new to count"

    async def test_a_lookup_alone_keeps_the_card(self) -> None:
        plan = _plan(
            _step("s1", "probe_notify_tool", text="find"),
            _step("s2", "probe_create_task_tool", title="$steps.s1.sent"),
        )
        state = await _first_pass(plan)

        assert state["pending_drafts"][0]["draft_type"] == "task", "a native draft"
        assert state["held_plan"] is None, "the card says the act; nothing else to tell"
        assert not _due(_decide(state, "confirm"))


def _summary(update: dict[str, Any]) -> str:
    """What the response model reads of the steps the update reports."""
    from src.domains.agents.formatters.agent_results import format_agent_results_for_prompt

    return format_agent_results_for_prompt(
        update["agent_results"], current_turn_id=3, user_language="en"
    )


def _asks_for_an_answer(summary: str) -> bool:
    """Whether the summary still carries a draft awaiting the person's answer.

    A draft's summary ends on its « action required » line, written in the run's
    declared language (the probe tools pass none).
    """
    from src.core.i18n import resolve_language
    from src.core.i18n_drafts import get_draft_summary_label

    return get_draft_summary_label("action_required", resolve_language(None)) in summary


class TestAConfirmedToolCallIsAnsweredFromWhatItReturned:
    """Owner rule (2026-10-31): a validated act runs to its end, and the person gets its result.

    A tool call asked before it ran — a dedicated agent's task, a read under « always
    ask » — returns the very content the person asked for: its card alone (« Action
    executed ») dropped it, and an act a resumed step asked was reported « awaiting
    confirmation » after it ran (measured on dev, 2026-10-31).
    """

    async def test_a_tool_call_alone_comes_back_to_the_plan(self) -> None:
        plan = _plan(_step("s1", "probe_archive_note_tool", note_id="n-7"))
        state = await _first_pass(plan)
        assert PERFORMED == [], "asked before it ran"
        assert _due(_decide(state, "confirm")), "the decision comes back to the plan"

        update = await _resume(_decide(state, "confirm"))

        assert PERFORMED == [("archive", "n-7")], "the act ran once"
        assert update["held_plan"]["acted"] == ["s1"]
        assert "archived n-7" in _summary(update), "what the tool returned reaches the answer"

    async def test_an_act_a_resumed_step_asked_is_reported_done_never_pending(self) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-42"),
            _step("s2", "probe_archive_note_tool", note_id="$steps.s1.deleted_id"),
        )
        state = await _first_pass(plan)
        first = await _resume(_decide(state, "confirm"))
        assert _asks_for_an_answer(_summary(first)), "the resumed step asked"
        second_state = {**state, **first, "pending_drafts": [first["pending_draft_critique"]]}
        assert _due(_decide(second_state, "confirm")), "its answer comes back to the plan"

        second = await _resume(_decide(second_state, "confirm"))

        assert PERFORMED == [("delete", "n-42"), ("archive", "n-42")], "each act once"
        summary = _summary(second)
        assert "archived n-42" in summary
        assert not _asks_for_an_answer(summary), "a decided act is never reported pending"
        assert second["held_plan"]["acted"] == ["s1", "s2"], "both tool calls report"
        assert second["held_plan"]["resumed"] == [], "s2 stands on its act now"

    async def test_a_refused_act_a_resumed_step_asked_is_never_reported_pending(self) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-42"),
            _step("s2", "probe_create_task_tool", title="$steps.s1.deleted_id"),
        )
        state = await _first_pass(plan)
        first = await _resume(_decide(state, "confirm"))
        second_state = {**state, **first, "pending_drafts": [first["pending_draft_critique"]]}
        assert _due(_decide(second_state, "cancel"))

        second = await _resume(_decide(second_state, "cancel"))

        assert not _asks_for_an_answer(_summary(second)), "its account says it was refused"
        assert second["held_plan"]["acted"] == ["s1"], "a native act is said by its account"
        assert len(second["executed_drafts"]) == 2, "both decisions reach the answer"


class TestWhatEachDecisionRecordGivesItsStep:
    def test_a_native_draft_gives_its_step_its_result_data(self) -> None:
        """A native executor returns top-level fields (``event_id``), not a tool answer."""
        from src.domains.agents.nodes.plan_resume import _inject

        record = {
            "status": "success",
            "draft_id": "d1",
            "draft_type": "event",
            "data": {"event_id": "e-1", "html_link": "https://x", "_draft_content": {"a": 1}},
        }
        completed: dict[str, Any] = {"s1": {"draft_id": "d1"}}

        _inject(completed, {"s1": ["d1"]}, {"d1": record}, {})  # type: ignore[typeddict-item]

        assert completed["s1"] == {"event_id": "e-1", "html_link": "https://x"}

    def test_an_approved_act_still_waiting_is_said_waiting_never_failed(self) -> None:
        from src.domains.agents.nodes.plan_resume import WAITING, _unrunnable

        assert _unrunnable({"s2": ["d1"]}, {"d1": {"status": "waiting"}}) == {"s2": WAITING}


class TestTheResumeReadsTheRegistryAsTheFirstPassDoes:
    async def test_an_item_the_state_holds_as_an_object_still_resolves(self) -> None:
        """The state holds RegistryItem objects or dicts (``merge_registry``); the executor dicts."""
        from src.domains.agents.data_registry.models import (
            RegistryItem,
            RegistryItemMeta,
            RegistryItemType,
        )

        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-1"),
            _step("s2", "probe_notify_tool", text="$steps.s1.deleted_id"),
            ExecutionStep(
                step_id="s3",
                step_type=StepType.TOOL,
                agent_name="probe_agent",
                tool_name="probe_notify_tool",
                parameters={"text": "items[0].title"},
                depends_on=["s2"],
            ),
        )
        state = await _first_pass(plan)
        state["registry"] = {
            "note_abc": RegistryItem(
                id="note_abc",
                type=RegistryItemType.NOTE,
                payload={"title": "Groceries"},
                meta=RegistryItemMeta(source="probe"),
            )
        }

        await _resume(_decide(state, "confirm"))

        assert RECEIVED == ["n-1", "Groceries"]


class TestAResumeIsNoNewPlan:
    async def test_the_plan_metrics_count_the_plan_once(self) -> None:
        from src.infrastructure.observability.metrics_agents import (
            task_orchestrator_plans_created,
        )

        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-3"),
            _step("s2", "probe_notify_tool", text="$steps.s1.deleted_id"),
        )
        state = await _first_pass(plan)
        created = task_orchestrator_plans_created.labels(
            intention="execution_plan_phase5.2b_asyncio", agents_count="2"
        )
        before = created._value.get()

        await _resume(_decide(state, "confirm"))

        assert created._value.get() == before, "a resume runs the same plan"


class TestAnExecutorThatRaisesIsSaidNeverACrash:
    async def test_the_resume_degrades_like_the_response(self) -> None:
        """The executor raising leaves the waiting step unrun and said — the turn survives."""
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-9"),
            _step("s2", "probe_notify_tool", text="$steps.s1.deleted_id"),
        )
        state = await _first_pass(plan)
        draft_id = state["pending_drafts"][0]["draft_id"]

        with patch(
            "src.domains.agents.services.draft_executor.execute_draft_if_confirmed",
            new=AsyncMock(side_effect=RuntimeError("executor registry unavailable")),
        ):
            update = await _resume(_decide(state, "confirm"))

        assert RECEIVED == [] and PERFORMED == []
        assert update["held_plan"]["not_run"] == {"s2": "failed"}
        assert update["executed_drafts"][draft_id]["status"] == "error"
        assert "executor registry unavailable" not in str(update["executed_drafts"])


class TestEveryStepRunsOnce:
    async def test_new_drafts_in_a_resume_start_a_new_round_and_each_step_runs_once(
        self,
    ) -> None:
        plan = _plan(
            _step("s1", "probe_delete_note_tool", note_id="n-42"),
            _step("s2", "probe_archive_note_tool", note_id="$steps.s1.deleted_id"),
            _step("s3", "probe_notify_tool", text="$steps.s2.archived_id"),
        )
        state = await _first_pass(plan)
        assert state["held_plan"]["held"] == {
            "s2": [state["pending_drafts"][0]["draft_id"]],
            "s3": [state["pending_drafts"][0]["draft_id"]],
        }

        first = await _resume(_decide(state, "confirm"))
        assert PERFORMED == [("delete", "n-42")]
        assert RECEIVED == [], "s3 now waits for the second question"
        assert first["pending_draft_critique"]["tool_name"] == "probe_archive_note_tool"
        assert not first.get("pending_drafts_queue"), "one new question: s2's"
        assert first["held_plan"]["held"] == {"s3": [first["pending_draft_critique"]["draft_id"]]}
        second_state = {
            **state,
            **first,
            "pending_drafts": [first["pending_draft_critique"]],
        }

        second = await _resume(_decide(second_state, "confirm"))

        assert PERFORMED == [("delete", "n-42"), ("archive", "n-42")], "each act once"
        assert RECEIVED == ["n-42-archived"]
        assert second["held_plan"]["resumed"] == ["s3"], "s2 stands on its act now"
        assert second["held_plan"]["acted"] == ["s1", "s2"]
        assert set(second["executed_drafts"]) == {
            state["pending_drafts"][0]["draft_id"],
            first["pending_draft_critique"]["draft_id"],
        }


async def _list(text: str = "") -> Any:
    return {"success": True, "data": {"notes": [{"id": "n1"}, {"id": "n2"}]}}


async def _tidy(text: str = "") -> Any:
    """What an iterative MCP task hands up: its narrative and TWO queued confirmations."""
    from src.domains.agents.effects.confirmation import confirmation_draft
    from src.domains.agents.orchestration.step_results import drafts_of

    first = confirmation_draft("probe_delete_note_tool", {"note_id": "t-1"})
    second = confirmation_draft("probe_delete_note_tool", {"note_id": "t-2"})
    return UnifiedToolOutput.data_success(
        message="Tidied the notes.",
        registry_updates={**first.registry_updates, **second.registry_updates},
        metadata={
            "requires_confirmation": True,
            "pending_drafts": [
                *drafts_of(first, "probe_delete_note_tool", None),
                *drafts_of(second, "probe_delete_note_tool", None),
            ],
        },
    )


class TestWhatAStepReadsAfterTheAnswers:
    async def test_a_for_each_aggregate_is_rebuilt_from_the_real_results(self) -> None:
        """The waiting step reads the PARENT's aggregate: it must carry the acts, not drafts."""
        _register("probe_list_notes_tool", _list, "text", "read")
        plan = ExecutionPlan(
            plan_id="plan-resume",
            user_id="u",
            session_id="s",
            execution_mode="parallel",
            steps=[
                _step("list", "probe_list_notes_tool", text="all"),
                ExecutionStep(
                    step_id="drop",
                    step_type=StepType.TOOL,
                    agent_name="probe_agent",
                    tool_name="probe_delete_note_tool",
                    parameters={"note_id": "$item.id"},
                    for_each="$steps.list.notes",
                    depends_on=["list"],
                ),
                _step("tell", "probe_notify_tool", text="$steps.drop.deleted_id"),
            ],
        )
        state = await _first_pass(plan)
        assert "tell" in state["held_plan"]["held"]

        update = await _resume(_decide(state, "confirm", "confirm"))

        assert PERFORMED == [("delete", "n1"), ("delete", "n2")]
        assert RECEIVED == ["n2"], "the aggregate of the REAL results (last scalar wins)"
        assert not update.get("pending_draft_critique"), "no item is asked about again"
        assert update["held_plan"]["held"] == {}

    async def test_a_task_with_several_acts_states_their_outcome_to_its_readers(self) -> None:
        from src.core.prompt_store import parse_prompt_sections, read_prompt_file

        _register("probe_tidy_tool", _tidy, "text", "read")
        plan = _plan(
            _step("tidy", "probe_tidy_tool", text="tidy"),
            _step("tell", "probe_notify_tool", text="$steps.tidy.result"),
        )
        state = await _first_pass(plan)
        assert state["held_plan"]["held"] == {
            "tell": [draft["draft_id"] for draft in state["pending_drafts"]]
        }

        await _resume(_decide(state, "confirm", "confirm"))

        lines = dict(parse_prompt_sections(read_prompt_file("mcp_sub_loop_lines"), 2))
        settled = lines["record_settled"].format(
            actions=lines["record_repeated"].format(action="probe_delete_note_tool", count=2)
        )
        assert PERFORMED == [("delete", "t-1"), ("delete", "t-2")]
        assert RECEIVED == [f"Tidied the notes.\n{settled}"], "the reader learns what was done"
