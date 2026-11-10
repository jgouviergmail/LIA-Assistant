"""The person's switch reaches every habits reader outside the nightly job.

Measured 2026-09-11 (sim C5): with « Apprendre mes habitudes » OFF, a live
turn still wrote the ledger. The gate is read where the learning happens and
fails CLOSED.
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


class TestReadLearningGate:
    async def test_switch_on_opens_the_gate(self) -> None:
        ctx, session = _db(True)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            gate = await read_learning_gate(str(uuid.uuid4()))
        assert gate == LearningGate(allowed=True)
        assert session.scalar.await_count == 1

    async def test_switch_off_closes_it(self) -> None:
        ctx, _ = _db(False)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            assert await read_learning_gate(uuid.uuid4()) == CLOSED

    async def test_unknown_account_is_closed(self) -> None:
        ctx, _ = _db(None)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            assert await read_learning_gate(uuid.uuid4()) == CLOSED

    async def test_a_failed_read_is_closed_not_raised(self) -> None:
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(side_effect=RuntimeError("db down"))
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("src.infrastructure.database.get_db_context", return_value=ctx):
            assert await read_learning_gate(uuid.uuid4()) == CLOSED

    async def test_a_malformed_user_id_is_closed(self) -> None:
        assert await read_learning_gate("not-a-uuid") == CLOSED
