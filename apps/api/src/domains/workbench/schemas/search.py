"""What one search across the tools takes and answers (ADR-369, lot 13)."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS


class SearchQuery(BaseModel):
    """The person's words."""

    model_config = ConfigDict(extra="forbid")

    q: Annotated[
        str,
        StringConstraints(
            strip_whitespace=True,
            min_length=1,
            max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS,
            pattern=r"^[^\x00-\x1f\x7f]+$",
        ),
    ] = Field(description="The words looked for.")


class SearchHit(BaseModel):
    """One thing found: what a person recognises, and how to open it."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="What its tool opens: a shortcut's target, not the shortcut.")
    title: str = Field(description="What it is called (may be empty at the provider).")
    subtitle: str | None = Field(default=None, description="Who or what it goes with.")
    mail_folder: str | None = Field(default=None, description="The place a message was found in.")
    calendar_id: str | None = Field(default=None, description="An event's calendar.")
    day: str | None = Field(default=None, description="An event's day, on the person's clock.")
    is_folder: bool = Field(default=False, description="What opens is a folder of the drive.")


class ToolHits(BaseModel):
    """What one tool found."""

    tool: str = Field(description="The tool.")
    hits: list[SearchHit] = Field(description="The first of what it found.")
    truncated: bool = Field(description="It holds more than these.")
    inbox_only: bool = Field(description="A mailbox searched from its inbox alone.")


class GlobalSearch(BaseModel):
    """What the tools found, and which of them could not say."""

    results: list[ToolHits] = Field(description="Each tool that answered, in the rail's order.")
    failed: list[str] = Field(description="The tools that could not answer, or only in part.")
