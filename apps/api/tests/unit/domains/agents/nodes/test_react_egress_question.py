"""The egress question is settled INSIDE the ReAct loop (ADR-298).

Measured 2026-09-18 on dev: « look at my last 5 mails and count the
attachments; also check that httpbin.org answers » — the model called both
tools in one iteration, the sandbox call asked for `httpbin.org`, the person
allowed it, and the turn ended on the draft's fast path with the httpbin
result alone: the draft handoff EXECUTES a draft and answers, it never resumes
the loop, so every step the model still had to take was lost. The question is
therefore an in-node ``interrupt()`` like a mutation tool's: the answer is
handed to the very call that asked, re-invoked, and the loop goes on.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable, MutableMapping
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from structlog.testing import capture_logs

from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes import react_egress_question as mod
from src.domains.agents.nodes import react_nodes
from src.domains.agents.python_sandbox.egress.grants import Decision, RecordOutcome
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.tool_registry import get_tool, register_external_tool
from src.domains.agents.utils.message_filters import TOOL_CALL_NOT_RUN, tool_call_ran

pytestmark = pytest.mark.unit

USER = uuid.uuid4()


def _draft_info(**over: Any) -> dict[str, Any]:
    return {
        "draft_id": "draft_e1",
        "draft_type": "sandbox_egress",
        "draft_content": {
            "hosts": ["example.com", "api.example.org"],
            "hosts_unknown": ["example.com"],
            "hosts_label": "example.com",
            "purpose": "fetch the title",
            "data_summary": {"counts": {"email": 5}, "available": True, "language": "fr"},
        },
        "draft_summary": "",
        "registry_ids": ["draft_e1"],
        "tool_name": "run_python_tool",
        "step_id": None,
        **over,
    }


@pytest.fixture
def context() -> Any:
    ctx = SimpleNamespace(user_id=USER, thread_id="t", execution_mode="react")
    with patch(f"{mod.__name__}.runtime_context_if_running", return_value=ctx):
        yield ctx


@pytest.fixture
def no_context_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """The tool context store out of the way: the loop reads it for every call."""

    async def _store() -> None:
        return None

    monkeypatch.setattr(
        "src.domains.agents.context.store.get_tool_context_store", _store, raising=True
    )


async def _asks(purpose: str) -> UnifiedToolOutput:
    """The sandbox's question for one host nobody permitted."""
    from src.domains.agents.python_sandbox.egress.draft import ask_for_hosts
    from src.domains.agents.python_sandbox.egress.hosts import HostDecision, HostStatus

    return ask_for_hosts(
        decision=HostDecision(
            statuses={"example.com": HostStatus.UNKNOWN},
            unknown=("example.com",),
            credentials=(),
            share_turn_data=True,
        ),
        purpose=purpose,
        items={},
        language="fr",
    )


def _registered(name: str, coroutine: Callable[..., Awaitable[UnifiedToolOutput]]) -> None:
    """A test tool, registered once: the registry is the process's."""
    if get_tool(name) is None:
        register_external_tool(
            StructuredTool.from_function(coroutine=coroutine, name=name, description="d")
        )


def _loop_state(*calls: tuple[str, str]) -> MessagesState:
    """One ReAct iteration whose model asked for ``calls`` — (tool, call id).

    Each call's purpose names it, so two calls of one tool are two calls, never
    one repeated.
    """
    state = create_initial_state(uuid.uuid4(), session_id="s", run_id="r", user_language="fr")
    state["messages"] = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": {"purpose": f"p-{call_id}"},
                    "id": call_id,
                    "type": "tool_call",
                }
                for name, call_id in calls
            ],
        )
    ]
    state["react_tool_names"] = list(dict.fromkeys(name for name, _ in calls))
    state["react_hitl_map"] = {name: False for name, _ in calls}
    state["react_iteration"] = 1
    state["react_call_digests"] = {}
    return state


def _processing_fails(*_args: object) -> None:
    """The loop's processing of an answer, failing once the answer came back."""
    raise RuntimeError("processing failed")


def _contact(key: str) -> RegistryItem:
    """A contact card an answer carries."""
    return RegistryItem(
        id=key,
        type=RegistryItemType.CONTACT,
        payload={"names": [{"displayName": "Ada"}]},
        meta=RegistryItemMeta(source="test", domain="contacts"),
    )


