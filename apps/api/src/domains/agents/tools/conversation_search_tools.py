"""Conversation search tool — what was SAID, word for word, in any discussion.

Long-term memory (ADR-313) holds what LIA DISTILLED from past conversations; this
lookup returns what was said, verbatim, in every discussion of the account, through
the door the history search field asks too (``conversations.discussion_search``).
No model call: the passages are the real messages, cut around the words.

Read-only, no HITL, no OAuth — the discussions belong to the person. The run's own
question is left out: it is archived before the run (ADR-117) and would be its first
match. The messages are technical English the model rewords (ADR-256).
"""

from __future__ import annotations

from datetime import tzinfo
from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg

from src.core.config import settings
from src.core.constants import (
    CONVERSATION_SEARCH_EXCERPT_CHARS,
    CONVERSATION_SEARCH_MAX_LENGTH,
    CONVERSATION_SEARCH_MIN_LENGTH,
)
from src.core.conversation_target import ConversationKind
from src.core.run_config import run_id_of
from src.core.time_utils import resolve_user_timezone
from src.domains.agents.constants import AGENT_MEMORY
from src.domains.agents.context.runtime_context import LiaRuntimeContext, tool_runtime_context
from src.domains.agents.display.plain_text import markdown_to_plain_text
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.decorators import read_tool
from src.domains.agents.tools.lookup_parameters import bounded_count
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.runtime_helpers import validate_runtime_config
from src.domains.conversations.discussion_search import DiscussionHit, search_discussions
from src.domains.shared.text_normalization import normalize_search_text
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)

_ELLIPSIS = "…"


def _match_start(text: str, needle: str) -> int | None:
    """Where the words begin in ``text``, read as the history search reads them.

    The text is folded character by character, each folded character remembering
    the original one it came from, so a match found in the folded text points
    back into the text itself — whatever folding changed in its length.
    """
    folded_needle = normalize_search_text(needle)
    if not folded_needle:
        return None
    folded: list[str] = []
    origin: list[int] = []
    for index, char in enumerate(text):
        for part in normalize_search_text(char):
            folded.append(part)
            origin.append(index)
    at = "".join(folded).find(folded_needle)
    return origin[at] if at >= 0 else None


def passage_excerpt(
    content: str, needle: str, width: int = CONVERSATION_SEARCH_EXCERPT_CHARS
) -> str:
    """A message as plain text, cut to ``width`` characters around the words.

    Args:
        content: The message as stored (Markdown, or the HTML of a card).
        needle: The words searched.
        width: Characters kept, ellipses aside.

    Returns:
        The whole message when it fits; otherwise the window around the first
        place the words appear, or its beginning when they cannot be located in
        the flattened text (a match inside markup).
    """
    text = " ".join(markdown_to_plain_text(content).split())
    if len(text) <= width:
        return text
    start = _match_start(text, needle)
    if start is None:
        return text[: width - 1] + _ELLIPSIS
    begin = max(0, min(start - max(0, (width - len(needle)) // 2), len(text) - width))
    end = begin + width
    return (_ELLIPSIS if begin else "") + text[begin:end] + (_ELLIPSIS if end < len(text) else "")


def _passage(hit: DiscussionHit, needle: str, zone: tzinfo) -> dict[str, str]:
    """One message as the model reads it."""
    secondary = hit.conversation_kind is ConversationKind.SECONDARY
    return {
        "discussion": (hit.conversation_title or "secondary") if secondary else "main",
        "said_by": "person" if hit.role == "user" else "assistant",
        "said_at": hit.created_at.astimezone(zone).isoformat(timespec="minutes"),
        "excerpt": passage_excerpt(hit.content, needle),
    }


@read_tool(name="search_conversations", agent_name=AGENT_MEMORY)
async def search_conversations_tool(
    query: Annotated[
        str,
        "Words the message contains, as they were written (case and accents do not matter).",
    ],
    runtime: Annotated[ToolRuntime[LiaRuntimeContext, Any], InjectedToolArg],
    max_results: Annotated[int | None, "Most passages to return (default: the maximum)."] = None,
) -> UnifiedToolOutput:
    """Find what was said in the user's past conversations, word for word.

    Args:
        query: The words to find.
        runtime: LangChain tool runtime (injected).
        max_results: Result ceiling, clamped to
            ``settings.conversation_search_tool_max_results``.

    Returns:
        UnifiedToolOutput with ``{passages: [...], count, more}``, newest first; a
        typed failure when the words are out of bounds.
    """
    config = validate_runtime_config(runtime, "search_conversations_tool")
    if isinstance(config, UnifiedToolOutput):
        return config
    needle = query.strip()
    if not CONVERSATION_SEARCH_MIN_LENGTH <= len(needle) <= CONVERSATION_SEARCH_MAX_LENGTH:
        return UnifiedToolOutput.failure(
            message=(
                f"Give the words to find, {CONVERSATION_SEARCH_MIN_LENGTH} to "
                f"{CONVERSATION_SEARCH_MAX_LENGTH} characters. Nothing was searched."
            ),
            error_code=ToolErrorCode.INVALID_INPUT.value,
        )

    limit = bounded_count(max_results, settings.conversation_search_tool_max_results)
    user_id = UUID(str(config.user_id))
    zone = resolve_user_timezone(tool_runtime_context(runtime))
    async with get_db_context() as db:
        page = await search_discussions(
            db, user_id, needle, limit=limit, excluding_run=run_id_of(runtime.config) or None
        )
    passages = [_passage(hit, needle, zone) for hit in page.hits]
    # Counts only: the words and the messages are the person's.
    logger.info(
        "conversation_search_tool_completed",
        user_id=str(user_id),
        found=len(passages),
        more=page.has_more,
        limit=limit,
    )
    if not passages:
        message = "No message of the past discussions contains these words."
    else:
        message = f"{len(passages)} past message(s) contain these words, newest first." + (
            " More, older ones exist: narrow the words to reach them." if page.has_more else ""
        )
    return UnifiedToolOutput.data_success(
        message=message,
        structured_data={"passages": passages, "count": len(passages), "more": page.has_more},
    )


__all__ = ["passage_excerpt", "search_conversations_tool"]
