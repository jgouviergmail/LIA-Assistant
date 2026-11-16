"""Reading the writing style from the conversation learns nothing and reads no mailbox.

What the assistant reads is what the settings show (``WritingStyleService.read``), and
the scopes the two confirmed acts bind are read from the same row, in the same terms.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceNotFoundError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.writing_style_schemas import (
    WritingStyleLearnScope,
    WritingStyleRecord,
)
from src.domains.writing_style.models import WritingStyle
from src.domains.writing_style.repository import StoredStyle, WritingStyleRepository
from src.domains.writing_style.schemas import WritingStyleResponse
from src.domains.writing_style.service import WritingStyleService


async def _stored(db: AsyncSession, actor_id: UUID) -> StoredStyle:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    stored = await WritingStyleRepository(db).read(actor_id)
    if stored is None:
        raise ResourceNotFoundError("writing_style", str(actor_id))
    return stored


def record_of(row: WritingStyle | None) -> WritingStyleRecord | None:
    """The record a card names, or None when nothing was ever learned (pure)."""
    if row is None:
        return None
    return WritingStyleRecord(
        learned_at=row.built_at.isoformat(),
        mails_read=row.mails_read,
        profile_learned=row.profile_encrypted is not None,
    )


async def read_writing_style(db: AsyncSession, actor_id: UUID) -> WritingStyleResponse:
    """What the settings show: the switch, how many e-mails a learning reads, the record."""
    await _stored(db, actor_id)
    return await WritingStyleService(db).read(actor_id)


async def learn_scope(db: AsyncSession, actor_id: UUID) -> WritingStyleLearnScope:
    """What a learning would read, and the record it would replace.

    Raises:
        AuthorizationError: The person's switch is off: nothing may be read.
    """
    stored = await _stored(db, actor_id)
    if not stored.enabled:
        raise AuthorizationError(detail={"error_code": "CAPABILITY_DISABLED"})
    return WritingStyleLearnScope(
        mails_to_read=settings.writing_style_sent_mails, replaces=record_of(stored.row)
    )


async def forget_scope(db: AsyncSession, actor_id: UUID) -> WritingStyleRecord:
    """The record forgetting would remove, whatever the switch says (ADR-280).

    Raises:
        ResourceNotFoundError: Nothing was ever learned: there is nothing to forget.
    """
    record = record_of((await _stored(db, actor_id)).row)
    if record is None:
        raise ResourceNotFoundError("writing_style", str(actor_id))
    return record
