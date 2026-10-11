"""Explicit source explanation and live provenance perform no discovery or learning."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.interest_detail_schemas import (
    InterestDetailProjection,
    InterestDetailRead,
)
from src.domains.interests.explainability import explain_interest, get_owned_interest
from src.domains.interests.repository import InterestRepository
from src.domains.shared.provenance_repository import ProvenanceRepository
from src.domains.shared.schemas import ProvenanceResponse


async def read_interest_details(
    db: AsyncSession, actor_id: UUID, request: InterestDetailRead
) -> InterestDetailProjection:
    selected = InterestDetailRead.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    row = await get_owned_interest(db, actor_id, selected.interest_id)
    now = datetime.now(UTC)
    explanation = explain_interest(row, InterestRepository(db), now=now)
    references = await ProvenanceRepository(db).resolve_for(
        user_id=actor_id, interest_id=selected.interest_id
    )
    provenance = ProvenanceResponse.from_references(references)
    await require_application_tools(db)
    await load_actor(db, actor_id)
    return InterestDetailProjection(
        interest_id=selected.interest_id,
        observed_at=now,
        explanation=explanation,
        provenance=provenance,
    )
