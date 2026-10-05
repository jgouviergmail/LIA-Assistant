"""Cookie-authenticated personal avatar control. Every response is non-cacheable."""

import structlog
from fastapi import APIRouter, Depends, Response

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.avatars.accounts import AvatarAccountStore
from src.domains.avatars.control_store import AvatarControlStore
from src.domains.avatars.leases import AvatarLeaseStore
from src.domains.avatars.schemas import (
    AvatarConfig,
    AvatarFace,
    AvatarFailureReport,
    AvatarHeartbeatRequest,
    AvatarLeaseRequest,
    AvatarLeaseResponse,
    AvatarSessionRequest,
    AvatarSessionResponse,
    AvatarSessionStatus,
    AvatarSettingsRequest,
)
from src.domains.avatars.service import AvatarService
from src.domains.feature_switches.guard import require_capability
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.live.session_store import LiveSessionStore
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.rate_limiting.redis_limiter import get_rate_limiter


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/avatars", tags=["Avatars"], dependencies=[Depends(no_store)])


async def avatar_service() -> AvatarService:
    redis = await get_redis_cache()
    return AvatarService(
        AvatarAccountStore(),
        AvatarLeaseStore(redis),
        LiveSessionStore(redis),
        await get_rate_limiter(),
        AvatarControlStore(redis),
    )


@router.get("/config", response_model=AvatarConfig)
async def config(
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> AvatarConfig:
    return await service.config(user.id)


@router.put("/settings", response_model=AvatarConfig)
async def save_settings(
    payload: AvatarSettingsRequest,
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> AvatarConfig:
    await service.accounts.save(user.id, payload)
    return await service.config(user.id)


@router.get("/faces", response_model=list[AvatarFace])
async def faces(
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> list[AvatarFace]:
    return await service.faces(user.id)


@router.post(
    "/sessions",
    response_model=AvatarSessionResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(require_capability(PlatformCapability.AVATAR))],
)
async def start(
    payload: AvatarSessionRequest,
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> AvatarSessionResponse:
    return await service.start(user.id, payload)


@router.post("/sessions/heartbeat", status_code=204)
async def heartbeat(
    payload: AvatarHeartbeatRequest,
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> None:
    await service.heartbeat(user.id, payload)


@router.post("/sessions/release", response_model=AvatarLeaseResponse)
async def release(
    payload: AvatarLeaseRequest,
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> AvatarLeaseResponse:
    return AvatarLeaseResponse(released=await service.release(user.id, payload))


@router.get("/sessions/current", response_model=AvatarSessionStatus | None)
async def current_session(
    user: User = Depends(get_current_active_session_for_stream),
    service: AvatarService = Depends(avatar_service),
) -> AvatarSessionStatus | None:
    return await service.status(user.id)


@router.post("/sessions/failure", status_code=204)
async def failure_report(
    payload: AvatarFailureReport,
    user: User = Depends(get_current_active_session_for_stream),
) -> None:
    structlog.get_logger(__name__).warning(
        "avatar_client_failure",
        user_id=str(user.id),
        owner_id=str(payload.owner_id),
        lease_id=str(payload.lease_id),
        code=payload.code,
    )
