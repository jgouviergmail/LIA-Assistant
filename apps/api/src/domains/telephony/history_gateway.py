"""Phone history is served only from the current active owner's records."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.telephony.history_queries import read_call_history
from src.domains.telephony.history_schemas import PhoneHistoryProjection, PhoneHistoryRead
from src.domains.users.models import User


class SavedPhoneHistory:
    async def read(
        self, db: AsyncSession, actor_id: UUID, request: PhoneHistoryRead
    ) -> PhoneHistoryProjection:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        return await read_call_history(db, actor_id, request)
