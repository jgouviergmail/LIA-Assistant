"""The page a mode works from, found in the conversation (ADR-370).

« Change the background », « can you display it? », « show me the code »: each
speaks of something LIA already answered. It lives with its message, never in the
registry channel of the graph state, which is capped and evicts in silence (see
``data_registry/message_widgets``). So the source is read back from the messages,
newest first: a page, or the HTML code of an answer. A person's own words are not
searched: pasted code reaches the tool through ``source_data``, and a page must
never be run out of a text nobody asked to run.
"""

from __future__ import annotations

import html
import re
from collections.abc import Iterator, Mapping
from typing import Any, Final

from src.core.config import settings
from src.domains.agents.data_registry.message_widgets import MESSAGE_METADATA_WIDGETS_KEY
from src.domains.agents.data_registry.models import RegistryItemType
from src.domains.attachments.thread_id import conversation_uuid
from src.domains.conversations.repository import ConversationRepository
from src.domains.interactive_pages.document import source_of
from src.domains.interactive_pages.schemas import PageMode, PageSource
from src.infrastructure.database.session import get_db_context

_ASSISTANT_ROLE: Final = "assistant"
#: Modes that show what is handed over, ahead of what the conversation holds.
_SHOWING_MODES: Final = frozenset({PageMode.SHOW, PageMode.CODE})

_HTML_CODE_OPEN: Final = re.compile(
    r"<pre\b[^<>]*>\s*<code\b[^<>]*\blanguage-html\b[^<>]*>", re.IGNORECASE
)
_HTML_CODE_CLOSE: Final = "</code>"
_HTML_FENCE_OPEN: Final = re.compile(r"^ {0,3}(`{3,}|~{3,})[ \t]*html[ \t]*$", re.IGNORECASE | re.M)
_TITLE: Final = re.compile(r"<title\b[^<>]*>([^<]*)</title\s*>", re.IGNORECASE)


def _answer_blocks(content: str) -> Iterator[str]:
    """The HTML code blocks of an HTML answer, decoded back to what was written."""
    for opening in _HTML_CODE_OPEN.finditer(content):
        end = content.find(_HTML_CODE_CLOSE, opening.end())
        if end < 0:
            return
        yield html.unescape(content[opening.end() : end]).removesuffix("\n")


def _fenced_blocks(content: str) -> Iterator[str]:
    """The ```` ```html ```` blocks of a Markdown answer."""
    for opening in _HTML_FENCE_OPEN.finditer(content):
        closing = re.compile(rf"^ {{0,3}}{re.escape(opening.group(1))}[ \t]*$", re.M)
        end = closing.search(content, opening.end())
        if end is None:
            return
        yield content[opening.end() : end.start()].strip("\n")


def html_code_of(content: str) -> str | None:
    """The page an answer shows as code.

    Args:
        content: An assistant message.

    Returns:
        Its longest HTML block, the page rather than a snippet beside it, or
        ``None`` when it holds none.
    """
    blocks = [*_answer_blocks(content), *_fenced_blocks(content)]
    return max(blocks, key=len, default=None)


def title_of(page: str) -> str:
    """The title a page gives itself.

    Args:
        page: The page as written.

    Returns:
        Its ``<title>``, decoded, or an empty string.
    """
    found = _TITLE.search(page)
    return html.unescape(found.group(1)).strip() if found else ""


def page_of_metadata(metadata: Mapping[str, Any] | None) -> PageSource | None:
    """The page a message carries as a widget.

    Args:
        metadata: The message's ``message_metadata``.

    Returns:
        The page as written, without the policy composed around it, or ``None``.
    """
    widgets = (metadata or {}).get(MESSAGE_METADATA_WIDGETS_KEY)
    if not isinstance(widgets, dict):
        return None
    for item in widgets.values():
        if not isinstance(item, dict) or item.get("type") != RegistryItemType.PAGE_APP.value:
            continue
        payload = item.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("html_content"), str):
            continue
        offset = payload.get("source_offset")
        return PageSource(
            html=source_of(payload["html_content"], offset if isinstance(offset, int) else 0),
            title=str(payload.get("title") or ""),
        )
    return None


def _page_of_message(content: str, metadata: Mapping[str, Any] | None) -> PageSource | None:
    """What one answer holds: its page, else the HTML code it shows."""
    page = page_of_metadata(metadata)
    if page is not None:
        return page
    code = html_code_of(content)
    return PageSource(html=code, title=title_of(code)) if code else None


async def find_page_source(conversation_id: str) -> PageSource | None:
    """The latest page or HTML code LIA answered in a conversation.

    The session ends here: the writer's call that follows holds none (ADR-304).

    Args:
        conversation_id: The conversation of the run.

    Returns:
        The newest page or code among the recent messages, or ``None``.
    """
    conversation = conversation_uuid(conversation_id)
    if conversation is None:
        return None
    async with get_db_context() as db:
        rows = await ConversationRepository(db).get_messages_for_conversation(
            conversation,
            limit=settings.interactive_page_source_lookback_messages,
            order_desc=True,
        )
        answers = [
            (row.content, row.message_metadata) for row in rows if row.role == _ASSISTANT_ROLE
        ]
    for content, metadata in answers:
        page = _page_of_message(content, metadata)
        if page is not None:
            return page
    return None


async def resolve_page_base(
    mode: PageMode, source_data: str, conversation_id: str
) -> PageSource | None:
    """The existing page a call works from.

    Args:
        mode: What is asked.
        source_data: What the caller handed over.
        conversation_id: The conversation of the run.

    Returns:
        ``None`` for a new page. Otherwise code handed over wins for what is only
        shown, and a revision starts from the conversation, or from what was
        handed over when the conversation holds no page.
    """
    if mode is PageMode.CREATE:
        return None
    handed_over = (
        PageSource(html=source_data, title=title_of(source_data)) if source_data.strip() else None
    )
    if mode in _SHOWING_MODES and handed_over is not None:
        return handed_over
    return await find_page_source(conversation_id) or handed_over
