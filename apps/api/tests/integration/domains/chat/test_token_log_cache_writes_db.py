"""A call's prompt-cache writes reach its token log row — on real PostgreSQL (ADR-362).

What only the server proves: the two columns exist with the model's types, the
tracking context's row carries the counts it priced, and a caller that does not
report them leaves NULL — unknown, never a zero nobody measured.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import FIELD_COST_EUR, FIELD_MODEL_NAME, FIELD_NODE_NAME
from src.domains.chat.models import TokenUsageLog
from src.domains.chat.repository import ChatRepository
from src.domains.chat.tracking_records import TokenUsageRecord, token_log_row
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def _owner(session: AsyncSession) -> User:
    user = User(email=f"writes-{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_the_tracked_row_keeps_its_writes_and_their_extended_part(
    async_session: AsyncSession,
) -> None:
    owner = await _owner(async_session)
    run_id = f"run_{uuid.uuid4().hex}"
    record = TokenUsageRecord(
        node_name="react_call_model",
        model_name="claude-sonnet-5",
        prompt_tokens=8_000,
        completion_tokens=100,
        cached_tokens=2_000,
        cost_usd=0.05,
        cost_eur=0.045,
        usd_to_eur_rate=Decimal("0.9"),
        cache_write_tokens=5_000,
        cache_write_extended_tokens=3_800,
    )
    untracked = {
        FIELD_NODE_NAME: "legacy",
        FIELD_MODEL_NAME: "claude-sonnet-5",
        "prompt_tokens": 10,
        "completion_tokens": 1,
        "cached_tokens": 0,
        "cost_usd": 0.0,
        FIELD_COST_EUR: 0.0,
    }

    await ChatRepository(async_session).bulk_create_token_logs(
        run_id=run_id, user_id=owner.id, logs=[token_log_row(record), untracked]
    )
    await async_session.flush()

    rows = {
        row.node_name: row
        for row in (
            await async_session.execute(select(TokenUsageLog).where(TokenUsageLog.run_id == run_id))
        ).scalars()
    }
    tracked = rows["react_call_model"]
    assert (tracked.cache_write_tokens, tracked.cache_write_extended_tokens) == (5_000, 3_800)
    assert (rows["legacy"].cache_write_tokens, rows["legacy"].cache_write_extended_tokens) == (
        None,
        None,
    )