async def _finds(purpose: str) -> UnifiedToolOutput:
    """An answer carrying one contact card, named after the call's purpose."""
    key = f"contact_{purpose}"
    return UnifiedToolOutput(success=True, message="found", registry_updates={key: _contact(key)})


def _events(logs: list[MutableMapping[str, Any]], event: str) -> list[str]:
    """The levels ``event`` was logged at."""
    return [entry["log_level"] for entry in logs if entry["event"] == event]


class TestWhatIsAQuestion:
    def test_only_the_egress_draft_type(self) -> None:
        assert mod.is_egress_question(_draft_info()) is True
        assert mod.is_egress_question(_draft_info(draft_type="email")) is False
        assert mod.is_egress_question(None) is False


class TestTheInterruptPayload:
    def test_is_the_draft_critique_shape_the_streaming_side_already_renders(self) -> None:
        payload = mod.build_interrupt_payload(_draft_info(), user_language="de")
        assert payload["hitl_type"] == "draft_critique"
        assert payload["generate_question_streaming"] is True
        assert payload["user_language"] == "de"
        request = payload["action_requests"][0]
        assert request["type"] == "draft_critique"
        assert request["draft_id"] == "draft_e1"
        assert request["draft_type"] == "sandbox_egress"
        assert request["draft_content"]["hosts_unknown"] == ["example.com"]
        assert request["registry_ids"] == ["draft_e1"]
        assert request["tool_name"] == "run_python_tool"


class TestReadingTheAnswer:
    @pytest.mark.parametrize(
        "decision,allowed,share",
        [
            ({"action": "confirm", "draft_id": "draft_e1"}, True, True),
            ({"action": "confirm", "share_turn_data": False}, True, False),
            ({"action": "approve"}, True, True),
            ({"action": "cancel"}, False, False),
            ({"action": "edit", "modification_instructions": "x"}, False, False),
            (None, False, False),
            ("garbage", False, False),
        ],
    )
    def test_confirm_is_the_only_yes_and_the_scope_travels_beside_it(
        self, decision: Any, allowed: bool, share: bool
    ) -> None:
        answer = mod.read_answer(decision)
        assert (answer.allowed, answer.share_turn_data) == (allowed, share)


