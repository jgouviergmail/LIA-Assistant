"""The current account's phone preferences behind the injected application port."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.telephony.preference_commands import (
    phone_preference_snapshot,
    update_phone_preferences,
)
from src.domains.telephony.schemas import TelephonyIdentityUpdateRequest
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.phone_preferences import (
    PhonePreferenceSnapshot,
    PhonePreferenceValues,
    PhoneWriteCheck,
)


class SavedPhonePreferences:
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhonePreferenceSnapshot:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        return phone_preference_snapshot(actor)

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        values: PhonePreferenceValues,
        *,
        expected: PhonePreferenceSnapshot,
        receipt: PreferenceWriteReceipt,
        check: PhoneWriteCheck,
    ) -> None:
        await update_phone_preferences(
            db,
            actor_id,
            TelephonyIdentityUpdateRequest(**values.model_dump()),
            expected=expected,
            receipt=receipt,
            check=check,
        )
