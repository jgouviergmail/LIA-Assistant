"""The chat turn ends its setup transaction and archives the request BEFORE any MCP wait.

Preparing the person's MCP servers can wait on a remote server for seconds
(p95 19 s measured in production, spec 2026-10-21 §0ter). It used to run inside
the setup transaction — the connection sat ``idle in transaction`` for the
whole wait (ADR-304) — and before the archive-first row, so the person's own
message reached their other tabs only after the slowest server answered.

These tests drive the real ``AgentService`` generator through the
characterization harness and read the ORDER in which its collaborators were
reached; a duration alone would prove nothing.
"""

from __future__ import annotations

import pytest

from tests.agents.test_agent_service_stream_characterization import (
    Harness,
    _router,
    _token,
    _types,
)


def _index(events: list[str], name: str) -> int:
    assert name in events, f"{name!r} never happened: {events}"
    return events.index(name)


@pytest.mark.asyncio
async def test_archive_first_precedes_mcp_preparation() -> None:
    """The person's request is archived before any server is prepared."""
    harness = Harness(script=[_router("conversation"), _token("Bonjour")])
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == ["router_decision", "token", "done"]
    assert _index(harness.events, "state") < _index(harness.events, "archive:user")
    assert _index(harness.events, "archive:user") < _index(harness.events, "mcp_setup")


@pytest.mark.asyncio
async def test_setup_transaction_committed_before_mcp_preparation() -> None:
    """The setup session commits before the first MCP await, so nothing waits in a transaction."""
    harness = Harness(script=[_router("conversation"), _token("Bonjour")])
    with pytest.MonkeyPatch.context() as mp:
        await harness.run(mp)

    assert _index(harness.events, "db_commit") < _index(harness.events, "mcp_setup")


@pytest.mark.asyncio
async def test_stale_hitl_decision_skips_mcp_preparation() -> None:
    """A stale one-click decision stops the turn before any server is contacted or any row written."""
    harness = Harness(
        script=[_router("conversation"), _token("never streamed")],
        original_run_id="run-stale-decision",
        stale_hitl=True,
    )
    with pytest.MonkeyPatch.context() as mp:
        chunks = await harness.run(mp)

    assert _types(chunks) == ["error", "done"]
    assert chunks[0].metadata["error_code"] == "hitl_decision_stale"
    assert "mcp_setup" not in harness.events
    assert harness.conv_service.archived == []


@pytest.mark.asyncio
async def test_archive_happens_once_on_hitl_resumption() -> None:
    """A resumption archives the answer once, flagged, before the preparation."""
    harness = Harness(
        script=[_router("actionable"), _token("Fait")],
        original_run_id="run-original-hitl",
        state={"messages": [], "metadata": {}, "_interrupt_resume_data": {"decision": "approved"}},
    )
    with pytest.MonkeyPatch.context() as mp:
        await harness.run(mp)

    user_rows = [row for row in harness.conv_service.archived if row[0] == "user"]
    assert len(user_rows) == 1
    assert user_rows[0][2]["hitl_response"] is True
    assert harness.events.count("archive:user") == 1
    assert _index(harness.events, "archive:user") < _index(harness.events, "mcp_setup")
