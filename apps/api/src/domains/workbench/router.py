"""Routes of the « Tools » section (ADR-369).

The router IS the ability: every route sits under the capability guard, and the
connectors themselves stay untouched when it is off. Every route authenticates
on a session of its own, closed before any provider is called (ADR-304), and
none depends on ``get_db``. Each tool mounts its own router here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.workbench import search
from src.domains.workbench.availability import read_availability
from src.domains.workbench.calendar_router import router as calendar_router
from src.domains.workbench.card_router import router as card_router
from src.domains.workbench.card_source import card_source_scope
from src.domains.workbench.contacts_router import router as contacts_router
from src.domains.workbench.files_router import router as files_router
from src.domains.workbench.lights_router import router as lights_router
from src.domains.workbench.mail_compose_router import router as mail_compose_router
from src.domains.workbench.mail_router import router as mail_router
from src.domains.workbench.mail_settings_router import router as mail_settings_router
from src.domains.workbench.rate_limits import rate_limit_read
from src.domains.workbench.schemas.common import WorkbenchAvailability
from src.domains.workbench.schemas.search import GlobalSearch, SearchQuery
from src.domains.workbench.tasks_router import router as tasks_router

router = APIRouter(
    prefix="/workbench",
    tags=["Workbench"],
    dependencies=[
        *capability_dependencies(PlatformCapability.WORKBENCH),
        Depends(card_source_scope),
    ],
)
router.include_router(mail_router)
router.include_router(mail_compose_router)
router.include_router(mail_settings_router)
router.include_router(calendar_router)
router.include_router(contacts_router)
router.include_router(files_router)
router.include_router(tasks_router)
router.include_router(lights_router)
router.include_router(card_router)


@router.get(
    "/search",
    response_model=GlobalSearch,
    summary="Words looked for across the tools; a tool that fails is named",
    dependencies=[Depends(rate_limit_read)],
)
async def get_search(
    query: Annotated[SearchQuery, Query()],
    user: Annotated[User, Depends(get_current_active_session_for_stream)],
) -> GlobalSearch:
    """Search the tools at once."""
    return await search.search_everything(user.id, resolve_user_timezone(user), query.q)


@router.get(
    "",
    response_model=WorkbenchAvailability,
    summary="The tools the account can use, and the bounds they enforce",
    description=(
        "For each tool of the « Tools » section (mail, calendar, tasks, contacts, files, "
        "lights): its state (ready, reconnect_required, not_connected, unavailable), the "
        "provider serving it, the gestures that provider accepts, and the bounds every "
        "route enforces (ADR-184: what is enforced is published)."
    ),
    dependencies=[Depends(rate_limit_read)],
)
async def get_workbench(
    user: User = Depends(get_current_active_session_for_stream),
) -> WorkbenchAvailability:
    """Read the rail of the signed-in account."""
    return await read_availability(user.id)
