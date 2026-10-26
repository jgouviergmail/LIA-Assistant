"""Bounded owner decoration; source text never enters a persisted home or snapshot."""

from typing import Literal

from pydantic import Field, model_validator

from src.domains.world.schemas import StrictModel, VersionedModel

HomeTone = Literal["sage", "teal", "clay", "violet", "amber", "cream"]
Palette = Literal["auto"] | HomeTone


class HomeLayout(VersionedModel):
    palette: Palette = Field(
        default="auto",
        description="Selected home colour palette; auto follows the account application theme.",
    )


class HomePreferences(HomeLayout):
    revision: int = Field(
        default=0,
        ge=0,
        le=2**31 - 1,
        description="Monotonic state or preference revision used to fence concurrent edits.",
    )


class HomeUpdate(HomeLayout):
    expected_revision: int = Field(
        ge=0,
        le=2**31 - 2,
        description="Previously read preference revision required for an atomic owner edit.",
    )
    reset: bool = Field(
        default=False,
        description="Explicitly request replacement of unreadable preferences through the declared repair path.",
    )

    @model_validator(mode="after")
    def reset_is_explicit(self) -> HomeUpdate:
        """Reject a reset mixed with palette edits so repair cannot silently discard an edit."""
        if self.reset and self.model_fields_set - {
            "version",
            "expected_revision",
            "reset",
        }:
            raise ValueError("home_reset_cannot_include_edits")
        return self


class DecoratedHome(StrictModel):
    automatic_palette: HomeTone = Field(
        description="Default home palette derived only from the native application colour theme."
    )
    palette: HomeTone = Field(
        description="Resolved owner home colour; auto has been replaced by the native theme colour."
    )


class HomeView(StrictModel):
    owner_id: str = Field(
        description="Authenticated owner of these private preferences; not a client-selected target."
    )
    preferences: HomePreferences = Field(
        description="Owner-only persisted preferences and their optimistic concurrency revision."
    )
    decoration: DecoratedHome = Field(
        description="Private resolved home colours; contains no learning sources or placements."
    )
    needs_reset: bool = Field(
        default=False,
        description="Saved preferences are unreadable and require explicit repair before replacement.",
    )


def read_home_preferences(raw: object) -> tuple[HomePreferences, bool]:
    """Read supported colours or return a repair flag without overwriting unreadable storage."""
    if raw is None:
        return HomePreferences(), False
    try:
        return HomePreferences.model_validate(raw), False
    except ValueError:
        # Preserve the stored document until an explicit reset; never write a
        # fallback over an unsupported/corrupt preference during a GET.
        return HomePreferences(), True


def project_home(preferences: HomePreferences, color_theme: str) -> DecoratedHome:
    """Resolve the owner palette from explicit preferences or the application theme."""
    themes: dict[str, HomeTone] = {
        "forest": "sage",
        "ocean": "teal",
        "sunset": "clay",
        "slate": "cream",
    }
    default = themes.get(color_theme, "clay")
    palette = default if preferences.palette == "auto" else preferences.palette
    return DecoratedHome(
        automatic_palette=default,
        palette=palette,
    )
