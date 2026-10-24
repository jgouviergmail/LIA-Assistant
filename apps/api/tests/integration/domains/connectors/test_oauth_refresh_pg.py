"""The refresh door's stores on real PostgreSQL and its claim on real Redis (audit AC-029).

A conditional UPDATE on a ``native_enum=False`` status column matches what its bind says,
which only a real server can prove; and two workers share nothing but Redis and the
database, so « one exchange for two workers » is proven on both, with the door's own
sessions — never the test's (the door never uses a caller's session).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.exceptions import ValidationError
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors import oauth_refresh, oauth_refresh_targets
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.oauth_refresh import Refreshed, RefreshTarget, StoredToken
from src.domains.connectors.oauth_refresh_exchange import (
    RefreshedToken,
    RefreshRefusal,
    RefreshRefused,
)
from src.domains.connectors.oauth_refresh_targets import (
    GrantTokenTarget,
    legacy_connector_target,
)
from src.domains.connectors.schemas import ConnectorCredentials
from tests.helpers.committed_users import commit_owner
from tests.helpers.oauth_refresh_io import commit_expired_connector, expired_ciphertext

pytestmark = pytest.mark.integration

_CALENDAR = "https://www.googleapis.com/auth/calendar"
_TASKS = "https://www.googleapis.com/auth/tasks"


def _fresh(access: str) -> Refreshed[ConnectorCredentials]:
    return Refreshed(
        ConnectorCredentials(
            access_token=access,
            refresh_token="refresh-2",
            token_type="Bearer",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        frozenset(),
    )


@pytest_asyncio.fixture
async def owner(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> UUID:
    return await commit_owner(async_engine, committed_user_ids)


async def _legacy(engine: AsyncEngine, owner: UUID, status: ConnectorStatus) -> Connector:
    return await commit_expired_connector(
        engine,
        owner,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=status,
        scopes=[_CALENDAR],
    )


async def _linked(engine: AsyncEngine, owner: UUID) -> tuple[Connector, Connector, OAuthGrant]:
    encrypted = expired_ciphertext()
    async with AsyncSession(engine, expire_on_commit=False) as db:
        grant = OAuthGrant(
            user_id=owner,
            provider="google",
            client_id=settings.google_client_id,
            subject=f"sub-{owner}",
            email="owner@example.test",
            scopes=[_CALENDAR, _TASKS],
            credentials_encrypted=encrypted,
        )
        db.add(grant)
        await db.flush()
        calendar = Connector(
            user_id=owner,
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            status=ConnectorStatus.ACTIVE,
            scopes=[_CALENDAR, _TASKS],
            credentials_encrypted=encrypted,
            oauth_grant_id=grant.id,
        )
        tasks = Connector(
            user_id=owner,
            connector_type=ConnectorType.GOOGLE_TASKS,
            status=ConnectorStatus.ACTIVE,
            scopes=[_CALENDAR, _TASKS],
            credentials_encrypted=encrypted,
            oauth_grant_id=grant.id,
        )
        db.add_all([calendar, tasks])
        await db.commit()
        return calendar, tasks, grant


async def _row(engine: AsyncEngine, connector_id: UUID) -> Connector:
    async with AsyncSession(engine) as db:
        row = await db.get(Connector, connector_id)
        assert row is not None
        return row


class TestTheConnectorStore:
    async def test_a_write_lands_only_on_the_token_it_started_from(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        target = legacy_connector_target(connector)
        started_from = connector.credentials_encrypted

        async with AsyncSession(async_engine) as db:
            first = await target.write_if_unchanged(db, started_from, _fresh("first"))
            await db.commit()
        async with AsyncSession(async_engine) as db:
            second = await target.write_if_unchanged(db, started_from, _fresh("second"))
            await db.commit()

        stored = ConnectorCredentials.model_validate_json(
            decrypt_data((await _row(async_engine, connector.id)).credentials_encrypted)
        )
        assert (first, second, stored.access_token) == (True, False, "first")

    async def test_a_write_never_lands_on_a_revoked_connector(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.REVOKED)
        target = legacy_connector_target(connector)

        async with AsyncSession(async_engine) as db:
            written = await target.write_if_unchanged(
                db, connector.credentials_encrypted, _fresh("late")
            )
            await db.commit()

        row = await _row(async_engine, connector.id)
        assert written is False
        assert row.credentials_encrypted == connector.credentials_encrypted

    async def test_a_revocation_lands_only_on_the_refused_token(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        target = legacy_connector_target(connector)

        async with AsyncSession(async_engine) as db:
            other = await target.revoke_if_unchanged(db, expired_ciphertext("someone-else"))
            await db.commit()
        assert (other, (await _row(async_engine, connector.id)).status) == (
            False,
            ConnectorStatus.ACTIVE,
        )

        async with AsyncSession(async_engine) as db:
            refused = await target.revoke_if_unchanged(db, connector.credentials_encrypted)
            await db.commit()
        assert (refused, (await _row(async_engine, connector.id)).status) == (
            True,
            ConnectorStatus.ERROR,
        )


class TestTheGrantStore:
    async def test_a_write_reaches_every_link_and_errors_an_uncovered_one(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        calendar, tasks, grant = await _linked(async_engine, owner)
        target = GrantTokenTarget(calendar)
        refreshed = Refreshed(_fresh("granted").credentials, frozenset({_CALENDAR}))

        async with AsyncSession(async_engine) as db:
            written = await target.write_if_unchanged(db, grant.credentials_encrypted, refreshed)
            await db.commit()

        calendar_row = await _row(async_engine, calendar.id)
        tasks_row = await _row(async_engine, tasks.id)
        async with AsyncSession(async_engine) as db:
            grant_row = await db.get(OAuthGrant, grant.id)
        assert grant_row is not None
        assert written is True
        assert grant_row.scopes == [_CALENDAR]
        assert calendar_row.credentials_encrypted == grant_row.credentials_encrypted
        assert tasks_row.credentials_encrypted == grant_row.credentials_encrypted
        assert (calendar_row.status, tasks_row.status) == (
            ConnectorStatus.ACTIVE,
            ConnectorStatus.ERROR,
        )

    async def test_a_write_lands_only_on_the_grant_token_it_started_from(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        calendar, _tasks, grant = await _linked(async_engine, owner)
        target = GrantTokenTarget(calendar)

        async with AsyncSession(async_engine) as db:
            first = await target.write_if_unchanged(db, grant.credentials_encrypted, _fresh("a"))
            await db.commit()
        async with AsyncSession(async_engine) as db:
            second = await target.write_if_unchanged(db, grant.credentials_encrypted, _fresh("b"))
            await db.commit()

        async with AsyncSession(async_engine) as db:
            grant_row = await db.get(OAuthGrant, grant.id)
        assert grant_row is not None
        stored = ConnectorCredentials.model_validate_json(
            decrypt_data(grant_row.credentials_encrypted)
        )
        assert (first, second, stored.access_token) == (True, False, "a")

    async def test_a_detached_connector_is_never_served_the_grant(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        calendar, _tasks, grant = await _linked(async_engine, owner)
        target = GrantTokenTarget(calendar)
        async with AsyncSession(async_engine) as db:
            await db.execute(
                update(Connector).where(Connector.id == calendar.id).values(oauth_grant_id=None)
            )
            await db.commit()

        async with AsyncSession(async_engine) as db:
            stored = await target.read(db)
            written = await target.write_if_unchanged(db, grant.credentials_encrypted, _fresh("x"))
            await db.commit()

        assert stored is not None and stored.active is False
        assert written is False

    async def test_a_revocation_errors_only_the_active_links_of_the_refused_token(
        self, async_engine: AsyncEngine, owner: UUID
    ) -> None:
        calendar, tasks, grant = await _linked(async_engine, owner)
        target = GrantTokenTarget(calendar)

        async with AsyncSession(async_engine) as db:
            assert await target.revoke_if_unchanged(db, expired_ciphertext("other")) is False
            assert await target.revoke_if_unchanged(db, grant.credentials_encrypted) is True
            await db.commit()

        assert (await _row(async_engine, calendar.id)).status == ConnectorStatus.ERROR
        assert (await _row(async_engine, tasks.id)).status == ConnectorStatus.ERROR


class TestTheDoorAcrossWorkers:
    async def test_two_workers_exchange_once_on_real_redis(
        self, async_engine: AsyncEngine, owner: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        gate = asyncio.Event()
        exchanges = 0

        async def provider(*_args: object, **_kwargs: object) -> RefreshedToken:
            nonlocal exchanges
            exchanges += 1
            await gate.wait()
            return RefreshedToken(
                access_token="shared",
                refresh_token="refresh-2",
                expires_at=datetime.now(UTC) + timedelta(hours=1),
                reported_scopes=frozenset(),
            )

        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", provider)
        start: StoredToken[ConnectorCredentials] = legacy_connector_target(connector).stored(
            connector
        )
        workers = [
            asyncio.create_task(
                oauth_refresh._coalesced(
                    legacy_connector_target(connector), start, force=False, refresh_before=None
                )
            )
            for _ in range(2)
        ]
        await asyncio.sleep(0.2)
        gate.set()

        verdicts = await asyncio.wait_for(asyncio.gather(*workers), 30)

        stored = ConnectorCredentials.model_validate_json(
            decrypt_data((await _row(async_engine, connector.id)).credentials_encrypted)
        )
        assert exchanges == 1
        assert stored.access_token == "shared"
        for verdict in verdicts:
            assert isinstance(verdict, oauth_refresh._Granted)
            assert verdict.credentials.access_token == "shared"

    async def test_invalid_grant_after_another_worker_s_rotation_disconnects_nobody(
        self, async_engine: AsyncEngine, owner: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A rotating provider refuses the token another worker just rotated."""
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        rotated = encrypt_data(_fresh("theirs").credentials.model_dump_json())

        async def provider(*_args: object, **_kwargs: object) -> RefreshedToken:
            async with AsyncSession(async_engine) as db:
                await db.execute(
                    update(Connector)
                    .where(Connector.id == connector.id)
                    .values(credentials_encrypted=rotated)
                )
                await db.commit()
            raise RefreshRefused(RefreshRefusal.REVOKED, status_code=400)

        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", provider)

        served = await oauth_refresh.ensure_fresh_credentials(legacy_connector_target(connector))

        row = await _row(async_engine, connector.id)
        assert served.access_token == "theirs"
        assert row.status == ConnectorStatus.ACTIVE


