"""SSE execution steps — the live trace the user watches while LIA works.

The "coulisses" panel is built from `execution_step` chunks emitted mid-stream.
Nothing downstream validates them: a step that is not emitted simply never
appears, a step emitted twice reads as the tool running twice, and a tool the
catalogue does not know must still show up rather than vanish.

Its tool steps come from ``tool_step_outcomes`` (2026-10-24: each step says
what it did):

* ``react_started_steps`` / ``react_finished_steps`` — a ReAct call starts with
  the AIMessage's ``tool_calls`` and finishes with its ToolMessage, both under
  the call's id, the read's counts on the finish.
* ``pipeline_steps`` — one step per tool of the executed plan, its calls added
  up, so a plan calling the same tool three times prints one line.
* ``tool_step`` — the catalogue lookup, with the fallback that keeps an
  unknown tool visible.

Plus the two small deciders that shape the stream: the routing-history
signature (which suppresses duplicate router decisions) and the context-usage
pill of the `done` chunk.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.core.field_names import FIELD_FOR_EACH_AGGREGATE, FIELD_FOR_EACH_FAILED_ITEMS
from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.orchestration.plan_schemas import ExecutionStep, StepType
from src.domains.agents.services.streaming.service import StreamingService
from src.domains.agents.services.streaming.tool_step_outcomes import (
    pipeline_steps,
    react_finished_steps,
    react_started_steps,
    tool_step,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def service() -> StreamingService:
    return StreamingService()


def ai_with_tool_calls(*tool_names: str) -> AIMessage:
    """An AIMessage shaped like a real ReAct tool-calling turn."""
    return AIMessage(
        content="",
        tool_calls=[
            {"name": name, "args": {}, "id": f"call_{index}"}
            for index, name in enumerate(tool_names)
        ],
    )


def plan_with_tools(*tool_names: str | None) -> SimpleNamespace:
    """An execution plan exposing `.steps[].tool_name` and `.step_id`, like ExecutionPlan."""
    return SimpleNamespace(
        steps=[
            SimpleNamespace(tool_name=name, step_id=f"step_{index}")
            for index, name in enumerate(tool_names)
        ],
    )


def for_each_step(step_id: str, tool_name: str) -> ExecutionStep:
    """A real FOR_EACH step, as the planner writes it (unexpanded)."""
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="some_agent",
        tool_name=tool_name,
        for_each="$steps.step_0.places",
    )


class TestToolStep:
    def test_a_catalogued_tool_gets_its_display_metadata(self) -> None:
        chunk = tool_step("get_contacts_tool", status="started")

        assert chunk.type == "execution_step"
        assert chunk.metadata["step_name"] == "get_contacts_tool"
        assert chunk.metadata["status"] == "started"

    def test_an_unknown_tool_still_produces_a_visible_step(self) -> None:
        # The fallback is the point: a tool missing from the catalogue must not
        # disappear from the trace, it must show up as a generic step.
        chunk = tool_step("a_tool_that_does_not_exist", status="completed")

        assert chunk.metadata["step_name"] == "a_tool_that_does_not_exist"
        assert chunk.metadata["step_type"] == "tool"
        assert chunk.metadata["status"] == "completed"
        assert chunk.metadata["emoji"]
        assert chunk.metadata["i18n_key"]

    def test_the_step_carries_no_body_text_and_counts_only(self) -> None:
        # The label is resolved client-side from `i18n_key`; a server-side
        # sentence here would bypass the 6-language contract — and the trace
        # is persisted, so what a step did travels as integers.
        chunk = tool_step(
            "get_contacts_tool", status="completed", step_key="call_0", outcome={"found": 3}
        )

        assert chunk.content == ""
        assert chunk.metadata["step_key"] == "call_0"
        assert chunk.metadata["outcome"] == {"found": 3}


class TestReactStartedSteps:
    def test_one_step_per_tool_call_keyed_by_its_id(self) -> None:
        steps = react_started_steps(
            {"messages": [ai_with_tool_calls("get_contacts_tool", "search_emails_tool")]}
        )

        assert [
            (chunk.metadata["step_name"], chunk.metadata["step_key"]) for chunk, _ in steps
        ] == [("get_contacts_tool", "call_0"), ("search_emails_tool", "call_1")]
        assert {chunk.metadata["status"] for chunk, _ in steps} == {"started"}

    def test_the_same_tool_called_twice_is_shown_twice(self) -> None:
        # Unlike the pipeline, ReAct steps are NOT merged here: two calls are
        # two real executions — the client adds them up as « ×2 ».
        steps = react_started_steps(
            {"messages": [ai_with_tool_calls("search_emails_tool", "search_emails_tool")]}
        )

        assert len(steps) == 2

    def test_a_turn_with_no_tool_call_emits_nothing(self) -> None:
        assert react_started_steps({"messages": [AIMessage(content="Bonjour")]}) == []

    @pytest.mark.parametrize(
        "state_delta",
        [{}, {"messages": []}, {"messages": [HumanMessage(content="salut")]}],
    )
    def test_nothing_to_read_yields_nothing(self, state_delta: dict[str, Any]) -> None:
        assert react_started_steps(state_delta) == []

    def test_a_tool_call_without_a_name_is_skipped(self) -> None:
        message = AIMessage(content="", tool_calls=[{"name": "", "args": {}, "id": "call_0"}])

        assert react_started_steps({"messages": [message]}) == []

    def test_tool_results_in_the_delta_are_not_mistaken_for_calls(self) -> None:
        delta = {
            "messages": [
                ToolMessage(content="{}", tool_call_id="call_0"),
                ai_with_tool_calls("get_contacts_tool"),
            ]
        }

        assert len(react_started_steps(delta)) == 1


class TestReactFinishedSteps:
    def test_an_answer_finishes_its_call_with_the_reads_counts(self) -> None:
        answer = ToolMessage(
            content="3 emails",
            tool_call_id="call_0",
            name="search_emails_tool",
            response_metadata={"items_found": 12, "items_shown": 5},
        )

        ((chunk, _),) = react_finished_steps({"messages": [answer]})

        assert chunk.metadata["status"] == "completed"
        assert chunk.metadata["step_key"] == "call_0"
        assert chunk.metadata["outcome"] == {"failed": 0, "found": 12, "shown": 5}

    def test_a_declared_failure_finishes_it_failed(self) -> None:
        answer = ToolMessage(
            content="refused",
            tool_call_id="call_1",
            name="search_emails_tool",
            status="error",
            response_metadata={"error_code": "NOT_FOUND"},
        )

        ((chunk, _),) = react_finished_steps({"messages": [answer]})

        assert chunk.metadata["status"] == "failed"
        assert chunk.metadata["outcome"] == {"failed": 1}

    def test_an_answer_without_a_tool_name_or_a_count_says_only_what_it_knows(self) -> None:
        nameless = ToolMessage(content="{}", tool_call_id="call_0")
        prose = ToolMessage(content="ok", tool_call_id="call_1", name="weather_tool")

        steps = react_finished_steps({"messages": [nameless, prose, ai_with_tool_calls("x")]})

        assert [chunk.metadata["outcome"] for chunk, _ in steps] == [{"failed": 0}]


class TestPipelineSteps:
    def test_each_tool_that_ran_is_one_step_with_its_calls_added_up(self) -> None:
        # Two steps of one tool: one line, its calls, its items.
        plan = plan_with_tools("search_emails_tool", "send_email_tool", "send_email_tool")
        completed = {
            "step_0": {"emails": [{"id": 1}, {"id": 2}, {"id": 3}], "total": 3},
            "step_1": {"success": True},
            "step_2": {"success": False, "error": "x", "error_code": "TIMEOUT"},
        }

        steps = pipeline_steps({"execution_plan": plan}, {"completed_steps": completed})

        assert [
            (chunk.metadata["step_name"], chunk.metadata["status"], chunk.metadata["outcome"])
            for chunk, _ in steps
        ] == [
            ("search_emails_tool", "completed", {"calls": 1, "found": 3, "failed": 0}),
            ("send_email_tool", "completed", {"calls": 2, "found": 0, "failed": 1}),
        ]

    def test_a_for_each_is_counted_by_its_items_never_by_its_aggregate(self) -> None:
        # The plan keeps the FOR_EACH unexpanded; the executor runs its items
        # as step_1_item_N and writes their merge back under step_1.
        loop = for_each_step("step_1", "get_place_details_tool")
        completed = {
            "step_0": {"places": [{"id": 1}, {"id": 2}, {"id": 3}]},
            "step_1_item_0": {"places": [{"id": 1}]},
            "step_1_item_1": {"success": False, "error": "x", "error_code": "TIMEOUT"},
            "step_1_item_2": {"places": [{"id": 3}]},
            "step_1": {
                "places": [{"id": 1}, {"id": 3}],
                FIELD_FOR_EACH_FAILED_ITEMS: [{"step_id": "step_1_item_1"}],
                FIELD_FOR_EACH_AGGREGATE: True,
            },
        }

        steps = pipeline_steps(
            {"execution_plan": SimpleNamespace(steps=[loop])}, {"completed_steps": completed}
        )

        assert [(chunk.metadata["status"], chunk.metadata["outcome"]) for chunk, _ in steps] == [
            ("completed", {"calls": 3, "found": 2, "failed": 1})
        ]

    def test_a_for_each_whose_every_item_failed_is_failed_once_per_item(self) -> None:
        loop = for_each_step("step_0", "send_email_tool")
        completed = {
            "step_0_item_0": {"success": False, "error": "x"},
            "step_0_item_1": {"success": False, "error": "y"},
            "step_0": {"success": False, "error": "x", FIELD_FOR_EACH_AGGREGATE: True},
        }

        steps = pipeline_steps(
            {"execution_plan": SimpleNamespace(steps=[loop])}, {"completed_steps": completed}
        )

        assert [(chunk.metadata["status"], chunk.metadata["outcome"]) for chunk, _ in steps] == [
            ("failed", {"calls": 2, "found": 0, "failed": 2})
        ]

    def test_a_for_each_over_nothing_never_ran(self) -> None:
        # An empty array expands to no item and the executor writes no aggregate.
        loop = for_each_step("step_1", "send_email_tool")

        steps = pipeline_steps(
            {"execution_plan": SimpleNamespace(steps=[loop])},
            {"completed_steps": {"step_0": {"places": []}}},
        )

        assert steps == []

    def test_a_tool_whose_every_call_failed_is_failed(self) -> None:
        steps = pipeline_steps(
            {"execution_plan": plan_with_tools("a_tool")},
            {"completed_steps": {"step_0": {"success": False, "error": "boom"}}},
        )

        assert [chunk.metadata["status"] for chunk, _ in steps] == ["failed"]

    def test_a_branch_not_taken_is_not_shown(self) -> None:
        steps = pipeline_steps(
            {"execution_plan": plan_with_tools("a_tool", "b_tool")},
            {"completed_steps": {"step_1": {"success": True}}},
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == ["b_tool"]

    def test_without_results_the_plans_tools_are_shown_once_as_before(self) -> None:
        # No `completed_steps` in the update: what the stream always showed.
        steps = pipeline_steps(
            {"execution_plan": plan_with_tools("b_tool", None, "a_tool", "b_tool", "")}, {}
        )

        assert [(chunk.metadata["step_name"], chunk.metadata["status"]) for chunk, _ in steps] == [
            ("b_tool", "started"),
            ("a_tool", "started"),
        ]

    @pytest.mark.parametrize(
        "state",
        [
            {},
            {"execution_plan": None},
            {"execution_plan": SimpleNamespace(steps=[])},
            {"execution_plan": SimpleNamespace(steps=None)},
        ],
    )
    def test_no_plan_means_no_step(self, state: dict[str, Any]) -> None:
        assert pipeline_steps(state, {"completed_steps": {}}) == []

    def test_a_plan_shaped_as_a_plain_dict_yields_nothing(self) -> None:
        # CHARACTERIZED: the reader is attribute-based (`getattr(plan, "steps")`),
        # so a plan that ever reached the stream as a dict would silently emit
        # no step at all. It does not today — the live stream carries the real
        # ExecutionPlan object — but the asymmetry is worth pinning.
        assert pipeline_steps({"execution_plan": {"steps": [{}]}}, {}) == []


def router_output(**overrides: Any) -> RouterOutput:
    """A RouterOutput the way router_node_v3 produces it."""
    fields: dict[str, Any] = {
        "intention": "conversation",
        "confidence": 0.9,
        "next_node": "response",
        "context_label": "general",
    }
    fields.update(overrides)
    return RouterOutput(**fields)


class TestRoutingHistorySignature:
    """What makes a router decision "new" — and stops the stale one.

    LangGraph hands the checkpoint state at turn start, so `routing_history[-1]`
    initially points at the PREVIOUS turn's decision. The signature is what
    tells the two apart; when it fails to, the voice streamer starts on a stale
    `intention="conversation"`.
    """

    def test_the_same_decision_yields_the_same_signature(self, service: StreamingService) -> None:
        assert StreamingService._routing_history_signature(
            [router_output()]
        ) == StreamingService._routing_history_signature([router_output()])

    @pytest.mark.parametrize(
        "changed",
        [
            {"intention": "contacts_search"},
            {"confidence": 0.42},
            {"next_node": "planner"},
            {"context_label": "suivi"},
        ],
    )
    def test_any_identifying_field_of_the_last_decision_changes_it(
        self, service: StreamingService, changed: dict[str, Any]
    ) -> None:
        # All four fields take part: a turn that only changes the target node
        # (same intention) must still count as a new decision.
        before = StreamingService._routing_history_signature([router_output()])
        after = StreamingService._routing_history_signature([router_output(**changed)])

        assert before != after

    def test_an_appended_entry_changes_the_signature(self, service: StreamingService) -> None:
        one = StreamingService._routing_history_signature([router_output()])
        two = StreamingService._routing_history_signature([router_output(), router_output()])

        assert one != two

    def test_an_empty_history_has_a_stable_signature(self, service: StreamingService) -> None:
        assert StreamingService._routing_history_signature(
            []
        ) == StreamingService._routing_history_signature([])

    def test_the_signature_is_hashable(self, service: StreamingService) -> None:
        # It is compared and stored between chunks; an unhashable value would
        # break the duplicate suppression at runtime only.
        assert hash(StreamingService._routing_history_signature([router_output()])) is not None

    def test_a_history_of_plain_dicts_collapses_to_a_blind_signature(
        self, service: StreamingService
    ) -> None:
        # CHARACTERIZED. The reader is attribute-based, so entries that ever
        # reached the stream as plain dicts would all share
        # `(len, None, None, None, None)` — two different decisions at the same
        # history length would be indistinguishable and the router_decision
        # chunk would stay suppressed. RouterOutput is a Pydantic model and
        # LangGraph's serde restores it as an object, so this does not happen
        # today; pinned because the failure mode is silent.
        blind = StreamingService._routing_history_signature([{"intention": "conversation"}])

        assert blind == (1, None, None, None, None)
        assert blind == StreamingService._routing_history_signature([{"intention": "actionable"}])


class TestComputeContextUsage:
    def test_no_snapshot_yet_means_no_pill(self, service: StreamingService) -> None:
        # First turn, nothing captured: the header pill stays hidden rather
        # than showing 0 / 0.
        assert service.compute_context_usage() is None

    def test_the_pill_reports_tokens_and_threshold(self, service: StreamingService) -> None:
        service.latest_state_messages = [HumanMessage(content="bonjour" * 20)]

        usage = service.compute_context_usage()

        assert usage is not None
        assert usage["context_tokens"] > 0
        assert usage["context_threshold"] > 0
        assert isinstance(usage["context_tokens"], int)
        assert isinstance(usage["context_threshold"], int)

    def test_a_counting_failure_hides_the_pill_instead_of_failing_the_done_chunk(
        self, service: StreamingService
    ) -> None:
        service.latest_state_messages = [HumanMessage(content="bonjour")]

        with patch(
            "src.domains.agents.services.compaction_service.CompactionService",
            side_effect=RuntimeError("tokenizer unavailable"),
        ):
            assert service.compute_context_usage() is None
