"""Real PostgreSQL transitions for one authorization serving several connectors."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.core.oauth.exceptions import OAuthStateValidationError
from src.core.oauth.flow_handler import OAuthTokenResponse
from src.core.security import decrypt_data, encrypt_data
from src.domains.connectors.models import (
    Connector,
    ConnectorGlobalConfig,
    ConnectorStatus,
    ConnectorType,
    OAuthGrant,
)
from src.domains.connectors.oauth_bulk import plan_connection, plan_reconnection
from src.domains.connectors.oauth_bulk_service import BulkOAuthService
from src.domains.connectors.oauth_identity import ProviderIdentity
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User

pytestmark = pytest.mark.integration


class _StateStore:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, object]] = {}

    async def store_oauth_state(
        self, state: str, data: dict[str, object], *, expire_minutes: int
    ) -> None:
        assert expire_minutes == 5
        self.values[state] = data

    async def get_oauth_state(self, state: str) -> dict[str, object] | None:
        return self.values.pop(state, None)


async def _expired(db: AsyncSession, user: User, kind: ConnectorType) -> Connector:
    old = ConnectorCredentials(
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    connector = Connector(
        user_id=user.id,
        connector_type=kind,
        status=ConnectorStatus.ERROR,
        scopes=[],
        credentials_encrypted=encrypt_data(old.model_dump_json()),
    )
    db.add(connector)
    await db.flush()
    return connector


def _tokens(scopes: str) -> OAuthTokenResponse:
    return OAuthTokenResponse(
        access_token="new-access",
        refresh_token="new-refresh",
        expires_in=3599,
        scope=scopes,
    )


async def test_authorization_url_contains_one_union_and_server_side_selection(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module

    gmail = await _expired(async_session, test_user, ConnectorType.GOOGLE_GMAIL)
    calendar = await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)

    response = await BulkOAuthService(async_session).initiate_reconnection(
        test_user.id, "google", [gmail.connector_type, calendar.connector_type]
    )

    query = parse_qs(urlparse(response.authorization_url).query)
    assert set(query["scope"][0].split()) == {
        "openid",
        "email",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.settings.basic",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    }
    assert len(query["scope"][0].split()) == 9
    assert query["redirect_uri"][0].endswith("/connectors/oauth-bulk/google/callback")
    assert query["access_type"] == ["offline"]
    assert query["prompt"] == ["consent"]
    assert store.values[response.state]["connector_types"] == "google_gmail,google_calendar"
    assert store.values[response.state]["user_id"] == str(test_user.id)


async def test_authenticated_bulk_route_starts_one_authorization(
    async_session: AsyncSession,
    authenticated_client: tuple[AsyncClient, User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module

    client, user = authenticated_client
    await _expired(async_session, user, ConnectorType.GOOGLE_GMAIL)
    await _expired(async_session, user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)

    response = await client.post(
        "/api/v1/connectors/oauth-bulk/google/authorize",
        json={"connector_types": ["google_gmail", "google_calendar"]},
    )

    assert response.status_code == 200
    assert urlparse(response.json()["authorization_url"]).hostname == "accounts.google.com"
    assert len(store.values) == 1


async def test_callback_consumes_state_once_and_activates_only_consented_services(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module
    from src.core.oauth.flow_handler import OAuthFlowHandler

    gmail = await _expired(async_session, test_user, ConnectorType.GOOGLE_GMAIL)
    calendar = await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)
    monkeypatch.setattr(bulk_module, "fetch_provider_keys", AsyncMock(return_value={"keys": []}))

    def verified_account(*args: object, **kwargs: object) -> ProviderIdentity:
        assert kwargs["access_token"] == "one-access"
        return ProviderIdentity("one-google-account", "owner@gmail.com")

    monkeypatch.setattr(
        bulk_module,
        "verify_provider_identity",
        verified_account,
    )

    async def exchange(self: OAuthFlowHandler, code: str, verifier: str) -> dict[str, object]:
        assert code == "one-code"
        assert verifier
        return {
            "access_token": "one-access",
            "refresh_token": "one-refresh",
            "expires_in": 3599,
            "scope": "openid email https://www.googleapis.com/auth/calendar",
            "id_token": "provider-id-token",
        }

    monkeypatch.setattr(OAuthFlowHandler, "_exchange_code_for_tokens", exchange)
    initiated = await BulkOAuthService(async_session).initiate_reconnection(
        test_user.id, "google", [gmail.connector_type, calendar.connector_type]
    )
    result = await BulkOAuthService(async_session).complete_callback(
        "google", "one-code", initiated.state
    )

    await async_session.refresh(gmail)
    await async_session.refresh(calendar)
    assert result.activated == (ConnectorType.GOOGLE_CALENDAR,)
    assert gmail.status == ConnectorStatus.ERROR
    assert calendar.status == ConnectorStatus.ACTIVE
    with pytest.raises(OAuthStateValidationError):
        await BulkOAuthService(async_session).complete_callback(
            "google", "one-code", initiated.state
        )


async def test_one_google_authorization_creates_one_grant_and_two_active_connectors(
    async_session: AsyncSession, test_user: User
) -> None:
    gmail = await _expired(async_session, test_user, ConnectorType.GOOGLE_GMAIL)
    calendar = await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    plan = plan_reconnection(
        "google", [gmail, calendar], [gmail.connector_type, calendar.connector_type]
    )

    result = await BulkOAuthService(async_session).activate_from_tokens(
        test_user.id,
        "google",
        plan,
        ProviderIdentity("google-123", "owner@gmail.com"),
        _tokens(" ".join(plan.scopes)),
        "lia-google-client",
    )

    await async_session.refresh(gmail)
    await async_session.refresh(calendar)
    grants = list((await async_session.scalars(select(OAuthGrant))).all())
    assert result.activated == (ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CALENDAR)
    assert result.denied == ()
    assert len(grants) == 1
    assert gmail.status == calendar.status == ConnectorStatus.ACTIVE
    assert gmail.oauth_grant_id == calendar.oauth_grant_id == grants[0].id
    assert (
        ConnectorCredentials.model_validate_json(
            decrypt_data(grants[0].credentials_encrypted)
        ).refresh_token
        == "new-refresh"
    )
    listed = await ConnectorService(async_session).get_user_connectors(test_user.id)
    assert {item.oauth_grant_id for item in listed.connectors} == {grants[0].id}


async def test_partial_google_consent_keeps_denied_service_in_error(
    async_session: AsyncSession, test_user: User
) -> None:
    gmail = await _expired(async_session, test_user, ConnectorType.GOOGLE_GMAIL)
    calendar = await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    plan = plan_reconnection(
        "google", [gmail, calendar], [gmail.connector_type, calendar.connector_type]
    )

    result = await BulkOAuthService(async_session).activate_from_tokens(
        test_user.id,
        "google",
        plan,
        ProviderIdentity("google-123", "owner@gmail.com"),
        _tokens("openid email https://www.googleapis.com/auth/calendar"),
        "lia-google-client",
    )

    await async_session.refresh(gmail)
    await async_session.refresh(calendar)
    assert result.activated == (ConnectorType.GOOGLE_CALENDAR,)
    assert result.denied == (ConnectorType.GOOGLE_GMAIL,)
    assert gmail.status == ConnectorStatus.ERROR
    assert gmail.oauth_grant_id is None
    assert calendar.status == ConnectorStatus.ACTIVE


async def test_reconnection_rejects_a_different_account_without_changing_rows(
    async_session: AsyncSession, test_user: User
) -> None:
    gmail = await _expired(async_session, test_user, ConnectorType.GOOGLE_GMAIL)
    grant = OAuthGrant(
        user_id=test_user.id,
        provider="google",
        client_id="lia-google-client",
        subject="original-google",
        email="old@gmail.com",
        scopes=[],
        credentials_encrypted=encrypt_data(
            ConnectorCredentials(access_token="old").model_dump_json()
        ),
    )
    async_session.add(grant)
    await async_session.flush()
    gmail.oauth_grant_id = grant.id
    await async_session.commit()
    plan = plan_reconnection("google", [gmail], [ConnectorType.GOOGLE_GMAIL])

    with pytest.raises(ValueError, match="account"):
        await BulkOAuthService(async_session).activate_from_tokens(
            test_user.id,
            "google",
            plan,
            ProviderIdentity("different-google", "other@gmail.com"),
            _tokens(" ".join(plan.scopes)),
            "lia-google-client",
        )

    await async_session.refresh(gmail)
    assert gmail.status == ConnectorStatus.ERROR
    assert gmail.oauth_grant_id == grant.id


async def test_one_microsoft_authorization_recovers_graph_services_for_one_tenant_account(
    async_session: AsyncSession, test_user: User
) -> None:
    outlook = await _expired(async_session, test_user, ConnectorType.MICROSOFT_OUTLOOK)
    tasks = await _expired(async_session, test_user, ConnectorType.MICROSOFT_TASKS)
    await async_session.commit()
    plan = plan_reconnection(
        "microsoft", [outlook, tasks], [outlook.connector_type, tasks.connector_type]
    )

    result = await BulkOAuthService(async_session).activate_from_tokens(
        test_user.id,
        "microsoft",
        plan,
        ProviderIdentity(
            "11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222",
            "owner@example.com",
        ),
        _tokens("User.Read Mail.ReadWrite Mail.Send Tasks.ReadWrite"),
        "lia-microsoft-client",
    )

    await async_session.refresh(outlook)
    await async_session.refresh(tasks)
    assert result.activated == (ConnectorType.MICROSOFT_OUTLOOK, ConnectorType.MICROSOFT_TASKS)
    assert outlook.oauth_grant_id == tasks.oauth_grant_id == result.grant_id


async def test_microsoft_callback_without_reported_scopes_never_assumes_consent(
    async_session: AsyncSession, test_user: User
) -> None:
    outlook = await _expired(async_session, test_user, ConnectorType.MICROSOFT_OUTLOOK)
    await async_session.commit()
    plan = plan_reconnection("microsoft", [outlook], [outlook.connector_type])

    with pytest.raises(ValueError, match="scopes"):
        await BulkOAuthService(async_session).activate_from_tokens(
            test_user.id,
            "microsoft",
            plan,
            ProviderIdentity(
                "11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222",
                "owner@example.com",
            ),
            OAuthTokenResponse(access_token="new", refresh_token="refresh", scope=None),
            "lia-microsoft-client",
        )

    await async_session.refresh(outlook)
    assert outlook.status == ConnectorStatus.ERROR
    assert outlook.oauth_grant_id is None


async def test_admin_disable_during_oauth_redirect_blocks_activation(
    async_session: AsyncSession, test_user: User
) -> None:
    calendar = await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()
    plan = plan_reconnection("google", [calendar], [calendar.connector_type])
    async_session.add(
        ConnectorGlobalConfig(
            connector_type=ConnectorType.GOOGLE_CALENDAR,
            is_enabled=False,
        )
    )
    await async_session.commit()

    with pytest.raises(AuthorizationError):
        await BulkOAuthService(async_session).activate_from_tokens(
            test_user.id,
            "google",
            plan,
            ProviderIdentity("google-sub", "owner@gmail.com"),
            _tokens(" ".join(plan.scopes)),
            "lia-google-client",
        )

    await async_session.refresh(calendar)
    assert calendar.status == ConnectorStatus.ERROR
    assert calendar.oauth_grant_id is None


async def test_wrong_account_returns_actionable_callback_code(
    async_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.domains.connectors.oauth_bulk_router import bulk_oauth_callback
    from src.domains.connectors.oauth_bulk_service import OAuthAccountMismatchError

    async def wrong_account(*args: object, **kwargs: object) -> None:
        raise OAuthAccountMismatchError("Provider account differs from the selected account")

    monkeypatch.setattr(BulkOAuthService, "complete_callback", wrong_account)
    response = await bulk_oauth_callback("google", "state", "code", None, False, async_session)
    assert parse_qs(urlparse(response.headers["location"]).query)["connector_error"] == [
        "account_mismatch"
    ]


async def test_connect_all_starts_one_google_authorization_for_absent_services(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module

    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)

    response = await BulkOAuthService(async_session).initiate_connect_all(test_user.id, "google")

    query = parse_qs(urlparse(response.authorization_url).query)
    assert query["prompt"] == ["select_account consent"]
    assert query["access_type"] == ["offline"]
    assert len(query["scope"][0].split()) > 5
    assert store.values[response.state]["bulk_mode"] == "connect"
    assert len(store.values[response.state]["connector_types"].split(",")) == 5
    assert len(store.values) == 1


async def test_authenticated_connect_all_route_derives_services_and_rejects_empty_selection(
    async_session: AsyncSession,
    authenticated_client: tuple[AsyncClient, User],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module

    client, user = authenticated_client
    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)

    response = await client.post(
        "/api/v1/connectors/oauth-bulk/microsoft/connect-all/authorize", json={}
    )
    assert response.status_code == 200
    state = response.json()["state"]
    assert len(store.values) == 1
    assert store.values[state]["bulk_mode"] == "connect"
    assert store.values[state]["user_id"] == str(user.id)
    assert len(store.values[state]["connector_types"].split(",")) == 4

    invalid = await client.post(
        "/api/v1/connectors/oauth-bulk/microsoft/connect-all/authorize",
        json={"connector_types": ["microsoft_outlook"]},
    )
    assert invalid.status_code == 422

    for connector_type in ConnectorType.get_microsoft_types():
        await _expired(async_session, user, connector_type)
    await async_session.commit()
    unavailable = await client.post(
        "/api/v1/connectors/oauth-bulk/microsoft/connect-all/authorize", json={}
    )
    assert unavailable.status_code == 400
    assert len(store.values) == 1


async def test_connect_all_callback_uses_one_state_and_reports_actual_partial_result(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module
    from src.core.oauth.flow_handler import OAuthFlowHandler

    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)
    monkeypatch.setattr(bulk_module, "fetch_provider_keys", AsyncMock(return_value={"keys": []}))
    monkeypatch.setattr(
        bulk_module,
        "verify_provider_identity",
        lambda *args, **kwargs: ProviderIdentity("account-one", "owner@gmail.com"),
    )

    async def exchange(self: OAuthFlowHandler, code: str, verifier: str) -> dict[str, object]:
        assert code == "one-code"
        assert verifier
        return {
            "access_token": "one-access",
            "refresh_token": "one-refresh",
            "expires_in": 3599,
            "scope": "openid email https://www.googleapis.com/auth/calendar",
            "id_token": "provider-id-token",
        }

    monkeypatch.setattr(OAuthFlowHandler, "_exchange_code_for_tokens", exchange)
    initiated = await BulkOAuthService(async_session).initiate_connect_all(test_user.id, "google")
    result = await BulkOAuthService(async_session).complete_callback(
        "google", "one-code", initiated.state
    )

    rows = list((await async_session.scalars(select(Connector))).all())
    assert result.mode == "connect"
    assert result.activated == (ConnectorType.GOOGLE_CALENDAR,)
    assert len(result.denied) == 4
    assert len(rows) == 1
    assert rows[0].connector_type == ConnectorType.GOOGLE_CALENDAR
    assert initiated.state not in store.values


async def test_connect_all_creates_only_services_with_actual_google_consent(
    async_session: AsyncSession, test_user: User
) -> None:
    selected = [ConnectorType.GOOGLE_GMAIL, ConnectorType.GOOGLE_CALENDAR]
    plan = plan_connection("google", [], selected)

    result = await BulkOAuthService(async_session).activate_from_tokens(
        test_user.id,
        "google",
        plan,
        ProviderIdentity("one-account", "owner@gmail.com"),
        _tokens("openid email https://www.googleapis.com/auth/calendar"),
        "lia-google-client",
        mode="connect",
    )

    rows = list((await async_session.scalars(select(Connector))).all())
    assert result.activated == (ConnectorType.GOOGLE_CALENDAR,)
    assert result.denied == (ConnectorType.GOOGLE_GMAIL,)
    assert [row.connector_type for row in rows] == [ConnectorType.GOOGLE_CALENDAR]
    assert rows[0].status == ConnectorStatus.ACTIVE
    assert rows[0].oauth_grant_id == result.grant_id


async def test_connect_all_microsoft_creates_four_services_with_one_grant(
    async_session: AsyncSession, test_user: User
) -> None:
    selected = list(ConnectorType.get_microsoft_types())
    plan = plan_connection("microsoft", [], selected)

    result = await BulkOAuthService(async_session).activate_from_tokens(
        test_user.id,
        "microsoft",
        plan,
        ProviderIdentity(
            "11111111-1111-1111-1111-111111111111:22222222-2222-2222-2222-222222222222",
            "owner@example.com",
        ),
        _tokens(
            "User.Read Mail.ReadWrite Mail.Send Calendars.ReadWrite Contacts.ReadWrite Tasks.ReadWrite"
        ),
        "lia-microsoft-client",
        mode="connect",
    )

    rows = list((await async_session.scalars(select(Connector))).all())
    assert len(result.activated) == len(rows) == 4
    assert {row.oauth_grant_id for row in rows} == {result.grant_id}


async def test_connect_all_can_bind_new_service_to_selected_existing_account(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.domains.connectors.oauth_bulk_service as bulk_module

    calendar = Connector(
        user_id=test_user.id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        scopes=["https://www.googleapis.com/auth/calendar"],
        credentials_encrypted=encrypt_data(
            ConnectorCredentials(access_token="old", refresh_token="old-refresh").model_dump_json()
        ),
    )
    grant = OAuthGrant(
        user_id=test_user.id,
        provider="google",
        client_id=settings.google_client_id,
        subject="one-account",
        email="owner@gmail.com",
        scopes=calendar.scopes,
        credentials_encrypted=calendar.credentials_encrypted,
    )
    async_session.add_all([calendar, grant])
    await async_session.flush()
    calendar.oauth_grant_id = grant.id
    await async_session.commit()
    user_id = test_user.id
    grant_id = grant.id
    store = _StateStore()
    monkeypatch.setattr(bulk_module, "get_redis_session", AsyncMock(return_value=object()))
    monkeypatch.setattr(bulk_module, "SessionService", lambda redis: store)

    initiated = await BulkOAuthService(async_session).initiate_connect_all(
        test_user.id, "google", grant.id
    )
    query = parse_qs(urlparse(initiated.authorization_url).query)
    assert query["login_hint"] == ["owner@gmail.com"]
    assert "https://www.googleapis.com/auth/calendar" in query["scope"][0].split()
    selected = [ConnectorType.GOOGLE_GMAIL]
    plan = plan_connection("google", [calendar], selected, expected_grant_id=grant.id)
    with pytest.raises(ValueError, match="account"):
        await BulkOAuthService(async_session).activate_from_tokens(
            test_user.id,
            "google",
            plan,
            ProviderIdentity("other-account", "other@gmail.com"),
            _tokens(" ".join(plan.scopes)),
            settings.google_client_id,
            mode="connect",
        )
    await async_session.rollback()

    result = await BulkOAuthService(async_session).activate_from_tokens(
        user_id,
        "google",
        plan,
        ProviderIdentity("one-account", "owner@gmail.com"),
        _tokens(" ".join((*plan.scopes, "https://www.googleapis.com/auth/calendar"))),
        settings.google_client_id,
        mode="connect",
    )
    rows = list((await async_session.scalars(select(Connector))).all())
    assert result.grant_id == grant_id
    assert len(rows) == 2
    assert {row.oauth_grant_id for row in rows} == {grant_id}


async def test_connect_all_rejects_a_grant_owned_by_another_user(
    async_session: AsyncSession, test_user: User
) -> None:
    other = User(
        email="other-account@example.com",
        hashed_password="test-hash",
        full_name="Other User",
        is_active=True,
        is_verified=True,
    )
    async_session.add(other)
    await async_session.flush()
    foreign_grant = OAuthGrant(
        user_id=other.id,
        provider="google",
        client_id=settings.google_client_id,
        subject="foreign-subject",
        email="foreign@gmail.com",
        scopes=["openid", "email"],
        credentials_encrypted="test-ciphertext",
    )
    async_session.add(foreign_grant)
    await async_session.commit()

    with pytest.raises(ValueError, match="missing"):
        await BulkOAuthService(async_session).initiate_connect_all(
            test_user.id, "google", foreign_grant.id
        )
    assert not (await async_session.scalars(select(Connector))).all()


async def test_connect_all_rechecks_absence_before_insert(
    async_session: AsyncSession, test_user: User
) -> None:
    plan = plan_connection("google", [], [ConnectorType.GOOGLE_CALENDAR])
    await _expired(async_session, test_user, ConnectorType.GOOGLE_CALENDAR)
    await async_session.commit()

    with pytest.raises(ValueError, match="unconfigured"):
        await BulkOAuthService(async_session).activate_from_tokens(
            test_user.id,
            "google",
            plan,
            ProviderIdentity("one-account", "owner@gmail.com"),
            _tokens(" ".join(plan.scopes)),
            "lia-google-client",
            mode="connect",
        )
