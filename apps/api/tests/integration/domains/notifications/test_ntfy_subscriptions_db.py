"""ntfy subscriptions on real PostgreSQL (ADR-391).

What an in-memory double cannot prove: the topic and the token are stored encrypted and read back
in clear for their owner only; the per-account ceiling holds against two simultaneous requests
(advisory lock, counted and written in one transaction); the table's own CHECKs refuse an
incoherent row; another account's subscription is « not found », never « forbidden ».
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import insert, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.constants import NTFY_TOPIC_PREFIX
from src.core.exceptions import BaseAPIException
from src.core.security.utils import decrypt_data
from src.domains.notifications.models import NtfySubscription
from src.domains.notifications.ntfy import NtfyContent, NtfyServerKind
from src.domains.notifications.ntfy_repository import NtfySubscriptionRepository
from src.domains.notifications.ntfy_schemas import (
    NtfySubscriptionCreate,
    NtfySubscriptionUpdate,
)
from src.domains.notifications.ntfy_service import NtfySubscriptionService
from src.domains.users.models import User
from src.infrastructure.external.ntfy_client import NtfyOutcome

pytestmark = pytest.mark.integration

TOKEN = "tk_" + "a1B2c3" * 4 + "d4E5f"


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"ntfy-{uuid4().hex[:10]}@example.com",
        hashed_password="x",
        is_active=True,
        full_name="Ntfy Proof",
    )
    db.add(user)
    await db.flush()
    return user


@pytest.fixture(autouse=True)
def _ntfy_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ntfy_server_url", "http://ntfy:80")
    monkeypatch.setattr(settings, "ntfy_public_url", "https://ntfy.example.org")
    monkeypatch.setattr(settings, "ntfy_custom_servers_enabled", True)
    monkeypatch.setattr(settings, "ntfy_max_subscriptions_per_user", 3)


def _refusal(error: pytest.ExceptionInfo[BaseAPIException]) -> str:
    """The stable code a refusal names itself with — what the settings translate."""
    detail = error.value.detail
    assert isinstance(detail, dict), detail
    return str(detail["code"])


class TestCreating:
    async def test_an_instance_subscription_draws_its_topic_and_keeps_it_encrypted(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)

        view = await NtfySubscriptionService(async_session).create(
            owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
        )
        await async_session.commit()

        assert view.topic is not None and view.topic.startswith(NTFY_TOPIC_PREFIX)
        assert view.server_url == "https://ntfy.example.org"
        assert view.content is NtfyContent.MINIMAL and view.has_token is False
        row = await async_session.get(NtfySubscription, view.id)
        assert row is not None and row.server_url is None
        assert row.topic_encrypted != view.topic
        assert decrypt_data(row.topic_encrypted) == view.topic

    async def test_an_instance_with_no_server_offers_none(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ntfy_server_url", "")
        owner = await _user(async_session)

        with pytest.raises(BaseAPIException) as refused:
            await NtfySubscriptionService(async_session).create(
                owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
            )

        assert _refusal(refused) == "ntfy_instance_unavailable"

    async def test_a_custom_subscription_keeps_its_topic_and_its_token_encrypted(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)

        view = await NtfySubscriptionService(async_session).create(
            owner.id,
            NtfySubscriptionCreate(
                server=NtfyServerKind.CUSTOM,
                server_url="https://ntfy.sh/",
                topic="my-alerts",
                token=TOKEN,
                content=NtfyContent.FULL,
            ),
        )
        await async_session.commit()

        assert (view.server_url, view.topic, view.has_token) == (
            "https://ntfy.sh",
            "my-alerts",
            True,
        )
        row = await async_session.get(NtfySubscription, view.id)
        assert row is not None and row.token_encrypted is not None
        assert TOKEN not in row.token_encrypted and decrypt_data(row.token_encrypted) == TOKEN

    async def test_a_custom_subscription_with_no_topic_gets_one_drawn(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)

        view = await NtfySubscriptionService(async_session).create(
            owner.id,
            NtfySubscriptionCreate(server=NtfyServerKind.CUSTOM, server_url="https://ntfy.sh"),
        )

        assert view.topic is not None and view.topic.startswith(NTFY_TOPIC_PREFIX)

    @pytest.mark.parametrize(
        ("fields", "refusal"),
        [
            ({"server_url": "http://ntfy.sh"}, "server_url_not_https"),
            ({"server_url": "https://10.0.0.5"}, "server_url_refused"),
            ({"server_url": None}, "server_url_not_https"),
            ({"server_url": "https://ntfy.sh", "topic": "a b"}, "topic_invalid"),
            ({"server_url": "https://ntfy.sh", "token": "tk_short"}, "token_invalid"),
        ],
    )
    async def test_what_ntfy_or_lia_would_refuse_is_refused_before_anything_is_kept(
        self, async_session: AsyncSession, fields: dict[str, str | None], refusal: str
    ) -> None:
        owner = await _user(async_session)

        with pytest.raises(BaseAPIException) as refused:
            await NtfySubscriptionService(async_session).create(
                owner.id, NtfySubscriptionCreate(server=NtfyServerKind.CUSTOM, **fields)
            )

        assert _refusal(refused) == f"ntfy_{refusal}"
        assert (await NtfySubscriptionService(async_session).overview(owner.id)).subscriptions == []

    async def test_custom_servers_withdrawn_by_the_operator_are_refused(
        self, async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "ntfy_custom_servers_enabled", False)
        owner = await _user(async_session)

        with pytest.raises(BaseAPIException) as refused:
            await NtfySubscriptionService(async_session).create(
                owner.id,
                NtfySubscriptionCreate(server=NtfyServerKind.CUSTOM, server_url="https://ntfy.sh"),
            )

        assert _refusal(refused) == "ntfy_custom_servers_disabled"


class TestTheCeiling:
    async def test_one_more_than_the_ceiling_is_refused(self, async_session: AsyncSession) -> None:
        owner = await _user(async_session)
        service = NtfySubscriptionService(async_session)
        for _ in range(settings.ntfy_max_subscriptions_per_user):
            await service.create(owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE))

        with pytest.raises(BaseAPIException) as refused:
            await service.create(owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE))

        assert _refusal(refused) == "ntfy_subscription_limit"
        # The figure the settings say travels with the code.
        assert refused.value.status_code == 409
        assert refused.value.detail == {
            "code": "ntfy_subscription_limit",
            "max": settings.ntfy_max_subscriptions_per_user,
        }

    async def test_two_simultaneous_requests_never_pass_it_together(
        self,
        async_engine: AsyncEngine,
        committed_user_ids: list,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Counted and written under one advisory lock: the second waits, then counts again."""
        monkeypatch.setattr(settings, "ntfy_max_subscriptions_per_user", 1)
        sessions = async_sessionmaker(async_engine, expire_on_commit=False)
        async with sessions() as db:
            owner = await _user(db)
            await db.commit()
        committed_user_ids.append(owner.id)

        async def attempt() -> bool:
            async with sessions() as db:
                try:
                    await NtfySubscriptionService(db).create(
                        owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
                    )
                    await asyncio.sleep(0.2)  # hold the lock while the other one asks
                    await db.commit()
                    return True
                except BaseAPIException:
                    await db.rollback()
                    return False

        results = await asyncio.gather(attempt(), attempt())

        assert sorted(results) == [False, True]
        async with sessions() as db:
            rows = await db.scalars(
                select(NtfySubscription).where(NtfySubscription.user_id == owner.id)
            )
            assert len(list(rows)) == 1