#: Short enough to keep the suite fast, long enough to be a real lock wait.
_HELD_BOUND_MS = 300

#: How long past the bound the door may take to hand back (the exchange is instant).
_HELD_SLACK_SECONDS = 5.0


def _issuing(access: str) -> object:
    async def provider(*_args: object, **_kwargs: object) -> RefreshedToken:
        return RefreshedToken(
            access_token=access,
            refresh_token="refresh-2",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            reported_scopes=frozenset(),
        )

    return provider


async def _refusing(*_args: object, **_kwargs: object) -> RefreshedToken:
    raise RefreshRefused(RefreshRefusal.REVOKED, status_code=400)


async def _while_held(
    engine: AsyncEngine, row_id: UUID, target: RefreshTarget[ConnectorCredentials]
) -> tuple[bool, asyncio.Task[ConnectorCredentials]]:
    """Hold ``row_id`` as a caller's open transaction would, then ask the door.

    The row is locked BEFORE the door starts, and ALWAYS released afterwards: a door
    that waits for it ends the test as a failure instead of hanging it.

    Returns:
        Whether the door handed back while the row was held, and the door itself.
    """
    async with AsyncSession(engine) as holder:
        await holder.execute(select(Connector).where(Connector.id == row_id).with_for_update())
        door = asyncio.create_task(oauth_refresh.ensure_fresh_credentials(target))
        handed_back, _ = await asyncio.wait(
            {door}, timeout=_HELD_BOUND_MS / 1000 + _HELD_SLACK_SECONDS
        )
        await holder.rollback()
    return door in handed_back, door


