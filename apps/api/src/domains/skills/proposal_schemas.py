"""What the chat card reads of a skill proposal (ADR-327)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from src.domains.skills.proposals import SkillProposal


class SkillProposalFile(BaseModel):
    """One file of the package — its content only while it may still be installed."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="Relative path inside the skill folder.")
    size: int = Field(..., ge=0, description="UTF-8 size in bytes.")
    content: str | None = Field(
        None, description="The file's text while the proposal is pending; null once installed."
    )


class SkillProposalChanges(BaseModel):
    """What a replacement does to the person's installed skill."""

    model_config = ConfigDict(frozen=True)

    added: list[str] = Field(..., description="Files the installed skill does not have.")
    modified: list[str] = Field(..., description="Files whose text differs.")
    removed: list[str] = Field(..., description="Text files whose content the install loses.")


class SkillProposalResponse(BaseModel):
    """A skill written in the chat, as its card shows it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(..., description="The proposal's id.")
    status: Literal["pending", "installed"] = Field(
        ..., description="pending until the person installs it."
    )
    name: str = Field(..., description="The skill's name.")
    description: str = Field(..., description="The skill's description.")
    replaces: bool = Field(..., description="Whether it replaces a skill of the person's own.")
    files: list[SkillProposalFile] = Field(..., description="The package, manifest first.")
    changes: SkillProposalChanges | None = Field(
        None, description="What a replacement changes; null for a new skill."
    )
    expires_at: str = Field(..., description="ISO-8601 UTC instant it can no longer be installed.")

    @classmethod
    def of(cls, proposal: SkillProposal) -> SkillProposalResponse:
        """The response for one proposal — the card's own shape, plus the contents.

        Args:
            proposal: The stored proposal.

        Returns:
            The response.
        """
        card = proposal.to_card()
        return cls(
            id=card["id"],
            status=proposal.status,
            name=card["name"],
            description=card["description"],
            replaces=card["replaces"],
            files=[
                SkillProposalFile(
                    path=item["path"],
                    size=item["size"],
                    content=proposal.files.get(item["path"]),
                )
                for item in card["files"]
            ],
            changes=(None if card["changes"] is None else SkillProposalChanges(**card["changes"])),
            expires_at=card["expires_at"],
        )
