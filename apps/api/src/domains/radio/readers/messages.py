"""What the radio's readers share about an archived message: its columns and a quotation.

A quotation is the beginning of what was written, flattened to plain words (an
archived message is Markdown or HTML) and cut at a word, never mid-word.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Final, Protocol
from uuid import UUID

from src.domains.agents.display.plain_text import markdown_to_plain_text

#: The longest quotation of a message a fact carries.
EXCERPT_MAX_CHARS: Final[int] = 300


class MessageRow(Protocol):
    """The columns of an archived message the radio reads."""

    @property
    def id(self) -> UUID: ...

    @property
    def role(self) -> str: ...

    @property
    def content(self) -> str: ...

    @property
    def message_metadata(self) -> dict[str, Any] | None: ...

    @property
    def created_at(self) -> datetime: ...


def excerpt(text: str) -> str:
    """The beginning of a message in plain words, cut at a word (empty when it says nothing)."""
    words = " ".join(markdown_to_plain_text(text).split())
    if len(words) <= EXCERPT_MAX_CHARS:
        return words
    return words[: EXCERPT_MAX_CHARS - 1].rsplit(" ", 1)[0] + "…"


__all__ = ["EXCERPT_MAX_CHARS", "MessageRow", "excerpt"]
