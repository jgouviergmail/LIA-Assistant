"""Always-mounted session-only controls; no background work starts from a settings read."""

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.dependencies import get_db
from src.core.exceptions import raise_unprocessable_entity
from src.core.private_input_route import PrivateApplicationInputRoute
from src.core.session_dependencies import get_current_active_session
from src.domains.proactive_discussions.api_schemas import (
    ContextEpochRequest,
    ContextPurgeRequest,
    ContextUseUpdate,
    DiscussionActivity,
    DiscussionSettingsResponse,
    DiscussionSettingsUpdate,
)
from src.domains.proactive_discussions.context_store.filters import ContextFilters
from src.domains.proactive_discussions.context_store.repository import ContextRepository
from src.domains.proactive_discussions.context_store.schemas import (
    ContextGeneration,
    ContextPurgePreview,
)
from src.domains.proactive_discussions.openings import (
    FeedbackRequest,
    OpeningPage,
    OpeningPageRequest,
    OpeningView,
    apply_feedback,
    get_opening,
    list_openings,
)
from src.domains.proactive_discussions.settings_service import read_settings, update_settings
from src.domains.users.models import User
from src.infrastructure.proactive.discussion_activity import read_activity
from src.infrastructure.proactive.discussion_rebuild import kick_context_rebuild


def private_response(response: Response) -> None:
    """Forbid any cache from keeping these private answers (``no-store``)."""
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/proactive-discussions",
    tags=["Proactive discussions"],
    route_class=PrivateApplicationInputRoute,
    dependencies=[Depends(private_response)],
)


@router.get("/openings", response_model=OpeningPage)
async def opening_history(
    limit: int = Query(default=30, ge=1, le=50),
    after_id: UUID | None = None,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OpeningPage:
    """List the openings LIA made, newest first, with their exact total."""
    return await list_openings(db, user.id, OpeningPageRequest(limit=limit, after_id=after_id))


@router.get("/openings/{opening_id}", response_model=OpeningView)
async def opening_details(
    opening_id: UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OpeningView:
    """Return one opening with the reason and the sources recorded when it began."""
    return await get_opening(db, user.id, opening_id)


@router.post("/openings/{opening_id}/feedback", response_model=OpeningView)
async def opening_feedback(
    opening_id: UUID,
    data: FeedbackRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> OpeningView:
    """Record the person's reaction to an opening; a stale expected reaction answers 409."""
    result = await apply_feedback(
        db, user.id, opening_id, data.feedback, expected=data.expected_feedback
    )
    await db.commit()
    return result


@router.get("/settings", response_model=DiscussionSettingsResponse)
async def get_settings(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscussionSettingsResponse:
    """Return the person's discussion settings and what the instance currently offers."""
    result = await read_settings(db, user.id)
    await db.commit()
    return result


@router.patch("/settings", response_model=DiscussionSettingsResponse)
async def patch_settings(
    data: DiscussionSettingsUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscussionSettingsResponse:
    """Change the settings against the revision read; incoherent 422, stale 409."""
    try:
        result = await update_settings(db, user.id, data)
    except ValueError:
        raise_unprocessable_entity("Invalid discussion preference change")
    await db.commit()
    return result


@router.get("/activity", response_model=DiscussionActivity)
async def get_activity(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> DiscussionActivity:
    """A rebuild in progress, the last runs and what they cost, and a ceiling reached."""
    result = await read_activity(db, user.id, now=datetime.now(UTC))
    await db.commit()
    return result


@router.get("/context", response_model=ContextGeneration)
async def get_context(
    limit: int = Query(default=30, ge=1, le=100),
    after_id: UUID | None = None,
    after_exclusion_id: UUID | None = None,
    filters: ContextFilters = Depends(),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ContextGeneration:
    """Return one page of the discussion context, its exclusions and its generation."""
    result = await ContextRepository(db).read_generation(
        user.id,
        now=datetime.now(UTC),
        limit=limit,
        after_id=after_id,
        after_exclusion_id=after_exclusion_id,
        filters=filters,
    )
    await db.commit()
    return result


@router.patch("/context/{item_id}/usability", response_model=ContextGeneration)
async def set_context_usable(
    item_id: UUID,
    data: ContextUseUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ContextGeneration:
    """Mark one context item not usable, or allow it again."""
    result = await ContextRepository(db).set_usable(
        user.id,
        item_id,
        usable=data.usable,
        expected_revision=data.expected_revision,
        expected_epoch=data.expected_epoch,
        now=datetime.now(UTC),
    )
    await db.commit()
    return result


@router.post("/context/purge", response_model=ContextGeneration)
async def purge_context(
    data: ContextPurgeRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ContextGeneration:
    """Purge the whole context, or the selected items and what derives from them."""
    result = await ContextRepository(db).purge(
        user.id,
        selection=data.selection,
        expected_epoch=data.expected_epoch,
        expected_generation=data.expected_generation,
        now=datetime.now(UTC),
    )
    await db.commit()
    return result


@router.post("/context/purge-preview", response_model=ContextPurgePreview)
async def preview_context_purge(
    data: ContextPurgeRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ContextPurgePreview:
    """Count what a purge would remove, without removing anything."""
    result = await ContextRepository(db).preview_purge(
        user.id,
        selection=data.selection,
        expected_epoch=data.expected_epoch,
        expected_generation=data.expected_generation,
        now=datetime.now(UTC),
    )
    await db.commit()
    return result


@router.post("/context/rebuild", response_model=ContextGeneration)
async def rebuild_context(
    data: ContextEpochRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ContextGeneration:
    """Request a context rebuild, then start it in the background once committed."""
    result = await ContextRepository(db).request_rebuild(
        user.id, expected_epoch=data.expected_epoch, now=datetime.now(UTC)
    )
    await db.commit()
    kick_context_rebuild(user.id, result.context_epoch)
    return result
