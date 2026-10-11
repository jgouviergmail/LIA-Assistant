"""Readers recheck consent even when their SQLAlchemy identity map is warm."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker

from src.core.config import settings
from src.domains.journals import context_builder, portrait_builder
from src.domains.journals import router as journal_router
from src.domains.journals.models import JournalEntry
from src.domains.journals.source_state import portrait_source_state
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]
VECTOR = [1.0] + [0.0] * 1535


@pytest.mark.parametrize("reader", ["context", "portrait", "api"])
async def test_reader_refuses_externally_disabled_consent_with_warm_identity_map(
    async_engine, committed_user_ids, monkeypatch, reader
):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    provider = SimpleNamespace(aembed_query=AsyncMock(side_effect=AssertionError("paid provider")))
    monkeypatch.setattr(settings, "journals_enabled", True)
    monkeypatch.setattr(settings, "journal_context_recent_entries", 0)
    monkeypatch.setattr(settings, "memory_embedding_model", "models/gemini-embedding-001")
    monkeypatch.setattr(settings, "journal_embedding_model", "models/gemini-embedding-001")
    monkeypatch.setattr(settings, "memory_embedding_dimensions", 1536)
    monkeypatch.setattr(settings, "journal_embedding_dimensions", 1536)
    monkeypatch.setattr(context_builder, "is_capability_enabled", AsyncMock(return_value=True))
    monkeypatch.setattr(context_builder, "effective_threshold", AsyncMock(return_value=0.63))
    monkeypatch.setattr(context_builder, "observe_score", AsyncMock())
    monkeypatch.setattr(context_builder, "track_injected_entries", Mock())
    monkeypatch.setattr("src.domains.journals.embedding.get_journal_embeddings", lambda: provider)
    monkeypatch.setattr(portrait_sources, "_REGISTRY", {})
    async with factory() as seed:
        user = User(
            email=f"journal-reader-{uuid4().hex}@example.test",
            hashed_password="x",
            journals_enabled=True,
            is_active=True,
            journal_portrait_compiled_at=datetime.now(UTC),
            journal_portrait_full="Grounded rule",
            journal_portrait_brief="Grounded rule",
        )
        seed.add(user)
        await seed.flush()
        committed_user_ids.append(user.id)
        user.journal_portrait_sources = {
            "journal_revision": user.journal_revision,
            "source_state": await portrait_source_state(seed, user),
        }
        seed.add(
            JournalEntry(
                user_id=user.id,
                theme="learnings",
                title="Compare alternatives",
                content="WHEN choosing -> DO compare alternatives",
                char_count=39,
                source="conversation",
                status="active",
                level="L1",
                confidence="medium",
                embedding=VECTOR,
                evidence_count=0,
                contradiction_count=0,
            )
        )
        await seed.commit()
        user_id = user.id

    async with factory() as cached, factory() as writer:
        warm_user = await cached.get(User, user_id)
        if reader == "context":
            before = await context_builder.build_journal_context(
                user_id, "choosing", cached, query_embedding=VECTOR
            )
            assert before[0] and before[2]
        elif reader == "portrait":
            assert await portrait_builder._read_current_portrait(cached, user_id, "full")
        else:
            assert (await journal_router.get_portrait(user=warm_user, db=cached)).full
        await writer.execute(update(User).where(User.id == user_id).values(journals_enabled=False))
        await writer.commit()
        assert (
            warm_user.journals_enabled is True
        )  # Retained object demonstrates the stale snapshot.
        default_read = (await cached.execute(select(User).where(User.id == user_id))).scalar_one()
        assert default_read is warm_user and default_read.journals_enabled is True
        if reader == "context":
            assert await context_builder.build_journal_context(
                user_id, "choosing", cached, query_embedding=VECTOR
            ) == (None, None, [])
        elif reader == "portrait":
            assert await portrait_builder._read_current_portrait(cached, user_id, "full") is None
        else:
            result = await journal_router.get_portrait(user=warm_user, db=cached)
            assert result.full is result.brief is result.compiled_at is result.sources is None
    provider.aembed_query.assert_not_awaited()
