"""One discussion as a Markdown document its owner can keep.

The account archive already exports every conversation at once
(``account_export``); this is the same record for ONE discussion, on demand,
from the chat. Three properties, each a way the document could have been
quietly wrong:

- **complete, and closed.** The messages are read through a server-side cursor
  (``export_stream``, ADR-273) — no page, no ceiling, constant memory — and the
  read is closed at the instant the export was asked: a message that lands
  while the document streams belongs to the next export. No count is printed:
  a count shown to a reader is exact or it does not exist (ADR-185), and a
  discussion can be reset between a count and the read it would describe.
- **what the chat shows.** The statement is the history's own
  (``message_reads.discussion_transcript``): nothing hidden, no blank progress
  row.
- **the reader's language and clock**, from their account. The person's words
  are exported as typed; an answer LIA drew as an HTML document is exported as
  Markdown, through the one conversion door (``core.html_markdown``) the kept
  answers already use.

The session is opened HERE and belongs to this generator: the cursor detaches
each row once rendered, which a shared session's other users would not expect.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from src.core.conversation_target import ConversationRef
from src.core.html_markdown import as_markdown
from src.core.i18n_account_export import render_discussion_label, render_export_turn
from src.core.text_clip import one_line
from src.core.time_utils import format_datetime_for_display
from src.domains.conversations.message_reads import TRANSCRIPT_ORDER, discussion_transcript
from src.infrastructure.database.export_stream import stream_all
from src.infrastructure.database.session import get_db_context

#: The role whose words are LIA's own drawing, converted when it is an HTML
#: document. Every other role's words are exported as stored.
_ASSISTANT_ROLE = "assistant"


class TranscriptMessage(Protocol):
    """What the renderer reads on a message row."""

    role: str
    content: str
    created_at: datetime


def _stamp(instant: datetime, language: str, timezone: str) -> str:
    """An instant on the reader's clock, in the reader's language."""
    return format_datetime_for_display(
        instant, timezone, language, include_time=True, include_day_name=False
    )


def render_header(title: str, *, language: str, timezone: str, generated_at: datetime) -> str:
    """The document's opening: the discussion's name, and when it was exported.

    Args:
        title: The discussion's title, or Main's name in the reader's language.
        language: The reader's language.
        timezone: The reader's IANA zone.
        generated_at: The instant the export was asked (UTC).

    Returns:
        The heading and the dated line, ready to be followed by the messages.
    """
    exported = render_discussion_label("exported_on", language).format(
        date=_stamp(generated_at, language, timezone)
    )
    # A heading is one line, whatever the title holds.
    return f"# {one_line(title)}\n\n_{exported}_\n\n---\n\n"


def render_message(message: TranscriptMessage, *, language: str, timezone: str) -> str:
    """One message of the discussion: who spoke, when on the reader's clock, the words.

    Args:
        message: The row.
        language: The reader's language.
        timezone: The reader's IANA zone.

    Returns:
        The block the account archive writes for a message, closed by a rule.
    """
    stamp = _stamp(message.created_at, language, timezone)
    return render_export_turn(message.role, stamp, _words(message), language) + "\n"


def _words(message: TranscriptMessage) -> str:
    """What a message says, as the document writes it.

    The person's words are exported as typed. An answer is converted only when
    it is an HTML DOCUMENT — it opens on a tag, as the ``html`` display mode
    draws it. A Markdown answer that merely carries an HTML block is valid
    Markdown as it stands, and converting it would escape every mark of its
    prose and fold its paragraphs. Measured on a development base, 2026-11-12:
    of 2 184 visible answers, 2 161 hold no tag, 12 open on one, 5 carry a
    block inside Markdown.

    Args:
        message: The row.

    Returns:
        The words, in Markdown.
    """
    if message.role != _ASSISTANT_ROLE or not message.content.lstrip().startswith("<"):
        return message.content
    return as_markdown(message.content).strip()


async def stream_discussion_markdown(
    target: ConversationRef,
    *,
    title: str,
    language: str,
    timezone: str,
    generated_at: datetime,
    batch: int,
) -> AsyncIterator[str]:
    """Render one discussion, reading it as it is written out.

    Args:
        target: The discussion its owner asked for, already resolved and owned.
        title: Its title, or Main's name in the reader's language.
        language: The reader's language.
        timezone: The reader's IANA zone.
        generated_at: The instant the export was asked: the read's upper bound.
        batch: How many rows the cursor buffers at a time.

    Yields:
        The document, chunk by chunk: its header, then every message the chat
        shows, oldest first.
    """
    yield render_header(title, language=language, timezone=timezone, generated_at=generated_at)
    empty = True
    async with get_db_context() as db:
        async for message in stream_all(
            db,
            discussion_transcript(target.id, generated_at),
            oldest_first=TRANSCRIPT_ORDER,
            batch=batch,
        ):
            empty = False
            yield render_message(message, language=language, timezone=timezone)
    if empty:
        yield f"_{render_discussion_label('empty', language)}_\n"
