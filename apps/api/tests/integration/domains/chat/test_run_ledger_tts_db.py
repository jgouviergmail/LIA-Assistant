"""Paid speech synthesis on the run's own row — on real PostgreSQL (ADR-324).

What only a server proves: a run's speech accumulates by column arithmetic
across its commits (a radio session commits once per production), the billed
figure carries it in Python and in SQL alike, and the upgrade's backfill sums
the bubbles per run without inventing a row. The schema this suite builds is
the post-upgrade one, so the backfill is run as the migration's own statement.
"""

from __future__ import annotations

import importlib.util
import uuid
from decimal import Decimal
from pathlib import Path
from types import ModuleType

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.field_names import (
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_COST_EUR,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
    FIELD_TTS_CHARACTERS,
    FIELD_TTS_COST_EUR,
)
from src.domains.chat.models import MessageTokenSummary
from src.domains.chat.repository import ChatRepository
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_09_26_1500-d79c9fc26844_tts_on_the_run_ledger.py"
)


def _load_migration() -> ModuleType:
    """The migration module itself, so its backfill SQL is what gets proven."""
    spec = importlib.util.spec_from_file_location("tts_on_the_run_ledger", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _commit(**families: float) -> dict[str, float]:
    """One commit's summary: no tokens, the families given."""
    return {
        FIELD_TOKENS_IN: 0,
        FIELD_TOKENS_OUT: 0,
        FIELD_TOKENS_CACHE: 0,
        FIELD_COST_EUR: families.pop(FIELD_COST_EUR, 0.0),
        **families,
    }


async def _owner(session: AsyncSession) -> User:
    user = User(email=f"ledger-{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_a_runs_speech_accumulates_on_its_row_and_is_billed(
    async_session: AsyncSession,
) -> None:
    owner = await _owner(async_session)
    repo = ChatRepository(async_session)
    run_id = f"radio_{uuid.uuid4().hex}"

    # Two productions of one session, each committing what it spent.
    await repo.create_or_update_token_summary(
        run_id=run_id,
        user_id=owner.id,
        session_id=run_id,
        conversation_id=None,
        summary_data=_commit(
            **{FIELD_COST_EUR: 0.002, FIELD_TTS_CHARACTERS: 1200, FIELD_TTS_COST_EUR: 0.018}
        ),
    )
    row = await repo.create_or_update_token_summary(
        run_id=run_id,
        user_id=owner.id,
        session_id=run_id,
        conversation_id=None,
        summary_data=_commit(
            **{
                FIELD_GOOGLE_API_COST_EUR: 0.001,
                FIELD_TTS_CHARACTERS: 800,
                FIELD_TTS_COST_EUR: 0.012,
            }
        ),
    )
    await async_session.refresh(row)

    assert (row.tts_characters, row.tts_cost_eur) == (2000, Decimal("0.030000"))
    assert row.billed_cost_eur == Decimal("0.033000")
    billed_in_sql = (
        await async_session.execute(
            select(MessageTokenSummary.billed_cost_sql()).where(
                MessageTokenSummary.run_id == run_id
            )
        )
    ).scalar_one()
    assert billed_in_sql == row.billed_cost_eur


async def test_the_backfill_sums_the_bubbles_per_run_and_invents_nothing(
    async_session: AsyncSession,
) -> None:
    owner = await _owner(async_session)
    conversation = Conversation(user_id=owner.id)
    async_session.add(conversation)
    await async_session.flush()
    resumed, silent = (f"run-{uuid.uuid4().hex}" for _ in range(2))
    orphan = f"run-{uuid.uuid4().hex}"
    for run_id in (resumed, silent):
        async_session.add(
            MessageTokenSummary(
                user_id=owner.id, session_id="s", run_id=run_id, conversation_id=conversation.id
            )
        )

    def bubble(run_id: str, provider: str | None, characters: int, cost: str) -> None:
        async_session.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="assistant",
                content="An answer read aloud.",
                message_metadata={"run_id": run_id},
                tts_provider=provider,
                tts_characters=characters if provider else None,
                tts_cost_eur=Decimal(cost) if provider else None,
            )
        )

    # A turn resumed after a question keeps its run id: two bubbles, one row.
    bubble(resumed, "openai", 300, "0.004500")
    bubble(resumed, "openai", 100, "0.001500")
    bubble(silent, None, 0, "0")  # a free engine records nothing
    bubble(orphan, "openai", 50, "0.000750")  # its run has no row
    await async_session.flush()

    await async_session.execute(text(_load_migration().BACKFILL_STATEMENT))

    rows = {
        row.run_id: (row.tts_characters, row.tts_cost_eur)
        for row in (
            await async_session.execute(
                select(MessageTokenSummary).where(MessageTokenSummary.user_id == owner.id)
            )
        ).scalars()
    }
    assert rows == {resumed: (400, Decimal("0.006000")), silent: (0, Decimal("0"))}
    orphan_rows = (
        await async_session.execute(
            select(func.count())
            .select_from(MessageTokenSummary)
            .where(MessageTokenSummary.run_id == orphan)
        )
    ).scalar_one()
    assert orphan_rows == 0
