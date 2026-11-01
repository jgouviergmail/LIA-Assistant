"""Every call of an iterative sub-loop owns its ledger key (spec D4).

An iterative MCP task runs a ReAct sub-agent INSIDE one pipeline step or one
ReAct call. Its inner calls used to inherit that step's scope whole, so they
shared one idempotency key: the ledger is unique on ``(thread, key)``, the
second recorded action lost its claim and was SERVED the first one's record —
measured 2026-10-29 by a probe on the real gate, a second archive never ran.

The model's call id is the natural identity of an inner call (the same one
ReAct uses, ``react_call_scope``). It must travel INSIDE the call: LangChain
prepares the arguments before it copies the context, so a ``ContextVar`` set
there would survive the call and hand its id to the next one.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.scope import EffectScope, current_scope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper
from src.domains.agents.tools.output import UnifiedToolOutput
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = [pytest.mark.unit]

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}

SERVER_KWARGS: list[dict[str, Any]] = []
SERVER_KEYS: list[str | None] = []


class _UniqueKeyLedger:
    """The repository's contract: one row per key; a lost claim is served the record."""

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


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    SERVER_KWARGS.append(dict(kwargs))
    scope = current_scope()
    SERVER_KEYS.append(scope.idempotency_key if scope else None)
    await asyncio.sleep(0.01)  # let a concurrent sibling interleave
    return UnifiedToolOutput.data_success(message="ok", structured_data={"ok": True})


def _wrapper(tool: str = "archive_note") -> _MCPReActWrapper:
    return _MCPReActWrapper(
        inner=UserMCPToolAdapter.from_discovered_tool(
            server_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            server_name="notes",
            tool_name=tool,
            description=f"{tool} on the notes server",
            input_schema=_SCHEMA,
        )
    )


def _call(wrapper: _MCPReActWrapper, call_id: str, note_id: str) -> dict[str, Any]:
    return {"name": wrapper.name, "args": {"note_id": note_id}, "id": call_id, "type": "tool_call"}


def _parent(*, approved: bool = False) -> EffectScope:
    """The scope a pipeline step publishes around the task tool (parallel_executor)."""
    return EffectScope(run_id="run-1", idempotency_key="step-1", source="user", approved=approved)


@pytest.fixture(autouse=True)
def _turn() -> Iterator[None]:
    SERVER_KWARGS.clear()
    SERVER_KEYS.clear()
    gate_runtime.reset_policy_cache()
    sink = AsyncMock()
    with (
        installed_shared_mcp_access() as actor,
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=actor.id,
                thread_id="thread-sub-loop",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.runtime.record_integrity_event", sink),
        patch("src.domains.agents.effects.treatments.record_integrity_event", sink),
        patch.object(UserMCPToolAdapter, "_call_server", new=_server),
        treatment_collector(run_id="sub-loop"),
    ):
        yield


def _policy(value: str | None) -> Any:
    return patch.object(gate_runtime, "resolve_policy", lambda _name: value)


