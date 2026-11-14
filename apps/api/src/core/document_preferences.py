"""How a person wants LIA's generated documents made — two choices on the account.

The document tool reads both at every generation:

- **illustrations** — ``auto`` lets the writer judge whether a picture serves the
  document (a short note needs none, a deck to present may open each part on
  one), ``on_request`` draws one only where the request asks for it, ``never``
  draws none. Every illustration is an image generation, billed to the turn: the
  choice is the person's because the spend is.
- **animations** — ``presented`` animates a deck the writer says will be
  presented (transitions, items revealed one by one) and leaves a deck meant to
  be read as it is; ``always`` animates every deck; ``never`` none.

The defaults are the owner's (2026-11-13): illustrations ``auto``, animations
``presented``. A stored value is read through ``illustrations_of`` and
``animations_of``, the one door that turns an unknown value into the default
rather than an error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DocumentIllustrations(StrEnum):
    """Whether LIA illustrates the documents it generates."""

    AUTO = "auto"
    ON_REQUEST = "on_request"
    NEVER = "never"


class DocumentAnimations(StrEnum):
    """Whether LIA animates the decks it generates."""

    PRESENTED = "presented"
    ALWAYS = "always"
    NEVER = "never"


DOCUMENT_ILLUSTRATIONS_DEFAULT = DocumentIllustrations.AUTO
DOCUMENT_ANIMATIONS_DEFAULT = DocumentAnimations.PRESENTED


def illustrations_of(value: str | None) -> DocumentIllustrations:
    """The stored illustrations choice, the default when absent or unknown."""
    try:
        return DocumentIllustrations(value) if value else DOCUMENT_ILLUSTRATIONS_DEFAULT
    except ValueError:
        return DOCUMENT_ILLUSTRATIONS_DEFAULT


def animations_of(value: str | None) -> DocumentAnimations:
    """The stored animations choice, the default when absent or unknown."""
    try:
        return DocumentAnimations(value) if value else DOCUMENT_ANIMATIONS_DEFAULT
    except ValueError:
        return DOCUMENT_ANIMATIONS_DEFAULT


@dataclass(frozen=True, slots=True)
class DocumentPreferences:
    """What one person asked of their documents, read once per generation.

    Attributes:
        illustrations: Whether LIA illustrates the document.
        animations: Whether LIA animates a deck.
        images_allowed: Whether the person may generate images at all — their
            own opt-in and the operator's switch; an illustration is an image.
        image_quality: The person's stored image quality, an INTENT the image
            domain maps onto what the configured model offers (ADR-305).
        image_size: The person's stored image size, whose billing tier an
            illustration keeps while its frame decides the proportions.
    """

    illustrations: DocumentIllustrations = DOCUMENT_ILLUSTRATIONS_DEFAULT
    animations: DocumentAnimations = DOCUMENT_ANIMATIONS_DEFAULT
    images_allowed: bool = False
    image_quality: str | None = None
    image_size: str | None = None

    @property
    def illustrates(self) -> bool:
        """Whether a document may carry pictures: the person did not say never, images can be made."""
        return self.images_allowed and self.illustrations is not DocumentIllustrations.NEVER


def document_preferences(
    *,
    illustrations: str | None,
    animations: str | None,
    images_allowed: bool,
    image_quality: str | None = None,
    image_size: str | None = None,
) -> DocumentPreferences:
    """The preferences of an account, its stored values read through the one door."""
    return DocumentPreferences(
        illustrations=illustrations_of(illustrations),
        animations=animations_of(animations),
        images_allowed=images_allowed,
        image_quality=image_quality,
        image_size=image_size,
    )


__all__ = [
    "DOCUMENT_ANIMATIONS_DEFAULT",
    "DOCUMENT_ILLUSTRATIONS_DEFAULT",
    "DocumentAnimations",
    "DocumentIllustrations",
    "DocumentPreferences",
    "document_preferences",
    "animations_of",
    "illustrations_of",
]
