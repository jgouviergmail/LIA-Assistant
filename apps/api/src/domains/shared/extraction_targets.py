"""Which message a post-response extraction should analyse.

The three extractors — long-term memory, interests, personal journal — all
answer the same question first: *which* of the conversation's messages is the
one the user actually said this turn. They each carried their own copy of the
backwards scan, and that duplication is a liability, because not every
``HumanMessage`` in the history was typed by a human.

On a tool-level HITL refusal the resumption layer injects a **fabricated**
``HumanMessage`` into the graph state whose body is system scaffolding
("[USER REFUSAL] ... IMPORTANT: do not mention any technical problem ..."). It
is long enough to escape the triviality heuristic, so it became the extraction
target: an embedding plus up to four LLM calls spent analysing the assistant's
own instructions, with the matching risk of writing them into the user's
long-term memory or journal.

Synthetic messages are flagged through ``additional_kwargs`` — the same
mechanism ``proactive_notification`` already uses for assistant messages that
must not be treated as conversation. This module is where both the flag and the
scan live, so a fourth extractor cannot forget either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

# additional_kwargs flag set by the HITL resumption layer on messages it
# fabricates. Never classify these by matching their text: the scaffolding is
# localized in six languages, and string-matching an LLM-facing payload is
# exactly the anti-pattern the tool error taxonomy exists to avoid.
SYNTHETIC_MESSAGE_KEY = "synthetic_hitl_scaffold"


def is_synthetic_message(message: BaseMessage) -> bool:
    """Whether a message was fabricated by the system rather than typed.

    Args:
        message: Any conversation message.

    Returns:
        True when the message carries the synthetic-scaffold flag.
    """
    return bool(getattr(message, "additional_kwargs", {}).get(SYNTHETIC_MESSAGE_KEY))


def find_last_user_message(messages: list[BaseMessage]) -> tuple[HumanMessage | None, int]:
    """Find the most recent message the user actually typed.

    Scans backwards and skips fabricated messages, so a HITL refusal turn
    resolves to the request that started the flow rather than to the system
    scaffolding wrapped around the user's answer.

    Args:
        messages: Full conversation history, oldest first.

    Returns:
        Tuple of (message, index), or (None, -1) when the history holds no
        genuine user message.
    """
    for index in range(len(messages) - 1, -1, -1):
        candidate = messages[index]
        if isinstance(candidate, HumanMessage) and not is_synthetic_message(candidate):
            return candidate, index
    return None, -1
