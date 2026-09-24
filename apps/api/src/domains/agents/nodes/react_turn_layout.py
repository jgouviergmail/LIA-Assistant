"""Where a ReAct turn's context goes: in the system prompt, or after the question (ADR-308).

A ReAct call sends ``[tools][system][history][question][loop]``. The versioned
prompt ends with the turn's own data after ``DYNAMIC_CONTEXT_MARKER`` (the date,
the domains' type links) and the context blocks follow it (memories, knowledge,
skills). There, the data changes the prefix every provider caches right after
the static prompt; on DeepSeek, which renders the system BEFORE the tools, it
even hides the tools from the cache (measured 2026-09-23: every tool bound and
the context left in place cost 44 % more per turn).

For frequent exchanges (:func:`frequent_exchanges`, ADR-311) the leading system
message is the static prompt alone, ending on its marker line -- where the
Anthropic and OpenAI payload shapers cut their breakpoint and where the OpenAI
cache key stops -- and the turn's data comes right after the question, before the
loop's own messages, so every iteration of the turn re-sends the same prefix. For
occasional exchanges, the layout is the one ADR-169 set: the blocks lead, then
the windowed history.

« After the question » has one shape per provider, DECLARED in
:data:`CONTEXT_PLACEMENT` and checked at boot: a provider added to
``ProviderType`` without a declaration refuses to start.
"""

from __future__ import annotations

import contextlib
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any, get_args

import structlog
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage

from src.core.config import settings
from src.core.constants import DYNAMIC_CONTEXT_MARKER
from src.core.exchange_rhythm import ExchangeRhythm
from src.core.prompt_layout import split_at_marker
from src.infrastructure.llm.providers.adapter import ProviderType

logger = structlog.get_logger(__name__)


class ContextPlacement(StrEnum):
    """How a provider takes the turn's context once it moves after the question."""

    #: A system message right after the question.
    TRAILING_SYSTEM = "trailing_system"
    #: The context appended to the question's own message, as text.
    QUESTION_TAIL = "question_tail"


#: The trailing system message was measured on the real API for the first three
#: (ReAct binding benchmark, 2026-09-23: OpenAI Responses, DeepSeek, Qwen
#: compatible mode). The others cannot take one: Anthropic refuses a system
#: message that is not first, ``langchain-google-genai`` merges it back into the
#: system instruction, a mid-conversation system role is left to each Ollama
#: model's own template, and Perplexity wants the system first and the roles
#: alternating. Text appended to the question is valid on all of them.
CONTEXT_PLACEMENT: dict[str, ContextPlacement] = {
    "openai": ContextPlacement.TRAILING_SYSTEM,
    "deepseek": ContextPlacement.TRAILING_SYSTEM,
    "qwen": ContextPlacement.TRAILING_SYSTEM,
    "anthropic": ContextPlacement.QUESTION_TAIL,
    "gemini": ContextPlacement.QUESTION_TAIL,
    "ollama": ContextPlacement.QUESTION_TAIL,
    "perplexity": ContextPlacement.QUESTION_TAIL,
}


def assert_context_placement_completeness() -> None:
    """Assert every ``ProviderType`` member declares where its context goes.

    Called from the startup fail-fast validations and from a unit test (ADR-085
    pattern): a provider missing here would silently take the fallback shape.

    Raises:
        AssertionError: Naming each provider without a declaration.
    """
    missing = sorted(set(get_args(ProviderType)) - set(CONTEXT_PLACEMENT))
    if missing:
        raise AssertionError(
            f"CONTEXT_PLACEMENT is missing {len(missing)} provider(s): {', '.join(missing)}. "
            "Every ProviderType must declare where the ReAct turn's context goes after the "
            "question -- see src/domains/agents/nodes/react_turn_layout.py."
        )


def frequent_exchanges(state: Mapping[str, Any]) -> bool:
    """Whether the turn is shaped for the next one (ADR-311).

    The ONE reading of the turn's rhythm by the loop: the setup binds every
    tool on it, and every call places the context after the question and drops
    the history by blocks on it. The router wrote the value at the turn's
    start; a state without one (a unit test, a checkpoint older than the
    rhythm) is an occasional turn.

    Args:
        state: The turn's graph state.

    Returns:
        True for a frequent-exchanges turn.
    """
    return state.get("exchange_rhythm") == ExchangeRhythm.FREQUENT


