"""Unit tests for TrackingContext.__aexit__ persistence semantics (ADR-117).

Records present at exit correspond to LLM calls that actually happened
(and were billed by the provider). They must be persisted whatever the
exit path: normal, exception, or task cancellation. Before ADR-117 Lot 1,
an interrupted run silently dropped its pending records (billing leak).
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.domains.chat.service import TrackingContext


def _make_tracker(auto_commit: bool = True) -> TrackingContext:
    tracker = TrackingContext(
        run_id="run_test",
        user_id=uuid.uuid4(),
        session_id="session_test",
        conversation_id=uuid.uuid4(),
        auto_commit=auto_commit,
    )
    # One pending record so __aexit__ has something to persist
    # (__aexit__ only checks len(); the record content is never touched
    # because _persist_to_database is mocked).
    tracker._node_records.append(MagicMock())
    tracker._persist_to_database = AsyncMock()  # type: ignore[method-assign]
    return tracker


@pytest.mark.unit
class TestTrackingContextExitPersistence:
    async def test_persists_on_normal_exit(self):
        tracker = _make_tracker()
        await tracker.__aexit__(None, None, None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_persists_on_exception(self):
        tracker = _make_tracker()
        await tracker.__aexit__(RuntimeError, RuntimeError("boom"), None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_persists_on_cancellation(self):
        tracker = _make_tracker()
        await tracker.__aexit__(asyncio.CancelledError, asyncio.CancelledError(), None)
        tracker._persist_to_database.assert_awaited_once()

    async def test_skips_when_auto_commit_disabled(self):
        tracker = _make_tracker(auto_commit=False)
        await tracker.__aexit__(None, None, None)
        tracker._persist_to_database.assert_not_awaited()

    async def test_persistence_failure_is_swallowed(self):
        # Tracking failure must never break the chat path (existing contract,
        # must hold on the new on-exception branch too).
        tracker = _make_tracker()
        tracker._persist_to_database = AsyncMock(  # type: ignore[method-assign]
            side_effect=RuntimeError("db down")
        )
        await tracker.__aexit__(RuntimeError, RuntimeError("boom"), None)
        tracker._persist_to_database.assert_awaited_once()
