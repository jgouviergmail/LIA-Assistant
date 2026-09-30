"""The routes the chat card of a skill proposal calls (ADR-327).

A skill written in the chat is only PROPOSED by the model; this card is where
the person reads it and installs it. Under the skills capability (a proposal
is a skill), per-account rate-limited, every refusal a stable code the card
translates (``proposal_errors``) and counted with its operation.

Mounted on its own prefix rather than under ``/skills``, whose ``/{name}/...``
routes a two-segment path could be read as.
"""

from __future__ import annotations

from typing import Final

from fastapi import APIRouter, Depends
from fastapi import Path as PathParam
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skills import proposal_service
from src.domains.skills.proposal_errors import ProposalRefusal, refuse
from src.domains.skills.proposal_schemas import SkillProposalResponse
from src.domains.users.models import User
from src.infrastructure.observability.metrics_registry import skill_proposals_total

router = APIRouter(
    prefix="/skill-proposals",
    tags=["Skill proposals"],
    dependencies=capability_dependencies(PlatformCapability.SKILLS),
)

# Read once at import, like every settings-driven module constant.
rate_limit_proposals = create_user_rate_limiter(
    "skill_proposals",
    max_calls=settings.skill_proposal_rate_limit_calls,
    window_seconds=settings.skill_proposal_rate_limit_window_seconds,
)

_OK: Final = "ok"

#: A proposal id is 32 hex characters (``uuid4().hex``): anything else is no id.
_PROPOSAL_ID = PathParam(..., pattern=r"^[0-9a-f]{32}$", description="The proposal's id.")


@router.get(
    "/{proposal_id}",
    response_model=SkillProposalResponse,
    dependencies=[Depends(rate_limit_proposals)],
    summary="Read a skill proposed in the chat",
    description="Refusals: `skill_proposal_not_found`, `skill_proposal_unavailable`.",
)
async def read_proposal(
    proposal_id: str = _PROPOSAL_ID,
    user: User = Depends(get_current_active_session),
) -> SkillProposalResponse:
    """The proposal with its files, for the card to show before the click."""
    try:
        proposal = await proposal_service.read(user.id, proposal_id)
    except ProposalRefusal as refusal:
        skill_proposals_total.labels(operation="read", outcome=refusal.code).inc()
        refuse(refusal)
    skill_proposals_total.labels(operation="read", outcome=_OK).inc()
    return SkillProposalResponse.of(proposal)


@router.post(
    "/{proposal_id}/install",
    response_model=SkillProposalResponse,
    dependencies=[Depends(rate_limit_proposals)],
    summary="Install a skill proposed in the chat",
    description=(
        "The person's act: installs exactly the proposed package. Installing an "
        "installed proposal answers it as installed. Refusals: "
        "`skill_proposal_disabled`, `skill_proposal_not_found`, `skill_proposal_busy`, "
        "`skill_proposal_stale`, `skill_proposal_name_taken`, "
        "`skill_proposal_quota_reached`, `skill_proposal_invalid`, "
        "`skill_proposal_unavailable`."
    ),
)
async def install_proposal(
    proposal_id: str = _PROPOSAL_ID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> SkillProposalResponse:
    """Install the proposal into the person's own skills."""
    try:
        installed = await proposal_service.install(db, user.id, proposal_id)
    except ProposalRefusal as refusal:
        skill_proposals_total.labels(operation="install", outcome=refusal.code).inc()
        refuse(refusal)
    skill_proposals_total.labels(operation="install", outcome=_OK).inc()
    return SkillProposalResponse.of(installed)