class TestOwnership:
    async def test_a_subscription_whose_topic_no_longer_reads_stays_removable(
        self, async_session: AsyncSession
    ) -> None:
        """One secret a changed key can no longer read never takes the settings down."""
        owner_id = (await _user(async_session)).id
        service = NtfySubscriptionService(async_session)
        view = await service.create(
            owner_id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
        )
        await async_session.execute(
            update(NtfySubscription)
            .where(NtfySubscription.id == view.id)
            .values(topic_encrypted="no-longer-a-fernet-token")
        )
        await async_session.commit()

        (shown,) = (await service.overview(owner_id)).subscriptions
        assert (shown.id, shown.topic) == (view.id, None)

        await service.delete(owner_id, view.id)
        await async_session.commit()
        assert (await service.overview(owner_id)).subscriptions == []

    async def test_a_subscription_changes_and_leaves_at_its_owner_s_word(
        self, async_session: AsyncSession
    ) -> None:
        owner = await _user(async_session)
        service = NtfySubscriptionService(async_session)
        view = await service.create(
            owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
        )

        changed = await service.update(
            owner.id, view.id, NtfySubscriptionUpdate(content=NtfyContent.FULL, is_active=False)
        )
        assert (changed.content, changed.is_active) == (NtfyContent.FULL, False)

        await service.delete(owner.id, view.id)
        assert (await service.overview(owner.id)).subscriptions == []

    async def test_another_account_s_subscription_is_not_found(
        self, async_session: AsyncSession
    ) -> None:
        owner, stranger = await _user(async_session), await _user(async_session)
        service = NtfySubscriptionService(async_session)
        view = await service.create(
            owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE)
        )

        for act in (
            service.update(stranger.id, view.id, NtfySubscriptionUpdate(is_active=False)),
            service.delete(stranger.id, view.id),
            service.owned(stranger.id, view.id),
        ):
            with pytest.raises(BaseAPIException) as refused:
                await act
            assert refused.value.status_code == 404
        assert (await service.overview(stranger.id)).subscriptions == []
        assert len((await service.overview(owner.id)).subscriptions) == 1


