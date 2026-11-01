"""Two acts of one iterative task are two ledger rows, on a real PostgreSQL (spec D4).

The unit tests prove the keys; this proves the repository's own uniqueness on
``(thread_id, idempotency_key)`` no longer swallows the second act of a task —
the measured defect of 2026-10-29 — and that replaying the same inner call id
still performs the act once.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.agents.tools.mcp_react_tools import _MCPReActWrapper
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.users.models import User
from src.infrastructure.mcp.user_tool_adapter import UserMCPToolAdapter
from tests.helpers.mcp_access import installed_shared_mcp_access

pytestmark = pytest.mark.integration

_SCHEMA: dict[str, Any] = {"type": "object", "properties": {"note_id": {"type": "string"}}}
SENT: list[dict[str, Any]] = []


async def _server(self: UserMCPToolAdapter, **kwargs: Any) -> UnifiedToolOutput:
    SENT.append(dict(kwargs))
    return UnifiedToolOutput.data_success(message="archived", structured_data={"ok": True})


@pytest.fixture
async def maker(async_engine: Any) -> Any:
    """Sessions of our own — the gate claims on its own committed connection."""
    from sqlalchemy.ext.asyncio import async_sessionmaker

    return async_sessionmaker(async_engine, expire_on_commit=False)


@pytest.fixture
async def user(maker: Any) -> Any:
    row = User(
        email=f"subloop-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Sub Loop Owner",
    )
    async with maker() as session:
        session.add(row)
        await session.commit()
    yield row
    async with maker() as session:
        await session.execute(delete(User).where(User.id == row.id))
        await session.commit()


def _wrapper(user_id: uuid.UUID, server_id: uuid.UUID) -> _MCPReActWrapper:
    return _MCPReActWrapper(
        inner=UserMCPToolAdapter.from_discovered_tool(
            server_id=server_id,
            user_id=user_id,
            server_name="notes",
            tool_name="archive_note",
            description="Archive a note",
            input_schema=_SCHEMA,
        )
    )


def _call(wrapper: _MCPReActWrapper, call_id: str, note_id: str) -> dict[str, Any]:
    return {"name": wrapper.name, "args": {"note_id": note_id}, "id": call_id, "type": "tool_call"}


async def _rows(maker: Any, tool_name: str) -> list[AgentEffect]:
    async with maker() as session:
        result = await session.execute(
            select(AgentEffect)
            .where(AgentEffect.tool_name == tool_name)
            .order_by(AgentEffect.idempotency_key)
        )
        return list(result.scalars().all())


class TestTwoActsOfOneTaskAreTwoRows:
    async def test_each_inner_call_is_claimed_performed_and_closed(
        self, maker: Any, user: User
    ) -> None:
        SENT.clear()
        archive = _wrapper(user.id, uuid.uuid4())
        step = EffectScope(run_id="run-subloop", idempotency_key="run-subloop:step:s1")
        with (
            installed_shared_mcp_access(actor_id=user.id),
            patch(
                "src.domains.agents.context.runtime_context.runtime_context_if_running",
                return_value=SimpleNamespace(
                    user_id=user.id,
                    thread_id=f"thread-{uuid.uuid4().hex[:8]}",
                    execution_mode="pipeline",
                    is_automated_source=False,
                    side_channel_queue=None,
                ),
            ),
            patch.object(UserMCPToolAdapter, "_call_server", new=_server),
            patch.object(gate_runtime, "resolve_policy", lambda _name: "reversible"),
            treatment_collector(run_id="run-subloop"),
            effect_scope(step),
        ):
            await archive.ainvoke(_call(archive, "c1", "n3"))
            await archive.ainvoke(_call(archive, "c2", "n4"))
            # The same inner call replayed (a node re-execution keeps the ids):
            await archive.ainvoke(_call(archive, "c1", "n3"))

        assert SENT == [{"note_id": "n3"}, {"note_id": "n4"}], "one act each, the replay served"
        rows = await _rows(maker, archive._inner.name)
        assert [row.idempotency_key for row in rows] == [
            "run-subloop:step:s1:sub:c1",
            "run-subloop:step:s1:sub:c2",
        ]
        assert all(row.status is EffectStatus.SUCCEEDED for row in rows)
        assert all(row.run_id == "run-subloop" for row in rows)
