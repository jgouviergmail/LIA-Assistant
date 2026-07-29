"""Relations domain router (N-09) — read-only personal CRM.

Two GET endpoints, both aggregating existing DB-local signals:

- GET /relations          : the overview (people ranked by recent interaction)
- GET /relations/{name}   : the 360° view of one relationship

No write surface: the CRM is a lens over data other domains own. Acting on a
relationship happens in the chat (the frontend deep-links a prepared intent),
so nothing new to authorize here beyond the session.
"""

from fastapi import APIRouter, Depends

from src.core.session_dependencies import get_current_active_session
from src.domains.relations.schemas import RelationDetail, RelationsOverview
from src.domains.relations.service import RelationsService
from src.domains.users.models import User

router = APIRouter(prefix="/relations", tags=["relations"])


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
