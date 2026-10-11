"""Resolve an exact phone consent proposal without a write, code or provider call."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.phone_preference_schemas import (
    PhonePreferencePatch,
    PhonePreferenceRequest,
)
from src.domains.agents.application.preparation import _preference_content
from src.domains.feature_switches.guard import require_capability_fresh
from src.domains.feature_switches.registry import PlatformCapability
from src.infrastructure.phone_preferences import PhonePreferenceValues, get_phone_preferences


async def prepare_phone_preferences(
    db: AsyncSession,
    actor_id: UUID,
    request: PhonePreferenceRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = PhonePreferenceRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    before = await get_phone_preferences().read(db, actor_id)
    values = PhonePreferenceValues.model_validate(
        {**before.values.model_dump(), **validated.model_dump(exclude_unset=True)}
    )
    await require_application_tools(db)
    await require_capability_fresh(db, PlatformCapability.TELEPHONY)
    await load_actor(db, actor_id)
    return _preference_content(
        actor_id,
        PhonePreferencePatch(phone_preferences=before.model_copy(update={"values": values})),
        {"phone_preferences": before.model_dump(mode="json")},
        command_id=command_id,
    )
