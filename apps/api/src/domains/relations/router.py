"""Relations domain router (N-09) — personal CRM.

Read surface aggregates existing DB-local signals:

- GET /relations          : the overview (people ranked by recent interaction)
- GET /relations/{name}   : the 360° view of one relationship

The ONLY write surface is the favorites star (the CRM's sole persisted
state — everything else is a lens over data other domains own):

- PUT    /relations/favorites/{name} : star a relationship (idempotent)
- DELETE /relations/favorites/{name} : unstar it (idempotent)

Both answer 204: the frontend toggles optimistically and reconciles on the
next overview read. Favorites routes are declared BEFORE the ``/{name}``
catch-all so the literal segment wins — and so is ``/{name}/context``, whose
longer path would otherwise be swallowed by it.

- GET /relations/{name}/context : the provider-backed sections (Bloc C)
- GET/PUT /relations/overview-scope : what a 360° point may read
"""

from fastapi import APIRouter, Depends, Query, Response, status

from src.core.config import settings
from src.core.exceptions import raise_invalid_input
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.relations.overview_scope import RelationOverviewScope
from src.domains.relations.providers.schemas import RelationContext
from src.domains.relations.providers.service import RelationContextService
from src.domains.relations.schemas import (
    RelationDetail,
    RelationMergeRequest,
    RelationsOverview,
)
from src.domains.relations.service import RelationsService
from src.domains.users.models import User

router = APIRouter(prefix="/relations", tags=["relations"])

# Read once at import, like every settings-driven module constant. This guards
# EXTERNAL quota, not the database: one provider-backed read costs up to
# 1 + 3×addresses + 1 API calls (mail asks from/to/cc separately), and every
# distinct NAME is its own cache entry — so the cache cannot bound a caller
# walking through names, and an exhausted Google/Microsoft quota breaks far
# more than this page.
rate_limit_relation_context = create_user_rate_limiter(
    action="relations_context",
    max_calls=settings.relations_provider_rate_limit_calls,
    window_seconds=settings.relations_provider_rate_limit_window_seconds,
)


@router.put(
    "/favorites/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Star a relationship (idempotent)",
)
async def add_relation_favorite(
    name: str,
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Persist the star; starring twice refreshes the stored spelling."""
    await RelationsService(current_user.id).add_favorite(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/favorites/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unstar a relationship (idempotent)",
)
async def remove_relation_favorite(
    name: str,
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Remove the star; unstarring an unstarred name is a no-op."""
    await RelationsService(current_user.id).remove_favorite(name)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/merges",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Merge two relationships into one (idempotent, reversible)",
    responses={
        400: {"description": "Blank name, or the same relationship on both sides"},
    },
)
async def merge_relations(
    payload: RelationMergeRequest,
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Record that two relationships are the same person.

    Manual by design: folding already merges what is literally the same
    spelling, and everything beyond that is a judgement only the user can
    make. Nothing is rewritten in the sources, so the merge is reversible.
    """
    try:
        await RelationsService(current_user.id).merge_relations(
            source=payload.source, target=payload.target
        )
    except ValueError as exc:
        raise_invalid_input(str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/merges/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Undo a merge — the relationship becomes its own card again",
    responses={400: {"description": "Blank name"}},
)
async def split_relation(
    name: str,
    current_user: User = Depends(get_current_active_session),
) -> Response:
    """Split one merged-away relationship back out (idempotent)."""
    try:
        await RelationsService(current_user.id).split_relation(name)
    except ValueError as exc:
        raise_invalid_input(str(exc))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/overview-scope",
    response_model=RelationOverviewScope,
    summary="What my 360° point is allowed to read",
    description=(
        "Pre-fills the selector on a relationship card. Absent = the defaults "
        "(every section, both directions, both roles, five items)."
    ),
)
async def get_overview_scope(
    current_user: User = Depends(get_current_active_session),
) -> RelationOverviewScope:
    """Read the caller's 360° scope (defaults when never saved)."""
    return await RelationsService(current_user.id).get_overview_scope()


@router.put(
    "/overview-scope",
    response_model=RelationOverviewScope,
    summary="Set what my 360° point reads",
    description=(
        "Written BEFORE the chat link opens: the request itself carries only "
        "prose, so this is what makes the reader's selection a guarantee "
        "rather than a hint the planner may or may not honor. It also becomes "
        "the pre-filled default next time."
    ),
)
async def set_overview_scope(
    payload: RelationOverviewScope,
    current_user: User = Depends(get_current_active_session),
) -> RelationOverviewScope:
    """Persist the caller's 360° scope and echo it back."""
    await RelationsService(current_user.id).set_overview_scope(payload)
    return payload


@router.get(
    "",
    response_model=RelationsOverview,
    summary="Personal CRM overview — relationships ranked by recent interaction",
)
async def get_relations_overview(
    current_user: User = Depends(get_current_active_session),
) -> RelationsOverview:
    """Aggregate open loops + calls into a ranked list of relationships."""
    return await RelationsService(current_user.id).build_overview()


@router.get(
    "/{name}/context",
    response_model=RelationContext,
    summary="Provider-backed sections of a relationship (contact, mail, meetings)",
    description=(
        "Contact card, mail exchanged and meetings shared with this person. "
        "SEPARATE from the 360° detail on purpose: it reaches the connectors, "
        "so it is slower and may fail per section — the detail must never wait "
        "for it. Each section carries its own status and no count (a provider "
        "page cannot prove a total). Rate limited per user: this spends "
        "external API quota, which the per-name cache cannot bound."
    ),
    dependencies=[Depends(rate_limit_relation_context)],
)
async def get_relation_context(
    name: str,
    refresh: str | None = Query(
        default=None,
        description=(
            "Comma-separated sections whose cache must be bypassed "
            "(contact, emails, events). Unknown names are ignored — a stale "
            "client must never turn a read into an error."
        ),
    ),
    current_user: User = Depends(get_current_active_session),
) -> RelationContext:
    """The provider half of the 360° view, section by section."""
    forced = frozenset(part.strip() for part in (refresh or "").split(",") if part.strip())
    return await RelationContextService(current_user.id).build(name, refresh=forced)


@router.get(
    "/{name}",
    response_model=RelationDetail,
    summary="360° view of one relationship (open loops, calls, memories)",
)
async def get_relation_detail(
    name: str,
    current_user: User = Depends(get_current_active_session),
) -> RelationDetail:
    """The full picture of one person, resolved by best-effort name match."""
    return await RelationsService(current_user.id).build_detail(name)
