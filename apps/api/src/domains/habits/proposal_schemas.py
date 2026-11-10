"""API schemas of the habit proposals (ADR-375).

A proposal travels as FACTS (``proposal_facts``): the card phrases them in the
person's language, so no sentence is stored or sent. A decision answers with
the routine an accepted proposal created, moved or opens, for the card to link.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.domains.habits.models import HabitProposal, ProposalKind, ProposalStatus
from src.domains.habits.proposal_facts import FACTS_BY_KIND, ProposalFacts


class HabitProposalResponse(BaseModel):
    """One open proposal, as the card reads it."""

    id: UUID = Field(description="The proposal's id.")
    kind: ProposalKind = Field(description="What it offers.")
    key: str = Field(description="Its identity within the kind (a domain, a routine id, ...).")
    facts: ProposalFacts = Field(description="The facts the card phrases and the act reads.")
    created_at: datetime = Field(description="When LIA first proposed it.")
    updated_at: datetime = Field(description="When its facts last changed.")

    @classmethod
    def from_row(cls, row: HabitProposal) -> HabitProposalResponse:
        """Project a stored proposal, its facts read back by its kind's model.

        Args:
            row: The stored proposal.

        Returns:
            The response.
        """
        kind = ProposalKind(row.kind)
        return cls(
            id=row.id,
            kind=kind,
            key=row.key,
            facts=FACTS_BY_KIND[kind].model_validate(row.payload),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


class HabitProposalsPage(BaseModel):
    """One page of the person's open proposals and the exact total (ADR-185)."""

    proposals: list[HabitProposalResponse] = Field(description="The page, newest first.")
    total: int = Field(ge=0, description="Every open proposal, beyond the page too.")
    learning_enabled: bool = Field(
        description=(
            "False when habit learning is off for this person or this instance: "
            "nothing is served then, which is not « nothing to propose »."
        )
    )


class HabitProposalDecisionResponse(BaseModel):
    """What a decision recorded."""

    id: UUID = Field(description="The proposal decided.")
    kind: ProposalKind = Field(description="Its kind.")
    status: ProposalStatus = Field(description="Its new status.")
    routine_id: UUID | None = Field(
        default=None, description="The routine an accepted proposal created, moved or opens."
    )
