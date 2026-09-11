"""The person's switch and tombstones reach the chat-side detector.

Measured 2026-09-11 (sim C5): with « Apprendre mes habitudes » OFF, a live
turn still wrote the ledger and the answer still carried the automation
suggestion. Only the promotion obeyed the switch.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.habits.learning_gate import CLOSED, LearningGate, read_learning_gate

pytestmark = pytest.mark.unit


def _db(*scalars: Any) -> Any:
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=list(scalars))
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return ctx, session


class TestSuggestionAllowed:
    def test_active_or_unknown_row_allows_a_suggestion(self) -> None:
        assert LearningGate(allowed=True).suggestion_allowed
        assert LearningGate(allowed=True, recurring_status="active").suggestion_allowed

    @pytest.mark.parametrize("status", ["paused", "blocked"])
    def test_a_snoozed_or_refused_row_forbids_it(self, status: str) -> None:
        assert not LearningGate(allowed=True, recurring_status=status).suggestion_allowed

    def test_switch_off_forbids_everything(self) -> None:
        assert not CLOSED.suggestion_allowed
        assert not LearningGate(allowed=False, recurring_status="active").suggestion_allowed


class TestReadLearningGate:
    async def test_switch_off_short_circuits_before_the_tombstone_read(self) -> None:
        ctx, session = _db(False)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            gate = await read_learning_gate(uuid.uuid4(), "email")
        assert gate == CLOSED
        assert session.scalar.await_count == 1

    async def test_preference_only_when_no_signature(self) -> None:
        ctx, session = _db(True)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            gate = await read_learning_gate(str(uuid.uuid4()))
        assert gate == LearningGate(allowed=True, recurring_status=None)
        assert session.scalar.await_count == 1

    async def test_tombstone_travels_with_the_gate(self) -> None:
        ctx, _ = _db(True, "blocked")
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            gate = await read_learning_gate(uuid.uuid4(), "email")
        assert gate.allowed and gate.recurring_status == "blocked"
        assert not gate.suggestion_allowed

    async def test_unknown_account_is_closed(self) -> None:
        ctx, _ = _db(None)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            assert await read_learning_gate(uuid.uuid4(), "email") == CLOSED

    async def test_a_failed_read_is_closed_not_raised(self) -> None:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            assert await read_learning_gate(uuid.uuid4(), "email") == CLOSED

    async def test_a_malformed_user_id_is_closed(self) -> None:
        assert await read_learning_gate("not-a-uuid") == CLOSED
