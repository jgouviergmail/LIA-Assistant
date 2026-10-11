"""Fresh live reflex reads and immutable proposals; no session or provider action."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.live_schemas import (
    LivePreferencePatch,
    LivePreferenceProjection,
    LivePreferenceRequest,
)
from src.domains.agents.application.preparation import _preference_content
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.live_preferences import LiveReflexValues, get_live_preferences


async def read_live_preferences(db: AsyncSession, actor_id: UUID) -> LivePreferenceProjection:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    await load_actor(db, actor_id)
    snapshot = await get_live_preferences().read(db, actor_id)
    return LivePreferenceProjection(
        preferences=snapshot.values, defaulted_fields=snapshot.defaulted_fields
    )


async def prepare_live_preference_content(
    db: AsyncSession,
    actor_id: UUID,
    request: LivePreferenceRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    await load_actor(db, actor_id)
    before = await get_live_preferences().read(db, actor_id)
    values = LiveReflexValues.model_validate(
        {**before.values.model_dump(), **request.model_dump(exclude_unset=True)}
    )
    return _preference_content(
        actor_id,
        LivePreferencePatch(live_reflexes=before.model_copy(update={"values": values})),
        {"live_reflexes": before.model_dump(mode="json")},
        command_id=command_id,
    )
