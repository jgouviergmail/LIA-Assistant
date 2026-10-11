"""Short-lived encrypted private continuations; credentials are consumed once."""

import math
from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter

from src.core.constants import MCP_USER_OAUTH_STATE_TTL_SECONDS
from src.core.exceptions import AuthorizationError
from src.core.security.utils import decrypt_data, encrypt_data
from src.domains.agents.application.continuation_approval import ApprovedInteractionClaim
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.interaction_claim import WaitingInteractionClaim
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.infrastructure.cache.redis import get_redis_session

_PREFIX = "application:mcp-oauth:"


class StoredOAuthClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    draft: ApplicationActionDraftContent
    previous_outcome: ApplicationExecutionOutcome
    command_token: UUID
    effect_id: UUID
    effect_token: UUID

    def ticket(self) -> ApprovedInteractionClaim:
        return ApprovedInteractionClaim(
            WaitingInteractionClaim(self.command_token, self.draft, self.previous_outcome),
            self.effect_id,
            self.effect_token,
        )


def _ttl(ticket: ApprovedInteractionClaim) -> int:
    remaining = math.ceil((ticket.command.draft.expires_at - datetime.now(UTC)).total_seconds())
    if remaining <= 0:
        raise AuthorizationError(detail={"error_code": "INTERACTION_EXPIRED"})
    return min(remaining, MCP_USER_OAUTH_STATE_TTL_SECONDS)


async def save_oauth_claim(ticket: ApprovedInteractionClaim) -> None:
    value = StoredOAuthClaim(
        draft=ticket.command.draft,
        previous_outcome=ticket.command.previous_outcome,
        command_token=ticket.command.token,
        effect_id=ticket.effect_id,
        effect_token=ticket.effect_token,
    )
    redis = await get_redis_session()
    if not await redis.set(
        f"{_PREFIX}{value.draft.command_id}:claim",
        encrypt_data(value.model_dump_json()),
        ex=_ttl(ticket),
        nx=True,
    ):
        raise AuthorizationError(detail={"error_code": "STALE_STATE"})


async def read_oauth_claim(command_id: UUID) -> ApprovedInteractionClaim:
    redis = await get_redis_session()
    raw = await redis.get(f"{_PREFIX}{command_id}:claim")
    if not raw:
        raise AuthorizationError(detail={"error_code": "INTERACTION_EXPIRED"})
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    value = StoredOAuthClaim.model_validate_json(decrypt_data(text))
    if value.draft.command_id != command_id:
        raise AuthorizationError(detail={"error_code": "INVALID_DRAFT"})
    ticket = value.ticket()
    _ttl(ticket)
    return ticket


async def stage_oauth_credentials(
    ticket: ApprovedInteractionClaim, encrypted_credentials: str
) -> None:
    redis = await get_redis_session()
    if not await redis.set(
        f"{_PREFIX}{ticket.command.draft.command_id}:credentials",
        encrypted_credentials,
        ex=_ttl(ticket),
        nx=True,
    ):
        raise AuthorizationError(detail={"error_code": "STALE_STATE"})


async def consume_oauth_credentials(command_id: UUID) -> str | None:
    redis = await get_redis_session()
    raw = await redis.getdel(f"{_PREFIX}{command_id}:credentials")
    return raw.decode("utf-8") if isinstance(raw, bytes) else raw


async def save_oauth_metadata(
    ticket: ApprovedInteractionClaim, metadata: dict[str, JsonValue]
) -> None:
    payload = TypeAdapter(dict[str, JsonValue]).dump_json(metadata).decode("utf-8")
    if len(payload.encode("utf-8")) > 64_000:
        raise ValueError("OAuth metadata too large")
    redis = await get_redis_session()
    if not await redis.set(
        f"{_PREFIX}{ticket.command.draft.command_id}:metadata",
        encrypt_data(payload),
        ex=_ttl(ticket),
        nx=True,
    ):
        raise AuthorizationError(detail={"error_code": "STALE_STATE"})


async def read_oauth_metadata(command_id: UUID) -> dict[str, JsonValue]:
    redis = await get_redis_session()
    raw = await redis.get(f"{_PREFIX}{command_id}:metadata")
    if raw is None:
        raise AuthorizationError(detail={"error_code": "INTERACTION_EXPIRED"})
    text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    return TypeAdapter(dict[str, JsonValue]).validate_json(decrypt_data(text))


async def forget_oauth_claim(command_id: UUID) -> None:
    redis = await get_redis_session()
    await redis.delete(
        f"{_PREFIX}{command_id}:claim",
        f"{_PREFIX}{command_id}:credentials",
        f"{_PREFIX}{command_id}:metadata",
    )
