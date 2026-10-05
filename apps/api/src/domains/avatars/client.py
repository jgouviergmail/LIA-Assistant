"""Fixed-origin, bounded Simli reads. Provider exceptions never expose credentials."""

from uuid import UUID

import structlog
from pydantic import BaseModel, Field, StrictInt, TypeAdapter, ValidationError

from src.core.config import settings
from src.domains.avatars.schemas import AvatarFace, IceServer
from src.infrastructure.simli import SimliError, SimliHttpClient


class SimliToken(BaseModel):
    session_token: str = Field(min_length=1, max_length=8192, repr=False)


class SimliFace(BaseModel):
    id: UUID
    name: str | None = Field(default=None, max_length=128)


class SimliAccountAvatar(BaseModel):
    # Account avatars can reference public faces absent from /faces. Discard
    # prompts, voice configuration and every other agent field at this boundary.
    face_id: UUID
    name: str = Field(min_length=1, max_length=128)


class ActiveSessions(BaseModel):
    currentUsage: StrictInt = Field(ge=0)


class SimliClient:
    """One short-lived HTTP client; no retries and no caller-controlled origin."""

    def __init__(self, api_key: str) -> None:
        self._http = SimliHttpClient(api_key)

    async def token(self, face_id: UUID) -> str:
        payload: dict[str, object] = {
            "faceId": str(face_id),
            "apiVersion": "v2",
            "handleSilence": True,
            "maxSessionLength": settings.avatar_session_length_seconds,
            "maxIdleTime": settings.avatar_idle_seconds,
            "audioInputFormat": "pcm16",
            "startFrame": 0,
        }
        try:
            return SimliToken.model_validate(
                await self._http.request("POST", "/compose/token", payload)
            ).session_token
        except ValidationError:
            raise SimliError("provider_bad_token") from None

    async def faces(self) -> list[AvatarFace]:
        private = []
        try:
            faces = TypeAdapter(list[SimliFace]).validate_python(await self._read("/faces"))
            if len(faces) > 256:
                raise SimliError("provider_bad_faces")
            private = [
                AvatarFace(id=face.id, name=face.name or str(face.id), source="private")
                for face in faces
            ]
        except SimliError, ValidationError:
            structlog.get_logger(__name__).warning("avatar_private_catalogue_unavailable")
        try:
            avatars = TypeAdapter(list[SimliAccountAvatar]).validate_python(
                await self._read("/auto/agents")
            )
            if len(avatars) > 256:
                raise SimliError("provider_bad_faces")
            private.extend(
                AvatarFace(id=avatar.face_id, name=avatar.name, source="private")
                for avatar in avatars
            )
        except SimliError, ValidationError:
            # A retired/temporarily unavailable agent catalogue must not hide
            # private faces that were successfully read or the public presets.
            structlog.get_logger(__name__).warning("avatar_account_catalogue_unavailable")
        return private

    async def active_count(self) -> int:
        try:
            return ActiveSessions.model_validate(
                await self._read("/ratelimiter/sessions")
            ).currentUsage
        except ValidationError:
            raise SimliError("provider_bad_sessions") from None

    async def _read(self, path: str) -> object:
        return await self._http.request("GET", path)

    async def ice(self) -> list[IceServer]:
        return await self._http.ice()
