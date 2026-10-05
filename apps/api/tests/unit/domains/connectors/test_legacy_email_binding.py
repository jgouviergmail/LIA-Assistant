"""Legacy mailboxes keep an authenticated generation through rotation, not reconnect."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import httpx
import pytest
from langchain_core.messages import AIMessage

from src.core.card_composition import (
    CardComposition,
    CardCompositionUnavailable,
    card_composition_ctx,
)
from src.core.security import decrypt_data, encrypt_data
from src.domains.agents.display.card_actions import with_card_actions
from src.domains.agents.tools.email_card_binding import bind_email_card_accounts
from src.domains.agents.tools.emails_tools import GetEmailsTool
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.legacy_email_binding import bind_legacy_email_account
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.domains.connectors.service import ConnectorService

pytestmark = pytest.mark.unit
USER = UUID(int=1)


def connector(credentials, *, user=USER, identity=UUID(int=2), provider=ConnectorType.GOOGLE_GMAIL):
    return Connector(
        id=identity,
        user_id=user,
        connector_type=provider,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        oauth_grant_id=None,
        credentials_encrypted=encrypt_data(credentials.model_dump_json()),
    )


def install_service(row):
    service = ConnectorService(AsyncMock())
    service.repository = AsyncMock()
    service.repository.get_by_user_and_type.return_value = row
    return service


@pytest.mark.asyncio
async def test_legacy_service_to_email_registry_to_projection_has_no_secrets_or_write():
    credentials = ConnectorCredentials(
        access_token="private-access",
        refresh_token="private-refresh",
        account_binding=str(UUID(int=99)),
    )
    row = connector(credentials)
    row.credentials_encrypted = encrypt_data(
        json.dumps(
            {
                "access_token": "private-access",
                "refresh_token": "private-refresh",
                "account_binding": str(UUID(int=99)),
            }
        )
    )
    service = install_service(row)
    authenticated = await service.get_connector_credentials(USER, ConnectorType.GOOGLE_GMAIL)
    assert authenticated.account_binding != credentials.account_binding
    assert UUID(authenticated.account_binding)
    assert "account_binding" not in authenticated.model_dump_json()
    client = GoogleGmailClient(USER, authenticated, Mock())
    emails = bind_email_card_accounts(
        client, [{"id": "canonical-email", "subject": "Selected email"}]
    )
    registry = GetEmailsTool().build_emails_output(emails).registry_updates
    projection = with_card_actions(
        AIMessage(content="Answer"), registry, run_id="source-run", enabled=True
    ).additional_kwargs["lia_card_actions"]
    assert projection["items"][0]["account_binding"] == authenticated.account_binding
    assert projection["items"][0]["actions"] == ["reply", "forward", "delete_email"]
    serialized = json.dumps(projection)
    assert "private-access" not in serialized and "private-refresh" not in serialized
    assert "legacy_account_generation" not in serialized
    service.repository.update_credentials.assert_not_awaited()
    service.db.commit.assert_not_awaited()


def test_identity_is_scoped_to_owner_connector_provider_and_connection_generation():
    credentials = ConnectorCredentials(access_token="access", refresh_token="refresh-a")
    first = connector(credentials)
    bound = bind_legacy_email_account(first, credentials)
    persisted = ConnectorCredentials.model_validate_json(bound.model_dump_json())
    assert persisted.account_binding is None
    variants = [
        bind_legacy_email_account(connector(credentials, user=UUID(int=3)), persisted),
        bind_legacy_email_account(connector(credentials, identity=UUID(int=4)), persisted),
        bind_legacy_email_account(
            connector(credentials, provider=ConnectorType.MICROSOFT_OUTLOOK), persisted
        ),
        bind_legacy_email_account(
            first, ConnectorCredentials(access_token="another", refresh_token="refresh-b")
        ),
    ]
    assert len({bound.account_binding, *(item.account_binding for item in variants)}) == 5
    assert (
        bind_legacy_email_account(
            first, persisted.model_copy(update={"access_token": "rotated"})
        ).account_binding
        == bound.account_binding
    )
    assert (
        bind_legacy_email_account(
            first, credentials.model_copy(update={"refresh_token": None})
        ).account_binding
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK])
@pytest.mark.parametrize("rotate_refresh", [False, True])
async def test_real_legacy_refresh_preserves_binding_after_database_round_trip(
    monkeypatch, provider, rotate_refresh
):
    current = ConnectorCredentials(
        access_token="old-access",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    row = connector(current, provider=provider)
    service = install_service(row)
    original = await service.get_connector_credentials(USER, provider)
    http = AsyncMock()
    http.__aenter__.return_value = http
    response = {"access_token": "new-access", "expires_in": 3600}
    if rotate_refresh:
        response["refresh_token"] = "legitimately-rotated-refresh"
    http.post.return_value = httpx.Response(200, json=response)
    monkeypatch.setattr("src.domains.connectors.service.httpx.AsyncClient", lambda **kwargs: http)
    monkeypatch.setattr(
        service,
        "_get_oauth_refresh_config",
        lambda _: {
            "client_id": "client",
            "client_secret": "secret",
            "include_scope": False,
            "token_url": "https://oauth.example.test/token",
        },
    )
    monkeypatch.setattr(
        "src.domains.connectors.service.invalidate_oauth_connector_cache", AsyncMock()
    )

    async def update(row, encrypted):
        row.credentials_encrypted = encrypted
        return row

    service.repository.update_credentials.side_effect = update
    refreshed = await service._refresh_oauth_token(row, original)
    assert refreshed.account_binding == original.account_binding
    stored = ConnectorCredentials.model_validate_json(decrypt_data(row.credentials_encrypted))
    assert stored.account_binding is None
    assert stored.legacy_account_generation == original.legacy_account_generation
    reread = await service.get_connector_credentials(USER, provider)
    assert reread.account_binding == original.account_binding
    assert reread.access_token == "new-access"


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK])
@pytest.mark.parametrize("expired", [False, True])
async def test_reconnected_legacy_account_is_refused_before_any_provider_action(provider, expired):
    original_credentials = ConnectorCredentials(
        access_token="old-access", refresh_token="first-account"
    )
    row = connector(original_credentials, provider=provider)
    service = install_service(row)
    original = await service.get_connector_credentials(USER, provider)
    service._refresh_oauth_token = AsyncMock()
    # A fresh OAuth callback supplies no stored generation, even on the same row.
    row.credentials_encrypted = encrypt_data(
        ConnectorCredentials(
            access_token="new-access",
            refresh_token="second-account",
            expires_at=datetime.now(UTC) - timedelta(minutes=1) if expired else None,
        ).model_dump_json()
    )
    token = card_composition_ctx.set(
        CardComposition(
            USER,
            "EMAIL",
            "canonical-email",
            "delete_email",
            provider.value,
            original.account_binding,
        )
    )
    try:
        with pytest.raises(CardCompositionUnavailable):
            await service.get_connector_credentials(USER, provider)
        service.repository.update_credentials.assert_not_awaited()
        service._refresh_oauth_token.assert_not_awaited()
    finally:
        card_composition_ctx.reset(token)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", [ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK])
async def test_actual_callback_restarts_generation_even_when_refresh_token_is_reused(
    monkeypatch, provider
):
    current = ConnectorCredentials(
        access_token="old-access", refresh_token="provider-reused-refresh"
    )
    row = connector(current, provider=provider)
    row.created_at = row.updated_at = datetime.now(UTC)
    service = install_service(row)
    original = await service.get_connector_credentials(USER, provider)
    tokens = SimpleNamespace(
        access_token="new-access",
        refresh_token=current.refresh_token,
        token_type="Bearer",
        expires_in=3600,
        scope="mail",
    )
    monkeypatch.setattr(
        "src.core.oauth.OAuthFlowHandler.handle_callback",
        AsyncMock(return_value=(tokens, {"user_id": str(USER), "connector_type": provider.value})),
    )
    monkeypatch.setattr("src.domains.connectors.service.get_redis_session", AsyncMock())
    monkeypatch.setattr(service, "_invalidate_user_connectors_cache", AsyncMock())

    async def find(user_id, connector_type):
        return row if connector_type == provider else None

    async def update(existing, changes):
        for key, value in changes.items():
            setattr(existing, key, value)
        return existing

    service.repository.get_by_user_and_type.side_effect = find
    service.repository.update.side_effect = update
    await service._handle_oauth_connector_callback(
        USER, "code", "state", provider, lambda settings: Mock()
    )
    fresh = await service.get_connector_credentials(USER, provider)
    assert fresh.refresh_token == original.refresh_token
    assert fresh.legacy_account_generation != original.legacy_account_generation
    assert fresh.account_binding != original.account_binding
