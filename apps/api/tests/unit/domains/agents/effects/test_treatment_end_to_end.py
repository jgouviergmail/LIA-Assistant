"""The register, proven NON-EMPTY from the REAL entry point (ADR-263, lot 4).

The rule this file enforces was bought at full price. Lot 3 shipped a card that
no message ever carried, with every unit test green: they drove the MECHANISM
(the summary reader, the enricher, the component) and never the PATH, so a
``run_id`` rebuilt one layer above filed the effects under the thread id and
made every surface look empty.

So a delivered surface is proven from the entry point the application actually
uses — ``AgentService.stream_chat_response`` — and proven NON-EMPTY. The
harness is the characterization one (reused, not rebuilt), whose scripted
stream accepts a callable: that callable consults a gated capability exactly
where a tool call happens in production, inside the recorder's ``async with``.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.agents.effects import runtime as gate_runtime
from src.domains.agents.effects.treatments import Treatment
from tests.agents.test_agent_service_stream_characterization import Harness, _chunk, _router

pytestmark = [pytest.mark.unit]

RUN_ID = "run-end-to-end"


class _Recorded:
    """The repository seam, capturing what the turn actually wrote."""

    def __init__(self) -> None:
        self.rows: list[Treatment] = []

    def __call__(self, _db: Any) -> Any:
        return self

    async def record_batch(self, rows: list[Treatment]) -> int:
        self.rows.extend(rows)
        return len(rows)


class _FakeDb:
    """A session with no synthesised coroutines.

    An ``AsyncMock`` would answer every attribute with a coroutine, and the
    ones production never awaits are reported by the F028 leak guard — a real
    rule, wrongly triggered by the double.
    """

    async def commit(self) -> None:
        return None

    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None


@asynccontextmanager
async def _session() -> Any:
    yield _FakeDb()


async def _read_capability(query: str = "x") -> dict[str, Any]:
    return {"success": True, "data": {"count": 2}}


async def _failing_capability(query: str = "x") -> dict[str, Any]:
    return {"success": False, "error": "provider down"}


async def _run_turn(recorded: _Recorded, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Drive one real turn whose stream consults two capabilities.

    Args:
        recorded: The repository seam the flush writes through.
        monkeypatch: Forwarded to the characterization harness.

    Returns:
        The SSE chunks the turn produced.
    """
    reader = gate_runtime.gated("get_emails_tool", _read_capability)
    failing = gate_runtime.gated("get_calendar_events_tool", _failing_capability)

    harness = Harness(
        script=[
            _router("actionable"),
            # Where a tool call happens in production: inside the stream,
            # inside the recorder's ``async with``.
            lambda _fake: reader(query="unread"),
            lambda _fake: failing(query="today"),
            _chunk("token", content="ok", fragment="ok"),
        ],
        original_run_id=RUN_ID,
    )
    with (
        patch.object(gate_runtime, "resolve_policy", lambda _n: "read"),
        patch(
            "src.domains.agents.context.runtime_context.runtime_context_if_running",
            return_value=SimpleNamespace(
                user_id="11111111-1111-4111-8111-111111111111",
                thread_id="thread-e2e",
                execution_mode="pipeline",
                is_automated_source=False,
            ),
        ),
        patch("src.domains.agents.effects.treatment_recorder.TreatmentRepository", recorded),
        patch("src.infrastructure.database.session.get_db_context", _session),
    ):
        return await harness.run(monkeypatch)


class TestARealTurnFillsTheRegister:
    async def test_the_register_is_not_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded = _Recorded()
        chunks = await _run_turn(recorded, monkeypatch)

        assert chunks, "the turn produced no stream at all"
        assert len(recorded.rows) == 2, (
            "a real turn consulted two capabilities and the register kept " f"{len(recorded.rows)}"
        )

    async def test_it_names_the_capabilities_that_were_consulted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = _Recorded()
        await _run_turn(recorded, monkeypatch)

        assert {row.tool_name for row in recorded.rows} == {
            "get_emails_tool",
            "get_calendar_events_tool",
        }

    async def test_it_says_which_one_did_not_answer(self, monkeypatch: pytest.MonkeyPatch) -> None:
        recorded = _Recorded()
        await _run_turn(recorded, monkeypatch)

        outcomes = {row.tool_name: row.outcome for row in recorded.rows}
        assert outcomes["get_emails_tool"] == "ok"
        assert outcomes["get_calendar_events_tool"] == "failed"

    async def test_the_rows_are_filed_under_the_TURNS_run_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The lot-3 defect, pinned at the layer that produced it."""
        recorded = _Recorded()
        await _run_turn(recorded, monkeypatch)

        assert {row.run_id for row in recorded.rows} == {RUN_ID}, (
            "the register filed the turn under something other than its run — "
            "this is exactly how lot 3's card became invisible"
        )

    async def test_the_rows_belong_to_the_acting_user(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded = _Recorded()
        await _run_turn(recorded, monkeypatch)

        assert {row.user_id for row in recorded.rows} == {"11111111-1111-4111-8111-111111111111"}
        assert {row.thread_id for row in recorded.rows} == {"thread-e2e"}
