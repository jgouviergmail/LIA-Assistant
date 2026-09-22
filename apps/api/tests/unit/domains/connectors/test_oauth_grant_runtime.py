"""A concurrent rotation supersedes an explicit refresh waiting for its lock."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from src.core.security import encrypt_data
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType, OAuthGrant
from src.domains.connectors.oauth_grant_runtime import OAuthGrantRuntime
from src.domains.connectors.schemas import ConnectorCredentials


async def test_force_refresh_uses_newly_rotated_grant_after_lock_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid4()
    old = ConnectorCredentials(
        access_token="old",
        refresh_token="old-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    fresh = ConnectorCredentials(
        access_token="fresh",
        refresh_token="fresh-refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    grant_id = uuid4()
    old_grant = OAuthGrant(
        id=grant_id,
        user_id=user_id,
        provider="google",
        client_id="client",
        subject="subject",
        scopes=[],
        credentials_encrypted=encrypt_data(old.model_dump_json()),
    )
    fresh_grant = OAuthGrant(
        id=grant_id,
        user_id=user_id,
        provider="google",
        client_id="client",
        subject="subject",
        scopes=[],
        credentials_encrypted=encrypt_data(fresh.model_dump_json()),
    )
    connector = Connector(
        user_id=user_id,
        connector_type=ConnectorType.GOOGLE_CALENDAR,
        status=ConnectorStatus.ACTIVE,
        scopes=[],
        credentials_encrypted="legacy",
        oauth_grant_id=grant_id,
    )

    class Session:
        calls = 0

        async def scalar(self, query: object) -> OAuthGrant:
            self.calls += 1
            return old_grant if self.calls == 1 else fresh_grant

    async def unexpected_refresh(*args: object) -> ConnectorCredentials:
        raise AssertionError("A concurrent rotation already refreshed the grant")

    session = Session()
    runtime = OAuthGrantRuntime(session)
    monkeypatch.setattr(runtime, "_refresh", unexpected_refresh)
    actual = await runtime.credentials_for(connector, force=True)

    assert session.calls == 2
    assert actual.access_token == "fresh"
