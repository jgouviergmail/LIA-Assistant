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
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.nodes import react_egress_question as mod
from src.domains.agents.python_sandbox.egress.grants import Decision, RecordOutcome
from src.domains.agents.tools.output import UnifiedToolOutput

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
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=rerun
            )
        rerun.assert_not_awaited()
        record.assert_not_awaited()
        assert result.success is False
        assert "example.com" in result.message
        grants_counter.labels.assert_called_with(decision="refused")

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

    async def test_outside_a_run_context_the_question_is_a_refusal(self) -> None:
        """No account to record for: the tool is told rather than guessed."""
        rerun = AsyncMock()
        with (
            patch(f"{mod.__name__}.runtime_context_if_running", return_value=None),
            patch(f"{mod.__name__}.interrupt", return_value={"action": "confirm"}),
            patch(f"{mod.__name__}.python_sandbox_egress_grants_total"),
        ):
            result = await mod.settle_egress_question(
                _draft_info(), state={"user_language": "fr"}, rerun=rerun
            )
        rerun.assert_not_awaited()
        assert result.success is False


class TestTheLoopGoesOn:
    """Driven through the node itself: the call asks, the person answers, the
    SAME call runs under the answer, and the node hands the loop a plain tool
    result — no draft left for the dispatch, no fast path, the model's next
    step still to come."""

    async def test_the_answered_call_becomes_a_tool_message_and_no_draft(
        self, monkeypatch: pytest.MonkeyPatch, context: Any
    ) -> None:
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.tools import StructuredTool

        from src.domains.agents.effects.scope import current_scope
        from src.domains.agents.nodes import react_nodes
        from src.domains.agents.python_sandbox.egress.tool_path import approved_hosts
        from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

        async def _store() -> None:
            return None

        monkeypatch.setattr(
            "src.domains.agents.context.store.get_tool_context_store", _store, raising=True
        )
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
                from src.domains.agents.python_sandbox.egress.draft import ask_for_hosts
                from src.domains.agents.python_sandbox.egress.hosts import (
                    HostDecision,
                    HostStatus,
                )

                decision = HostDecision(
                    statuses={"example.com": HostStatus.UNKNOWN},
                    unknown=("example.com",),
                    credentials=(),
                    share_turn_data=True,
                )
                return ask_for_hosts(decision=decision, purpose=purpose, items={}, language="fr")
            return UnifiedToolOutput(
                success=True, message="Script executed.", structured_data={"stdout": "42\n"}
            )

        if get_tool("egress_probe_tool") is None:
            register_external_tool(
                StructuredTool.from_function(
                    coroutine=_egress_probe, name="egress_probe_tool", description="d"
                )
            )
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "egress_probe_tool",
                            "args": {"purpose": "count"},
                            "id": "c-egress",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "react_tool_names": ["egress_probe_tool"],
            "react_hitl_map": {"egress_probe_tool": False},
            "react_iteration": 1,
            "react_call_digests": {},
            "user_language": "fr",
        }
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
            result = await react_nodes.react_execute_tools_node(state, {})

        assert [c["approved"] for c in calls] == [{}, {"example.com": True}]
        assert calls[1]["scope_approved"] is True
        assert calls[1]["approval_kind"] == "draft_critique"
        tool_messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_messages) == 1 and "42" in str(tool_messages[0].content)
        assert result.get("pending_draft_critique") is None
        assert not result.get("pending_drafts_queue")

    async def test_the_interrupt_escapes_the_nodes_error_net(
        self, monkeypatch: pytest.MonkeyPatch, context: Any
    ) -> None:
        """Measured 2026-09-18 on dev: the first pass raised no question at
        all — ``interrupt()`` raises ``GraphInterrupt`` from INSIDE the call,
        and the node's « any tool error becomes a message » net swallowed it
        (« Error executing run_python_tool: … »), so the loop went on and told
        the person the measurement was « suspended ». A bubble-up is not an
        error."""
        from langchain_core.messages import AIMessage
        from langchain_core.tools import StructuredTool
        from langgraph.errors import GraphInterrupt

        from src.domains.agents.nodes import react_nodes
        from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

        async def _store() -> None:
            return None

        monkeypatch.setattr(
            "src.domains.agents.context.store.get_tool_context_store", _store, raising=True
        )

        async def _asks(purpose: str) -> UnifiedToolOutput:
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

        if get_tool("egress_asks_tool") is None:
            register_external_tool(
                StructuredTool.from_function(
                    coroutine=_asks, name="egress_asks_tool", description="d"
                )
            )
        state = {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "egress_asks_tool",
                            "args": {"purpose": "p"},
                            "id": "c-ask",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "react_tool_names": ["egress_asks_tool"],
            "react_hitl_map": {"egress_asks_tool": False},
            "react_iteration": 1,
            "react_call_digests": {},
        }

        def _raise(payload: Any) -> Any:
            raise GraphInterrupt()

        with (
            patch(f"{mod.__name__}.interrupt", side_effect=_raise),
            pytest.raises(GraphInterrupt),
        ):
            await react_nodes.react_execute_tools_node(state, {})
