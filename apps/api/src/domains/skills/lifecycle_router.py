"""The settings routes of a skill's life (lot 14): answer the unused-skill proposal, go back a version.

Beside ``router.py``, under the same prefix and the same capability: the
listing that shows each skill's use and previous version stays there, the two
acts it offers live here. No route here reads as a route of the other: no
``POST /{skill_name}`` exists there to take ``dormant-decision`` for a skill's
name, and its only two-segment POST is the static ``/admin/import``, which
``/{skill_name}/restore-previous`` never spells.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import SKILLS_DORMANT_DECISION_MAX_IDS
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.skills.restore import restore_previous
from src.domains.skills.ui_projection import parsed_skill_metadata
from src.domains.skills.usage import DormantDecision, settle_dormant
from src.domains.users.models import User

router = APIRouter(
    prefix="/skills",
    tags=["Skills"],
    dependencies=capability_dependencies(PlatformCapability.SKILLS),
)


class SkillDormantDecisionRequest(BaseModel):
    """The person's answer to the dormant-skills proposal."""

    skill_ids: list[UUID] = Field(
        ...,
        min_length=1,
        max_length=SKILLS_DORMANT_DECISION_MAX_IDS,
        description="The skills the proposal showed; only those still dormant are settled",
    )
    decision: DormantDecision = Field(
        ..., description="switch_off: they leave the analyzer's list; keep: asked again in a period"
    )


@router.post(
    "/dormant-decision",
    summary="Answer the proposal to switch off unused skills",
    description=(
        "Switch off, or keep, the listed skills still unused for "
        "SKILLS_DORMANT_AFTER_DAYS; the verdict is taken again on the locked state."
    ),
)
async def settle_dormant_skills(
    body: SkillDormantDecisionRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Apply the person's answer to the shown skills that are still dormant.

    Args:
        body: The skills the proposal showed, and the answer.
        user: The person.
        db: The request's session.

    Returns:
        ``decision`` echoed, and ``settled``: the names the answer applied to.
    """
    settled = await settle_dormant(
        db,
        user.id,
        body.skill_ids,
        decision=body.decision,
        now=datetime.now(UTC),
        after_days=settings.skills_dormant_after_days,
    )
    await db.commit()
    return {"decision": body.decision.value, "settled": settled}


@router.post(
    "/{skill_name}/restore-previous",
    summary="Restore the previous version of a skill",
    description=(
        "Put back the version the last replacement of the person's own skill "
        "replaced; the replaced version becomes restorable in turn."
    ),
)
async def restore_previous_skill(
    skill_name: str,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Restore the previous version of the person's own skill.

    Args:
        skill_name: The skill, by name.
        user: The person.
        db: The request's session (the import pipeline commits).

    Returns:
        The restored skill (safe subset), as an import answers it.

    Raises:
        ResourceNotFoundError: Nothing the person may restore under that name.
    """
    skill = await restore_previous(db, user.id, skill_name)
    return parsed_skill_metadata(skill, "user")
