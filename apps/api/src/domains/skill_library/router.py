"""The skill library's routes (ADR-327) — exactly what the web client names.

Every route sits under BOTH switches: the skills capability (a library skill
is a skill) and the library's own (the router IS the ability: searching,
installing, updating). Removing an installed skill is the skills section's
ordinary delete, which stays open when the library is closed.

None holds a request session: each route reaches a portal or GitHub, so the
account is read on a session of its own (``get_current_active_session_for_stream``)
and every store opens its own short one around its queries, never around a
network wait (ADR-304). A refusal carries a stable code in ``detail.code`` the
web app translates, and is counted with its operation.
"""

from __future__ import annotations

from collections.abc import Awaitable
from typing import Final, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from src.core.config import settings
from src.core.constants import SKILL_LIBRARY_QUERY_MAX_CHARS
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skill_library import service
from src.domains.skill_library.errors import LibraryRefusal, refuse
from src.domains.skill_library.schemas import (
    LibraryInstalledResponse,
    LibraryInstallRequest,
    LibraryInstallResponse,
    LibraryPreviewAnswer,
    LibrarySearchResponse,
    LibraryUpdatePreviewResponse,
    LibraryUpdateRequest,
)
from src.domains.users.models import User
from src.infrastructure.observability.metrics_registry import skill_library_operations_total

router = APIRouter(
    prefix="/skill-library",
    tags=["Skill library"],
    dependencies=[
        *capability_dependencies(PlatformCapability.SKILLS),
        *capability_dependencies(PlatformCapability.SKILL_LIBRARY),
    ],
)

# Read once at import, like every settings-driven module constant: each call
# reaches a portal or GitHub, whose anonymous allowance the instance shares.
rate_limit_library = create_user_rate_limiter(
    "skill_library",
    max_calls=settings.skill_library_rate_limit_calls,
    window_seconds=settings.skill_library_rate_limit_window_seconds,
    authenticate=get_current_active_session_for_stream,
)

_OK: Final = "ok"
T = TypeVar("T")


async def _answered(operation: str, work: Awaitable[T]) -> T:
    """Run one operation, count its outcome, and turn a refusal into the API's answer."""
    try:
        answer = await work
    except LibraryRefusal as refusal:
        skill_library_operations_total.labels(operation=operation, outcome=refusal.code).inc()
        refuse(refusal)
    skill_library_operations_total.labels(operation=operation, outcome=_OK).inc()
    return answer


@router.get(
    "/search",
    response_model=LibrarySearchResponse,
    summary="Search a skill portal",
    description="Refusals: `skill_library_query_invalid`, `skill_library_unreachable`.",
    dependencies=[Depends(rate_limit_library)],
)
async def search(
    q: str = Query(..., max_length=SKILL_LIBRARY_QUERY_MAX_CHARS, description="Search text."),
    portal: str | None = Query(None, max_length=40, description="The portal (default skills.sh)."),
    user: User = Depends(get_current_active_session_for_stream),
) -> LibrarySearchResponse:
    """Search the portal, marking what the caller already installed."""
    return await _answered("search", service.search(user.id, q, portal))


@router.get(
    "/preview",
    response_model=LibraryPreviewAnswer,
    summary="Read a skill before installing it",
    description=(
        "Either a `repository` with the portal's `skill_id`, or a pasted `address` "
        "(owner/repo or a github.com URL); `path` names the folder. When the "
        "repository holds several skills and none is named, answers the folders to "
        "choose from. Refusals: `skill_library_source_invalid`, `skill_library_not_found`, "
        "`skill_library_ambiguous`, `skill_library_too_large`, `skill_library_invalid_skill`, "
        "`skill_library_rate_limited`, `skill_library_unreachable`."
    ),
    dependencies=[Depends(rate_limit_library)],
)
async def preview(
    repository: str | None = Query(None, max_length=200, description="owner/repo."),
    address: str | None = Query(None, max_length=500, description="A pasted GitHub address."),
    skill_id: str | None = Query(None, max_length=200, description="The portal's skill id."),
    path: str | None = Query(None, max_length=500, description="The folder."),
    ref: str | None = Query(None, max_length=200, description="A branch or tag."),
    portal: str | None = Query(None, max_length=40, description="The portal it was found on."),
    registry_id: str | None = Query(None, max_length=300, description="The portal's id."),
    user: User = Depends(get_current_active_session_for_stream),
) -> LibraryPreviewAnswer:
    """Read one skill of a repository at the commit its ref points at now."""
    return await _answered(
        "preview",
        service.preview(
            user.id,
            repository=repository,
            address=address,
            skill_id=skill_id,
            path=path.strip("/") if path is not None else None,
            ref=ref,
            portal=portal,
            registry_id=registry_id,
        ),
    )


@router.post(
    "/install",
    response_model=LibraryInstallResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Install the skill a preview showed",
    description=(
        "Installs the folder at the commit the preview read. Refusals: "
        "`skill_library_audit_blocked` (with `risk`), `skill_library_name_taken`, "
        "`skill_library_already_installed`, `skill_library_quota_reached`, "
        "`skill_library_invalid_skill`, and every preview refusal."
    ),
    dependencies=[Depends(rate_limit_library)],
)
async def install(
    request: LibraryInstallRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> LibraryInstallResponse:
    """Install one skill from its repository."""
    return await _answered("install", service.install(user.id, request))


@router.get(
    "/installed",
    response_model=LibraryInstalledResponse,
    summary="The skills installed from a library, and whether each moved",
    dependencies=[Depends(rate_limit_library)],
)
async def installed(
    user: User = Depends(get_current_active_session_for_stream),
) -> LibraryInstalledResponse:
    """List the caller's library skills with an update verdict each."""
    return await _answered("installed", service.installed(user.id))


@router.get(
    "/installed/{skill_id}/update",
    response_model=LibraryUpdatePreviewResponse,
    summary="Read the next version of an installed skill",
    description="Refusals: `skill_library_not_installed`, and every preview refusal.",
    dependencies=[Depends(rate_limit_library)],
)
async def update_preview(
    skill_id: UUID,
    user: User = Depends(get_current_active_session_for_stream),
) -> LibraryUpdatePreviewResponse:
    """The version an update installs, and the files it changes."""
    return await _answered("update_preview", service.update_preview(user.id, skill_id))


@router.post(
    "/installed/{skill_id}/update",
    response_model=LibraryInstallResponse,
    summary="Update an installed skill to the version its update preview showed",
    description=(
        "Refusals: `skill_library_not_installed`, `skill_library_renamed`, "
        "`skill_library_audit_blocked`, and every install refusal."
    ),
    dependencies=[Depends(rate_limit_library)],
)
async def update(
    skill_id: UUID,
    request: LibraryUpdateRequest,
    user: User = Depends(get_current_active_session_for_stream),
) -> LibraryInstallResponse:
    """Replace an installed skill by the version the preview read."""
    return await _answered("update", service.update(user.id, skill_id, request.commit_sha))
