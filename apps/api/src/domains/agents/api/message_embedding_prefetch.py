"""The person's message embedding, computed while the turn prepares (latency lot 3).

The router's first readers, the response-context prefetch and the analyzer's
broad memory facts, both need the vector of the message the person sent, and
the analyzer cannot start before the facts. Computed at the router's entry, it
sat on the critical path of every turn (about 0.3 s on the production host). It
now starts as soon as the turn's state is prepared, overlapping the MCP
preparation and the stream's start; the router's readers find it cached, or
join its flight (``get_or_compute_embedding`` serves concurrent callers once).

The prefetch belongs to its turn. It is created inside the turn's tracking
scope, so its spend is the turn's, and that scope waits for it before closing:
a record arriving after the tracker filed would be a euro nobody counts.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from types import TracebackType
from typing import Any, Self

from langchain_core.messages import HumanMessage

from src.domains.agents.constants import STATE_KEY_MESSAGES
from src.infrastructure.llm.embedding_context import (
    clear_embedding_context,
    set_embedding_context,
)
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.user_message_embedding import get_or_compute_embedding


class MessageEmbeddingPrefetch:
    """One turn's early embedding of the person's message, as an async context manager."""

    def __init__(self) -> None:
        """Nothing runs until :meth:`start` names the message."""
        self._task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        """Enter the turn's scope.

        Returns:
            The prefetch, started later by :meth:`start`.
        """
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Wait for a prefetch still running: its spend must reach the tracker.

        Args:
            exc_type: The exception leaving the scope, if any.
            exc: Its value.
            traceback: Its traceback.
        """
        if self._task is not None and not self._task.done():
            await asyncio.gather(self._task, return_exceptions=True)

    def start(
        self,
        state: Mapping[str, Any],
        user_id: str,
        session_id: str,
        run_id: str,
        *,
        resuming: bool,
    ) -> None:
        """Start embedding the text the router will read: the turn's last message.

        Args:
            state: The turn's prepared state.
            user_id: The account the turn runs for.
            session_id: The request's session identifier.
            run_id: The turn's run, under which the spend is filed.
            resuming: A resumed turn (HITL) does not run the router: nothing starts.
        """
        if resuming or self._task is not None:
            return
        messages = state.get(STATE_KEY_MESSAGES) or []
        last = messages[-1] if messages else None
        if not isinstance(last, HumanMessage):
            return
        text = coerce_content_to_text(last.content)
        if not text.strip():
            return
        self._task = asyncio.create_task(
            _embed(text, user_id, session_id, run_id), name=f"message_embedding_{run_id}"
        )


async def _embed(text: str, user_id: str, session_id: str, run_id: str) -> None:
    """Compute and cache the message's vector, filed under the turn's run.

    Args:
        text: The message, exactly as the router will read it.
        user_id: The account the turn runs for.
        session_id: The request's session identifier.
        run_id: The turn's run.
    """
    set_embedding_context(user_id=user_id, session_id=session_id, run_id=run_id)
    try:
        # Never raises: a failure answers None, and the readers try again.
        await get_or_compute_embedding(
            message=text, user_id=user_id, session_id=session_id, is_conversational=True
        )
    finally:
        clear_embedding_context()
