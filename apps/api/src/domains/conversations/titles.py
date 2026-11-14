"""Titles the server writes: Main's legacy default, and an annex's automatic one.

A discussion's role never depends on its title. An annex created without a
title waits for the person's first message and takes its title from it
(ADR-378 amendment 2026-11-12): :func:`derive_title` is that reading.
"""

from datetime import UTC, datetime

from src.core.constants import CONVERSATION_AUTO_TITLE_MAX_LENGTH
from src.core.i18n import resolve_language
from src.core.i18n_api_messages import APIMessages
from src.core.text_clip import clip_on_word, has_visible_text, one_line

#: PostgreSQL text cannot store it, and the catalogue's grammar refuses it.
_NUL = chr(0)


def default_conversation_title(language: str | None = None) -> str:
    """Render the existing date-based title in the account's declared language."""
    return APIMessages.conversation_default_title(
        datetime.now(UTC).date(), resolve_language(language)
    )


def derive_title(message: str) -> str | None:
    """The title a discussion takes from the first message its owner wrote.

    The first line that says something, on one line, cut on a word past
    ``CONVERSATION_AUTO_TITLE_MAX_LENGTH``. The person's own words, so they
    recognise the discussion in the list — and no model is called to produce
    it: a title costs nothing and is there before the answer.

    Args:
        message: The message as the person sent it.

    Returns:
        A title the catalogue's grammar accepts, or None when the message has
        nothing readable (the discussion then keeps waiting).
    """
    for line in message.replace(_NUL, "").splitlines():
        candidate = one_line(line)
        if has_visible_text(candidate):
            return clip_on_word(candidate, CONVERSATION_AUTO_TITLE_MAX_LENGTH)
    return None
