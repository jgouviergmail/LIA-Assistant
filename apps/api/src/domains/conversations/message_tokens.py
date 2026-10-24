"""What the chat history shows of a run's tokens: once, on the run's newest answer.

The history comes back newest first, each message with the token summary of its run. A
run that answered more than once (a HITL flow asks, then answers) would show its tokens
and cost on every answer; the page keeps them on the newest one, so a run is never
counted twice on screen. An assistant message with no visible text is an ephemeral
progress bubble, and is not shown at all.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from src.core.field_names import (
    FIELD_CONTENT,
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
    FIELD_RUN_ID,
    FIELD_TOKENS_CACHE,
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
)

#: What a message entry carries of its run's summary; a run's earlier answers show none.
TOKEN_FIELDS: Final[tuple[str, ...]] = (
    FIELD_TOKENS_IN,
    FIELD_TOKENS_OUT,
    FIELD_TOKENS_CACHE,
    FIELD_COST_EUR,
    FIELD_GOOGLE_API_REQUESTS,
)


def _answer_run(entry: Mapping[str, object]) -> str | None:
    """The run an assistant entry answered, or None for any other entry."""
    if entry.get("role") != "assistant":
        return None
    metadata = entry.get("message_metadata")
    run_id = metadata.get(FIELD_RUN_ID) if isinstance(metadata, dict) else None
    return run_id if isinstance(run_id, str) and run_id else None


def _has_no_visible_text(entry: Mapping[str, object]) -> bool:
    """An assistant entry with nothing to read: an ephemeral progress bubble."""
    content = entry.get(FIELD_CONTENT)
    return entry.get("role") == "assistant" and not (
        content.strip() if isinstance(content, str) else ""
    )


def shown_with_tokens_once(entries: list[dict[str, object]]) -> list[dict[str, object]]:
    """The entries the history shows, each run's tokens on its newest answer only.

    Args:
        entries: The message entries, newest first.

    Returns:
        The entries in the same order, without the answers that have no visible text,
        a run's earlier answers stripped of its token fields.
    """
    shown = [entry for entry in entries if not _has_no_visible_text(entry)]
    answered: set[str] = set()
    for entry in shown:
        run_id = _answer_run(entry)
        if run_id is None:
            continue
        if run_id in answered:
            for field in TOKEN_FIELDS:
                entry[field] = None
        else:
            answered.add(run_id)
    return shown
