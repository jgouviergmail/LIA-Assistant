"""The images a message carries inside itself: one rule for every provider (ADR-369, lot 3).

What the HTML names ``cid:`` is the message's own part, so showing it tells a sender
nothing and asks no click. It reaches the frame as a ``data:`` address, the one image
source its policy opens without one. Only a type a frame draws is kept, never an SVG.
Each image, the sum and their number are bounded, and what was left out is counted
for the page to say (ADR-185). Each provider walks its own shape of the part tree
under this rule; ``InlineBudget`` is the one place that decides.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from typing import Final

#: The types a sandboxed frame draws as an image; an SVG is a document, and is left out.
_DRAWN_TYPES: Final = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_TYPE_ALIASES: Final = {"image/jpg": "image/jpeg"}


@dataclass(frozen=True)
class InlineImage:
    """One image of a message, as the frame draws it."""

    cid: str
    data_url: str


def content_id_of(header: str | None) -> str | None:
    """A part's ``Content-ID`` without its angle brackets; None when it has none."""
    return (header or "").strip().strip("<>").strip() or None


def usable_image_type(mime_type: str) -> str | None:
    """The type a frame draws this as, its parameters left out; None when it draws none."""
    bare = mime_type.split(";", 1)[0].strip().lower()
    named = _TYPE_ALIASES.get(bare, bare)
    return named if named in _DRAWN_TYPES else None


@dataclass
class InlineBudget:
    """What one message may carry to the frame."""

    each_max: int
    total_max: int
    count_max: int
    images: list[InlineImage] = field(default_factory=list)
    skipped: int = 0
    _total: int = 0

    def _fits(self, size: int) -> bool:
        return (
            size <= self.each_max
            and self._total + size <= self.total_max
            and len(self.images) < self.count_max
        )

    def worth_reading(self, size: int | None) -> bool:
        """Whether a part is worth its read; one past the bound is counted, unread.

        Args:
            size: Its size as the provider lists it, None when it does not say.
        """
        if self._fits(size or 0):
            return True
        self.skipped += 1
        return False

    def admit(self, cid: str, mime_type: str, data: bytes) -> bool:
        """Keep an image read; what is not kept is counted.

        Returns:
            Whether it was kept.
        """
        drawn = usable_image_type(mime_type)
        if drawn is None or not self._fits(len(data)):
            self.skipped += 1
            return False
        self._total += len(data)
        encoded = base64.b64encode(data).decode("ascii")
        self.images.append(InlineImage(cid=cid, data_url=f"data:{drawn};base64,{encoded}"))
        return True
