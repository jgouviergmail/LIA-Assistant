"""A document's pictures: how many it may carry, and what a drawn one is (ADR-274).

Light on purpose — the renderers' context imports it, and a renderer must not
pull the image vendors' clients in to know what a picture is. The production of
pictures lives in ``illustrations.py``; this module holds the ONE answer to
« how many pictures may this document carry? », read by the normalization that
enforces it and by the prompt that publishes it (ADR-184).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.config import settings
from src.core.document_preferences import DocumentPreferences


@dataclass(frozen=True, slots=True)
class Frame:
    """Where a picture goes, named: its proportions decide the picture's.

    Attributes:
        name: The frame's name, part of the picture's key.
        width_in: Its width in inches.
        height_in: Its height in inches.
    """

    name: str
    width_in: float
    height_in: float

    @property
    def aspect(self) -> float:
        """Width divided by height."""
        return self.width_in / self.height_in


def picture_key(frame: str, subject: str) -> str:
    """The key a drawn picture is found under: one subject drawn for one frame."""
    return f"{frame}:{subject}"


@dataclass(frozen=True, slots=True)
class IllustrationRequest:
    """One picture to draw: what it shows and the frame it fills.

    Attributes:
        subject: The scene, in English, as the writer described it.
        frame: The frame it fills.
    """

    subject: str
    frame: Frame

    @property
    def key(self) -> str:
        """Where the renderer looks the drawn picture up."""
        return picture_key(self.frame.name, self.subject)


@dataclass(frozen=True, slots=True)
class Picture:
    """A drawn illustration, ready to be placed.

    Attributes:
        data: The picture, JPEG-encoded, cropped and resampled to its frame.
        width_px: Its width in pixels.
        height_px: Its height in pixels.
    """

    data: bytes
    width_px: int
    height_px: int


def illustration_budget(preferences: DocumentPreferences) -> int:
    """How many pictures a document of this person may carry.

    Args:
        preferences: The person's document preferences.

    Returns:
        The instance's cap when the person illustrates (images on, not « never »),
        else 0 — which strips every picture the writer asked for.
    """
    return settings.document_illustrations_max if preferences.illustrates else 0


__all__ = ["Frame", "IllustrationRequest", "Picture", "illustration_budget", "picture_key"]
