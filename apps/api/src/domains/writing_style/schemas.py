"""What the settings read of how the person writes (ADR-383)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WritingStyleResponse(BaseModel):
    """The person's writing style as LIA learned it, and their switch."""

    enabled: bool = Field(description="The person's switch: e-mails LIA writes follow the style")
    profile: str | None = Field(
        default=None,
        description="How the person writes, as learned from their sent mail; None: nothing learned",
    )
    mails_read: int | None = Field(
        default=None,
        description="How many sent e-mails it was learned from; None before any learning",
    )
    learned_at: datetime | None = Field(
        default=None, description="When it was learned (UTC); None before any learning"
    )
    renews_at: datetime | None = Field(
        default=None,
        description="From when the next e-mail LIA writes learns it again (UTC)",
    )


__all__ = ["WritingStyleResponse"]
