"""Bind phone reads to a fresh owner and a non-mutating pending-status check."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.telephony.identity import TelephonyIdentityService
from src.domains.telephony.identity_queries import native_identity_projection, project_identity
from src.domains.telephony.verification import TelephonyVerificationService
from src.domains.users.models import User
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.phone_identity import PhoneIdentityProjection


class SavedPhoneIdentity:
    async def read(self, db: AsyncSession, actor_id: UUID) -> PhoneIdentityProjection:
        actor: User | None = await db.scalar(
            select(User).where(User.id == actor_id).execution_options(populate_existing=True)
        )
        if actor is None or not actor.is_active or actor.is_deleted:
            raise AuthorizationError(detail={"error_code": "FORBIDDEN"})
        identity = TelephonyIdentityService(db)
        current = await identity.get_identity(actor_id)
        verification = TelephonyVerificationService(
            db, redis=await get_redis_cache(), identity=identity
        )
        pending = await verification.pending(actor_id, cleanup=False)
        return native_identity_projection(
            actor, project_identity(current, verification_pending=pending)
        )
