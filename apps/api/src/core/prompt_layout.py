"""Where a versioned prompt's static part ends, and what a single call sends (ADR-309).

Every versioned prompt keeps what each call repeats above ONE line holding
``DYNAMIC_CONTEXT_MARKER`` and the call's own data below it. That line is the one
boundary every cache mechanism is translated from: the Anthropic and OpenAI
payload shapers place their breakpoint there, the OpenAI cache key stops there,
and a provider caching prefixes by itself reads everything above it again.

A single call (an extraction, the query analyzer, the initiative) used to send
its whole prompt as ONE user message. The shapers mark instruction roles only, so
the static part was never marked: measured 2026-09-23 on gpt-6-luna, every
extraction read 0 % of its prompt from the cache and wrote all of it at 1.25x.
:func:`single_call_messages` sends the static part as the system message, ending
on the marker's line, and the call's data as the question — the same text, in
two roles.

:func:`split_at_marker` is the ONE reading of « where the static part ends »; the
ReAct turn layout (ADR-308) reads it too.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.constants import DYNAMIC_CONTEXT_MARKER


@dataclass(frozen=True)
class MarkerSplit:
    """A prompt cut at the end of its marker's line.

    Attributes:
        static: Everything up to the end of the marker's line, marker included —
            the shapers find the marker where the static part ends.
        marker_line: The marker's own line.
        dynamic: What follows the marker's line, stripped.
    """

    static: str
    marker_line: str
    dynamic: str


def split_at_marker(prompt: str) -> MarkerSplit | None:
    """Cut a prompt at the end of its ``DYNAMIC_CONTEXT_MARKER`` line.

    Args:
        prompt: A rendered versioned prompt.

    Returns:
        The split, or None when the prompt carries no marker.
    """
    start = prompt.find(DYNAMIC_CONTEXT_MARKER)
    if start < 0:
        return None
    end = prompt.find("\n", start)
    end = len(prompt) if end < 0 else end
    return MarkerSplit(
        static=prompt[:end], marker_line=prompt[start:end], dynamic=prompt[end:].strip()
    )


def single_call_messages(prompt: str) -> list[BaseMessage]:
    """The messages one call sends for a rendered versioned prompt.

    Args:
        prompt: The rendered prompt.

    Returns:
        ``[system: static part, human: the call's data]``; a single user message
        when the prompt carries no marker or nothing follows it — nothing then
        says where the per-call part starts.
    """
    split = split_at_marker(prompt)
    if split is None or not split.dynamic:
        return [HumanMessage(content=prompt)]
    return [SystemMessage(content=split.static), HumanMessage(content=split.dynamic)]