class TestADeliveryReadsItsTargets:
    async def test_a_language_group_larger_than_the_driver_s_bind_limit_is_read_whole(
        self, async_session: AsyncSession
    ) -> None:
        """A broadcast reads the topics of a whole language group before it is written:
        a refusal by the driver there would cost the broadcast itself."""
        owners = [await _user(async_session) for _ in range(2)]
        service = NtfySubscriptionService(async_session)
        made = [
            await service.create(owner.id, NtfySubscriptionCreate(server=NtfyServerKind.INSTANCE))
            for owner in owners
        ]
        await async_session.commit()
        # Past asyncpg's 32 767 bound values, the real accounts last.
        group = [uuid4() for _ in range(40_000)] + [owner.id for owner in owners]
        repository = NtfySubscriptionRepository(async_session)

        targets = await repository.active_targets(group)

        assert {target.id for target in targets} == {view.id for view in made}
        assert all(target.topic.startswith(NTFY_TOPIC_PREFIX) for target in targets)

        at = datetime.now(UTC)
        await repository.record_outcomes(
            [(uuid4(), NtfyOutcome.SENT) for _ in range(40_000)]
            + [(view.id, NtfyOutcome.SENT) for view in made],
            at=at,
        )
        await async_session.commit()
        stamped = await async_session.scalars(
            select(NtfySubscription.last_sent_at).where(
                NtfySubscription.id.in_([view.id for view in made])
            )
        )
        assert set(stamped) == {at}


class TestTheTableRefusesIncoherence:
    @pytest.mark.parametrize(
        "row",
        [
            {"server_kind": "instance", "server_url": "https://x.example"},
            {"server_kind": "custom", "server_url": None},
            {"server_kind": "instance", "server_url": None, "token_encrypted": "t"},
            {"server_kind": "other", "server_url": None},
            {"server_kind": "instance", "server_url": None, "content": "loud"},
        ],
    )
    async def test_an_incoherent_row_never_lands(
        self, async_session: AsyncSession, row: dict[str, str | None]
    ) -> None:
        owner = await _user(async_session)
        values = {
            "id": uuid4(),
            "user_id": owner.id,
            "topic_encrypted": "t",
            "content": "minimal",
            "is_active": True,
            "created_at": owner.created_at,
            "updated_at": owner.created_at,
            **row,
        }

        with pytest.raises(IntegrityError):
            await async_session.execute(insert(NtfySubscription).values(**values))
