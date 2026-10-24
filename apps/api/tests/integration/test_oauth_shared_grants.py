"""A shared refresh rotates once and leaves every linked service consistent (ADR-302).

Every refresh goes through the one refresh door (audit AC-029), which reads and writes
on sessions of its own: a refresh is therefore proven on rows committed outside the
test's rollback transaction, with the provider scripted behind the exchange's own HTTP
client — the whole chain runs, from the service to the conditional write. What needs no
refresh (a disconnection, a reconnection, an account deletion) keeps the test session.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from functools import partial
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from tenacity import wait_none

from src.core.config import settings
from src.core.exceptions import ConnectorTokenExpiredError, ValidationError
from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler
from src.core.oauth.flow_handler import OAuthTokenResponse
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors import oauth_refresh_exchange
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from tests.helpers.committed_users import commit_owner
from tests.helpers.oauth_refresh_io import commit_expired_connector

pytestmark = pytest.mark.integration

_CALENDAR = "https://www.googleapis.com/auth/calendar"
_TASKS = "https://www.googleapis.com/auth/tasks"

#: A cache entry a failed test leaves behind expires on its own: the Redis is shared.
_CACHED_TTL_SECONDS = 60


class _TokenEndpoint:
    """The provider's token endpoint: answers what a test scripts, the last one repeating."""

    def __init__(self, *answers: httpx.Response) -> None:
        self._answers: Iterator[httpx.Response] = iter(answers)
        self._last = answers[-1]
        self.calls = 0

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self._last = next(self._answers, self._last)
        return self._last


@pytest.fixture
def token_endpoint(monkeypatch: pytest.MonkeyPatch) -> Callable[..., _TokenEndpoint]:
    """Install a scripted provider behind the exchange's own HTTP client, retries unspaced."""
    real_client = httpx.AsyncClient
    monkeypatch.setattr(oauth_refresh_exchange, "_retry_wait", wait_none)

    def install(*answers: httpx.Response) -> _TokenEndpoint:
        scripted = _TokenEndpoint(*answers)
        transport = httpx.MockTransport(scripted.handle)
        monkeypatch.setattr(httpx, "AsyncClient", partial(real_client, transport=transport))
        return scripted

    return install


@pytest_asyncio.fixture
async def owner(async_engine: AsyncEngine, committed_user_ids: list[UUID]) -> UUID:
    return await commit_owner(async_engine, committed_user_ids)


def _stale() -> str:
    return encrypt_data(
        ConnectorCredentials(
            access_token="stale-access",
            refresh_token="stale-refresh",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        ).model_dump_json()
    )


def _grant(user_id: UUID, encrypted: str) -> OAuthGrant:
    return OAuthGrant(
        user_id=user_id,
        provider="google",
        client_id=settings.google_client_id,
        subject="google-sub",
        email="owner@gmail.com",
        scopes=[_CALENDAR, _TASKS],
        credentials_encrypted=encrypted,
    )


def _link(user_id: UUID, connector_type: ConnectorType, grant: OAuthGrant) -> Connector:
    return Connector(
        user_id=user_id,
        connector_type=connector_type,
        status=ConnectorStatus.ACTIVE,
        scopes=list(grant.scopes),
        credentials_encrypted=grant.credentials_encrypted,
        oauth_grant_id=grant.id,
    )


async def _linked_pair(db: AsyncSession, user: User) -> tuple[Connector, Connector, OAuthGrant]:
    grant = _grant(user.id, _stale())
    db.add(grant)
    await db.flush()
    calendar = _link(user.id, ConnectorType.GOOGLE_CALENDAR, grant)
    tasks = _link(user.id, ConnectorType.GOOGLE_TASKS, grant)
    db.add_all([calendar, tasks])
    await db.commit()
    return calendar, tasks, grant