class TestEachInnerCallOwnsItsKey:
    async def test_two_inner_reversible_calls_both_run(self) -> None:
        archive, label = _wrapper("archive_note"), _wrapper("label_note")
        ledger = _UniqueKeyLedger()
        with (
            _policy("reversible"),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_parent()),
        ):
            await archive.ainvoke(_call(archive, "c1", "n3"))
            await label.ainvoke(_call(label, "c2", "n4"))

        assert set(ledger.keys) == {"step-1:sub:c1", "step-1:sub:c2"}
        assert [kwargs["note_id"] for kwargs in SERVER_KWARGS] == [
            "n3",
            "n4",
        ], "the second action lost its claim to the first one's key"

    async def test_concurrent_inner_calls_get_distinct_keys(self) -> None:
        archive = _wrapper()
        ledger = _UniqueKeyLedger()
        with (
            _policy("reversible"),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_parent()),
        ):
            await asyncio.gather(
                archive.ainvoke(_call(archive, "cA", "n3")),
                archive.ainvoke(_call(archive, "cB", "n4")),
            )

        assert sorted(ledger.keys) == ["step-1:sub:cA", "step-1:sub:cB"]
        assert sorted(SERVER_KEYS) == ["step-1:sub:cA", "step-1:sub:cB"]
        assert len(SERVER_KWARGS) == 2

    async def test_no_stale_id_after_a_call(self) -> None:
        archive = _wrapper()
        ledger = _UniqueKeyLedger()
        with (
            _policy("reversible"),
            patch.object(gate_runtime, "_LEDGER", ledger),
            effect_scope(_parent()),
        ):
            await archive.ainvoke(_call(archive, "cA", "n3"))
            await archive._arun(note_id="n4")

        assert ledger.keys[0] == "step-1:sub:cA"
        assert ledger.keys[1].startswith("step-1:sub:")
        assert ledger.keys[1] != "step-1:sub:cA", "a stale call id outlived its call"
        assert len(SERVER_KWARGS) == 2

    async def test_the_private_key_never_reaches_the_server(self) -> None:
        from src.domains.agents.tools.mcp_react_tools import _SUB_CALL_ID_KWARG

        archive = _wrapper()
        with (
            _policy("reversible"),
            patch.object(gate_runtime, "_LEDGER", _UniqueKeyLedger()),
            effect_scope(_parent()),
        ):
            await archive.ainvoke(_call(archive, "cA", "n3"))

        assert SERVER_KWARGS == [{"note_id": "n3"}]
        assert all(_SUB_CALL_ID_KWARG not in kwargs for kwargs in SERVER_KWARGS)


class TestTheChildScope:
    def test_it_derives_the_key_and_keeps_every_other_field(self) -> None:
        from src.domains.agents.effects.scope import sub_call_scope

        parent = EffectScope(
            run_id="run-1",
            idempotency_key="call:draft_9",
            source="scheduled",
            approved=True,
            approval_kind="draft_critique",
            approval_ref="draft_9",
            draft_digest="d1",
        )
        child = sub_call_scope(parent, "cA")

        assert child is not None
        assert child.idempotency_key == "call:draft_9:sub:cA"
        assert (child.run_id, child.source, child.approved) == ("run-1", "scheduled", True)
        assert (child.approval_kind, child.approval_ref, child.draft_digest) == (
            "draft_critique",
            "draft_9",
            "d1",
        )

    def test_a_missing_call_id_never_reuses_a_key(self) -> None:
        from src.domains.agents.effects.scope import sub_call_scope

        first, second = sub_call_scope(_parent(), None), sub_call_scope(_parent(), None)

        assert first is not None and second is not None
        assert first.idempotency_key.startswith("step-1:sub:")
        assert first.idempotency_key != second.idempotency_key

    def test_no_parent_scope_publishes_none(self) -> None:
        from src.domains.agents.effects.scope import sub_call_scope

        assert sub_call_scope(None, "x") is None

    async def test_child_inherits_approval_only_from_parent(self) -> None:
        archive = _wrapper("delete_note")
        approved_ledger, refused_ledger = _UniqueKeyLedger(), _UniqueKeyLedger()
        with _policy("confirm"):
            with (
                patch.object(gate_runtime, "_LEDGER", approved_ledger),
                effect_scope(_parent(approved=True)),
            ):
                await archive.ainvoke(_call(archive, "cA", "n2"))
            with (
                patch.object(gate_runtime, "_LEDGER", refused_ledger),
                effect_scope(_parent(approved=False)),
            ):
                await archive.ainvoke(_call(archive, "cB", "n2"))

        assert approved_ledger.keys == ["step-1:sub:cA"]
        assert refused_ledger.keys == [], "an unapproved confirm call must not be claimed"
        assert SERVER_KWARGS == [{"note_id": "n2"}], "only the approved call may reach the server"

    async def test_no_parent_scope_leaves_the_call_unscoped(self) -> None:
        archive = _wrapper()
        with _policy(None), patch.object(gate_runtime, "_LEDGER", _UniqueKeyLedger()):
            await archive.ainvoke(_call(archive, "cA", "n3"))

        assert SERVER_KEYS == [None]
