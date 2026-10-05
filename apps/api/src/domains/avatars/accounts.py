"""Short, owned database units. No ORM object crosses a provider wait."""

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import ValidationError as PayloadError
from sqlalchemy import select

from src.core.exceptions import AuthorizationError, ValidationError
from src.core.security import decrypt_data
from src.domains.avatars.preferences import read_face_id, with_face_id
from src.domains.avatars.schemas import AvatarSettingsRequest
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.schemas import APIKeyCredentials
from src.domains.feature_switches.registry import PlatformCapability, is_capability_enabled
from src.domains.users.models import User
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True, slots=True)
class AvatarAccount:
    user_id: UUID
    active: bool
    available: bool
    enabled: bool
    voice_enabled: bool
    connected: bool
    face_id: UUID | None
    credential_version: str | None
    api_key: str | None = field(default=None, repr=False)
    connector_id: UUID | None = None

    @property
    def credential_digest(self) -> str:
        if self.api_key is None:
            raise AuthorizationError("avatar_connector_unavailable")
        return sha256(self.api_key.encode()).hexdigest()


class AvatarAccountStore:
    async def read(self, user_id: UUID, *, credentials: bool = False) -> AvatarAccount:
        available = await is_capability_enabled(PlatformCapability.AVATAR)
        async with get_db_context() as db:
            user = await db.get(User, user_id)
            repository = ConnectorRepository(db)
            connector = await repository.get_by_user_and_type(user_id, ConnectorType.SIMLI)
            global_config = await repository.get_global_config_by_type(ConnectorType.SIMLI)
            return self._snapshot(
                user_id,
                user,
                connector,
                available and (global_config is None or global_config.is_enabled),
                credentials,
            )

    async def save(self, user_id: UUID, payload: AvatarSettingsRequest) -> None:
        available = await is_capability_enabled(PlatformCapability.AVATAR)
        async with get_db_context() as db:
            user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None or not user.is_active:
                raise AuthorizationError("avatar_account_unavailable")
            connector = await db.scalar(
                select(Connector)
                .where(
                    Connector.user_id == user_id,
                    Connector.connector_type == ConnectorType.SIMLI,
                )
                .with_for_update()
            )
            global_config = await ConnectorRepository(db).get_global_config_by_type(
                ConnectorType.SIMLI
            )
            self._validate_settings(
                payload,
                connector,
                available and (global_config is None or global_config.is_enabled),
            )
            user.speaking_avatar_enabled = payload.enabled
            if connector is not None:
                connector.connector_metadata = self._face_metadata(
                    connector.connector_metadata, payload.face_id
                )

    @staticmethod
    def _validate_settings(
        payload: AvatarSettingsRequest, connector: Connector | None, available: bool
    ) -> None:
        if not payload.enabled:
            return
        if not available:
            raise AuthorizationError("avatar_disabled")
        if connector is None or connector.status is not ConnectorStatus.ACTIVE:
            raise AuthorizationError("avatar_connector_unavailable")
        if payload.face_id is None:
            raise ValidationError("avatar_face_required")

    @staticmethod
    def _face_metadata(metadata: dict[str, Any] | None, face_id: UUID | None) -> dict[str, Any]:
        if face_id is not None:
            return with_face_id(metadata, face_id)
        return {k: v for k, v in (metadata or {}).items() if k != "avatar_face_id"}

    @staticmethod
    def _snapshot(
        user_id: UUID,
        user: User | None,
        connector: Connector | None,
        available: bool,
        credentials: bool,
    ) -> AvatarAccount:
        connected = connector is not None and connector.status is ConnectorStatus.ACTIVE
        api_key = None
        if connected and credentials and connector is not None:
            try:
                api_key = APIKeyCredentials.model_validate_json(
                    decrypt_data(connector.credentials_encrypted)
                ).api_key
            except PayloadError, ValueError:
                raise AuthorizationError("avatar_connector_unavailable") from None
        return AvatarAccount(
            user_id=user_id,
            active=user is not None and user.is_active,
            available=available,
            enabled=user is not None and user.speaking_avatar_enabled,
            voice_enabled=user is not None and user.voice_enabled,
            connected=connected,
            face_id=read_face_id(connector.connector_metadata) if connector is not None else None,
            credential_version=(
                sha256(connector.credentials_encrypted.encode()).hexdigest()
                if connected and connector is not None
                else None
            ),
            api_key=api_key,
            connector_id=connector.id if connected and connector is not None else None,
        )