async def _committed_pair(
    engine: AsyncEngine, owner: UUID, encrypted: str | None = None
) -> tuple[Connector, Connector, OAuthGrant]:
    """A grant and its two links, committed where the refresh door's sessions see them."""
    async with AsyncSession(engine, expire_on_commit=False) as db:
        grant = _grant(owner, encrypted or _stale())
        db.add(grant)
        await db.flush()
        calendar = _link(owner, ConnectorType.GOOGLE_CALENDAR, grant)
        tasks = _link(owner, ConnectorType.GOOGLE_TASKS, grant)
        db.add_all([calendar, tasks])
        await db.commit()
        return calendar, tasks, grant


async def _rows(
    engine: AsyncEngine, *ids: UUID
) -> tuple[list[Connector], OAuthGrant | None, str | None]:
    """The links' rows, their grant, and the refresh token the grant stores."""
    async with AsyncSession(engine) as db:
        links = [row for row in [await db.get(Connector, i) for i in ids] if row is not None]
        grant = await db.get(OAuthGrant, links[0].oauth_grant_id) if links else None
    if grant is None:
        return links, None, None
    stored = ConnectorCredentials.model_validate_json(decrypt_data(grant.credentials_encrypted))
    return links, grant, stored.refresh_token


async def _read(engine: AsyncEngine, owner: UUID, connector_type: ConnectorType) -> object:
    async with AsyncSession(engine) as caller:
        return await ConnectorService(caller).get_connector_credentials(owner, connector_type)


