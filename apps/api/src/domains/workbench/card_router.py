"""Read-only admission of native Tools destinations carried by assistant cards."""

from typing import Annotated

from fastapi import APIRouter, Depends

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.workbench.card_opening import open_card_target
from src.domains.workbench.card_targets import CardTargetRequest, CardTargetResponse
from src.domains.workbench.rate_limits import rate_limit_read

router = APIRouter()


@router.post(
    "/card-target",
    response_model=CardTargetResponse,
    dependencies=[Depends(rate_limit_read)],
    summary="Revalidate the source of a native card before opening its record in Tools",
)
async def resolve_card_target(
    body: CardTargetRequest,
    user: Annotated[User, Depends(get_current_active_session_for_stream)],
) -> CardTargetResponse:
    """A navigation click grants no mutation and never redirects to a provider."""
    return await open_card_target(body.token, user.id)
