"""Consent to the shipped topics reaches only a preference nobody edited — real PostgreSQL.

Migration ``6b2c4e8f0a17`` (owner decision 2026-10-21) gives the shipped sensitive
topics to every preference row still carrying the former default (no topic) and
never edited (``revision = 0``). An edited row keeps its list, an empty one
included: an empty list may be a refusal, and consent to a sensitive topic is never
inferred from one. What is proven is the migration's own statement.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.proactive_discussions.models import DiscussionPreference
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_MIGRATION = (
    Path(__file__).resolve().parents[4]
    / "alembic"
    / "versions"
    / "2026_10_21_1110-6b2c4e8f0a17_discussion_sensitive_topics_default.py"
)


def _load_migration() -> ModuleType:
    """The migration module itself, so its backfill SQL is what gets proven."""
    spec = importlib.util.spec_from_file_location("discussion_topics_default", _MIGRATION)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _preference(
    db: AsyncSession, *, topics: list[str], revision: int
) -> DiscussionPreference:
    owner = User(
        email=f"topics-{uuid4().hex[:8]}@example.test",
        hashed_password="x",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        full_name="Fictional owner",
    )
    db.add(owner)
    await db.flush()
    row = DiscussionPreference(user_id=owner.id, sensitive_topics=topics, revision=revision)
    db.add(row)
    await db.flush()
    return row


async def test_only_a_preference_nobody_edited_receives_the_shipped_consent(
    async_session: AsyncSession,
) -> None:
    untouched = await _preference(async_session, topics=[], revision=0)
    # Edited to nothing: possibly a refusal, never read as consent.
    refused = await _preference(async_session, topics=[], revision=4)
    chosen = await _preference(async_session, topics=["grief"], revision=0)
    migration = _load_migration()

    await async_session.execute(
        text(migration.BACKFILL_STATEMENT).bindparams(topics=migration.SHIPPED_DEFAULT)
    )
    for row in (untouched, refused, chosen):
        await async_session.refresh(row)

    assert untouched.sensitive_topics == [
        "health",
        "relationships",
        "finances",
        "grief",
        "intimacy",
    ]
    assert refused.sensitive_topics == []
    assert chosen.sensitive_topics == ["grief"]
    # Consent is data, not an edit: the person's revision counter does not move.
    assert (untouched.revision, refused.revision) == (0, 4)
