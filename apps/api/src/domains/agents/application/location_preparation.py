"""Resolve an address once, then freeze location data and its deletion cascade."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.location_schemas import HomeLocationPatch, LocationChangeRequest
from src.domains.agents.application.preparation import _preference_content
from src.domains.users.home_location_commands import (
    location_values,
    require_places,
    resolve_home_location,
)
from src.domains.users.schemas import HomeLocationUpdate


async def prepare_location_patch(
    db: AsyncSession,
    actor_id: UUID,
    patch: HomeLocationPatch,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    validated = HomeLocationPatch.model_validate(patch.model_dump(exclude_unset=True))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    if validated.home_location is not None:
        await require_places(db, actor_id)
    return _preference_content(
        actor_id,
        validated,
        location_values(actor, validated.model_fields_set),
        command_id=command_id,
    )


async def prepare_location_change(
    db: AsyncSession,
    actor_id: UUID,
    request: LocationChangeRequest,
    *,
    command_id: UUID | None = None,
) -> ApplicationActionDraftContent:
    request = LocationChangeRequest.model_validate(request.model_dump(exclude_unset=True))
    await require_application_tools(db)
    actor = await load_actor(db, actor_id)
    fields = (
        {"home_location", "last_known_location"} if request.action == "clear" else {"home_location"}
    )
    before = location_values(actor, fields)
    if request.action == "clear":
        patch = HomeLocationPatch(home_location=None, last_known_location=None)
    else:
        assert request.address is not None
        home = await resolve_home_location(
            db, actor_id, HomeLocationUpdate(address=request.address, lat=0, lon=0)
        )
        await require_application_tools(db)
        await load_actor(db, actor_id)
        patch = HomeLocationPatch.model_validate({"home_location": home.model_dump()})
    # Before is the snapshot obtained before network resolution. A concurrent UI
    # write makes the approval stale, never silently overwrites that write.
    return _preference_content(actor_id, patch, before, command_id=command_id)
