"""Admission is tested at DB/Redis/provider boundaries, not internal helpers."""

import asyncio
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.exceptions import AuthorizationError, ExternalServiceError, ResourceConflictError
from src.domains.avatars.accounts import AvatarAccount, AvatarAccountStore
from src.domains.avatars.client import SimliClient, SimliError
from src.domains.avatars.leases import AvatarLease, AvatarLeaseStore, LeasePhase
from src.domains.avatars.schemas import (
    AvatarHeartbeatRequest,
    AvatarLeaseRequest,
    AvatarSessionRequest,
    IceServer,
)
from src.domains.avatars.service import AvatarService
from src.domains.live.session_store import LiveSessionRecord, LiveSessionStore
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

pytestmark = pytest.mark.unit


@pytest.fixture
def setup():
    uid = uuid4()
    snapshot = AvatarAccount(uid, True, True, True, True, True, uuid4(), "epoch", "test-only-key")
    accounts = AsyncMock(spec=AvatarAccountStore)
    accounts.read.return_value = snapshot
    leases = AsyncMock(spec=AvatarLeaseStore)
    leases.claim.return_value = True
    leases.mark.side_effect = lambda lease, phase: lease.model_copy(update={"phase": phase})
    live = AsyncMock(spec=LiveSessionStore)
    live.get.return_value = None
    limiter = AsyncMock(spec=RedisRateLimiter)
    limiter.acquire.return_value = True
    client = AsyncMock(spec=SimliClient)
    client.ice.return_value = [IceServer(urls="stun:fixture.invalid")]
    client.active_count.return_value = 0
    client.token.return_value = "test-token"
    request = AvatarSessionRequest(owner_id=uuid4(), source="comments")
    with patch("src.domains.avatars.service.SimliClient", return_value=client):
        yield AvatarService(accounts, leases, live, limiter), snapshot, request, client


async def test_valid_mode_mints_once_and_rechecks_credentials_before_publish(setup):
    service, account, request, client = setup
    response = await service.start(account.user_id, request)
    assert response.session_token == "test-token"
    client.token.assert_awaited_once_with(account.face_id)
    assert service.accounts.read.await_count == 2
    assert service.leases.claim.await_count == 1
    assert service.leases.mark.call_args.args[1] is LeasePhase.READY


@pytest.mark.parametrize("field", ["active", "available", "enabled", "connected", "voice_enabled"])
async def test_disabled_account_mode_or_connector_never_reaches_provider(setup, field):
    service, account, request, client = setup
    service.accounts.read.return_value = replace(account, **{field: False})
    with pytest.raises(AuthorizationError):
        await service.start(account.user_id, request)
    client.token.assert_not_awaited()
    service.leases.claim.assert_not_awaited()


async def test_second_owner_refused_before_any_provider_operation(setup):
    service, account, request, client = setup
    service.leases.claim.return_value = False
    with pytest.raises(ResourceConflictError):
        await service.start(account.user_id, request)
    client.ice.assert_not_awaited()
    client.token.assert_not_awaited()


async def test_unknown_mint_is_not_retried_or_released(setup):
    service, account, request, client = setup
    client.token.side_effect = SimliError("provider_unavailable")
    with pytest.raises(ExternalServiceError):
        await service.start(account.user_id, request)
    client.token.assert_awaited_once()
    service.leases.abandon_before_post.assert_not_awaited()
    service.leases.release.assert_not_awaited()
    assert service.leases.mark.call_args.args[1] is LeasePhase.UNKNOWN


async def test_unpaid_admission_conflict_does_not_consume_the_mint_allowance(setup):
    service, account, request, client = setup
    service.leases.claim.return_value = False
    with pytest.raises(ResourceConflictError):
        await service.start(account.user_id, request)
    service.limiter.acquire.assert_not_awaited()
    client.token.assert_not_awaited()


async def test_key_rotation_during_mint_discards_token_and_keeps_quarantine(setup):
    service, account, request, client = setup
    service.accounts.read.side_effect = [account, replace(account, credential_version="new-key")]
    with pytest.raises(AuthorizationError):
        await service.start(account.user_id, request)
    client.token.assert_awaited_once()
    service.leases.release.assert_not_awaited()


async def test_failed_read_before_post_releases_only_its_own_claim(setup):
    service, account, request, client = setup
    client.ice.side_effect = SimliError("provider_unavailable")
    with pytest.raises(ExternalServiceError):
        await service.start(account.user_id, request)
    client.token.assert_not_awaited()
    service.leases.abandon_before_post.assert_awaited_once()