async def test_legacy_connector_transient_refresh_keeps_active_status_and_error_type(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    connector = await commit_expired_connector(
        async_engine, owner, connector_type=ConnectorType.GOOGLE_CALENDAR
    )
    endpoint = token_endpoint(httpx.Response(503, json={"error": "temporarily_unavailable"}))

    with pytest.raises(ValidationError, match="OAuth"):
        await _read(async_engine, owner, ConnectorType.GOOGLE_CALENDAR)

    async with AsyncSession(async_engine) as db:
        row = await db.get(Connector, connector.id)
    assert row is not None and row.status == ConnectorStatus.ACTIVE
    stored = ConnectorCredentials.model_validate_json(decrypt_data(row.credentials_encrypted))
    assert stored.refresh_token == "refresh-1"
    assert endpoint.calls > 1, "an outage is retried before it is reported"


async def test_rotated_refresh_token_is_stored_once_and_seen_by_both_connectors(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    calendar, tasks, _grant_row = await _committed_pair(async_engine, owner)
    cache = await get_redis_cache()
    await cache.set(f"user_connectors:{owner}", "cached", ex=_CACHED_TTL_SECONDS)
    endpoint = token_endpoint(
        httpx.Response(
            200,
            json={
                "access_token": "fresh-access",
                "refresh_token": "rotated-refresh",
                "expires_in": 3599,
            },
        )
    )

    first = await _read(async_engine, owner, ConnectorType.GOOGLE_CALENDAR)
    second = await _read(async_engine, owner, ConnectorType.GOOGLE_TASKS)

    links, grant, stored = await _rows(async_engine, calendar.id, tasks.id)
    assert endpoint.calls == 1
    assert await cache.get(f"user_connectors:{owner}") is None
    assert isinstance(first, ConnectorCredentials) and isinstance(second, ConnectorCredentials)
    assert first.refresh_token == second.refresh_token == "rotated-refresh"
    assert stored == "rotated-refresh"
    assert grant is not None
    assert {row.credentials_encrypted for row in links} == {grant.credentials_encrypted}


async def test_connector_uses_grant_as_authority_when_legacy_copy_is_stale(
    async_session: AsyncSession, test_user: User
) -> None:
    calendar, _, grant = await _linked_pair(async_session, test_user)
    grant.credentials_encrypted = encrypt_data(
        ConnectorCredentials(
            access_token="grant-access",
            refresh_token="grant-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ).model_dump_json()
    )
    calendar.credentials_encrypted = encrypt_data(
        ConnectorCredentials(
            access_token="row-access",
            refresh_token="row-refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ).model_dump_json()
    )
    await async_session.commit()

    actual = await ConnectorService(async_session).get_connector_credentials(
        test_user.id, ConnectorType.GOOGLE_CALENDAR
    )

    assert actual is not None
    assert actual.access_token == "grant-access"


async def test_invalid_grant_marks_only_its_linked_services_in_error(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    calendar, tasks, _grant_row = await _committed_pair(async_engine, owner)
    cache = await get_redis_cache()
    await cache.set(f"user_connectors:{owner}", "cached", ex=_CACHED_TTL_SECONDS)
    token_endpoint(httpx.Response(400, json={"error": "invalid_grant"}))

    with pytest.raises(ConnectorTokenExpiredError):
        await _read(async_engine, owner, ConnectorType.GOOGLE_CALENDAR)

    links, _grant, stored = await _rows(async_engine, calendar.id, tasks.id)
    assert [row.status for row in links] == [ConnectorStatus.ERROR, ConnectorStatus.ERROR]
    assert await cache.get(f"user_connectors:{owner}") is None
    assert stored == "stale-refresh"


async def test_transient_refresh_failure_keeps_grant_and_services_active(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    calendar, tasks, _grant_row = await _committed_pair(async_engine, owner)
    token_endpoint(httpx.Response(503, json={"error": "temporarily_unavailable"}))

    with pytest.raises(ValidationError):
        await _read(async_engine, owner, ConnectorType.GOOGLE_CALENDAR)

    links, _grant, stored = await _rows(async_engine, calendar.id, tasks.id)
    assert [row.status for row in links] == [ConnectorStatus.ACTIVE, ConnectorStatus.ACTIVE]
    assert stored == "stale-refresh"


async def test_disconnecting_one_service_keeps_shared_grant_for_its_sibling(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    calendar, tasks, grant = await _linked_pair(async_session, test_user)
    service = ConnectorService(async_session)

    async def unexpected_revoke(connector: Connector) -> None:
        raise AssertionError("The shared grant must not be revoked")

    monkeypatch.setattr(service, "_revoke_oauth_token", unexpected_revoke)
    await service.delete_connector(test_user.id, calendar.id)

    assert await async_session.get(Connector, calendar.id) is None
    remaining = await async_session.get(Connector, tasks.id)
    assert remaining is not None and remaining.status == ConnectorStatus.ACTIVE
    assert await async_session.get(OAuthGrant, grant.id) is not None


async def test_malformed_refresh_response_preserves_last_good_grant(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    calendar, tasks, _grant_row = await _committed_pair(async_engine, owner)
    token_endpoint(httpx.Response(200, json=["unexpected", "list"]))

    with pytest.raises(ValidationError):
        await _read(async_engine, owner, ConnectorType.GOOGLE_CALENDAR)

    links, _grant, stored = await _rows(async_engine, calendar.id, tasks.id)
    assert [row.status for row in links] == [ConnectorStatus.ACTIVE, ConnectorStatus.ACTIVE]
    assert stored == "stale-refresh"


async def test_disconnecting_last_service_removes_its_grant(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    calendar, tasks, grant = await _linked_pair(async_session, test_user)
    service = ConnectorService(async_session)
    client = AsyncMock()
    monkeypatch.setattr(httpx, "AsyncClient", client)
    await service.delete_connector(test_user.id, calendar.id)
    await service.delete_connector(test_user.id, tasks.id)
    client.assert_not_called()

    assert await async_session.get(OAuthGrant, grant.id) is None


async def test_individual_reconnection_detaches_only_selected_service_from_shared_grant(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.service as service_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)

    async def callback(
        self: OAuthFlowHandler, code: str, state: str
    ) -> tuple[OAuthTokenResponse, dict[str, str]]:
        return (
            OAuthTokenResponse(
                access_token="individual-access",
                refresh_token="individual-refresh",
                expires_in=3599,
                scope="https://www.googleapis.com/auth/calendar",
            ),
            {"user_id": str(test_user.id), "connector_type": "google_calendar"},
        )

    monkeypatch.setattr(OAuthFlowHandler, "handle_callback", callback)
    monkeypatch.setattr(service_module, "get_redis_session", AsyncMock(return_value=object()))
    result = await ConnectorService(async_session)._handle_oauth_connector_callback(
        test_user.id,
        "code",
        "state",
        ConnectorType.GOOGLE_CALENDAR,
        GoogleOAuthProvider.for_calendar,
    )

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    assert result.oauth_grant_id is None
    assert calendar.oauth_grant_id is None
    assert tasks.oauth_grant_id == grant.id
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(calendar.credentials_encrypted)
        ).refresh_token
        == "individual-refresh"
    )
    assert await async_session.get(OAuthGrant, grant.id) is not None


async def test_account_deletion_revokes_each_distinct_google_account_grant(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _linked_pair(async_session, test_user)
    second = OAuthGrant(
        user_id=test_user.id,
        provider="google",
        client_id=settings.google_client_id,
        subject="second-google-sub",
        email="second@gmail.com",
        scopes=[],
        credentials_encrypted=encrypt_data(
            ConnectorCredentials(
                access_token="second-access", refresh_token="second-refresh"
            ).model_dump_json()
        ),
    )
    async_session.add(second)
    await async_session.commit()
    revoked: list[str] = []

    class ProviderClient:
        async def __aenter__(self) -> ProviderClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, data: dict[str, str]) -> httpx.Response:
            assert url == "https://oauth2.googleapis.com/revoke"
            revoked.append(data["token"])
            return httpx.Response(200)

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: ProviderClient())
    await AccountDeletionService(async_session)._revoke_all_oauth_tokens(test_user.id)

    assert set(revoked) == {"stale-refresh", "second-refresh"}


async def test_proactive_refresh_uses_its_longer_threshold_for_shared_grant(
    async_engine: AsyncEngine, owner: UUID, token_endpoint: Callable[..., _TokenEndpoint]
) -> None:
    from src.infrastructure.scheduler.token_refresh import _process_connector

    soon = encrypt_data(
        ConnectorCredentials(
            access_token="soon-access",
            refresh_token="soon-refresh",
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        ).model_dump_json()
    )
    calendar, tasks, _grant_row = await _committed_pair(async_engine, owner, soon)
    endpoint = token_endpoint(
        httpx.Response(200, json={"access_token": "proactive-access", "expires_in": 3599})
    )

    result = await _process_connector(calendar, datetime.now(UTC) + timedelta(minutes=30))

    _links, grant, _stored = await _rows(async_engine, calendar.id, tasks.id)
    assert result == "refreshed"
    assert endpoint.calls == 1
    assert grant is not None
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).access_token
        == "proactive-access"
    )


async def test_admin_disabling_one_shared_service_never_revokes_another_link(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.service as service_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)
    tasks.status = ConnectorStatus.ERROR
    await async_session.commit()
    revoked: list[str] = []

    class Client:
        async def __aenter__(self) -> Client:
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def post(self, url: str, *, data: dict[str, str]) -> httpx.Response:
            revoked.append(data["token"])
            return httpx.Response(200)

    class Mailer:
        async def send_connector_disabled_notification(self, **kwargs: object) -> bool:
            return True

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Client())
    monkeypatch.setattr(service_module, "get_email_service", lambda: Mailer())
    await ConnectorService(async_session)._revoke_all_connectors_by_type(
        ConnectorType.GOOGLE_CALENDAR, None
    )

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    assert revoked == []
    assert calendar.status == ConnectorStatus.REVOKED
    assert tasks.status == ConnectorStatus.ERROR
    assert await async_session.get(OAuthGrant, grant.id) is not None
