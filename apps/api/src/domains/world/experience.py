"""Private, finite World presentation preferences, independent of home and avatar.

The stored document is exactly ``{version, revision, show_route, season_mode,
hemisphere}``. The retired introduction left no field behind: a document still
carrying one is unsupported and reads as needing the explicit repair.
"""

from typing import Literal

from pydantic import Field, model_validator

from src.domains.world.wire_models import StrictModel, VersionedModel


class ExperienceLayout(VersionedModel):
    show_route: bool = Field(
        default=True, description="Display the current walking route; never changes navigation."
    )
    season_mode: Literal["off", "calendar", "spring", "summer", "autumn", "winter"] = Field(
        default="calendar",
        description="Cosmetic season selection; calendar follows the owner's civil date.",
    )
    hemisphere: Literal["north", "south"] = Field(
        default="north", description="Hemisphere used only to resolve the calendar season."
    )


class ExperiencePreferences(ExperienceLayout):
    revision: int = Field(
        default=0,
        ge=0,
        le=2**31 - 1,
        description="Monotonic revision fencing concurrent owner preference edits.",
    )


class ExperienceUpdate(ExperienceLayout):
    expected_revision: int = Field(
        ge=0,
        le=2**31 - 2,
        description="Previously read revision required for an atomic owner edit.",
    )
    reset: bool = Field(
        default=False, description="Explicitly replace unreadable storage with supported defaults."
    )

    @model_validator(mode="after")
    def reset_is_explicit(self) -> ExperienceUpdate:
        """Refuse mixing repair with edits that would otherwise be silently discarded."""
        if self.reset and self.model_fields_set - {"version", "expected_revision", "reset"}:
            raise ValueError("experience_reset_cannot_include_edits")
        return self


class ExperienceView(StrictModel):
    owner_id: str = Field(
        description="Authenticated owner of this private document, never a caller-selected account."
    )
    preferences: ExperiencePreferences = Field(
        description="Owner-only preferences and their optimistic concurrency revision."
    )
    needs_reset: bool = Field(
        default=False,
        description="Stored preferences are unsupported and must be explicitly repaired before editing.",
    )


def read_experience_preferences(raw: object) -> tuple[ExperiencePreferences, bool]:
    """Return supported preferences without rewriting absent or unreadable storage.

    Args:
        raw: The stored JSON document, or None when never saved.

    Returns:
        The supported preferences (defaults when absent or unreadable) and whether
        the stored document needs the explicit repair.
    """
    if raw is None:
        return ExperiencePreferences(), False
    try:
        return ExperiencePreferences.model_validate(raw), False
    except ValueError:
        return ExperiencePreferences(), True
