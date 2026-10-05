"""Actual HTTP schemas, ownership and cache headers at the avatar door."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.avatars.router import avatar_service, router
from src.domains.avatars.schemas import AvatarConfig, AvatarSessionResponse, IceServer
from src.domains.avatars.service import AvatarService

pytestmark = pytest.mark.unit


@pytest.fixture
async def endpoint(monkeypatch):
    monkeypatch.setattr(
        "src.domains.feature_switches.guard.is_capability_enabled", AsyncMock(return_value=True)
    )
    app = FastAPI()
    app.include_router(router)
    uid = uuid4()
    service = AsyncMock(spec=AvatarService)
    service.accounts = SimpleNamespace(save=AsyncMock())
    service.config.return_value = AvatarConfig(
        available=True,
        enabled=False,
        connected=True,
        face_id=None,
        connector_version="v1",
        session_length_seconds=3600,
        connect_timeout_seconds=15,
    )
    service.start.return_value = AvatarSessionResponse(
        session_token="test-token",
        lease_id=uuid4(),
        ice_servers=[IceServer(urls="stun:fixture.invalid")],
        max_session_seconds=3600,
    )
    app.dependency_overrides[get_current_active_session_for_stream] = lambda: SimpleNamespace(
        id=uid
    )
    app.dependency_overrides[avatar_service] = lambda: service
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        yield client, service, uid


async def test_token_has_no_store_and_only_the_authenticated_owner(endpoint):
    client, service, uid = endpoint
    owner = uuid4()
    response = await client.post(
        "/avatars/sessions", json={"owner_id": str(owner), "source": "comments"}
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["session_token"] == "test-token"
    assert service.start.call_args.args[0] == uid
    assert service.start.call_args.args[1].owner_id == owner


@pytest.mark.parametrize(
    "extra", [{"user_id": str(uuid4())}, {"api_key": "test-only"}, {"emotion": "happy"}]
)
async def test_browser_cannot_override_owner_credentials_or_provider_parameters(endpoint, extra):
    client, service, _ = endpoint
    response = await client.post(
        "/avatars/sessions", json={"owner_id": str(uuid4()), "source": "comments", **extra}
    )
    assert response.status_code == 422
    service.start.assert_not_awaited()


async def test_off_preference_remains_writable_without_touching_voice_mode(endpoint):
    client, service, uid = endpoint
    response = await client.put("/avatars/settings", json={"enabled": False, "face_id": None})
    assert response.status_code == 200
    service.accounts.save.assert_awaited_once()
    assert service.accounts.save.call_args.args[0] == uid
    assert response.json()["enabled"] is False


async def test_live_admission_and_lease_calls_accept_the_browser_contract(endpoint):
    client, service, uid = endpoint
    identity = {"owner_id": str(uuid4()), "lease_id": str(uuid4())}
    demand = {"owner_id": identity["owner_id"], "source": "live", "live_session_id": str(uuid4())}
    assert (await client.post("/avatars/sessions", json=demand)).status_code == 200
    assert str(service.start.call_args.args[1].live_session_id) == demand["live_session_id"]
    assert (
        await client.post("/avatars/sessions/heartbeat", json={**demand, **identity})
    ).status_code == 204
    assert service.heartbeat.call_args.args[0] == uid
    service.release.return_value = True
    released = await client.post("/avatars/sessions/release", json=identity)
    assert released.status_code == 200
    assert released.json() == {"released": True}
    assert released.headers["cache-control"] == "no-store"


async def test_instance_switch_refuses_admission_but_preserves_cleanup_and_opt_out(
    endpoint, monkeypatch
):
    client, service, _ = endpoint
    monkeypatch.setattr(
        "src.domains.feature_switches.guard.is_capability_enabled", AsyncMock(return_value=False)
    )
    refused = await client.post(
        "/avatars/sessions", json={"owner_id": str(uuid4()), "source": "comments"}
    )
    assert refused.status_code == 403
    assert refused.json()["detail"]["capability"] == "avatar"
    service.start.assert_not_awaited()
    assert (await client.get("/avatars/config")).status_code == 200
    assert (await client.put("/avatars/settings", json={"enabled": False})).status_code == 200
    service.release.return_value = True
    assert (
        await client.post("/avatars/sessions/release", json={"owner_id": str(uuid4())})
    ).status_code == 200
