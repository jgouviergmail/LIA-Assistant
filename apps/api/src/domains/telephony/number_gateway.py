"""The account's declared number behind the injected application port."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.telephony.number_commands import phone_number_snapshot, update_phone_number
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.phone_number_preferences import PhoneNumberSnapshot, PhoneNumberWriteCheck


class SavedPhoneNumber:
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhoneNumberSnapshot:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or actor.id != actor_id or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        return phone_number_snapshot(actor)

    async def write(
        self,
        db: AsyncSession,
        actor_id: UUID,
        number: str | None,
        *,
        expected: PhoneNumberSnapshot,
        receipt: PreferenceWriteReceipt,
        check: PhoneNumberWriteCheck,
    ) -> None:
        await update_phone_number(
            db, actor_id, number, expected=expected, receipt=receipt, check=check
        )
