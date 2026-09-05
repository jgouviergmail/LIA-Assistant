"""A gated tool call becomes a ledger row, against a real PostgreSQL (ADR-263).

The unit tests prove the ORDER of operations with a stubbed ledger; this proves
the whole chain actually works: registration installs the gate, the executor
publishes a scope, the gate claims through its own committed session, the tool
runs, and the row closes carrying what came back.

It is also where the founding defect is pinned END TO END: the same approval,
replayed, performs the effect once.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.tools import StructuredTool
from sqlalchemy import select

from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.tools import tool_registry
from src.domains.users.models import User

pytestmark = pytest.mark.integration

CALLS: list[dict[str, Any]] = []


async def _switch_light(room: str = "Salon") -> dict[str, Any]:
    """A reversible mutation that reports a provider identifier."""
    CALLS.append({"room": room})
    return {"success": True, "data": {"id": f"hue-{len(CALLS)}"}}


@pytest.fixture
async def maker(async_engine: Any) -> Any:
    """Sessions of our own.

    The gate claims through ``get_db_context()`` — its OWN connection, on
    purpose, because the claim must be committed before the effect. The suite's
    shared ``async_session`` runs inside a transaction it rolls back, so a user
    created there is invisible to that connection and the row it writes is
    invisible here. This test therefore owns its data end to end.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def user(maker: Any) -> Any:
    from sqlalchemy import delete

    row = User(
        email=f"gate-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Gate Owner",
    )
    async with maker() as session:
        session.add(row)
        await session.commit()
    yield row
    async with maker() as session:
        await session.execute(delete(User).where(User.id == row.id))
        await session.commit()


@pytest.fixture
def gated_tool() -> StructuredTool:
    """A tool registered the way production registers one — gate included."""
    CALLS.clear()
    name = f"e2e_light_{uuid.uuid4().hex[:6]}_tool"
    tool = StructuredTool.from_function(
        coroutine=_switch_light, name=name, description="switch a light"
    )
    tool_registry.register_external_tool(tool)
    return tool


def _as_user(user: User) -> Any:
    """Patch the run context so the gate knows who is acting."""
    return patch(
        "src.domains.agents.context.runtime_context.runtime_context_if_running",
        return_value=SimpleNamespace(
            user_id=user.id,
            thread_id="thread-e2e",
            execution_mode="react",
            is_automated_source=False,
        ),
    )


def _policy(value: str) -> Any:
    from src.domains.agents.effects import runtime as gate_runtime

    return patch.object(gate_runtime, "resolve_policy", lambda _name: value)


async def _rows(maker: Any, tool_name: str) -> list[AgentEffect]:
    """Read the ledger through a fresh connection, like an operator would."""
    async with maker() as session:
        result = await session.execute(
            select(AgentEffect).where(AgentEffect.tool_name == tool_name)
        )
        return list(result.scalars().all())


