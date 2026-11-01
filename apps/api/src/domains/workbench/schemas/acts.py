"""What an act on a selection answers — messages, Drive files (ADR-369).

Never all-or-nothing: each item is done, or said with why — gone since it was
listed, refused for it alone, or never answered because the provider stopped
mid-way.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: What became of an item an act could not do: gone since it was listed,
#: refused for it alone, or never answered (the provider stopped mid-way).
ActStatus = Literal["not_found", "failed", "unavailable"]


class ActFailure(BaseModel):
    """One item an act could not do, and why."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="The item.")
    status: ActStatus = Field(description="Why it was not done.")


class ActOutcome(BaseModel):
    """What an act on a selection did — never all-or-nothing."""

    done: list[str] = Field(description="The items done, in the selection's order.")
    failed: list[ActFailure] = Field(description="The others, each with why.")