def react_slot_provider() -> str | None:
    """The provider the ``react_agent`` slot runs on, or None when it cannot be read.

    Returns:
        The provider name of the slot's effective configuration.
    """
    # Best-effort read: an unreadable slot falls back to the shape every client
    # accepts (the context appended to the question), never breaks the loop.
    with contextlib.suppress(Exception):
        from src.core.llm_config_helper import get_llm_config_for_agent

        return get_llm_config_for_agent(settings, "react_agent").provider
    logger.debug("react_turn_layout_provider_unreadable")
    return None


def compose_turn_messages(
    system_blocks: Sequence[str],
    windowed: Sequence[BaseMessage],
    *,
    context_after_question: bool,
    provider: str | None,
) -> list[BaseMessage]:
    """The messages one ReAct call sends, the turn's context placed per the flag.

    Args:
        system_blocks: The turn's system blocks (``react_system_blocks``): the
            rendered prompt first, then the context blocks.
        windowed: The windowed history, ending with the current question and the
            loop's own messages.
        context_after_question: Whether the turn's context follows the question
            (``REACT_CROSS_TURN_CACHE_ENABLED``) instead of closing the system prompt.
        provider: The provider the call goes to, which decides the shape.

    Returns:
        A new list. Nothing given is mutated: a question the context closes is a copy.
    """
    leading: list[BaseMessage] = [SystemMessage(content=block) for block in system_blocks]
    if not context_after_question:
        return [*leading, *windowed]
    question_at = _current_question(windowed)
    split = _split_context(system_blocks)
    if question_at is None or split is None:
        return [*leading, *windowed]
    static, context = split
    before, question, after = (
        windowed[:question_at],
        windowed[question_at],
        windowed[question_at + 1 :],
    )
    placement = CONTEXT_PLACEMENT.get(provider or "", ContextPlacement.QUESTION_TAIL)
    if placement is ContextPlacement.TRAILING_SYSTEM:
        placed = [question, SystemMessage(content=context)]
    else:
        placed = [_closed_by(question, context)]
    return [SystemMessage(content=static), *before, *placed, *after]


def _current_question(windowed: Sequence[BaseMessage]) -> int | None:
    """Index of the last human message -- the current turn's question -- or None."""
    for index in range(len(windowed) - 1, -1, -1):
        if isinstance(windowed[index], HumanMessage):
            return index
    return None


def _split_context(system_blocks: Sequence[str]) -> tuple[str, str] | None:
    """(static prompt, turn context) of the blocks, or None when nothing is dynamic.

    The static prompt runs to the end of the marker's line, so the shapers still
    find the marker where the static part ends. The context opens on that same
    line -- or on the bare marker when the prompt carries none -- then the
    prompt's dynamic part, then every other block, in their order.
    """
    if not system_blocks:
        return None
    prompt, *blocks = system_blocks
    split = split_at_marker(prompt)
    if split is None:
        static, header, tail = prompt, DYNAMIC_CONTEXT_MARKER, ""
    else:
        static, header, tail = split.static, split.marker_line, split.dynamic
    parts = [part for part in (tail, *blocks) if part.strip()]
    if not parts:
        return None
    return static, f"{header}\n" + "\n\n".join(parts)


def _closed_by(question: BaseMessage, context: str) -> BaseMessage:
    """A copy of the question whose content ends with the context.

    A text question stays TEXT: every client accepts it, and the token counter
    behind the delivered-context metric counts text content only -- a list would
    have hidden the turn's whole context from it. A question that already carries
    parts (an attachment) gets the context as one more text part.
    """
    content = question.content
    if isinstance(content, str):
        closed: str | list[str | dict[str, Any]] = f"{content}\n\n{context}" if content else context
    else:
        closed = [*content, {"type": "text", "text": context}]
    return question.model_copy(update={"content": closed})


__all__ = [
    "CONTEXT_PLACEMENT",
    "ContextPlacement",
    "assert_context_placement_completeness",
    "compose_turn_messages",
    "frequent_exchanges",
    "react_slot_provider",
]