class TestAnEffectBecomesARow:
    async def test_a_reversible_call_is_claimed_run_and_closed(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        scope = EffectScope(run_id="run-e2e", idempotency_key="call-1", source="user")

        with _as_user(user), _policy("reversible"), effect_scope(scope):
            result = await gated_tool.coroutine(room="Salon")

        assert result["success"] is True
        assert CALLS == [{"room": "Salon"}]

        rows = await _rows(maker, gated_tool.name)
        assert len(rows) == 1
        row = rows[0]
        assert row.status is EffectStatus.SUCCEEDED
        assert row.mutation_policy == "reversible"
        assert row.idempotency_key == "call-1"
        assert row.run_id == "run-e2e"
        assert row.provider_ref == "hue-1"
        assert row.closed_at is not None

    async def test_the_same_approval_performs_the_effect_once(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        """The founding defect, pinned end to end."""
        scope = EffectScope(run_id="run-e2e", idempotency_key="call-replay", source="user")

        with _as_user(user), _policy("reversible"), effect_scope(scope):
            first = await gated_tool.coroutine(room="Salon")
            second = await gated_tool.coroutine(room="Salon")

        assert len(CALLS) == 1, "the light must not be switched twice"
        assert first["success"] is True
        assert second == first, "the replay is served from the ledger"
        assert len(await _rows(maker, gated_tool.name)) == 1

    async def test_a_read_leaves_no_trace(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        scope = EffectScope(run_id="run-e2e", idempotency_key="call-read", source="user")

        with _as_user(user), _policy("read"), effect_scope(scope):
            await gated_tool.coroutine(room="Salon")

        assert CALLS == [{"room": "Salon"}]
        assert await _rows(maker, gated_tool.name) == []


class TestAnUnconfirmedEffectNeverHappens:
    async def test_a_confirm_without_approval_asks_and_records_the_refusal(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        """H2: an MCP tool whose server demands confirmation, in the pipeline.

        It used to run UNCONFIRMED. It now comes back as a draft the user can
        answer — asking, not failing — and the fact that nothing was performed
        is recorded either way.
        """
        scope = EffectScope(run_id="run-e2e", idempotency_key="call-unconfirmed", source="user")

        with _as_user(user), _policy("confirm"), effect_scope(scope):
            result = await gated_tool.coroutine(room="Salon")

        assert CALLS == [], "the tool must not have run"
        payload = result.model_dump()
        assert payload["metadata"]["requires_confirmation"] is True
        assert payload["metadata"]["draft_type"] == "tool_call"

        rows = await _rows(maker, gated_tool.name)
        assert len(rows) == 1
        assert rows[0].status is EffectStatus.REFUSED
        assert rows[0].error_code == "confirmation_missing"

    async def test_the_confirmed_replay_performs_the_effect_exactly_once(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        """The whole cycle: asked, answered, replayed — and only once."""
        from src.domains.agents.effects.confirmation import execute_tool_call_draft

        scope = EffectScope(run_id="run-e2e", idempotency_key="call-cycle", source="user")
        with _as_user(user), _policy("confirm"), effect_scope(scope):
            asked = await gated_tool.coroutine(room="Salon")
        draft_id = asked.model_dump()["metadata"]["draft_id"]

        approved = EffectScope(
            run_id="run-e2e",
            idempotency_key=f"draft:{draft_id}",
            source="user",
            approved=True,
            approval_kind="draft_critique",
            approval_ref=draft_id,
        )
        content = {"tool_name": gated_tool.name, "tool_args": {"room": "Salon"}}
        with _as_user(user), _policy("confirm"), effect_scope(approved):
            first = await execute_tool_call_draft(content, user.id, None)
            second = await execute_tool_call_draft(content, user.id, None)

        assert len(CALLS) == 1, "one confirmation, one effect"
        assert first["success"] is True
        assert second == first, "the replay is served from the ledger"

        performed = [r for r in await _rows(maker, gated_tool.name) if r.approval_ref == draft_id]
        assert len(performed) == 1
        assert performed[0].status is EffectStatus.SUCCEEDED
        assert performed[0].mutation_policy == "confirm"

    async def test_a_confirmed_effect_runs_and_records_its_authority(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        scope = EffectScope(
            run_id="run-e2e",
            idempotency_key="call-confirmed",
            source="user",
            approved=True,
            approval_kind="tool_confirmation",
            approval_ref="msg-42",
        )

        with _as_user(user), _policy("confirm"), effect_scope(scope):
            result = await gated_tool.coroutine(room="Salon")

        assert CALLS == [{"room": "Salon"}]
        assert result["success"] is True

        rows = await _rows(maker, gated_tool.name)
        assert len(rows) == 1
        assert rows[0].status is EffectStatus.SUCCEEDED
        assert rows[0].approval_kind == "tool_confirmation"
        assert rows[0].approval_ref == "msg-42"

    async def test_an_unattended_turn_is_refused_with_its_own_reason(
        self, maker: Any, user: User, gated_tool: StructuredTool
    ) -> None:
        scope = EffectScope(run_id="run-e2e", idempotency_key="call-scheduled", source="scheduled")

        with _as_user(user), _policy("confirm"), effect_scope(scope):
            result = await gated_tool.coroutine(room="Salon")

        assert CALLS == []
        assert result["success"] is False
        rows = await _rows(maker, gated_tool.name)
        assert rows[0].error_code == "confirmation_impossible_unattended"
        assert rows[0].source.value == "scheduled"
