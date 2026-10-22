"""The real SMS owner reader retains pages, consent and alert independence."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey, SourceReadRequest
from src.domains.sms.discussion_source import SmsDiscussionSource
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.sms.models import SmsMessage
from src.domains.users.models import User
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


def scope(owner: UUID, now: datetime) -> SourceReadRequest:
    return SourceReadRequest(
        owner_id=owner,
        run_id=uuid4(),
        policy_revision=1,
        request=ResearchRequest(source=SourceKey.SMS, operation="recent"),
        allowed_sources=(SourceKey.SMS,),
        now=now,
        window_start=now - timedelta(days=3),
        window_end=now,
        item_limit=1,
        call_limit=1,
        timeout_seconds=10,
    )


async def seed_sms(engine: AsyncEngine, owner: UUID, now: datetime) -> None:
    async with AsyncSession(engine) as db:
        user = await db.get(User, owner)
        assert user is not None
        user.sms_preferences = {"assistant_enabled": True}
        principal = await authority(db, user)
        result = await SmsIngestionService(db).ingest(
            principal,
            [
                message(
                    body="Fictional lunch this week", date=(now - timedelta(hours=2)).isoformat()
                ),
                message(
                    body="Fictional walk yesterday", date=(now - timedelta(hours=1)).isoformat()
                ),
            ],
        )
        assert result.inserted == 2
        rows = (await db.scalars(select(SmsMessage).where(SmsMessage.user_id == owner))).all()
        for row in rows:
            row.proactive_mentioned_at = now
        await db.commit()


async def test_paging_includes_already_notified_messages_without_marking_them(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    now = datetime.now(UTC)
    await seed_sms(async_engine, discussion_owner, now)
    source = SmsDiscussionSource()
    first = await source.read(scope(discussion_owner, now))
    assert first.status == "truncated" and first.total == 2 and first.cursor
    second = await source.read(
        scope(discussion_owner, now).model_copy(update={"cursor": first.cursor})
    )
    assert second.status == "ok" and not second.complete
    assert first.items[0].reference != second.items[0].reference
    assert first.revision == second.revision
    assert first.physical_calls == second.physical_calls == 0
    async with AsyncSession(async_engine) as db:
        stamps = (
            await db.scalars(
                select(SmsMessage.proactive_mentioned_at).where(
                    SmsMessage.user_id == discussion_owner,
                )
            )
        ).all()
        assert stamps == [now, now]


async def test_assistant_consent_rechecked_on_next_page(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    now = datetime.now(UTC)
    await seed_sms(async_engine, discussion_owner, now)
    first = await SmsDiscussionSource().read(scope(discussion_owner, now))
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.sms_preferences = {"assistant_enabled": False}
        await db.commit()
    with pytest.raises(AuthorizationError):
        await SmsDiscussionSource().read(
            scope(discussion_owner, now).model_copy(update={"cursor": first.cursor})
        )


async def test_refusal_does_not_open_sms_database(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden() -> None:
        pytest.fail("refused source opened its native reader")

    monkeypatch.setattr("src.domains.sms.discussion_source.get_db_context", forbidden)
    result = await SmsDiscussionSource().read(
        scope(uuid4(), datetime.now(UTC)).model_copy(update={"allowed_sources": ()})
    )
    assert result.status == "disabled"