class TestARowHeldByItsCallerNeverHangsTheDoor:
    """The door writes on a session of its own: a caller whose open transaction holds
    the row waits on the door while the door would wait on its lock. On the real
    server, the door gives up within its bound and says so (audit AC-029)."""

    @pytest.fixture(autouse=True)
    def _short_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "oauth_refresh_write_lock_timeout_ms", _HELD_BOUND_MS)

    async def test_a_held_connector_row_serves_the_issued_token_unstored(
        self, async_engine: AsyncEngine, owner: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", _issuing("issued"))
        handed_back, door = await _while_held(
            async_engine, connector.id, legacy_connector_target(connector)
        )

        served = await door
        row = await _row(async_engine, connector.id)
        assert handed_back, "the door waited for its caller's row past its bound"
        assert served.access_token == "issued"
        assert row.credentials_encrypted == connector.credentials_encrypted

    async def test_a_held_link_bounds_the_grant_write(
        self, async_engine: AsyncEngine, owner: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The grant is locked first, then EVERY link: one held link is enough."""
        calendar, tasks, grant = await _linked(async_engine, owner)
        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", _issuing("granted"))
        handed_back, door = await _while_held(async_engine, tasks.id, GrantTokenTarget(calendar))

        served = await door
        async with AsyncSession(async_engine) as db:
            grant_row = await db.get(OAuthGrant, grant.id)
        assert grant_row is not None
        assert handed_back, "the door waited for a held link past its bound"
        assert served.access_token == "granted"
        assert grant_row.credentials_encrypted == grant.credentials_encrypted

    async def test_a_refusal_the_door_cannot_verify_is_a_failure_not_a_disconnection(
        self, async_engine: AsyncEngine, owner: UUID, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        connector = await _legacy(async_engine, owner, ConnectorStatus.ACTIVE)
        monkeypatch.setattr(oauth_refresh_targets, "exchange_refresh_token", _refusing)
        handed_back, door = await _while_held(
            async_engine, connector.id, legacy_connector_target(connector)
        )

        with pytest.raises(ValidationError):
            await door
        assert handed_back, "the door waited for its caller's row past its bound"
        assert (await _row(async_engine, connector.id)).status == ConnectorStatus.ACTIVE
