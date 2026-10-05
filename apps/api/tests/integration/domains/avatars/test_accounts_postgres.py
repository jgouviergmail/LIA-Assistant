"""Real encrypted credentials/JSONB and detached transaction lifetimes."""

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, inspect
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.exceptions import ValidationError
from src.domains.avatars.accounts import AvatarAccountStore
from src.domains.avatars.leases import AvatarLeaseStore
from src.domains.avatars.schemas import AvatarSessionRequest, AvatarSettingsRequest
from src.domains.avatars.service import AvatarService
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.router import activate_api_key_connector
from src.domains.connectors.schemas import APIKeyActivationRequest
from src.domains.live.session_store import LiveSessionStore
from src.domains.users.models import User
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

pytestmark = pytest.mark.integration


@pytest.fixture
async def account(async_engine, monkeypatch):
    factory = async_sessionmaker(async_engine, expire_on_commit=False)
    units: list[AsyncSession] = []
    uid = uuid4()
    async with factory() as db:
        db.add(
            User(
                id=uid,
                email=f"simli-{uid}@example.invalid",
                full_name="Avatar test",
                is_active=True,
                is_verified=True,
                voice_enabled=True,
            )
        )
        await db.commit()

    @asynccontextmanager
    async def own_unit():
        async with factory() as db:
            units.append(db)
            yield db
            await db.commit()

    monkeypatch.setattr("src.domains.avatars.accounts.get_db_context", own_unit)
    monkeypatch.setattr(
        "src.domains.avatars.accounts.is_capability_enabled", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("src.domains.avatars.service.stamp_api_key_use", AsyncMock())
    try:
        yield uid, factory, units
    finally:
        async with factory() as db:
            await db.execute(delete(User).where(User.id == uid))
            await db.commit()


async def test_actual_activation_rejects_invalid_key_and_keeps_no_transaction_during_ice(
    account, monkeypatch
):
    uid, factory, _ = account
    original = httpx.AsyncClient
    requests = []
    async with factory() as db:
        user = await db.get(User, uid)

        def refuse(request):
            assert not db.in_transaction()
            requests.append(request)
            return httpx.Response(401, json={})

        monkeypatch.setattr(
            httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(refuse), **kw)
        )
        with pytest.raises(ValidationError):
            await activate_api_key_connector(
                APIKeyActivationRequest(
                    connector_type=ConnectorType.SIMLI, api_key="test-only-key"
                ),
                user,
                db,
            )
        assert await ConnectorRepository(db).get_by_user_and_type(uid, ConnectorType.SIMLI) is None
    assert [(r.method, r.url.path) for r in requests] == [("GET", "/compose/ice")]


async def test_preferences_round_trip_and_http_waits_release_owned_units_without_committing_caller(
    account, monkeypatch
):
    uid, factory, units = account
    requests = []
    original = httpx.AsyncClient

    def provider(request):
        requests.append(request)
        assert all(not db.in_transaction() for db in units)
        if request.url.path == "/compose/ice":
            return httpx.Response(200, json=[{"urls": "stun:fixture.invalid"}])
        if request.url.path == "/ratelimiter/sessions":
            return httpx.Response(200, json={"currentUsage": 0})
        assert request.url.path == "/compose/token"
        return httpx.Response(200, json={"session_token": "test-token"})

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kw: original(transport=httpx.MockTransport(provider), **kw)
    )
    async with factory() as db:
        user = await db.get(User, uid)
        assert user.speaking_avatar_enabled is False
        response = await activate_api_key_connector(
            APIKeyActivationRequest(connector_type=ConnectorType.SIMLI, api_key="test-only-key"),
            user,
            db,
        )
        assert "test-only-key" not in response.model_dump_json()
        connector = await ConnectorRepository(db).get_by_user_and_type(uid, ConnectorType.SIMLI)
        assert connector.credentials_encrypted != "test-only-key"
        assert connector.connector_metadata["functionally_verified"] is True
        await db.commit()
    face = uuid4()
    accounts = AvatarAccountStore()
    await accounts.save(uid, AvatarSettingsRequest(enabled=True, face_id=face))
    snapshot = await accounts.read(uid, credentials=True)
    assert snapshot.enabled and snapshot.voice_enabled and snapshot.face_id == face
    assert snapshot.api_key == "test-only-key" and "test-only-key" not in repr(snapshot)
    async with factory() as caller:
        user = await caller.get(User, uid)
        user.full_name = "Pending caller write"
        leases = AsyncMock(spec=AvatarLeaseStore)
        leases.claim.return_value = True
        leases.mark.side_effect = lambda lease, phase: lease.model_copy(update={"phase": phase})
        live = AsyncMock(spec=LiveSessionStore)
        live.get.return_value = None
        limiter = AsyncMock(spec=RedisRateLimiter)
        limiter.acquire.return_value = True
        token = await AvatarService(accounts, leases, live, limiter).start(
            uid, AvatarSessionRequest(owner_id=uuid4(), source="comments")
        )
        assert token.session_token == "test-token"
        assert inspect(user).session is caller.sync_session
        await caller.rollback()
        await caller.refresh(user)
        assert user.full_name == "Avatar test"
    async with factory() as db:
        connector = await ConnectorRepository(db).get_by_user_and_type(uid, ConnectorType.SIMLI)
        assert connector.connector_metadata["avatar_face_id"] == str(face)
        assert connector.connector_metadata["functionally_verified"] is True
    await accounts.save(uid, AvatarSettingsRequest(enabled=False, face_id=face))
    assert (await accounts.read(uid)).enabled is False
    assert sum(r.url.path == "/compose/token" for r in requests) == 1
