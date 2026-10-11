"""Stored debrief provenance is read through its source service, never synthesized."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.relation_settings_read import _debrief_available
from src.domains.relations.debrief.schemas import DebriefStatus, RelationDebriefRead
from src.domains.relations.debrief.service import RelationDebriefService
from src.domains.shared.text_normalization import fold_name

# Refuse malformed/oversized stored data instead of silently changing its meaning.
RELATION_STORED_DEBRIEF_MAX_BYTES = 64_000


class RelationStoredDebriefQuery(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str = Field(min_length=1, max_length=255, strict=True)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        key = fold_name(value)
        if not key or len(key) > 255:
            raise ValueError("An explicit relationship name is required")
        return value.strip()


class RelationStoredDebriefProjection(RelationDebriefRead):
    model_config = ConfigDict(frozen=True, extra="forbid")
    observed_at: datetime


async def read_stored_relation_debrief(
    db: AsyncSession, actor_id: UUID, query: RelationStoredDebriefQuery
) -> RelationStoredDebriefProjection:
    selected = RelationStoredDebriefQuery.model_validate(query.model_dump())
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    available = await _debrief_available(db)
    if not available or not actor.relation_debrief_enabled:
        observed = RelationDebriefRead(status=DebriefStatus.DISABLED, person=selected.name)
    else:
        observed = await RelationDebriefService(actor_id).read(selected.name)
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if not await _debrief_available(db) or not actor.relation_debrief_enabled:
        observed = RelationDebriefRead(status=DebriefStatus.DISABLED, person=selected.name)
    require_bounded_debrief(observed)
    return RelationStoredDebriefProjection(**observed.model_dump(), observed_at=datetime.now(UTC))


def require_bounded_debrief(observed: RelationDebriefRead) -> None:
    if len(observed.model_dump_json().encode("utf-8")) > RELATION_STORED_DEBRIEF_MAX_BYTES:
        raise ValueError(
            "Stored debrief exceeds the bounded native read; review in the Relations page"
        )
