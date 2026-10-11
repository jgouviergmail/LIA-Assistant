"""Direct UI and confirmed assistant number changes share the locked source owner."""

import hashlib
import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceConflictError
from src.core.i18n import resolve_language
from src.core.security.utils import encrypt_data
from src.domains.telephony.errors import raise_phone_number_invalid
from src.domains.telephony.number_state import stored_phone_number
from src.domains.telephony.phone_numbers import to_e164
from src.domains.telephony.preference_commands import locked_phone_actor
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.domains.users.repository import UserRepository
from src.infrastructure.phone_number_preferences import (
    PhoneNumberSnapshot,
    PhoneNumberValues,
    PhoneNumberWriteCheck,
)


def phone_number_snapshot(actor: User) -> PhoneNumberSnapshot:
    number = stored_phone_number(actor)
    stamp = actor.phone_number_verified_at
    payload = json.dumps(
        {
            "number": actor.phone_number_encrypted,
            "verified_at": stamp.isoformat() if stamp else None,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return PhoneNumberSnapshot(
        values=PhoneNumberValues(
            phone_number=number,
            number_status=(
                "available" if number else "unreadable" if actor.phone_number_encrypted else "unset"
            ),
            verified=bool(number and stamp),
            verified_at=stamp if number else None,
        ),
        stored_digest=hashlib.sha256(payload.encode("utf-8")).hexdigest(),
    )


async def update_phone_number(
    db: AsyncSession,
    actor_id: UUID,
    number: str | None,
    *,
    expected: PhoneNumberSnapshot | None = None,
    receipt: PreferenceWriteReceipt | None = None,
    check: PhoneNumberWriteCheck | None = None,
    users: UserRepository | None = None,
    language: str | None = None,
) -> None:
    canonical = to_e164(number) if number is not None else None
    if number is not None and canonical is None:
        raise_phone_number_invalid(resolve_language(language))
    repository = users or UserRepository(db)
    actor = await locked_phone_actor(repository, actor_id, check)
    current = phone_number_snapshot(actor)
    if expected is not None and current != expected:
        raise ResourceConflictError("phone number", detail={"error_code": "STALE_STATE"})
    if _number_is_unchanged(actor, canonical, current):
        if receipt is not None:
            receipt.committed, receipt.no_op = True, True
        return
    await repository.update(
        actor,
        {
            "phone_number_encrypted": encrypt_data(canonical) if canonical else None,
            "phone_number_verified_at": None,
        },
    )
    await db.commit()
    if receipt is not None:
        receipt.committed = True


def _number_is_unchanged(actor: User, number: str | None, current: PhoneNumberSnapshot) -> bool:
    if number is not None:
        return current.values.phone_number == number
    return actor.phone_number_encrypted is None and actor.phone_number_verified_at is None
