"""What the caller WANTS from a reasoning model, in one shape.

Replaces a four-member discriminated union whose shape was dispatched on a
catalogue column. Measured before the change over the 54 configured slots:
**21 stored** ``{"effort": "off"}`` and **6** ``{"effort": "none"}`` to say the
same thing, and three authorities -- the ``reasoning_widget`` column, the shape
of the stored JSONB and the builder's ``isinstance`` check -- had to agree or
the LLM failed to instantiate.

An intent says what is wanted; a :class:`ReasoningProfile` says what the model
can do; ``translate`` reconciles the two. Nothing about *shape* is stored.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.core.constants import ANTHROPIC_MIN_THINKING_BUDGET_TOKENS

#: The ordinal ladder, from "let the provider decide" up to the deepest mode.
#: ``provider_default`` sits at the bottom deliberately: it is the identity, not
#: a depth, and coercion never targets it.
LEVELS: tuple[str, ...] = (
    "provider_default",
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)

Level = Literal["provider_default", "none", "minimal", "low", "medium", "high", "xhigh", "max"]

_ORDINALS: dict[str, int] = {level: index for index, level in enumerate(LEVELS)}


def level_ordinal(level: str) -> int:
    """Return a level's rank on the ladder.

    Args:
        level: A :data:`LEVELS` member.

    Returns:
        Its index, which coercion uses to measure distance.

    Raises:
        KeyError: on any value outside the ladder. Never guess a rank -- a
            silent default would make coercion pick an arbitrary neighbour, and
            an arbitrary neighbour of "high" can be "none".
    """
    return _ORDINALS[level]


@dataclass(frozen=True)
class ReasoningIntent:
    """A request for reasoning depth, independent of any provider.

    Attributes:
        level: How much thinking is wanted. ``provider_default`` asks for
            nothing and produces no kwarg on any family.
        budget_tokens: An explicit token budget, for the families that accept
            one. When both a level and a budget are given, the family's
            translator uses whichever it can express.
        exclude_from_output: Orthogonal to depth -- keep the reasoning out of
            the response. A family that cannot express it ignores it rather
            than failing, so a caller never has to know which families can.
    """

    level: Level = "provider_default"
    budget_tokens: int | None = None
    exclude_from_output: bool = False


#: The keys of the one stored shape. A dict whose keys are a subset of these
#: is already an intent -- the predicate lives HERE because three callers need
#: it (the two Pydantic shims and migration ``d3e4f5a6b7c8``) and a fourth that
#: forgot it would silently re-encode a migrated row.
_INTENT_KEYS = frozenset({"level", "budget_tokens", "exclude_from_output"})


def requested_level(stored: Any) -> str:
    """The level a stored reasoning value asks for, whatever shape it holds.

    Adapters need the level itself — not the provider kwargs — to answer
    questions the translator does not: whether a GPT-5.1+ model at ``none``
    still accepts sampling parameters, what to put in a log line. Reading
    ``.level`` alone was wrong on a legacy dict, and reading ``.effort`` alone
    became wrong the day the field was retyped: a log built on it printed
    ``None`` on every DeepSeek call.

    Args:
        stored: A :class:`ReasoningIntent`, a stored dict in any of the shapes
            ADR-245 replaced, ``None``, or an object exposing ``level``.

    Returns:
        The level, or ``provider_default`` when nothing was asked.
    """
    if isinstance(stored, ReasoningIntent):
        return stored.level
    if stored is None or isinstance(stored, dict):
        return intent_from_legacy(stored).level
    level = getattr(stored, "level", None)
    return str(level) if level else "provider_default"


def is_intent_shape(value: dict[str, Any]) -> bool:
    """True when a stored dict is already in the single intent shape.

    Args:
        value: A stored ``reasoning_effort`` payload.

    Returns:
        Whether it carries only intent keys. An empty dict counts: it reads as
        ``provider_default`` either way.
    """
    return not (value.keys() - _INTENT_KEYS)


def intent_from_legacy(value: dict[str, Any] | None) -> ReasoningIntent:
    """Read one of the four stored shapes as an intent.

    The encodings of "no reasoning" collapse to ``level="none"``. Measured over
    the 54 configured slots: ``{"effort": "off"}`` on 21 of them and
    ``{"effort": "none"}`` on 6, saying the same thing two ways, plus
    ``{"enabled": false}`` and the never-used ``{"budget": 0}`` in the
    catalogue's declared values.

    Args:
        value: The stored JSONB, or ``None``.

    Returns:
        The equivalent intent. A shape outside the four reads as
        ``provider_default`` rather than raising: the migration must be total,
        and an unrecognised shape is an absent instruction, not an error.
    """
    if not value:
        return ReasoningIntent()
    if is_intent_shape(value):
        # Already migrated. Total on its own output, so replaying a seed, or an
        # older instance reading a row a newer one wrote, cannot re-encode it.
        level = str(value.get("level") or "provider_default")
        budget = value.get("budget_tokens")
        return ReasoningIntent(
            level=level if level in LEVELS else "provider_default",  # type: ignore[arg-type]
            budget_tokens=int(budget) if budget is not None else None,
            exclude_from_output=bool(value.get("exclude_from_output", False)),
        )
    if "effort" in value:
        effort = str(value["effort"])
        level = "none" if effort == "off" else effort
        # An effort string outside the ladder is an absent instruction, not an
        # error: writing it through would make ``level_ordinal`` raise deep in
        # the runtime translator, on a row an operator could hand-edit.
        return ReasoningIntent(level=level if level in LEVELS else "provider_default")  # type: ignore[arg-type]
    if "enabled" in value:
        if not value["enabled"]:
            return ReasoningIntent(level="none")
        budget = value.get("budget")
        return ReasoningIntent(
            budget_tokens=(
                int(budget) if budget is not None else ANTHROPIC_MIN_THINKING_BUDGET_TOKENS
            )
        )
    if "budget" in value:
        budget = int(value["budget"])
        if budget == -1:
            return ReasoningIntent()
        if budget == 0:
            return ReasoningIntent(level="none")
        return ReasoningIntent(budget_tokens=budget)
    return ReasoningIntent()
