"""Encrypted command/transport identity never stores an authentication permission."""

import hmac
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from src.core.application_origin import ApplicationOrigin, ApplicationSessionFacts
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.command_models import ApplicationCommand
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.digest import draft_digest
from src.infrastructure.application_sessions import require_live_application_binding


class CommandOriginBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    schema_version: Literal[1] = 1
    actor_id: UUID
    command_id: UUID
    operation_id: str = Field(min_length=1, max_length=100)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    session_binding: str = Field(pattern=r"^[0-9a-f]{64}$", repr=False)
    approved_until: AwareDatetime
    device_id: UUID | None = None


async def capture_command_origin(
    content: ApplicationActionDraftContent,
    origin: ApplicationOrigin | None,
    *,
    bind_device: bool = False,
) -> str | None:
    if origin is None:
        if bind_device:
            raise AuthorizationError(detail={"error_code": "DEVICE_UNAVAILABLE"})
        return None
    if bind_device and origin.device_id is None:
        raise AuthorizationError(detail={"error_code": "DEVICE_UNAVAILABLE"})
    await origin.require_session(content.actor_id, expected_binding=origin.binding_id)
    binding = CommandOriginBinding(
        actor_id=content.actor_id,
        command_id=content.command_id,
        operation_id=content.operation_id,
        content_digest=draft_digest(content.model_dump(mode="json")),
        session_binding=origin.binding_id,
        approved_until=content.expires_at,
        device_id=origin.device_id if bind_device else None,
    )
    return encrypt_data(binding.model_dump_json())


def _stored_binding(command: ApplicationCommand) -> CommandOriginBinding:
    encrypted = command.origin_binding_encrypted
    if encrypted is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    try:
        binding = CommandOriginBinding.model_validate_json(decrypt_data(encrypted))
    except ValueError:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"}) from None
    if (
        (binding.actor_id, binding.command_id, binding.operation_id)
        != (command.actor_id, command.id, command.operation_id)
        or not hmac.compare_digest(binding.content_digest, command.content_digest)
        or command.expires_at.tzinfo is None
        or command.expires_at > binding.approved_until
    ):
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"})
    return binding


def command_has_device_binding(command: ApplicationCommand) -> bool:
    return _stored_binding(command).device_id is not None


async def require_command_origin_alive(command: ApplicationCommand) -> None:
    """Callback guard reads real sessions; it grants no originating-browser write proof."""
    binding = _stored_binding(command)
    if command.expires_at <= datetime.now(UTC):
        raise AuthorizationError(detail={"error_code": "INTERACTION_EXPIRED"})
    await require_live_application_binding(command.actor_id, binding.session_binding)


async def require_command_origin(
    command: ApplicationCommand,
    origin: ApplicationOrigin | None,
    *,
    allow_expired: bool = False,
    recent_step_up: bool = False,
    require_device: bool = False,
) -> ApplicationSessionFacts:
    binding = _stored_binding(command)
    if require_device and binding.device_id is None:
        raise AuthorizationError(detail={"error_code": "DEVICE_UNAVAILABLE"})
    if origin is None:
        raise AuthorizationError(detail={"error_code": "SESSION_UNAVAILABLE"})
    if binding.device_id is not None and binding.device_id != origin.device_id:
        raise AuthorizationError(detail={"error_code": "DEVICE_MISMATCH"})
    if not allow_expired and command.expires_at <= datetime.now(UTC):
        raise AuthorizationError(detail={"error_code": "INTERACTION_EXPIRED"})
    return await origin.require_session(
        command.actor_id,
        expected_binding=binding.session_binding,
        recent_step_up=recent_step_up,
    )
