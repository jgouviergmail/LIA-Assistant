"""Raw L0 corrections preserve user input without provider work under locks."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.domains.journals.feedback_hooks import JournalResponseFeedbackHooks
from src.domains.journals.repository import JournalEntryRepository
from src.domains.journals.service import JournalService
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.mark.parametrize("prefix_length", [0, 1150])
async def test_complete_raw_correction_is_stored_without_any_provider_call(
    async_engine, monkeypatch, prefix_length
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    provider = AsyncMock(side_effect=AssertionError("Raw L0 feedback must not call a provider"))
    monkeypatch.setattr("src.domains.journals.service._generate_dual_embeddings", provider)
    monkeypatch.setattr(
        "src.domains.journals.feedback_hooks.is_capability_enabled", AsyncMock(return_value=True)
    )
    async with factory() as db:
        user = User(
            email=f"raw-feedback-{uuid4().hex}@example.test",
            hashed_password="synthetic",
            journals_enabled=True,
            is_active=True,
        )
        db.add(user)
        await db.commit()
        user_id = user.id
    tail = " Keep this instruction limited to the current task."
    correction = "x" * prefix_length + tail
    try:
        async with factory() as db:
            await JournalResponseFeedbackHooks().record_correction(db, user_id, correction)
            await db.commit()
        async with factory() as db:
            entries = await JournalService(db).get_all_active(user_id)
            assert len(entries) == 1
            entry = entries[0]
            assert entry.content == correction and entry.content.endswith(tail)
            assert entry.level == "L0" and entry.source == "user_correction"
            assert entry.embedding is entry.keyword_embedding is None
            assert entry.evidence_count == entry.contradiction_count == entry.injection_count == 0
            assert (
                await JournalEntryRepository(db).get_recent_for_user(
                    user_id, exclude_levels=["L0", "L3"], operational_only=True
                )
                == []
            )
        provider.assert_not_awaited()
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
