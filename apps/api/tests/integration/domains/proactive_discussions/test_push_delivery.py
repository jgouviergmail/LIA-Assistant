"""Discussion pushes settle their devices like the batch sender, on real PostgreSQL."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.notifications.models import UserFCMToken
from src.domains.notifications.service import FCMNotificationService, FCMSendResult
from src.domains.proactive_discussions.outbox_repository import DiscussionDelivery
from src.infrastructure.proactive import discussion_delivery

pytestmark = pytest.mark.integration


def _envelope(owner, *, sensitive: bool) -> DiscussionDelivery:
    return DiscussionDelivery(
        owner_id=owner,
        opening_id=uuid4(),
        attempt=uuid4(),
        conversation_id=uuid4(),
        message_id=uuid4(),
        run_id=uuid4(),
        context_epoch=0,
        language="en",
        text="Would you like to talk about your fictional plans?",
        sensitive=sensitive,
        metadata={},
    )


@pytest.fixture
def delivery_db(async_engine, monkeypatch):
    @asynccontextmanager
    async def context():
        async with AsyncSession(async_engine, expire_on_commit=False) as db:
            yield db
            await db.commit()

    monkeypatch.setattr(discussion_delivery, "get_db_context", context)
    monkeypatch.setattr(discussion_delivery, "_may_send", AsyncMock(return_value=True))
    return context


async def test_an_accepted_device_is_stamped_and_an_invalid_one_retired(
    delivery_db, discussion_owner, monkeypatch
):
    async with delivery_db() as db:
        db.add_all(
            [
                UserFCMToken(user_id=discussion_owner, token="fictional-live", device_type="web"),
                UserFCMToken(user_id=discussion_owner, token="fictional-dead", device_type="web"),
            ]
        )
    sent = []

    async def send(self, *, token, title, body, data, occurrence_key):
        sent.append((token, body, data))
        if token == "fictional-dead":
            return FCMSendResult(success=False, token=token, token_invalid=True, error="gone")
        return FCMSendResult(success=True, token=token, message_id="fictional")

    monkeypatch.setattr(FCMNotificationService, "send_to_device", send)
    assert await discussion_delivery._send_pushes(_envelope(discussion_owner, sensitive=True))
    async with delivery_db() as db:
        rows = {row.token: row for row in await db.scalars(select(UserFCMToken))}
    assert rows["fictional-dead"].is_active is False and rows["fictional-dead"].last_error == "gone"
    assert rows["fictional-live"].is_active is True and rows["fictional-live"].last_used_at
    # A private opening never shows its words on a lock screen.
    assert all("fictional plans" not in body for _, body, _ in sent)
    assert {data["sensitive_in_app_only"] for _, _, data in sent} == {"true"}


async def test_no_device_accepting_reads_as_not_delivered(
    delivery_db, discussion_owner, monkeypatch
):
    async with delivery_db() as db:
        db.add(UserFCMToken(user_id=discussion_owner, token="fictional-dead", device_type="web"))
    monkeypatch.setattr(
        FCMNotificationService,
        "send_to_device",
        AsyncMock(return_value=FCMSendResult(success=False, token="x", token_invalid=True)),
    )
    assert not await discussion_delivery._send_pushes(_envelope(discussion_owner, sensitive=False))