class TestSettling:
    async def test_an_allowed_answer_records_the_grant_and_reruns_the_call_under_it(
        self, context: Any
    ) -> None:
        seen: list[dict[str, bool]] = []

        async def _rerun() -> Any:
            from src.domains.agents.python_sandbox.egress.tool_path import approved_hosts

            seen.append(dict(approved_hosts()))
            return UnifiedToolOutput(success=True, message="ran", structured_data={"stdout": "x"})

        record = AsyncMock(
            return_value=RecordOutcome(allowed=True, share_turn_data=False, one_shot=False)
        )
        with (
            patch(
                f"{mod.__name__}.interrupt",
                return_value={"action": "confirm", "share_turn_data": False},
            ) as ask,
            patch(f"{mod.__name__}.record_decision", record),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total") as grants_counter,
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=_rerun
            )
        ask.assert_called_once()
        record.assert_awaited_once_with(USER, ["example.com"], Decision.WITHOUT_DATA)
        assert seen == [{"example.com": False}], "the answer reached the re-invocation alone"
        assert result.success is True and result.structured_data["stdout"] == "x"
        grants_counter.labels.assert_called_with(decision="without_data")

    async def test_at_the_cap_the_answer_holds_for_this_run_and_is_counted_one_shot(
        self, context: Any
    ) -> None:
        seen: list[dict[str, bool]] = []

        async def _rerun() -> Any:
            from src.domains.agents.python_sandbox.egress.tool_path import approved_hosts

            seen.append(dict(approved_hosts()))
            return UnifiedToolOutput(success=True, message="ran")

        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "confirm"}),
            patch(
                f"{mod.__name__}.record_decision",
                AsyncMock(
                    return_value=RecordOutcome(allowed=True, share_turn_data=True, one_shot=True)
                ),
            ),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total") as grants_counter,
        ):
            await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=_rerun
            )
        assert seen == [{"example.com": True}]
        grants_counter.labels.assert_called_with(decision="one_shot")

    async def test_a_refusal_runs_nothing_and_tells_the_model_which_hosts(
        self, context: Any
    ) -> None:
        rerun = AsyncMock()
        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "cancel"}),
            patch(f"{mod.__name__}.record_decision", AsyncMock()) as record,
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total") as grants_counter,
            patch(f"{mod.__name__}.react_agent_hitl_interrupts_total") as interrupts_counter,
            capture_logs() as logs,
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=rerun
            )
        rerun.assert_not_awaited()
        record.assert_not_awaited()
        assert result.success is False
        assert "example.com" in result.message
        # A decision, never a failure: the answer says the call never ran.
        assert result.metadata == {TOOL_CALL_NOT_RUN: True}
        grants_counter.labels.assert_called_with(decision="refused")
        interrupts_counter.labels.assert_called_with(
            tool_name=mod.PYTHON_SANDBOX_TOOL_NAME, decision="reject"
        )
        assert _events(logs, "sandbox_egress_question_refused") == ["info"]

    async def test_the_approval_never_outlives_the_re_invocation(self, context: Any) -> None:
        from src.domains.agents.python_sandbox.egress.tool_path import approved_hosts

        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "confirm"}),
            patch(
                f"{mod.__name__}.record_decision",
                AsyncMock(
                    return_value=RecordOutcome(allowed=True, share_turn_data=True, one_shot=False)
                ),
            ),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total"),
        ):
            await mod.settle_egress_question(
                _draft_info(),
                state={"user_language": "fr"},
                rerun=AsyncMock(return_value=UnifiedToolOutput(success=True, message="ran")),
            )
        assert approved_hosts() == {}

    async def test_a_yes_no_account_can_record_is_the_system_s_failure_never_a_refusal(
        self,
    ) -> None:
        """No account to record for: the tool is told rather than guessed."""
        rerun = AsyncMock()
        with (
            patch(f"{mod.__name__}.runtime_context_if_running", return_value=None),
            patch(f"{mod.__name__}.interrupt", return_value={"action": "confirm"}),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total") as grants_counter,
            patch(f"{mod.__name__}.react_agent_hitl_interrupts_total") as interrupts_counter,
            capture_logs() as logs,
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=rerun
            )
        rerun.assert_not_awaited()
        assert result.success is False
        # Nobody refused: the person said yes, the system could not grant. It
        # stays a failure, the model is never told the person refused, and no
        # refusal is counted.
        assert TOOL_CALL_NOT_RUN not in result.metadata
        assert "refused" not in result.message
        assert result.error_code == "INTERNAL_ERROR"
        grants_counter.labels.assert_not_called()
        interrupts_counter.labels.assert_not_called()
        assert _events(logs, "sandbox_egress_question_unrecorded") == ["warning"]
        assert _events(logs, "sandbox_egress_question_refused") == []

    async def test_a_refusal_outside_a_run_context_is_still_the_person_s(self) -> None:
        """The person said no: a decision, whether or not an account could have
        recorded a yes."""
        with (
            patch(f"{mod.__name__}.runtime_context_if_running", return_value=None),
            patch(f"{mod.__name__}.interrupt", return_value={"action": "cancel"}),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total") as grants_counter,
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=AsyncMock()
            )
        assert result.metadata == {TOOL_CALL_NOT_RUN: True}
        grants_counter.labels.assert_called_with(decision="refused")


