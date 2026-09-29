"""A paid native decision is filed even when the remaining meeting work fails."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.agents.effects.models import DecisionOutcome
from src.domains.meetings import native_spend

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("paid", [True, False])
@pytest.mark.parametrize("outcome", list(DecisionOutcome))
async def test_finalize_files_only_native_spend_with_actual_outcome(monkeypatch, paid, outcome):
    db = AsyncMock()
    db.scalar.return_value = paid

    @asynccontextmanager
    async def context():
        yield db

    writer = AsyncMock()
    monkeypatch.setattr(native_spend, "get_db_context", context)
    monkeypatch.setattr(native_spend, "record_decision_once", writer, raising=False)
    owner = uuid4()
    await native_spend.finalize_native_meeting_run(owner, "run", outcome)
    if not paid:
        writer.assert_not_awaited()
        return
    decision = writer.await_args.args[0]
    assert decision.user_id == owner and decision.run_id == "run"
    assert decision.outcome == outcome and decision.source == "user"
    assert decision.route == "meeting"


async def test_finalize_does_not_break_processing_when_ledger_is_unavailable(monkeypatch):
    @asynccontextmanager
    async def context():
        raise ConnectionError("offline")
        yield

    monkeypatch.setattr(native_spend, "get_db_context", context)
    await native_spend.finalize_native_meeting_run(uuid4(), "run", DecisionOutcome.FAILED)
