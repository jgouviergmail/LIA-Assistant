"""Sensitive derived facts and global journal refusal stay explicit at the source."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.journals.discussion_source import PortraitDiscussionSource
from src.domains.memories.discussion_source import MemoryDiscussionSource
from src.domains.memories.models import Memory
from src.domains.shared.discussion_sources import SourceKey
from src.domains.users.models import User
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def test_biometric_memory_keeps_health_sensitivity_when_authorized(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    monkeypatch.setattr(settings, "health_metrics_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.health_metrics_agents_enabled = True
        db.add(
            Memory(
                user_id=discussion_owner,
                content="Authorized health-related fact",
                category="event",
                context_biometric={"delta": 1},
            )
        )
        await db.commit()
    request = read_request(discussion_owner, SourceKey.MEMORIES).model_copy(
        update={
            "allowed_sources": (SourceKey.MEMORIES, SourceKey.HEALTH),
            "sensitive_topics": ("health",),
        }
    )
    result = await MemoryDiscussionSource().read(request)
    assert result.status == "ok" and len(result.items) == 1
    assert result.items[0].sensitive_topics == ("health",)
    assert result.items[0].required_sources == (SourceKey.HEALTH,)


async def test_global_journal_refusal_is_disabled_not_an_empty_portrait(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.journals_enabled = False
        user.journal_portrait_brief = "Must remain private"
        user.journal_portrait_compiled_at = NOW
        await db.commit()
    result = await PortraitDiscussionSource().read(
        read_request(discussion_owner, SourceKey.PORTRAIT)
    )
    assert result.status == "disabled" and not result.items and not result.complete