@pytest.mark.parametrize("standby", [True, False])
async def test_comments_demand_is_suppressed_by_live_including_standby(setup, standby):
    service, account, request, client = setup
    now = datetime.now(UTC)
    service.live.get.return_value = LiveSessionRecord(
        session_id=uuid4().hex,
        user_id=account.user_id,
        provider="gemini",
        model="fixture",
        run_id="fixture",
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token="fixture",
        standby_since=now if standby else None,
    )
    with pytest.raises(AuthorizationError):
        await service.start(account.user_id, request)
    client.token.assert_not_awaited()


async def test_live_uses_its_authenticated_record_and_does_not_require_comments_enabled(setup):
    service, account, request, client = setup
    now = datetime.now(UTC)
    session_id = uuid4()
    service.live.get.return_value = LiveSessionRecord(
        session_id=session_id.hex,
        user_id=account.user_id,
        provider="gemini",
        model="fixture",
        run_id="fixture",
        started_at=now,
        expires_at=now + timedelta(minutes=10),
        token="fixture",
    )
    service.accounts.read.return_value = replace(account, voice_enabled=False)
    request = AvatarSessionRequest(
        owner_id=request.owner_id, source="live", live_session_id=session_id
    )
    assert (await service.start(account.user_id, request)).session_token == "test-token"
    client.token.assert_awaited_once()


async def test_cancellation_after_post_keeps_the_credential_quarantined(setup):
    service, account, request, client = setup
    client.token.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError):
        await service.start(account.user_id, request)
    service.leases.abandon_before_post.assert_not_awaited()
    assert service.leases.mark.call_args.args[1] is LeasePhase.UNKNOWN


@pytest.mark.parametrize("count,released", [(1, False), (0, True)])
async def test_release_requires_actual_remote_closure(setup, count, released):
    service, account, request, client = setup
    record = AvatarLease(
        user_id=account.user_id,
        owner_id=request.owner_id,
        digest=account.credential_digest,
        credential_version="epoch",
        phase=LeasePhase.READY,
    )
    service.leases.get.return_value = record
    service.leases.release.return_value = True
    client.active_count.return_value = count
    assert (
        await service.release(
            account.user_id, AvatarLeaseRequest(owner_id=request.owner_id, lease_id=record.lease_id)
        )
        is released
    )
    assert service.leases.release.await_count == int(released)


async def test_old_release_never_releases_a_successors_lease(setup):
    service, account, request, client = setup
    service.leases.get.return_value = AvatarLease(
        user_id=account.user_id,
        owner_id=request.owner_id,
        digest=account.credential_digest,
        credential_version="epoch",
        phase=LeasePhase.READY,
    )
    assert not await service.release(
        account.user_id, AvatarLeaseRequest(owner_id=request.owner_id, lease_id=uuid4())
    )
    client.active_count.assert_not_awaited()
    service.leases.release.assert_not_awaited()


async def test_empty_or_failed_private_gallery_keeps_public_presets_without_mint(setup):
    service, account, _, client = setup
    client.faces.side_effect = SimliError("provider_unavailable")
    faces = await service.faces(account.user_id)
    assert any(face.source == "preset" for face in faces)
    client.token.assert_not_awaited()


@pytest.mark.parametrize("change", [None, "face", "credential"])
async def test_heartbeat_checks_current_face_and_credential_without_provider_calls(setup, change):
    service, account, request, client = setup
    lease = AvatarLease(
        user_id=account.user_id,
        owner_id=request.owner_id,
        digest=account.credential_digest,
        credential_version="epoch",
        face_id=account.face_id,
        phase=LeasePhase.READY,
    )
    service.leases.get.return_value = lease
    if change == "face":
        service.accounts.read.return_value = replace(account, face_id=uuid4())
    elif change == "credential":
        service.accounts.read.return_value = replace(account, credential_version="new")
    payload = AvatarHeartbeatRequest(
        owner_id=request.owner_id, source="comments", lease_id=lease.lease_id
    )
    if change is None:
        await service.heartbeat(account.user_id, payload)
    else:
        with pytest.raises(ResourceConflictError):
            await service.heartbeat(account.user_id, payload)
    client.active_count.assert_not_awaited()
    client.token.assert_not_awaited()


async def test_redis_unavailable_fails_closed_before_mint(setup):
    service, account, request, client = setup
    service.leases.claim.side_effect = RedisConnectionError("cache refused")
    with pytest.raises(ExternalServiceError):
        await service.start(account.user_id, request)
    client.token.assert_not_awaited()


async def test_unknown_mint_cannot_be_released_by_a_browser_close_claim(setup):
    service, account, request, client = setup
    service.leases.get.return_value = AvatarLease(
        user_id=account.user_id,
        owner_id=request.owner_id,
        digest=account.credential_digest,
        credential_version="epoch",
        phase=LeasePhase.UNKNOWN,
    )
    assert not await service.release(account.user_id, AvatarLeaseRequest(owner_id=request.owner_id))
    client.active_count.assert_not_awaited()
    service.leases.release.assert_not_awaited()
