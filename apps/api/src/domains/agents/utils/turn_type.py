"""Turn type helpers — tolerant to case and composite values.

Historical convention mismatch:
    - Constants in `agents.constants` (`TURN_TYPE_ACTION`, `TURN_TYPE_REFERENCE`,
      `TURN_TYPE_REFERENCE_PURE`, `TURN_TYPE_REFERENCE_ACTION`,
      `TURN_TYPE_CONVERSATIONAL`) are lowercase (`"action"`, `"reference"`, ...).
    - `QueryIntelligence.turn_type` emits UPPERCASE (`"ACTION"`, `"REFERENCE_PURE"`,
      `"REFERENCE_ACTION"`).
    - The router writes `state[STATE_KEY_TURN_TYPE] = intelligence.turn_type`
      verbatim → state carried UPPERCASE values.
    - Consumers comparing against the constants (e.g. response_node) silently
      missed REFERENCE turns, which caused resolved_context to never feed the
      LLM summary for reference-only queries.

These helpers centralize the comparison logic and accept both conventions.
They should be used everywhere `STATE_KEY_TURN_TYPE` is read. The canonical
form is lowercase (writers should `.lower()` before writing; legacy callers
are tolerated).
"""

from __future__ import annotations

from src.domains.agents.constants import (
    TURN_TYPE_ACTION,
    TURN_TYPE_CONVERSATIONAL,
    TURN_TYPE_REFERENCE,
    TURN_TYPE_REFERENCE_ACTION,
    TURN_TYPE_REFERENCE_PURE,
)

_REFERENCE_VARIANTS: frozenset[str] = frozenset(
    {
        TURN_TYPE_REFERENCE,
        TURN_TYPE_REFERENCE_PURE,
        TURN_TYPE_REFERENCE_ACTION,
    }
)


def _normalize(turn_type: str | None) -> str:
    """Lowercase/strip the value; empty string for None.

    Args:
        turn_type: Raw value, possibly None or padded with whitespace.

    Returns:
        Stripped lowercase string; empty string when input is None.
    """
    return (turn_type or "").strip().lower()


def is_reference_turn(turn_type: str | None) -> bool:
    """Tell whether the turn is part of the REFERENCE family.

    Covers the three reference variants (REFERENCE, REFERENCE_PURE,
    REFERENCE_ACTION). Accepts uppercase (legacy `QueryIntelligence.turn_type`
    output) and lowercase (`TURN_TYPE_*` constants) representations.

    Args:
        turn_type: Raw turn type value from state or intelligence.

    Returns:
        True if the value matches any reference variant, False otherwise.
    """
    return _normalize(turn_type) in _REFERENCE_VARIANTS


def is_action_turn(turn_type: str | None) -> bool:
    """Tell whether the turn is a pure ACTION (not a reference variant).

    Args:
        turn_type: Raw turn type value.

    Returns:
        True when the value equals TURN_TYPE_ACTION (case-insensitive).
    """
    return _normalize(turn_type) == TURN_TYPE_ACTION


def is_conversational_turn(turn_type: str | None) -> bool:
    """Tell whether the turn is purely conversational.

    Args:
        turn_type: Raw turn type value.

    Returns:
        True when the value equals TURN_TYPE_CONVERSATIONAL (case-insensitive).
    """
    return _normalize(turn_type) == TURN_TYPE_CONVERSATIONAL


def normalize_turn_type(turn_type: str | None) -> str:
    """Normalise a turn_type to its canonical lowercase form.

    Default to TURN_TYPE_ACTION when the input is empty or None. This is the
    value writers (e.g. router_node_v3) should persist in state so consumers
    can compare against TURN_TYPE_* constants without worrying about case.

    Args:
        turn_type: Raw turn type value.

    Returns:
        Canonical lowercase turn type string.
    """
    normalized = _normalize(turn_type)
    return normalized if normalized else TURN_TYPE_ACTION


__all__ = [
    "is_action_turn",
    "is_conversational_turn",
    "is_reference_turn",
    "normalize_turn_type",
]