class TestTheLoopGoesOn:
    """Driven through the node itself: the call asks, the person answers, the
    SAME call runs under the answer, and the node hands the loop a plain tool
    result — no draft left for the dispatch, no fast path, the model's next
    step still to come."""

    async def test_the_answered_call_becomes_a_tool_message_and_no_draft(
        self, no_context_store: None, context: Any
    ) -> None:
        from src.domains.agents.effects.scope import current_scope
        from src.domains.agents.python_sandbox.egress.tool_path import approved_hosts

        calls: list[dict[str, Any]] = []

        async def _egress_probe(purpose: str) -> UnifiedToolOutput:
            scope = current_scope()
            calls.append(
                {
                    "approved": dict(approved_hosts()),
                    "scope_approved": bool(scope and scope.approved),
                    "approval_kind": scope.approval_kind if scope else None,
                }
            )
            if not approved_hosts():
                return await _asks(purpose)
            return UnifiedToolOutput(
                success=True, message="Script executed.", structured_data={"stdout": "42\n"}
            )

        _registered("egress_probe_tool", _egress_probe)
        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "confirm"}),
            patch(
                f"{mod.__name__}.record_decision",
                AsyncMock(
                    return_value=RecordOutcome(allowed=True, share_turn_data=True, one_shot=False)
                ),
            ),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total"),
        ):
            result = await react_nodes.react_execute_tools_node(
                _loop_state(("egress_probe_tool", "c-egress")), {}
            )

        assert [c["approved"] for c in calls] == [{}, {"example.com": True}]
        assert calls[1]["scope_approved"] is True
        assert calls[1]["approval_kind"] == "draft_critique"
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1 and "42" in str(tool_messages[0].content)
        assert result.get("pending_draft_critique") is None
        assert not result.get("pending_drafts_queue")

    async def test_the_interrupt_escapes_the_nodes_error_net(
        self, no_context_store: None, context: Any
    ) -> None:
        """Measured 2026-09-18 on dev: the first pass raised no question at
        all — ``interrupt()`` raises ``GraphInterrupt`` from INSIDE the call,
        and the node's « any tool error becomes a message » net swallowed it
        (« Error executing run_python_tool: … »), so the loop went on and told
        the person the measurement was « suspended ». A bubble-up is not an
        error."""
        from langgraph.errors import GraphInterrupt

        _registered("egress_asks_tool", _asks)

        def _raise(payload: Any) -> Any:
            raise GraphInterrupt()

        with (
            patch(f"{mod.__name__}.interrupt", side_effect=_raise),
            pytest.raises(GraphInterrupt),
        ):
            await react_nodes.react_execute_tools_node(
                _loop_state(("egress_asks_tool", "c-ask")), {}
            )

    async def test_a_refused_question_is_a_call_never_run_and_marks_no_other(
        self, no_context_store: None, context: Any
    ) -> None:
        """The person's no reached the loop as a tool FAILURE: the honesty
        directive told them their own choice was a breakdown, and the turn's
        outcome counted it. The next call of the same iteration, failing before
        it returned anything, must not inherit the refusal's mark either."""

        async def _breaks(purpose: str) -> UnifiedToolOutput:
            raise RuntimeError("the tool broke")

        _registered("egress_refused_tool", _asks)
        _registered("egress_breaks_tool", _breaks)
        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "cancel"}),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total"),
        ):
            result = await react_nodes.react_execute_tools_node(
                _loop_state(
                    ("egress_refused_tool", "c-refused"), ("egress_breaks_tool", "c-breaks")
                ),
                {},
            )

        refused, broke = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert (refused.status, tool_call_ran(refused)) == ("success", False)
        assert "example.com" in str(refused.content)
        assert (broke.status, tool_call_ran(broke)) == ("error", True)

    async def test_a_failure_after_the_refusal_came_back_carries_no_mark(
        self, no_context_store: None, context: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Status and mark are decided together: a call whose processing failed
        after the refusal came back is a failure, never also « never run » —
        the honesty directive and the outcome would disagree about it."""
        _registered("egress_refused_later_tool", _asks)
        monkeypatch.setattr(react_nodes, "_extract_draft_info", _processing_fails)
        with (
            patch(f"{mod.__name__}.interrupt", return_value={"action": "cancel"}),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total"),
        ):
            result = await react_nodes.react_execute_tools_node(
                _loop_state(("egress_refused_later_tool", "c-later")), {}
            )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert (answer.status, tool_call_ran(answer)) == ("error", True)


class TestTheCallsBooks:
    """Driven through the node: a call's books (the iteration it buys, its
    draft, its registry items, the « never run » mark) close only once nothing
    of the call can fail any more."""

    async def test_an_answer_buys_one_iteration(self, no_context_store: None) -> None:
        async def _answers(purpose: str) -> UnifiedToolOutput:
            return UnifiedToolOutput(success=True, message="found", structured_data={"n": 1})

        _registered("books_answers_tool", _answers)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_answers_tool", "c-answers")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert answer.status == "success"
        assert result["react_productive_iterations"] == 1

    async def test_a_declared_failure_buys_no_iteration(self, no_context_store: None) -> None:
        """The tool said it failed, by returning: it taught the loop nothing to
        build on, so it extends no budget (ADR-256)."""

        async def _refuses(purpose: str) -> UnifiedToolOutput:
            return UnifiedToolOutput.failure(
                message="the provider refused", error_code=ToolErrorCode.EXTERNAL_API_ERROR
            )

        _registered("books_refuses_tool", _refuses)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_refuses_tool", "c-refuses")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        # The tool's own words and nothing else: a call that raised would read
        # « Error executing … » around them.
        assert answer.content == "the provider refused"
        assert answer.status == "error"
        assert "react_productive_iterations" not in result

    async def test_a_call_whose_processing_failed_buys_no_iteration(
        self, no_context_store: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A call's books come last: an answer the loop then failed to process
        is a failure, and a failure buys no iteration (ADR-256) — counted
        before the processing, it extended the budget with an error."""

        async def _answers(purpose: str) -> UnifiedToolOutput:
            return UnifiedToolOutput(success=True, message="found", structured_data={"n": 1})

        _registered("processing_fails_tool", _answers)
        monkeypatch.setattr(react_nodes, "_extract_draft_info", _processing_fails)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("processing_fails_tool", "c-fails")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert answer.status == "error"
        assert "react_productive_iterations" not in result

    async def test_a_declared_failure_still_hands_on_the_items_it_returned(
        self, no_context_store: None
    ) -> None:
        """A tool that fails by RETURNING keeps what it did return, as the
        pipeline does: only a call that raised hands on nothing."""

        async def _partial(purpose: str) -> UnifiedToolOutput:
            return UnifiedToolOutput(
                success=False,
                message="the provider refused the rest",
                error_code=ToolErrorCode.EXTERNAL_API_ERROR,
                registry_updates={"contact_partial": _contact("contact_partial")},
            )

        _registered("books_partial_tool", _partial)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_partial_tool", "c-partial")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert answer.status == "error"
        assert "react_productive_iterations" not in result
        assert set(result["registry"]) == {"contact_partial"}

    async def test_a_draft_whose_answer_could_not_be_processed_is_held_by_nobody(
        self, no_context_store: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The draft is booked with the call: an answer the loop failed to
        process hands no draft to the confirmation."""

        async def _drafts(purpose: str) -> UnifiedToolOutput:
            return UnifiedToolOutput(
                success=True,
                message="draft ready",
                metadata={
                    "requires_confirmation": True,
                    "draft_id": "d-lost",
                    "draft_type": "email",
                },
            )

        def _compose_fails(*_args: object, **_kwargs: object) -> str:
            raise RuntimeError("composition failed")

        _registered("books_drafts_tool", _drafts)
        monkeypatch.setattr(
            "src.domains.agents.tools.react_tool_wrapper.compose_tool_message", _compose_fails
        )
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_drafts_tool", "c-draft")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert answer.status == "error"
        assert result["pending_draft_critique"] is None

    async def test_an_answer_hands_on_its_registry_items(self, no_context_store: None) -> None:
        _registered("books_finds_tool", _finds)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_finds_tool", "c-finds")), {}
        )

        assert set(result["registry"]) == {"contact_p-c-finds"}
        assert set(result["current_turn_registry"]) == {"contact_p-c-finds"}

    async def test_a_call_whose_processing_failed_hands_on_no_registry_item(
        self, no_context_store: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Its answer carried a card, then the loop failed to process it: the
        card belongs to a failed call, never to the turn."""
        _registered("books_finds_then_fails_tool", _finds)
        monkeypatch.setattr(react_nodes, "_extract_draft_info", _processing_fails)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_finds_then_fails_tool", "c-lost")), {}
        )

        (answer,) = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert answer.status == "error"
        assert "registry" not in result
        assert "current_turn_registry" not in result

    async def test_a_failed_call_leaves_nothing_to_the_next_call_of_its_tool(
        self, no_context_store: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One wrapper serves every call of a tool in an iteration: what the
        failed first call left in it never reaches the second call's books."""

        def _first_processing_fails(raw_result: UnifiedToolOutput, tool_name: str) -> None:
            if "contact_p-c-first" in raw_result.registry_updates:
                raise RuntimeError("processing failed")

        _registered("books_twice_tool", _finds)
        monkeypatch.setattr(react_nodes, "_extract_draft_info", _first_processing_fails)
        result = await react_nodes.react_execute_tools_node(
            _loop_state(("books_twice_tool", "c-first"), ("books_twice_tool", "c-second")), {}
        )

        first, second = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert (first.status, second.status) == ("error", "success")
        assert set(result["registry"]) == {"contact_p-c-second"}
