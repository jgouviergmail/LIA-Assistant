"""A shared refresh rotates once and leaves every linked service consistent."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import wait_none

from src.core.config import settings
from src.core.exceptions import ConnectorTokenExpiredError, ValidationError
from src.core.oauth import GoogleOAuthProvider, OAuthFlowHandler
from src.core.oauth.flow_handler import OAuthTokenResponse
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.oauth_grant_runtime import OAuthGrantRuntime
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.users.account_deletion_service import AccountDeletionService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


async def test_legacy_connector_transient_refresh_keeps_active_status_and_error_type(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.service as service_module

    credentials = ConnectorCredentials(
        access_token="expired",
        refresh_token="still-valid",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    connector = Connector(
        user_id=test_user.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted=encrypt_data(credentials.model_dump_json()),
    )
    async_session.add(connector)
    await async_session.commit()

    real_client = httpx.AsyncClient

    def unavailable_client(*args: object, **kwargs: object) -> httpx.AsyncClient:
        def unavailable(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={"error": "temporarily_unavailable"})

        return real_client(*args, transport=httpx.MockTransport(unavailable), **kwargs)

    monkeypatch.setattr(service_module.httpx, "AsyncClient", unavailable_client)
    monkeypatch.setattr(service_module, "wait_exponential", lambda **kwargs: wait_none())

    with pytest.raises(ValidationError, match="OAuth"):
        await ConnectorService(async_session).get_connector_credentials(
            test_user.id, ConnectorType.GOOGLE_CALENDAR
        )

    await async_session.refresh(connector)
    assert connector.status == ConnectorStatus.ACTIVE
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(connector.credentials_encrypted)
        ).refresh_token
        == "still-valid"
    )


async def _linked_pair(db: AsyncSession, user: User) -> tuple[Connector, Connector, OAuthGrant]:
    credentials = ConnectorCredentials(
        access_token="stale-access",
        refresh_token="stale-refresh",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    encrypted = encrypt_data(credentials.model_dump_json())
    grant = OAuthGrant(
        user_id=user.id,
        provider="google",
        client_id=settings.google_client_id,
        subject="google-sub",
        email="owner@gmail.com",
        scopes=[
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/tasks",
        ],
        credentials_encrypted=encrypted,
    )
    db.add(grant)
    await db.flush()
    calendar = Connector(
        user_id=user.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        scopes=grant.scopes,
        credentials_encrypted=encrypted,
        oauth_grant_id=grant.id,
    )
    tasks = Connector(
        user_id=user.id,
        connector_type=ConnectorType.GOOGLE_TASKS,
        status=ConnectorStatus.ACTIVE,
        scopes=grant.scopes,
        credentials_encrypted=encrypted,
        oauth_grant_id=grant.id,
    )
    db.add_all([calendar, tasks])
    await db.commit()
    return calendar, tasks, grant


async def test_rotated_refresh_token_is_stored_once_and_seen_by_both_connectors(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_grant_runtime as runtime_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)
    calls = 0

    async def provider_response(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            200,
            json={
                "access_token": "fresh-access",
                "refresh_token": "rotated-refresh",
                "expires_in": 3599,
            },
        )

    monkeypatch.setattr(runtime_module, "_post_refresh", provider_response)
    cache = AsyncMock()
    monkeypatch.setattr(
        runtime_module, "get_redis_cache", AsyncMock(return_value=cache), raising=False
    )
    first = await OAuthGrantRuntime(async_session).credentials_for(calendar)
    second = await OAuthGrantRuntime(async_session).credentials_for(tasks)

    await async_session.refresh(grant)
    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    assert calls == 1
    cache.delete.assert_awaited_once_with(f"user_connectors:{test_user.id}")
    assert first.refresh_token == second.refresh_token == "rotated-refresh"
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).refresh_token
        == "rotated-refresh"
    )
    assert (
        calendar.credentials_encrypted == tasks.credentials_encrypted == grant.credentials_encrypted
    )


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
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_grant_runtime as runtime_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)

    async def revoked(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    monkeypatch.setattr(runtime_module, "_post_refresh", revoked)
    cache = AsyncMock()
    monkeypatch.setattr(
        runtime_module, "get_redis_cache", AsyncMock(return_value=cache), raising=False
    )
    with pytest.raises(ConnectorTokenExpiredError):
        await OAuthGrantRuntime(async_session).credentials_for(calendar)

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    await async_session.refresh(grant)
    assert calendar.status == tasks.status == ConnectorStatus.ERROR
    cache.delete.assert_awaited_once_with(f"user_connectors:{test_user.id}")
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).refresh_token
        == "stale-refresh"
    )


async def test_transient_refresh_failure_keeps_grant_and_services_active(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_grant_runtime as runtime_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)

    async def unavailable(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(503, json={"error": "temporarily_unavailable"})

    monkeypatch.setattr(runtime_module, "_post_refresh", unavailable)
    with pytest.raises(ValidationError):
        await OAuthGrantRuntime(async_session).credentials_for(calendar)

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    await async_session.refresh(grant)
    assert calendar.status == tasks.status == ConnectorStatus.ACTIVE
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).refresh_token
        == "stale-refresh"
    )


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
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_grant_runtime as runtime_module

    calendar, tasks, grant = await _linked_pair(async_session, test_user)

    async def malformed(*args: object, **kwargs: object) -> httpx.Response:
        return httpx.Response(200, json=["unexpected", "list"])

    monkeypatch.setattr(runtime_module, "_post_refresh", malformed)
    with pytest.raises(ValidationError):
        await OAuthGrantRuntime(async_session).credentials_for(calendar)

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    await async_session.refresh(grant)
    assert calendar.status == tasks.status == ConnectorStatus.ACTIVE
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grant.credentials_encrypted)
        ).refresh_token
        == "stale-refresh"
    )


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
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_grant_runtime as runtime_module
    from src.infrastructure.scheduler.token_refresh import _process_connector

    calendar, tasks, grant = await _linked_pair(async_session, test_user)
    soon = ConnectorCredentials(
        access_token="soon-access",
        refresh_token="soon-refresh",
        expires_at=datetime.now(UTC) + timedelta(minutes=15),
    )
    grant.credentials_encrypted = calendar.credentials_encrypted = tasks.credentials_encrypted = (
        encrypt_data(soon.model_dump_json())
    )
    await async_session.commit()
    calls = 0

    async def refreshed(*args: object, **kwargs: object) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"access_token": "proactive-access", "expires_in": 3599})

    monkeypatch.setattr(runtime_module, "_post_refresh", refreshed)
    result = await _process_connector(
        calendar, datetime.now(UTC) + timedelta(minutes=30), async_session
    )

    assert result == "refreshed"
    assert calls == 1
    await async_session.refresh(grant)
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
        ConnectorType.GOOGLE_CALENDAR
    )

    await async_session.refresh(calendar)
    await async_session.refresh(tasks)
    assert revoked == []
    assert calendar.status == ConnectorStatus.REVOKED
    assert tasks.status == ConnectorStatus.ERROR
    assert await async_session.get(OAuthGrant, grant.id) is not None
