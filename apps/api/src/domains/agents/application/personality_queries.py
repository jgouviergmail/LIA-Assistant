"""Public UI personality data, without translation jobs or configuration writes."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.core.i18n import resolve_language
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.personality_schemas import (
    PersonalityProjection,
    PersonalityRead,
)
from src.domains.personalities.service import PersonalityService


async def read_personalities(
    db: AsyncSession, actor_id: UUID, query: PersonalityRead
) -> PersonalityProjection:
    selected = PersonalityRead.model_validate(query.model_dump())
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    language, preference = actor.language, actor.personality_id
    service = PersonalityService(db)
    catalogue = await service.list_active(language)
    effective = await service.get_user_personality(preference, language)
    start = 0
    if selected.after_id is not None:
        index = next(
            (i for i, item in enumerate(catalogue.personalities) if item.id == selected.after_id),
            None,
        )
        if index is None:
            raise ResourceNotFoundError("personality cursor", selected.after_id)
        start = index + 1
    rows = catalogue.personalities[start : start + selected.limit]
    more = start + len(rows) < catalogue.total
    await require_application_tools(db)
    refreshed = await load_actor(db, actor_id)
    if refreshed.language != language or refreshed.personality_id != preference:
        raise ValueError("Personality preferences changed while reading; retry")
    return PersonalityProjection(
        personalities=rows,
        total=catalogue.total,
        personality_id=preference,
        personality=effective,
        returned_count=len(rows),
        truncated=more,
        next_cursor=rows[-1].id if more else None,
        language=resolve_language(language),
        observed_at=datetime.now(UTC),
    )
