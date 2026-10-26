"""Declared public appearance; no inference, private profile or generated content."""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from src.core.i18n import _
from src.domains.world.wire_models import StrictModel, VersionedModel, explicit_consent

AvatarColor = Literal[
    "charcoal",
    "brown",
    "silver",
    "gold",
    "red",
    "green",
    "blue",
    "violet",
    "cream",
    "orange",
]
AvatarHair = Literal["bald", "short", "long", "curly", "ponytail", "mohawk"]
AvatarSkin = Literal["porcelain", "sand", "caramel", "walnut", "espresso"]


class AvatarAppearance(VersionedModel):
    model_config = ConfigDict(frozen=True)
    skin: AvatarSkin = Field(
        default="caramel",
        description="Explicit catalogue skin tone for the public avatar.",
    )
    hair: AvatarHair = Field(default="short", description="Selected catalogue hair silhouette.")
    hair_color: AvatarColor = Field(
        default="brown", description="Selected catalogue colour for the avatar hair."
    )
    outfit: Literal["casual", "suit", "dress"] = Field(
        default="casual", description="Selected catalogue outfit silhouette."
    )
    outfit_color: AvatarColor = Field(
        default="green", description="Selected catalogue colour for the avatar outfit."
    )
    headwear: Literal["none", "cap", "beanie", "hat"] = Field(
        default="none",
        description="Selected catalogue headwear, including the explicit none option.",
    )
    headwear_color: AvatarColor = Field(
        default="blue", description="Selected catalogue colour for the avatar headwear."
    )
    glasses: bool = Field(
        default=False,
        description="Explicit catalogue choice to display glasses on the public avatar.",
    )


class AvatarPreferences(VersionedModel):
    revision: int = Field(
        default=0,
        ge=0,
        le=2**53 - 1,
        description="Monotonic state or preference revision used to fence concurrent edits.",
    )
    appearance: AvatarAppearance = Field(
        default_factory=AvatarAppearance,
        description="Explicitly selected, catalogue-validated public avatar appearance.",
    )


class AvatarUpdate(StrictModel):
    expected_revision: int = Field(
        ge=0,
        description="Previously read preference revision required for an atomic owner edit.",
    )
    appearance: AvatarAppearance = Field(
        description="Explicitly selected, catalogue-validated public avatar appearance."
    )
    consent: Literal[True] = Field(
        description="Literal permission to publish the account name and selected avatar appearance."
    )
    reset: bool = Field(
        default=False,
        description="Explicitly request replacement of unreadable preferences through the declared repair path.",
    )

    @field_validator("consent", mode="before")
    @classmethod
    def require_consent(cls, value: object) -> object:
        """Reject coerced truthy values; public appearance requires literal consent."""
        return explicit_consent(value)


class AvatarView(StrictModel):
    owner_id: str = Field(
        description="Authenticated owner of these private preferences; not a client-selected target."
    )
    public_name: str = Field(
        min_length=1,
        max_length=24,
        description="Normalized account name or localized neutral fallback, bounded for Canvas labels.",
    )
    preferences: AvatarPreferences = Field(
        description="Owner-only persisted preferences and their optimistic concurrency revision."
    )
    needs_setup: bool = Field(
        description="Avatar preferences have not yet been explicitly published for World entry."
    )
    needs_reset: bool = Field(
        description="Saved preferences are unreadable and require explicit repair before replacement."
    )


def public_world_name(full_name: str | None, language: str | None = None) -> str:
    """Normalize the native account name for a public World label.

    Args:
        full_name: Native account name, never an email or inferred profile value.
        language: Account language for an empty-name fallback; otherwise the
            declared request language is resolved by the shared gettext path.

    Returns:
        NFC text with collapsed whitespace and no control/format characters,
        bounded to the public name contract, or a localized neutral fallback.
    """
    normalized = " ".join(unicodedata.normalize("NFC", full_name or "").split())
    clean = "".join(
        char for char in normalized if unicodedata.category(char) not in {"Cc", "Cf"}
    ).strip()
    # Preserve the existing bounded world-name contract, without editing LIA's name.
    return clean[:24].rstrip() or _("LIA explorer", language)


def read_avatar_preferences(raw: object) -> tuple[AvatarPreferences, bool]:
    """Read supported preferences or preserve only a valid revision for explicit repair."""
    if raw is None:
        return AvatarPreferences(), False
    try:
        return AvatarPreferences.model_validate(raw), False
    except ValueError:
        # Retain only a valid concurrency counter during explicit repair.
        revision = raw.get("revision") if isinstance(raw, dict) else None
        safe_revision = revision if type(revision) is int and 0 <= revision <= 2**53 - 1 else 0
        return AvatarPreferences(revision=safe_revision), True


@dataclass(frozen=True)
class PublicWorldIdentity:
    name: str
    appearance: AvatarAppearance
    revision: int = 0
