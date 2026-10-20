"""Saved SMS references require live consent, the same revision and owned source rows."""

from collections.abc import Mapping, Sequence
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.sms.projection import SmsToolItem
from src.domains.sms.models import SmsMessage
from src.domains.sms.reads import require_read
from src.infrastructure.database.session import get_db_context


class SmsSnapshotGuard:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def allows(self, owner: UUID, items: list[SmsToolItem]) -> bool:
        if len(items) > 50 or any(item.owner_id != owner for item in items):
            return False
        try:
            actor = await require_read(self.db, owner, assistant=True)
            if any(item.revision != (actor.extraction_revision or 0) for item in items):
                return False
            ids = {item.id for item in items}
            live = set(
                (
                    await self.db.scalars(
                        select(SmsMessage.id).where(
                            SmsMessage.user_id == owner, SmsMessage.id.in_(ids)
                        )
                    )
                ).all()
            )
            return live == ids
        except AuthorizationError, SQLAlchemyError, OSError, TimeoutError:
            return False


async def sms_context_read_allowed(owner: str, items: Sequence[Mapping[str, object]]) -> bool:
    try:
        selected = [
            SmsToolItem.model_validate(
                {key: value for key, value in item.items() if key != "index"}
            )
            for item in items
        ]
        async with get_db_context() as db:
            return await SmsSnapshotGuard(db).allows(UUID(owner), selected)
    except ValidationError, ValueError, SQLAlchemyError, OSError, TimeoutError:
        return False
