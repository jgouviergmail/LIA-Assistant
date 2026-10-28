"""A call the loop decided not to run is answered — and marked as never run.

Declined by the person, or a repeat the loop guard blocked: neither a success
nor a failure. The answer keeps no error status (a refusal is a decision,
ADR-303), and its structural mark is what the business outcome reads to count
no verdict for it (review 8: a declined mutation used to make its turn a
success). Driven through the real node, the marker is also proven to survive
the checkpoint's serializer.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from src.core.config import settings
from src.domains.agents.api.run_origin import RunOrigin, out_of_turn_origin_ctx
from src.domains.agents.effects.gate import (
    ERROR_CONFIRMATION_IMPOSSIBLE,
    UNATTENDED_REFUSAL_MESSAGE,
)
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.nodes import react_nodes
from src.domains.agents.utils.loop_guard import compute_call_digest
from src.domains.agents.utils.message_filters import TOOL_CALL_NOT_RUN, tool_call_ran
from src.infrastructure.observability import metrics_effects
from tests.helpers.runtime_context import installed_runtime_context

pytestmark = [pytest.mark.unit]


def _register_tool(name: str) -> None:
    from src.domains.agents.tools.tool_registry import get_tool, register_external_tool

    if get_tool(name) is not None:
        return

    async def _fn() -> dict[str, Any]:
        return {"success": True, "data": "ok"}

    register_external_tool(StructuredTool.from_function(coroutine=_fn, name=name, description="d"))


def _state(name: str, *, mutation: bool, **extra: Any) -> dict[str, Any]:
    call = {"name": name, "args": {}, "id": "c1", "type": "tool_call"}
    return {
        "messages": [AIMessage(content="", tool_calls=[call])],
        "react_tool_names": [name],
        "react_hitl_map": {name: mutation},
        "react_iteration": 1,
        "react_call_digests": {},
        **extra,
    }


@pytest.fixture(autouse=True)
def _no_store(monkeypatch: pytest.MonkeyPatch) -> None:
    """The context store needs PostgreSQL; answering a call does not."""

    async def _store() -> None:
        return None

    monkeypatch.setattr(
        "src.domains.agents.context.store.get_tool_context_store", _store, raising=True
    )


def _only_answer(result: dict[str, Any]) -> ToolMessage:
    (message,) = result["messages"]
    assert isinstance(message, ToolMessage)
    return message


async def test_a_mutation_the_person_declined_is_answered_as_never_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _register_tool("not_run_probe_mutation")
    monkeypatch.setattr(react_nodes, "interrupt", lambda _payload: {"action": "reject"})

    answer = _only_answer(
        await react_nodes.react_execute_tools_node(
            _state("not_run_probe_mutation", mutation=True), {}
        )
    )

    assert answer.status == "success"  # a decision, never a failure (ADR-303)
    assert answer.artifact == TOOL_CALL_NOT_RUN
    assert not tool_call_ran(answer)


async def test_a_confirmed_mutation_runs_and_is_marked_as_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control: the same call, confirmed, carries no mark."""
    _register_tool("not_run_probe_mutation")
    monkeypatch.setattr(react_nodes, "interrupt", lambda _payload: {"action": "confirm"})

    answer = _only_answer(
        await react_nodes.react_execute_tools_node(
            _state("not_run_probe_mutation", mutation=True), {}
        )
    )

    assert tool_call_ran(answer)


def _refusals_unattended() -> float:
    return float(
        metrics_effects.effect_refusals_total.labels(
            reason=ERROR_CONFIRMATION_IMPOSSIBLE
        )._value.get()
    )


def _never_asked(_payload: object) -> object:
    raise AssertionError("a question was raised in a turn nobody can answer")


async def test_a_confirmation_nobody_can_give_is_never_asked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N10: a routine's loop met a tool that needs a confirmation and ASKED —
    the question stayed on the person's thread and read their next message as
    its answer. Nobody can answer a routine: the call is answered as never run,
    in the gate's own words, and counted like the gate's own refusal."""
    _register_tool("not_run_probe_mutation")
    monkeypatch.setattr(react_nodes, "interrupt", _never_asked)
    before = _refusals_unattended()

    with installed_runtime_context(is_automated_source=True):
        answer = _only_answer(
            await react_nodes.react_execute_tools_node(
                _state("not_run_probe_mutation", mutation=True), {}
            )
        )

    assert answer.content == UNATTENDED_REFUSAL_MESSAGE
    assert answer.status == "success"  # nothing broke: the call never ran (ADR-303)
    assert not tool_call_ran(answer)
    assert _refusals_unattended() - before == 1


async def test_a_ticket_still_asks_its_confirmation(monkeypatch: pytest.MonkeyPatch) -> None:
    """The control: a ticket run is unattended too, but it CARRIES the question
    to the person (ADR-276 lot 7) — it keeps asking."""
    _register_tool("not_run_probe_mutation")
    asked: list[object] = []

    def _confirm(payload: object) -> object:
        asked.append(payload)
        return {"action": "confirm"}

    monkeypatch.setattr(react_nodes, "interrupt", _confirm)
    token = out_of_turn_origin_ctx.set(
        RunOrigin(kind="workboard", ticket_id="t1", run_id="r1", can_carry_draft=True)
    )
    try:
        # The confirmed call RUNS, so it is consulted: a real turn publishes the
        # register; without one the gate schedules a real database write.
        with (
            installed_runtime_context(is_automated_source=True),
            treatment_collector(run_id="react-ticket-confirmation"),
        ):
            answer = _only_answer(
                await react_nodes.react_execute_tools_node(
                    _state("not_run_probe_mutation", mutation=True), {}
                )
            )
    finally:
        out_of_turn_origin_ctx.reset(token)

    assert len(asked) == 1
    assert tool_call_ran(answer)


async def test_a_repeat_the_loop_guard_blocked_is_answered_as_never_run() -> None:
    _register_tool("not_run_probe_read")
    digest = compute_call_digest("not_run_probe_read", {}, settings.secret_key)
    already = {digest: settings.react_repeated_call_block_threshold - 1}

    answer = _only_answer(
        await react_nodes.react_execute_tools_node(
            _state("not_run_probe_read", mutation=False, react_call_digests=already), {}
        )
    )

    assert answer.status == "success"
    assert not tool_call_ran(answer)


def test_the_mark_survives_the_checkpoint() -> None:
    """The graph state is checkpointed through this serializer between turns
    and around every interrupt; a mark it dropped would count the call again.
    Built as the checkpointer builds it, allowlist included."""
    from src.domains.conversations.checkpointer import _CHECKPOINT_ALLOWED_MODULES

    serde = JsonPlusSerializer(allowed_msgpack_modules=_CHECKPOINT_ALLOWED_MODULES)
    declined = ToolMessage(
        content="declined", tool_call_id="c1", name="t", artifact=TOOL_CALL_NOT_RUN
    )

    (restored,) = serde.loads_typed(serde.dumps_typed([declined]))

    assert not tool_call_ran(restored)
