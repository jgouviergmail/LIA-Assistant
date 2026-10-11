"""Observed relationship controls are source projections, never a provider request or debrief."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import AuthorizationError
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.relations.overview_scope import (
    OverviewDirection,
    OverviewRole,
    OverviewSection,
    RelationOverviewScope,
)


class RelationSettingsProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    overview_scope: RelationOverviewScope
    debrief_enabled: bool
    debrief_platform_enabled: bool
    observed_at: datetime = Field(description="UTC observation time; no debrief or provider call")

    @field_validator("overview_scope")
    @classmethod
    def bound_source_selection(cls, value: RelationOverviewScope) -> RelationOverviewScope:
        for selection, ceiling in (
            (value.sections, len(OverviewSection)),
            (value.directions, len(OverviewDirection)),
            (value.roles, len(OverviewRole)),
        ):
            if len(selection) > ceiling:
                raise ValueError(
                    "Stored relation selection exceeds source option count; review in the Relations page"
                )
        return value


async def _debrief_available(db: AsyncSession) -> bool:
    try:
        await require_capability_fresh(db, PlatformCapability.RELATION_DEBRIEF)
    except AuthorizationError as error:
        if (
            isinstance(error.detail, dict)
            and error.detail.get("error_code") == "CAPABILITY_DISABLED"
        ):
            return False
        raise
    return True


async def read_relation_settings(db: AsyncSession, actor_id: UUID) -> RelationSettingsProjection:
    await require_application_tools(db)
    await load_actor(db, actor_id)
    available = await _debrief_available(db)
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    return RelationSettingsProjection(
        overview_scope=RelationOverviewScope.from_stored(actor.relation_overview_scope),
        debrief_enabled=bool(actor.relation_debrief_enabled),
        debrief_platform_enabled=available,
        observed_at=datetime.now(UTC),
    )
