"""Saved provider-settings proposals use a delta and never perform a provider probe."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.live_connector_schemas import (
    LiveConnectorChangeRequest,
    LiveConnectorCommandValues,
    LiveConnectorPreferencePatch,
)
from src.domains.agents.application.preparation import _preference_content
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.live_connector_preferences import (
    LiveConnectorPreferenceProjection,
    get_live_connector_preferences,
)


async def read_live_connector_preferences(
    db: AsyncSession, actor_id: UUID
) -> LiveConnectorPreferenceProjection:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    await load_actor(db, actor_id)
    return await get_live_connector_preferences().read(db, actor_id)


async def prepare_live_connector_content(
    db: AsyncSession,
    actor_id: UUID,
    request: LiveConnectorChangeRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.LIVE)
    await load_actor(db, actor_id)
    snapshot, saved, desired = await get_live_connector_preferences().prepare(
        db, actor_id, request.provider, request.settings.model_dump(mode="json", exclude_unset=True)
    )
    before = LiveConnectorCommandValues(expected=snapshot, settings=saved)
    return _preference_content(
        actor_id,
        LiveConnectorPreferencePatch(
            live_connector_settings=before.model_copy(update={"settings": desired})
        ),
        {"live_connector_settings": before.model_dump(mode="json")},
        command_id=command_id,
    )
