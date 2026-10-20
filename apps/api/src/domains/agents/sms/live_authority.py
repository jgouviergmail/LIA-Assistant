"""One bounded indexed source check for all SMS copies about to enter a model."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.sms.models import SmsMessage
from src.domains.sms.reads import require_read
from src.infrastructure.database.session import get_db_context


@dataclass(frozen=True)
class SmsLiveAuthority:
    owner: UUID
    revision: int
    ids: frozenset[UUID]


async def load_sms_authority(owner: UUID, ids: set[UUID]) -> SmsLiveAuthority | None:
    if len(ids) > settings.registry_max_items + 128:
        return None
    try:
        async with get_db_context() as db:
            actor = await require_read(db, owner, assistant=True)
            live = frozenset(
                (
                    await db.scalars(
                        select(SmsMessage.id).where(
                            SmsMessage.user_id == owner, SmsMessage.id.in_(ids)
                        )
                    )
                ).all()
            )
            return SmsLiveAuthority(owner=owner, revision=actor.extraction_revision or 0, ids=live)
    except AuthorizationError, SQLAlchemyError, OSError, TimeoutError:
        return None
