"""From the gate to the sentence under the bubble, end to end (ADR-263).

Every piece of this chain has its own unit test. This one asserts that they are
actually connected — the failure mode no unit test can see, because each half
passes while the seam between them is wrong: the tool runs, the row is written,
the turn summary reads it back BY RUN, the label decrypts, and the message
metadata carries keys and values rather than a frozen sentence.

Against the real database on purpose: the encryption, the enum spellings and
the `run_id` filter are exactly what a mock would paper over.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.scope import EffectScope, effect_scope
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account the effects belong to."""
    row = User(
        email=f"chain-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Chain Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


@pytest.fixture(autouse=True)
def one_session(async_session: AsyncSession) -> Any:
    """Give the gate the TEST session instead of opening its own.

    The gate opens its own transaction in production on purpose — a claim that
    stayed inside the caller's could be rolled back after the effect happened,
    and the lot-1 integration tests prove exactly that against two real
    sessions. What THIS file proves is the chain: real repository, real SQL,
    real encryption, one session. Committing here would end the fixture's
    transaction, so the commit is a flush.
    """
    from contextlib import asynccontextmanager

    class _NoCommit:
        """The test session, minus the commit that would end the fixture."""

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        def __getattr__(self, name: str) -> Any:
            return getattr(self._session, name)

        async def commit(self) -> None:
            await self._session.flush()

    @asynccontextmanager
    async def _context() -> Any:
        yield _NoCommit(async_session)

    with patch("src.infrastructure.database.session.get_db_context", _context):
        yield


class _Capture:
    """Stands in for the turn's ``TraceCapture``."""

    @staticmethod
    def snapshot() -> list[dict[str, str]]:
        return []


async def _run_gated_tool(user: Any, run_id: str, *, succeeds: bool = True) -> Any:
    """Perform one gated effect exactly as a turn would."""

    async def _tool(room: str = "Salon") -> dict[str, Any]:
        if succeeds:
            return {"success": True, "data": {"id": "hue-1"}}
        return {"success": False, "error": "the bridge refused"}

    gated = gate_runtime.gated("control_hue_light_tool", _tool)
    with (
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id=user.id,
                thread_id=f"thread-{run_id}",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch.object(gate_runtime, "resolve_policy", lambda _n: "reversible"),
        effect_scope(EffectScope(run_id=run_id, idempotency_key=f"step:{run_id}", source="user")),
    ):
        return await gated(room="Salon")


class TestTheWholeChain:
    async def test_an_effect_reaches_the_message_as_keys_and_values(self, user: Any) -> None:
        from src.domains.agents.api.archive_metadata import build_assistant_metadata
        from src.domains.agents.effects.turn_summary import performed_effects

        run_id = f"run-chain-{uuid.uuid4().hex[:8]}"
        result = await _run_gated_tool(user, run_id)
        assert result["success"] is True, "the tool must actually run"

        entries = await performed_effects(run_id)

        assert len(entries) == 1, "the register did not report the effect of this run"
        assert entries[0]["status"] == "succeeded"
        assert entries[0]["tool_name"] == "control_hue_light_tool"
        assert entries[0]["label_key"] == "effects.labels.control_hue_light_tool"
        assert entries[0]["values"] == {"target": "Salon"}

        metadata = build_assistant_metadata(
            {"llm_calls": 1},
            widgets=None,
            trace_capture=_Capture(),
            duration_ms=1234,
            run_id=run_id,
            followup_suggestions=None,
            initiative_motivation=None,
            effects=entries,
        )

        carried = metadata["performed_effects"]
        assert carried == entries
        assert all(
            "label" not in entry for entry in carried
        ), "a translated sentence in the metadata would freeze the reader's language"

    async def test_a_failure_is_carried_as_a_failure(self, user: Any) -> None:
        """Honesty cuts both ways: the bubble states an attempt that failed."""
        from src.domains.agents.effects.turn_summary import performed_effects

        run_id = f"run-fail-{uuid.uuid4().hex[:8]}"
        await _run_gated_tool(user, run_id, succeeds=False)

        entries = await performed_effects(run_id)

        assert [entry["status"] for entry in entries] == ["failed"]

    async def test_the_same_approval_reports_ONE_effect(self, user: Any) -> None:
        """The founding defect: one approval, one execution, one line."""
        from src.domains.agents.effects.turn_summary import performed_effects

        run_id = f"run-once-{uuid.uuid4().hex[:8]}"
        await _run_gated_tool(user, run_id)
        await _run_gated_tool(user, run_id)

        entries = await performed_effects(run_id)

        assert len(entries) == 1

    async def test_a_turn_that_changed_nothing_reports_nothing(self, user: Any) -> None:
        from src.domains.agents.api.archive_metadata import build_assistant_metadata
        from src.domains.agents.effects.turn_summary import performed_effects

        entries = await performed_effects(f"run-empty-{uuid.uuid4().hex[:8]}")
        assert entries == []

        metadata = build_assistant_metadata(
            {},
            widgets=None,
            trace_capture=_Capture(),
            duration_ms=1,
            run_id="run-empty",
            followup_suggestions=None,
            initiative_motivation=None,
            effects=entries,
        )
        assert "performed_effects" not in metadata


class TestTheEndpointSeesTheSameRows:
    async def test_the_run_endpoint_returns_what_the_summary_reported(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The panel, the card and the journal must not disagree."""
        from src.domains.agents.effects.router import list_run_effects
        from src.domains.agents.effects.turn_summary import performed_effects

        run_id = f"run-endpoint-{uuid.uuid4().hex[:8]}"
        await _run_gated_tool(user, run_id)

        summary = await performed_effects(run_id)
        served = await list_run_effects(run_id, db=async_session, user=user)

        assert len(served) == len(summary) == 1
        assert served[0].label_key == summary[0]["label_key"]
        assert served[0].values == summary[0]["values"]
        assert served[0].status == summary[0]["status"]
