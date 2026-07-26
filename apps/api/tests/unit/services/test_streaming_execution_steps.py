"""SSE execution steps — the live trace the user watches while LIA works.

The "coulisses" panel is built from `execution_step` chunks emitted mid-stream.
Nothing downstream validates them: a step that is not emitted simply never
appears, a step emitted twice reads as the tool running twice, and a tool the
catalogue does not know must still show up rather than vanish.

Three extractors feed it, and none of them was driven:

* ``_extract_react_tool_steps`` — one step per tool the ReAct model decided to
  call, read off the AIMessage's ``tool_calls``.
* ``_extract_pipeline_tool_steps`` — one step per distinct tool of the pipeline
  execution plan, deduplicated so a plan calling the same tool three times does
  not print it three times.
* ``_emit_tool_execution_step`` — the catalogue lookup, with the fallback that
  keeps an unknown tool visible.

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

from src.domains.agents.domain_schemas import RouterOutput
from src.domains.agents.services.streaming.service import StreamingService

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
    """An execution plan exposing `.steps[].tool_name`, like ExecutionPlan does."""
    return SimpleNamespace(
        steps=[SimpleNamespace(tool_name=name) for name in tool_names],
    )


class TestEmitToolExecutionStep:
    def test_a_catalogued_tool_gets_its_display_metadata(self, service: StreamingService) -> None:
        chunk = service._emit_tool_execution_step("get_contacts_tool")

        assert chunk is not None
        assert chunk.type == "execution_step"
        assert chunk.metadata["step_name"] == "get_contacts_tool"
        assert chunk.metadata["status"] == "started"

    def test_an_unknown_tool_still_produces_a_visible_step(self, service: StreamingService) -> None:
        # The fallback is the point: a tool missing from the catalogue must not
        # disappear from the trace, it must show up as a generic step.
        chunk = service._emit_tool_execution_step("a_tool_that_does_not_exist")

        assert chunk is not None
        assert chunk.metadata["step_name"] == "a_tool_that_does_not_exist"
        assert chunk.metadata["step_type"] == "tool"
        assert chunk.metadata["emoji"]
        assert chunk.metadata["i18n_key"]

    def test_the_step_carries_no_body_text(self, service: StreamingService) -> None:
        # The label is resolved client-side from `i18n_key`; a server-side
        # sentence here would bypass the 6-language contract.
        chunk = service._emit_tool_execution_step("get_contacts_tool")

        assert chunk is not None
        assert chunk.content == ""


class TestExtractReactToolSteps:
    def test_one_step_per_tool_call(self, service: StreamingService) -> None:
        steps = service._extract_react_tool_steps(
            {"messages": [ai_with_tool_calls("get_contacts_tool", "search_emails_tool")]}
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == [
            "get_contacts_tool",
            "search_emails_tool",
        ]

    def test_the_same_tool_called_twice_is_shown_twice(self, service: StreamingService) -> None:
        # Unlike the pipeline extractor, ReAct steps are NOT deduplicated: two
        # calls are two real executions the user should see.
        steps = service._extract_react_tool_steps(
            {"messages": [ai_with_tool_calls("search_emails_tool", "search_emails_tool")]}
        )

        assert len(steps) == 2

    def test_a_turn_with_no_tool_call_emits_nothing(self, service: StreamingService) -> None:
        assert service._extract_react_tool_steps({"messages": [AIMessage(content="Bonjour")]}) == []

    @pytest.mark.parametrize(
        "state_delta",
        [{}, {"messages": []}, {"messages": [HumanMessage(content="salut")]}],
    )
    def test_nothing_to_read_yields_nothing(
        self, service: StreamingService, state_delta: dict[str, Any]
    ) -> None:
        assert service._extract_react_tool_steps(state_delta) == []

    def test_a_tool_call_without_a_name_is_skipped(self, service: StreamingService) -> None:
        message = AIMessage(content="", tool_calls=[{"name": "", "args": {}, "id": "call_0"}])

        assert service._extract_react_tool_steps({"messages": [message]}) == []

    def test_tool_results_in_the_delta_are_not_mistaken_for_calls(
        self, service: StreamingService
    ) -> None:
        delta = {
            "messages": [
                ToolMessage(content="{}", tool_call_id="call_0"),
                ai_with_tool_calls("get_contacts_tool"),
            ]
        }

        assert len(service._extract_react_tool_steps(delta)) == 1


class TestExtractPipelineToolSteps:
    def test_one_step_per_plan_tool(self, service: StreamingService) -> None:
        steps = service._extract_pipeline_tool_steps(
            {"execution_plan": plan_with_tools("get_contacts_tool", "search_emails_tool")}
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == [
            "get_contacts_tool",
            "search_emails_tool",
        ]

    def test_a_tool_repeated_in_the_plan_is_shown_once(self, service: StreamingService) -> None:
        # A FOR_EACH plan calls one tool per item; printing it per item would
        # flood the panel with the same line.
        steps = service._extract_pipeline_tool_steps(
            {"execution_plan": plan_with_tools("send_email_tool", "send_email_tool", "x_tool")}
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == [
            "send_email_tool",
            "x_tool",
        ]

    def test_the_first_occurrence_order_is_preserved(self, service: StreamingService) -> None:
        steps = service._extract_pipeline_tool_steps(
            {"execution_plan": plan_with_tools("b_tool", "a_tool", "b_tool")}
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == ["b_tool", "a_tool"]

    def test_a_step_without_a_tool_name_is_skipped(self, service: StreamingService) -> None:
        # CONDITIONAL / FOR_EACH container steps carry no tool_name.
        steps = service._extract_pipeline_tool_steps(
            {"execution_plan": plan_with_tools(None, "a_tool", "")}
        )

        assert [chunk.metadata["step_name"] for chunk, _ in steps] == ["a_tool"]

    @pytest.mark.parametrize(
        "state",
        [
            {},
            {"execution_plan": None},
            {"execution_plan": SimpleNamespace(steps=[])},
            {"execution_plan": SimpleNamespace(steps=None)},
        ],
    )
    def test_no_plan_means_no_step(self, service: StreamingService, state: dict[str, Any]) -> None:
        assert service._extract_pipeline_tool_steps(state) == []

    def test_a_plan_shaped_as_a_plain_dict_yields_nothing(self, service: StreamingService) -> None:
        # CHARACTERIZED: the reader is attribute-based (`getattr(plan, "steps")`),
        # so a plan that ever reached the stream as a dict would silently emit
        # no step at all. It does not today — the live `values` stream carries
        # the real ExecutionPlan object — but the asymmetry is worth pinning.
        assert service._extract_pipeline_tool_steps({"execution_plan": {"steps": [{}]}}) == []


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
