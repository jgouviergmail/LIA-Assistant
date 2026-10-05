"""Personal-credit admission; all network calls run outside database units."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import structlog
from redis.exceptions import RedisError

from src.core.config import settings
from src.core.exceptions import (
    AuthorizationError,
    ExternalServiceError,
    RateLimitError,
    ResourceConflictError,
)
from src.domains.avatars.accounts import AvatarAccount, AvatarAccountStore
from src.domains.avatars.client import SimliClient, SimliError
from src.domains.avatars.control_store import AvatarControlStore
from src.domains.avatars.face_catalogue import merge_faces
from src.domains.avatars.leases import AvatarLease, AvatarLeaseStore, LeasePhase
from src.domains.avatars.schemas import (
    AvatarConfig,
    AvatarFace,
    AvatarHeartbeatRequest,
    AvatarLeaseRequest,
    AvatarSessionRequest,
    AvatarSessionResponse,
    AvatarSessionStatus,
    AvatarSource,
)
from src.domains.connectors.api_key_use import stamp_api_key_use
from src.domains.live.session_store import LiveSessionStore
from src.infrastructure.rate_limiting.redis_limiter import RedisRateLimiter

logger = structlog.get_logger(__name__)


class AvatarService:
    def __init__(
        self,
        accounts: AvatarAccountStore,
        leases: AvatarLeaseStore,
        live: LiveSessionStore,
        limiter: RedisRateLimiter,
        controls: AvatarControlStore,
    ) -> None:
        self.accounts = accounts
        self.leases = leases
        self.live = live
        self.limiter = limiter
        self.controls = controls

    async def start(self, user_id: UUID, payload: AvatarSessionRequest) -> AvatarSessionResponse:
        try:
            return await self._start(user_id, payload)
        except (RedisError, SimliError) as exc:
            code = str(exc) if isinstance(exc, SimliError) else "avatar_admission_unavailable"
            raise ExternalServiceError(
                "simli", detail=code, error_type=type(exc).__name__
            ) from None

    async def _start(self, user_id: UUID, payload: AvatarSessionRequest) -> AvatarSessionResponse:
        account = await self.accounts.read(user_id, credentials=True)
        await self._authorize(account, payload)
        lease = AvatarLease(
            user_id=user_id,
            owner_id=payload.owner_id,
            digest=account.credential_digest,
            credential_version=account.credential_version or "",
            face_id=account.face_id,
            controlled=True,
        )
        ttl = (
            settings.avatar_session_length_seconds
            + int(settings.avatar_connect_timeout_seconds)
            + 60
        )
        if not await self.leases.claim(lease, ttl):
            raise ResourceConflictError("avatar", "avatar_already_active")
        posted = False
        try:
            # Authorization narrowed these optionals. They stay optional in a
            # snapshot because config/disconnection must remain readable.
            if account.api_key is None or account.face_id is None:
                raise AuthorizationError("avatar_connector_unavailable")
            client = SimliClient(account.api_key)
            ice = await client.ice()
            if await client.active_count() != 0:
                raise ResourceConflictError("avatar", "avatar_provider_already_active")
            await self._check_mint_budget(account)
            posted = True
            token = await client.token(account.face_id)
            current = await self.accounts.read(user_id, credentials=True)
            await self._authorize(current, payload)
            if (current.credential_version, current.face_id) != (
                account.credential_version,
                account.face_id,
            ):
                raise AuthorizationError("avatar_configuration_changed")
            if account.connector_id is not None:
                await stamp_api_key_use(account.connector_id)
            ticket = await self.controls.issue(
                lease.model_copy(update={"phase": LeasePhase.READY}), token, account.api_key, ttl
            )
            if await self.leases.mark(lease, LeasePhase.READY) is None:
                await self.controls.stop(lease)
                raise ResourceConflictError("avatar", "avatar_lease_expired")
            return AvatarSessionResponse(
                session_token=ticket,
                lease_id=lease.lease_id,
                ice_servers=ice,
                max_session_seconds=settings.avatar_session_length_seconds,
            )
        except Exception, asyncio.CancelledError:
            # A timeout/cancellation may follow a successful provider POST.
            # Leaving MINTING on a failed Redis write is equally conservative.
            if posted:
                try:
                    await self.leases.mark(lease, LeasePhase.UNKNOWN)
                except RedisError:
                    logger.warning("avatar_quarantine_write_failed")
            raise
        finally:
            if not posted:
                await self.leases.abandon_before_post(lease)

    async def _check_mint_budget(self, account: AvatarAccount) -> None:
        if await self.limiter.acquire(
            key=f"ratelimit:avatar:{account.credential_digest}",
            max_calls=settings.avatar_mints_per_hour,
            window_seconds=3600,
        ):
            return
        raise RateLimitError(
            settings.avatar_mints_per_hour,
            3600,
            3600,
            detail="avatar_start_rate_limited",
            headers={"Retry-After": "3600"},
        )

    async def _authorize(self, account: AvatarAccount, payload: AvatarSessionRequest) -> None:
        self._authorize_account(account)
        live = await self.live.get(account.user_id)
        if payload.source is AvatarSource.COMMENTS:
            # Standby explicitly suppresses comments demand too.
            if not account.voice_enabled or live is not None:
                raise AuthorizationError("avatar_comments_inactive")
            return
        try:
            session_id = UUID(live.session_id) if live is not None else None
        except ValueError:
            raise AuthorizationError("avatar_live_inactive") from None
        if (
            live is None
            or live.user_id != account.user_id
            or live.in_standby
            or live.expires_at <= datetime.now(UTC)
            or session_id != payload.live_session_id
        ):
            raise AuthorizationError("avatar_live_inactive")

    @staticmethod
    def _authorize_account(account: AvatarAccount) -> None:
        if not (
            account.active
            and account.available
            and account.enabled
            and account.connected
            and account.api_key
            and account.face_id
        ):
            raise AuthorizationError("avatar_unavailable")

    async def heartbeat(self, user_id: UUID, payload: AvatarHeartbeatRequest) -> None:
        try:
            account = await self.accounts.read(user_id, credentials=True)
            await self._authorize(account, payload)
            lease = await self.leases.get(user_id, payload.owner_id)
            if (
                lease is None
                or lease.lease_id != payload.lease_id
                or lease.phase is not LeasePhase.READY
                or lease.credential_version != account.credential_version
                or lease.face_id != account.face_id
                or lease.digest != account.credential_digest
            ):
                raise ResourceConflictError("avatar", "avatar_lease_expired")
            if lease.controlled and not await self.controls.touch(lease.lease_id):
                raise ResourceConflictError("avatar", "avatar_lease_expired")
        except RedisError:
            raise ExternalServiceError("simli", "avatar_admission_unavailable") from None

    async def release(self, user_id: UUID, payload: AvatarLeaseRequest) -> bool:
        try:
            lease = await self.leases.get(user_id, payload.owner_id)
            if lease is None:
                completed = (
                    await self.controls.completed(user_id, payload.owner_id, payload.lease_id)
                    if payload.lease_id
                    else None
                )
                return (
                    completed is not None
                    and await SimliClient(completed.api_key).active_count() == 0
                )
            if lease.phase is not LeasePhase.READY or (
                payload.lease_id is not None and lease.lease_id != payload.lease_id
            ):
                return False
            account = await self.accounts.read(user_id, credentials=True)
            if account.api_key is None or account.credential_digest != lease.digest:
                return False
            if not await self._close_controlled(lease):
                return False
            # The ticket is revoked and the server's socket has closed; verify provider inactivity too.
            if await SimliClient(account.api_key).active_count() != 0:
                return False
            return await self.leases.release(lease)
        except RedisError, SimliError, AuthorizationError, ValueError:
            return False

    async def _close_controlled(self, lease: AvatarLease) -> bool:
        if not lease.controlled:
            return True
        for _ in range(40):
            if await self.controls.stop(lease):
                return True
            await asyncio.sleep(0.1)
        return await self.controls.stop(lease)

    async def status(self, user_id: UUID) -> AvatarSessionStatus | None:
        account = await self.accounts.read(user_id, credentials=True)
        if not account.api_key:
            return None
        lease = await self.leases.current(user_id, account.credential_digest)
        if lease is None:
            return None
        return AvatarSessionStatus(
            owner_id=lease.owner_id,
            lease_id=lease.lease_id,
            phase=lease.phase.value,
            controlled=lease.controlled,
            control_phase=await self.controls.phase(lease.lease_id) if lease.controlled else None,
        )

    async def config(self, user_id: UUID) -> AvatarConfig:
        account = await self.accounts.read(user_id)
        return AvatarConfig(
            available=account.available,
            enabled=account.enabled,
            connected=account.connected,
            face_id=account.face_id,
            connector_version=account.credential_version,
            session_length_seconds=settings.avatar_session_length_seconds,
            connect_timeout_seconds=settings.avatar_connect_timeout_seconds,
        )

    async def faces(self, user_id: UUID) -> list[AvatarFace]:
        try:
            account = await self.accounts.read(user_id, credentials=True)
            if account.available and account.connected and account.api_key:
                return merge_faces(await SimliClient(account.api_key).faces())
        except (SimliError, AuthorizationError) as exc:
            logger.warning("avatar_private_faces_unavailable", error_type=type(exc).__name__)
        return merge_faces([])
