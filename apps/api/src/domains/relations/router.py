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
catch-all so the literal segment wins.
"""

from fastapi import APIRouter, Depends, Response, status

from src.core.session_dependencies import get_current_active_session
from src.domains.relations.schemas import RelationDetail, RelationsOverview
from src.domains.relations.service import RelationsService
from src.domains.users.models import User

router = APIRouter(prefix="/relations", tags=["relations"])


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
