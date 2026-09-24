"""What the Claude Messages API accepts from each model generation, declared once.

Three things change between Claude generations, and each one is an HTTP 400 on
every call when it is got wrong — measured on the Claude API on 2026-09-23
(ADR-306: the Models API for the thinking shape, then near-free validation
requests for the rest):

* **sampling** — a ``temperature`` or ``top_p`` other than its default is
  refused from Opus 4.7 on (« `temperature` is deprecated for this model »);
* **forced tool choice** — ``tool_choice`` ``any``/``tool`` is refused by the
  generations that bind their thinking to the conversation, and only by them;
* **thinking** — six shapes: none (the retired 3.5 models), a token budget (the
  4.5 generation, where ``adaptive`` and ``effort`` are refused), adaptive and
  off unless asked (4.6, then 4.7/4.8 with a visibility control), adaptive and
  ON unless disabled (Opus 5, Sonnet 5), always on (Fable, Opus 5.5 —
  ``disabled`` is refused).

A fourth fact is not a 400 today but becomes one on every account created from
2026-08-31: a generation that binds a thinking block to the conversation that
produced it refuses that block once the history before it changed (the ``system``
prompt LIA rebuilds every turn is enough — measured on Opus 5.5).

The reasoning ladder is derived from the thinking shape by
:mod:`src.core.reasoning_profiles`; this module holds the facts and nothing
else, so it imports nothing and every reader — the provider adapter, the
structured-output door, the reasoning resolution — reads the same row.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

#: How a generation reasons (see the module docstring); the reasoning family and
#: ladder are derived from it in ``reasoning_profiles``.
ClaudeThinking = Literal["none", "budget", "adaptive", "opt_in", "default_on", "always_on"]


@dataclass(frozen=True)
class ClaudeSurface:
    """The request surface of one Claude generation.

    Attributes:
        prefixes: The model names this row covers (a dated snapshot shares its
            alias's row). Rows are ORDERED: a newer name is tested before the
            older name it starts with.
        thinking: How the generation reasons, or ``None`` for a model this table
            does not declare.
        implicit_effort: The effort the API applies when a thinking-by-default
            generation is sent no ``effort`` (``medium`` on Opus 5.5, ``high``
            elsewhere); ``None`` when the generation does not think unasked.
        accepts_sampling: Whether a non-default ``temperature``/``top_p`` is
            accepted.
        accepts_forced_tool_choice: Whether ``tool_choice`` may force a tool.
        binds_thinking_to_conversation: Whether a thinking block is refused
            once the history that produced it changed (« preserved thinking »).
    """

    prefixes: tuple[str, ...]
    thinking: ClaudeThinking | None
    implicit_effort: str | None
    accepts_sampling: bool
    accepts_forced_tool_choice: bool
    binds_thinking_to_conversation: bool


#: ORDERED: the first row whose prefix starts the model name wins. The Mythos
#: names are Glasswing's Fable under another name — declared so a manually added
#: row behaves, never offered by the catalogue (unreachable from an ordinary
#: organisation, measured on the Models API).
CLAUDE_SURFACES: tuple[ClaudeSurface, ...] = (
    ClaudeSurface(
        prefixes=("claude-3-5",),
        thinking="none",
        implicit_effort=None,
        accepts_sampling=True,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
    ClaudeSurface(
        prefixes=("claude-fable-5-1", "claude-mythos-5-1"),
        thinking="always_on",
        implicit_effort="high",
        accepts_sampling=False,
        accepts_forced_tool_choice=False,
        binds_thinking_to_conversation=True,
    ),
    ClaudeSurface(
        prefixes=("claude-opus-5-5",),
        thinking="always_on",
        implicit_effort="medium",
        accepts_sampling=False,
        accepts_forced_tool_choice=False,
        binds_thinking_to_conversation=True,
    ),
    ClaudeSurface(
        prefixes=("claude-fable-5", "claude-mythos-5"),
        thinking="always_on",
        implicit_effort="high",
        accepts_sampling=False,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
    ClaudeSurface(
        prefixes=("claude-opus-5", "claude-sonnet-5"),
        thinking="default_on",
        implicit_effort="high",
        accepts_sampling=False,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
    ClaudeSurface(
        prefixes=("claude-opus-4-7", "claude-opus-4-8"),
        thinking="opt_in",
        implicit_effort=None,
        accepts_sampling=False,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
    ClaudeSurface(
        prefixes=("claude-opus-4-6", "claude-sonnet-4-6"),
        thinking="adaptive",
        implicit_effort=None,
        accepts_sampling=True,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
    # The 4.5 generation, plus the retired 4.0/4.1 names still found in the
    # registries (``claude-opus-4-20250514``, ``claude-sonnet-4-0``...).
    ClaudeSurface(
        prefixes=(
            "claude-opus-4-5",
            "claude-haiku-4-5",
            "claude-sonnet-4-5",
            "claude-opus-4",
            "claude-sonnet-4",
        ),
        thinking="budget",
        implicit_effort=None,
        accepts_sampling=True,
        accepts_forced_tool_choice=True,
        binds_thinking_to_conversation=False,
    ),
)

#: A generation released after this table: sent what EVERY generation accepts —
#: no sampling parameter (the API default applies), no forced tool call (the
#: auto-tool path works everywhere), no binding control (it requires a thinking
#: form an unknown model may refuse). Its reasoning stays unknown.
UNDECLARED_CLAUDE = ClaudeSurface(
    prefixes=(),
    thinking=None,
    implicit_effort=None,
    accepts_sampling=False,
    accepts_forced_tool_choice=False,
    binds_thinking_to_conversation=False,
)


def claude_surface(model: str) -> ClaudeSurface:
    """The declared surface of a Claude model.

    Args:
        model: The Claude model name as configured (alias or dated snapshot).

    Returns:
        The first matching row, or :data:`UNDECLARED_CLAUDE`. Never raises.
    """
    for surface in CLAUDE_SURFACES:
        if model.startswith(surface.prefixes):
            return surface
    return UNDECLARED_CLAUDE


def requests_thinking(thinking: object) -> bool:
    """Whether a ``thinking`` request field switches thinking ON.

    The shape is the Claude API's: ``enabled`` (a budget) and ``adaptive`` think,
    ``disabled`` does not. Reading the key's mere presence instead -- the rule
    before ADR-306 -- stopped being the same question the day ``disabled`` had
    to be spelled out for Opus 5 and Sonnet 5.

    Args:
        thinking: The field as it will be sent, or anything else.

    Returns:
        True only for a mapping whose ``type`` asks for thinking.
    """
    return isinstance(thinking, Mapping) and thinking.get("type") in ("enabled", "adaptive")


def sampling_omitted(model: str, thinking: object) -> bool:
    """Whether ``temperature`` and ``top_p`` must stay out of a request.

    Two causes, both 400s: thinking switched on (« temperature may only be set
    to 1 when thinking is enabled »), and a generation that refuses a
    non-default sampling parameter outright (Opus 4.7 on). The provider adapter
    and the configuration write path read this one rule, so what an
    administrator can store is what a request can carry.

    Args:
        model: The Claude model name.
        thinking: The ``thinking`` field the request carries (or would).

    Returns:
        True when neither parameter may be sent.
    """
    return requests_thinking(thinking) or not claude_surface(model).accepts_sampling


__all__ = [
    "CLAUDE_SURFACES",
    "UNDECLARED_CLAUDE",
    "ClaudeSurface",
    "ClaudeThinking",
    "claude_surface",
    "requests_thinking",
    "sampling_omitted",
]
