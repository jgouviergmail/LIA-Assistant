"""What LIA reads of a message: what its reader shows (owner, 2026-11-14).

The Tools draw a message in its original layout when it has one (ADR-369, D3), and that is what the
person asks LIA about. So a model reads that layout through the reading door every mailbox uses
(``shown_words``, ADR-287 amendment 2026-11-15), whole — its quoted history and its signature
included, as the frame shows them — never the text part a sender wrote beside it, which can say
nothing of what the page shows. Measured in production on 2026-11-14: « make it an event » on HTML
mail read a nearly empty body and found nothing. A message with no HTML keeps the mailbox's text,
itself turned to text when it was markup sent as text.

The message's HTML is read whole here, its parts too large to travel inline included, which a
mailbox's normalisation cannot do; the door cuts it at its ceiling and runs off the event loop: a
mailer's HTML outweighs its words many times over, and parsing it would hold every stream of the
worker.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from src.domains.connectors.clients.normalizers.html_text import shown_words


class _HtmlReader(Protocol):
    """What the door needs of a mailbox: a message's HTML, or none."""

    async def get_message_html(self, message_id: str) -> str | None: ...


async def words_as_shown(client: _HtmlReader, message_id: str, text: str) -> str:
    """A message's words as its reader shows them.

    Args:
        client: The open mailbox.
        message_id: The message.
        text: Its text as the mailbox gave it.

    Returns:
        The text of its HTML when it has HTML holding words; else ``text``, turned to text when it
        is markup.
    """
    html = await client.get_message_html(message_id)
    return await asyncio.to_thread(shown_words, text, html)


__all__ = ["words_as_shown"]
