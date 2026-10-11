"""UI and confirmed assistant consent patches share one locked, atomic write."""

import hashlib
import json
from typing import get_args
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError, ResourceConflictError
from src.core.i18n import resolve_language
from src.domains.shared.phone_domains import is_phone_domain, unknown_phone_domains
from src.domains.telephony.errors import raise_phone_domain_unknown
from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.domains.voice_sessions.session import as_voice_session_mode
from src.infrastructure.phone_preferences import (
    PhonePreferenceSnapshot,
    PhonePreferenceValues,
    PhoneWriteCheck,
)


def assert_phone_preference_coverage() -> None:
    if set(TelephonyIdentityUpdateRequest.model_fields) != set(PhonePreferenceValues.model_fields):
        raise AssertionError("New phone settings require native projection review")
    source_mode = get_args(TelephonyIdentityUpdateRequest.model_fields["call_mode"].annotation)[0]
    if set(get_args(source_mode)) != set(
        get_args(PhonePreferenceValues.model_fields["call_mode"].annotation)
    ):
        raise AssertionError("New phone modes require native projection review")


assert_phone_preference_coverage()


def phone_preference_snapshot(actor: User) -> PhonePreferenceSnapshot:
    raw = json.dumps(
        {
            "rich_context": actor.phone_rich_context_enabled,
            "domains": actor.phone_disabled_domains,
            "mode": actor.phone_call_mode,
            "number": actor.phone_number_encrypted,
            "verified_at": (
                actor.phone_number_verified_at.isoformat()
                if actor.phone_number_verified_at
                else None
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return PhonePreferenceSnapshot(
        values=PhonePreferenceValues(
            rich_context_enabled=bool(actor.phone_rich_context_enabled),
            disabled_domains=[
                d for d in (actor.phone_disabled_domains or []) if is_phone_domain(str(d))
            ],
            call_mode=as_voice_session_mode(str(actor.phone_call_mode or "delegated")),
        ),
        stored_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )


async def update_phone_preferences(
    db: AsyncSession,
    actor_id: UUID,
    patch: TelephonyIdentityUpdateRequest,
    *,
    expected: PhonePreferenceSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: PhoneWriteCheck | None = None,
    language: str | None = None,
    users: UserRepository | None = None,
) -> PhonePreferenceValues:
    # Validate the entire source patch before any field changes or lock waits.
    validated = TelephonyIdentityUpdateRequest.model_validate(patch.model_dump(exclude_unset=True))
    if validated.disabled_domains is not None and unknown_phone_domains(validated.disabled_domains):
        raise_phone_domain_unknown(resolve_language(language))
    repository = users or UserRepository(db)
    actor = await locked_phone_actor(repository, actor_id, check)
    current = phone_preference_snapshot(actor)
    if expected is not None and current != expected:
        raise ResourceConflictError("phone preferences", detail={"error_code": "STALE_STATE"})
    delta = validated.model_dump(exclude_none=True)
    desired = PhonePreferenceValues.model_validate({**current.values.model_dump(), **delta})
    if desired == current.values and _saved_fields_match(actor, desired, delta):
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return desired
    columns = {
        "rich_context_enabled": "phone_rich_context_enabled",
        "disabled_domains": "phone_disabled_domains",
        "call_mode": "phone_call_mode",
    }
    values = desired.model_dump()
    await repository.update(actor, {columns[field]: values[field] for field in delta})
    await db.commit()
    if receipt is not None:
        receipt.committed = True
    return desired


async def locked_phone_actor(
    repository: UserRepository, actor_id: UUID, check: PhoneWriteCheck | None
) -> User:
    actor = await repository.get_by_id_for_preference_update(actor_id)
    if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
        raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
    if check is not None:
        await check()
    return actor


def _saved_fields_match(
    actor: User, desired: PhonePreferenceValues, delta: dict[str, object]
) -> bool:
    saved: dict[str, object] = {
        "rich_context_enabled": actor.phone_rich_context_enabled,
        "disabled_domains": actor.phone_disabled_domains,
        "call_mode": actor.phone_call_mode,
    }
    return all(
        saved[name] == value for name, value in desired.model_dump().items() if name in delta
    )
