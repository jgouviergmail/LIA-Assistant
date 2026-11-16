"""The live register snapshot reaches the debug panel after its collectors close."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.turn_verdicts import note_verdict
from src.domains.agents.effects.decisions import current_turn, note_engine, note_route
from src.domains.agents.effects.treatments import Treatment, observe
from tests.agents.test_agent_service_stream_characterization import (
    CONVERSATION_ID,
    USER_ID,
    FakeStreamingService,
    Harness,
    _router,
    _token,
)

pytestmark = pytest.mark.unit


def _record_evidence(stream: FakeStreamingService) -> None:
    """Record synthetic facts in the real collectors inherited by the stream task."""
    turn = current_turn()
    assert turn is not None
    note_engine("react", "requested")
    note_route("actionable")
    observe(
        Treatment(
            user_id=str(USER_ID),
            thread_id=str(CONVERSATION_ID),
            run_id=turn.run_id,
            source="user",
            execution_mode="react",
            tool_name="get_events_tool",
            mutation_policy="read",
            outcome="ok",
            duration_ms=12,
            occurred_at=datetime.now(UTC),
        )
    )
    note_verdict("reasoning_coerced", "high->medium")


@pytest.mark.parametrize("debug_enabled", [False, True])
async def test_registers_reach_the_debug_panel_after_the_recorders_close(
    monkeypatch: pytest.MonkeyPatch, debug_enabled: bool
) -> None:
    """The real producer delivers the owned snapshot only to a permitted reader."""
    monkeypatch.setattr(
        "src.domains.system_settings.debug_access.can_read_debug",
        AsyncMock(return_value=debug_enabled),
    )
    harness = Harness(
        script=[_record_evidence, _router("actionable"), _token("Answer")],
        user_execution_mode="auto",
    )

    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    assert current_turn() is None
    assert chunks[-1].type == "done"
    snapshots = [
        chunk.metadata["registers"]
        for chunk in chunks
        if chunk.type == "debug_metrics_update" and "registers" in chunk.metadata
    ]
    if not debug_enabled:
        assert snapshots == []
        return

    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot["decision"]["execution_mode"] == "react"
    assert snapshot["decision"]["requested_mode"] == "auto"
    assert snapshot["decision"]["outcome"] == "answered"
    assert snapshot["decision"]["settled"] is False
    assert snapshot["treatments"] == {
        "entries": [
            {
                "tool_name": "get_events_tool",
                "mutation_policy": "read",
                "outcome": "ok",
                "duration_ms": 12,
            }
        ],
        "count": 1,
        "failed_count": 0,
    }
    assert snapshot["verdicts"] == {
        "entries": [{"kind": "reasoning_coerced", "detail": "high->medium"}],
        "count": 1,
        "dropped": 0,
    }


async def test_a_failed_register_snapshot_does_not_prevent_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The best-effort debug capture cannot turn an answered request into an error."""
    monkeypatch.setattr(
        "src.domains.system_settings.debug_access.can_read_debug", AsyncMock(return_value=True)
    )
    capture = Mock(side_effect=RuntimeError("synthetic snapshot failure"))
    monkeypatch.setattr(
        "src.domains.agents.services.streaming.register_debug.registers_debug", capture
    )
    harness = Harness(script=[_router("conversation"), _token("Answer")])

    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    capture.assert_called_once_with()
    assert chunks[-1].type == "done"
    assert any(role == "assistant" for role, _, _ in harness.conv_service.archived)
    assert all("registers" not in chunk.metadata for chunk in chunks)


async def test_a_stopped_stream_does_not_publish_an_unfinished_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Closing the generator during its answer still closes all recording scopes."""
    monkeypatch.setattr(
        "src.domains.system_settings.debug_access.can_read_debug", AsyncMock(return_value=True)
    )
    harness = Harness(
        script=[_record_evidence, _router("actionable"), _token("Partial")], stop_after=2
    )

    chunks = await harness.run(monkeypatch)

    assert harness.raised is None
    assert current_turn() is None
    assert [chunk.type for chunk in chunks] == ["router_decision", "token"]
    assert all(role != "assistant" for role, _, _ in harness.conv_service.archived)
