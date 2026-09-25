"""The admin broadcast routes, end to end on real PostgreSQL (ADR-312).

``POST /notifications/admin/broadcast`` must record WHO a targeted broadcast was
for, and ``GET /notifications/admin/broadcasts`` draws the history the settings
page shows under the send form: newest first, the exact total, the audience
with a recipient sample, the expiry and the read receipts — for a superuser
only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import BROADCAST_HISTORY_PAGE_SIZE_MAX
from src.domains.notifications.models import (
    AdminBroadcast,
    AdminBroadcastRecipient,
    UserBroadcastRead,
)
from src.domains.notifications.repository import BroadcastRepository
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_HISTORY = "/api/v1/notifications/admin/broadcasts"
_SEND = "/api/v1/notifications/admin/broadcast"


async def _reader(db: AsyncSession, name: str) -> User:
    user = User(
        email=f"{name.lower()}-{uuid4().hex[:6]}@example.com",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name=name,
        language="fr",
    )
    db.add(user)
    await db.commit()
    return user


class TestHistoryRoute:
    """What an administrator reads below the send form."""

    async def test_a_page_carries_audience_recipients_expiry_and_reads(
        self, admin_client: tuple[AsyncClient, User], async_session: AsyncSession
    ) -> None:
        client, admin = admin_client
        alice = await _reader(async_session, "Alice")
        bob = await _reader(async_session, "Bob")
        repo = BroadcastRepository(async_session)
        now = datetime.now(UTC)

        to_all = await repo.create_broadcast(
            message="Maintenance tonight", sent_by=admin.id, expires_at=now + timedelta(days=7)
        )
        to_all.created_at = now - timedelta(minutes=5)
        to_all.total_recipients = 3
        targeted = await repo.create_broadcast(
            message="For you two", sent_by=admin.id, recipient_ids=[bob.id, alice.id]
        )
        targeted.total_recipients = 2
        targeted.fcm_sent = 1
        async_session.add(UserBroadcastRead(user_id=alice.id, broadcast_id=targeted.id))
        await async_session.commit()

        response = await client.get(_HISTORY, params={"limit": 10, "offset": 0})

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        newest, older = body["items"]

        assert newest["id"] == str(targeted.id)
        assert newest["audience"] == "selected"
        assert newest["recipients_total"] == 2
        assert [r["full_name"] for r in newest["recipients"]] == ["Alice", "Bob"]
        assert newest["reached_count"] == 2
        assert newest["fcm_sent"] == 1
        assert newest["read_count"] == 1
        assert newest["expires_at"] is None
        assert newest["expires_in_days"] is None
        assert newest["is_expired"] is False
        assert newest["sender_name"] == admin.full_name

        assert older["id"] == str(to_all.id)
        assert older["audience"] == "all"
        assert older["recipients"] == [] and older["recipients_total"] == 0
        assert older["expires_in_days"] == 7
        assert older["is_expired"] is False
        assert older["read_count"] == 0
        assert older["message"] == "Maintenance tonight"

    async def test_an_expired_broadcast_says_so(
        self, admin_client: tuple[AsyncClient, User], async_session: AsyncSession
    ) -> None:
        client, admin = admin_client
        repo = BroadcastRepository(async_session)
        sent = datetime.now(UTC) - timedelta(days=40)
        old = await repo.create_broadcast(
            message="Old news", sent_by=admin.id, expires_at=sent + timedelta(days=30)
        )
        old.created_at = sent
        await async_session.commit()

        item = (await client.get(_HISTORY)).json()["items"][0]

        assert item["is_expired"] is True
        assert item["expires_in_days"] == 30

    async def test_the_page_size_bound_is_published_and_enforced(
        self, admin_client: tuple[AsyncClient, User]
    ) -> None:
        client, _admin = admin_client

        too_big = await client.get(_HISTORY, params={"limit": BROADCAST_HISTORY_PAGE_SIZE_MAX + 1})
        negative = await client.get(_HISTORY, params={"offset": -1})

        assert too_big.status_code == 422
        assert negative.status_code == 422


class TestSendRecordsTheAudience:
    """The send path persists recipients in the transaction that creates the row."""

    async def test_a_targeted_send_writes_its_recipients(
        self, admin_client: tuple[AsyncClient, User], async_session: AsyncSession
    ) -> None:
        client, _admin = admin_client
        alice = await _reader(async_session, "Alice")

        response = await client.post(
            _SEND, json={"message": "Hi Alice", "user_ids": [str(alice.id)]}
        )

        assert response.status_code == 200, response.text
        broadcast_id = response.json()["broadcast_id"]
        broadcast = await async_session.get(AdminBroadcast, broadcast_id)
        recipients = (
            await async_session.scalars(
                select(AdminBroadcastRecipient.user_id).where(
                    AdminBroadcastRecipient.broadcast_id == broadcast.id
                )
            )
        ).all()
        assert broadcast.audience == "selected"
        assert recipients == [alice.id]
        assert response.json()["total_users"] == 1

    async def test_an_empty_selection_is_refused_rather_than_sent_to_everyone(
        self, admin_client: tuple[AsyncClient, User], async_session: AsyncSession
    ) -> None:
        """``user_ids: []`` used to mean « all users » — a cleared selection broadcast."""
        client, _admin = admin_client

        response = await client.post(_SEND, json={"message": "Oops", "user_ids": []})

        assert response.status_code == 422
        assert (await async_session.scalars(select(AdminBroadcast.id))).all() == []

    async def test_a_selection_with_no_active_account_is_refused(
        self, admin_client: tuple[AsyncClient, User], async_session: AsyncSession
    ) -> None:
        client, _admin = admin_client
        ghost = await _reader(async_session, "Ghost")
        ghost.is_active = False
        await async_session.commit()

        response = await client.post(_SEND, json={"message": "Nobody", "user_ids": [str(ghost.id)]})

        assert response.status_code == 400
        assert (await async_session.scalars(select(AdminBroadcast.id))).all() == []


class TestHistoryIsForAdministrators:
    async def test_a_regular_account_is_refused(
        self, authenticated_client: tuple[AsyncClient, User]
    ) -> None:
        client, _user = authenticated_client

        response = await client.get(_HISTORY)

        assert response.status_code == 403
