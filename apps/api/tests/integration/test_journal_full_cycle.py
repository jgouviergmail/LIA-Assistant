"""Integration tests for the full stratified journal cycle (ADR-079).

Validates that the persistence layer end-to-end honors:

1. **Stratification persistence** — entries created with explicit ``level``
   and ``confidence`` round-trip through the DB.
2. **Atomic counter increments** — multiple ``evidence_outcome`` calls on
   the same entry accumulate without race-condition writes.
3. **Level promotion** — an L1 → L2 update is materialized in the DB.
4. **Portrait persistence** — the User columns are read back exactly via
   ``build_journal_user_model_block``.
5. **GDPR scrub** — ``_mark_user_deleted`` blanks out the three portrait
   fields in addition to the existing user fields.

External dependencies (Gemini embeddings, LLM calls) are stubbed out —
this test focuses on the SQL contract, not the network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.auth.models import User
from src.domains.journals.models import (
    JournalEntry,
    JournalEntryConfidence,
    JournalEntryLevel,
    JournalEntrySource,
)
from src.domains.journals.portrait_builder import build_journal_user_model_block
from src.domains.journals.service import JournalService

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


@pytest.fixture
def stubbed_embeddings():
    """Avoid the network round-trip to Gemini in every integration test.

    Returns a context-manager-like fixture that patches the dual-embedding
    helper so persistence tests don't depend on outbound HTTP.
    """
    with patch(
        "src.domains.journals.service._generate_dual_embeddings",
        AsyncMock(return_value=(None, None)),
    ):
        yield


async def _make_user(session: AsyncSession, *, journals_enabled: bool = True) -> User:
    """Create a minimal user with journals enabled by default."""
    from src.core.security import get_password_hash

    suffix = uuid4().hex[:8]
    user = User(
        email=f"journal-cycle-{suffix}@example.test",
        hashed_password=get_password_hash("TestPass123!!"),
        full_name="Journal Cycle Test User",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        journals_enabled=journals_enabled,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _make_entry(
    session: AsyncSession,
    user: User,
    *,
    level: str = JournalEntryLevel.L1.value,
    confidence: str = JournalEntryConfidence.MEDIUM.value,
    title: str = "Test directive",
    content: str = "Test directive content",
) -> JournalEntry:
    """Persist an entry directly — bypasses the LLM pipeline."""
    entry = JournalEntry(
        user_id=user.id,
        theme="user_observations",
        title=title,
        content=content,
        mood="reflective",
        status="active",
        source=JournalEntrySource.MANUAL.value,
        char_count=len(content),
        level=level,
        confidence=confidence,
        evidence_count=0,
        contradiction_count=0,
    )
    session.add(entry)
    await session.commit()
    await session.refresh(entry)
    return entry


# -----------------------------------------------------------------------------
# 1. Stratification round-trip
# -----------------------------------------------------------------------------


class TestStratificationRoundTrip:
    """Entries created with the new ADR-079 columns survive the DB round-trip."""

    async def test_entry_persists_level_and_confidence(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(
            async_session,
            user,
            level=JournalEntryLevel.L0.value,
            confidence=JournalEntryConfidence.LOW.value,
            title="Raw observation",
        )

        # Re-fetch from DB to make sure values are persisted, not just in-memory.
        fetched = await async_session.get(JournalEntry, entry.id)
        assert fetched is not None
        assert fetched.level == JournalEntryLevel.L0.value
        assert fetched.confidence == JournalEntryConfidence.LOW.value
        assert fetched.evidence_count == 0
        assert fetched.contradiction_count == 0

    async def test_default_level_is_l1_when_unspecified(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        """Legacy code that omits the level column must still work — default L1."""
        user = await _make_user(async_session)

        # Directly construct without specifying level — defaults to L1.
        entry = JournalEntry(
            user_id=user.id,
            theme="learnings",
            title="Implicit L1",
            content="No level specified at construction",
            mood="reflective",
            status="active",
            source=JournalEntrySource.MANUAL.value,
            char_count=33,
        )
        async_session.add(entry)
        await async_session.commit()
        await async_session.refresh(entry)

        assert entry.level == JournalEntryLevel.L1.value
        assert entry.confidence == JournalEntryConfidence.MEDIUM.value


# -----------------------------------------------------------------------------
# 2. Atomic counter increments
# -----------------------------------------------------------------------------


class TestAtomicIncrements:
    """Multiple evidence/contradiction signals must accumulate correctly in the DB."""

    async def test_three_evidence_signals_accumulate_to_three(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user)

        service = JournalService(async_session)

        # Signal evidence three times — each call adds exactly +1.
        for _ in range(3):
            await service.update_entry(entry, evidence_outcome="evidence")

        # Re-fetch to confirm the DB state, not just the ORM cache.
        await async_session.refresh(entry)
        assert entry.evidence_count == 3
        assert entry.contradiction_count == 0

    async def test_mixed_evidence_and_contradiction_signals(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user)
        service = JournalService(async_session)

        await service.update_entry(entry, evidence_outcome="evidence")
        await service.update_entry(entry, evidence_outcome="contradiction")
        await service.update_entry(entry, evidence_outcome="evidence")
        await service.update_entry(entry, evidence_outcome="contradiction")

        await async_session.refresh(entry)
        assert entry.evidence_count == 2
        assert entry.contradiction_count == 2


# -----------------------------------------------------------------------------
# 3. Level promotion in DB
# -----------------------------------------------------------------------------


class TestLevelPromotionPersistence:
    """A level update is materialized in the DB."""

    async def test_l1_to_l2_promotion_persists(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)
        entry = await _make_entry(async_session, user, level=JournalEntryLevel.L1.value)

        service = JournalService(async_session)
        await service.update_entry(entry, level=JournalEntryLevel.L2.value)

        # Re-fetch from a fresh statement to defeat any ORM cache.
        result = await async_session.execute(
            select(JournalEntry).where(JournalEntry.id == entry.id)
        )
        fetched = result.scalar_one()
        assert fetched.level == JournalEntryLevel.L2.value


# -----------------------------------------------------------------------------
# 4. Portrait persistence + builder round-trip
# -----------------------------------------------------------------------------


class TestPortraitPersistence:
    """The compiled portrait survives a SQL round-trip via build_journal_user_model_block."""

    async def test_full_and_brief_portraits_round_trip(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)

        # Simulate what the consolidation step does at the end of its run.
        user.journal_portrait_full = "Full portrait body — multiple facets here."
        user.journal_portrait_brief = "Brief portrait body — essence in 2 sentences."
        async_session.add(user)
        await async_session.commit()

        # The portrait_builder owns its own session via get_db_context — patch
        # it to reuse our test session so we read the same DB.
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _ctx():
            yield async_session

        with (
            patch("src.domains.journals.portrait_builder.get_db_context", new=_ctx),
            patch(
                "src.domains.journals.portrait_builder.settings",
                type("S", (), {"journals_enabled": True})(),
            ),
        ):
            full_block = await build_journal_user_model_block(
                user.id, format="full", flow="response"
            )
            brief_block = await build_journal_user_model_block(
                user.id, format="brief", flow="reminder"
            )

        assert "Full portrait body" in full_block
        assert "Brief portrait body" in brief_block
        # Discipline directive must be present in both formats.
        assert "psychological profile" in full_block.lower()
        assert "psychological profile" in brief_block.lower()

    async def test_user_with_journals_disabled_returns_empty(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session, journals_enabled=False)
        user.journal_portrait_full = "Portrait would be here but user disabled journals"
        user.journal_portrait_brief = "Brief would be here too"
        async_session.add(user)
        await async_session.commit()

        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def _ctx():
            yield async_session

        with (
            patch("src.domains.journals.portrait_builder.get_db_context", new=_ctx),
            patch(
                "src.domains.journals.portrait_builder.settings",
                type("S", (), {"journals_enabled": True})(),
            ),
        ):
            block = await build_journal_user_model_block(user.id, format="full", flow="response")

        assert block == ""


# -----------------------------------------------------------------------------
# 5. GDPR scrub
# -----------------------------------------------------------------------------


class TestGDPRScrub:
    """Account deletion blanks out the three portrait columns alongside other PII."""

    async def test_mark_user_deleted_scrubs_portrait_columns(
        self,
        async_session: AsyncSession,
        stubbed_embeddings: Any,
    ) -> None:
        user = await _make_user(async_session)
        user.journal_portrait_full = "Sensitive portrait full"
        user.journal_portrait_brief = "Sensitive portrait brief"
        from datetime import UTC, datetime

        user.journal_portrait_compiled_at = datetime.now(UTC)
        async_session.add(user)
        await async_session.commit()

        from src.domains.users.account_deletion_service import (
            AccountDeletionService,
        )

        service = AccountDeletionService(async_session)
        await service._mark_user_deleted(user, reason="user_initiated")
        await async_session.commit()
        await async_session.refresh(user)

        assert user.journal_portrait_full is None
        assert user.journal_portrait_brief is None
        assert user.journal_portrait_compiled_at is None
