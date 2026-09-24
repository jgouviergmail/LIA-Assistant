"""How a person exchanges with LIA, and what the ReAct loop shapes its prompt for (ADR-311).

A ReAct turn's prompt can be shaped for the NEXT turn or for this one alone:

- **frequent** exchanges bind every tool, place the turn's context after the
  question and drop the history by blocks, so that a turn following soon after
  reads the previous one back from the provider's prompt cache (ADR-308,
  ADR-309) — a heavier first turn, cheaper turns after it;
- **occasional** exchanges keep the relevance selection (ADR-293), whose cost
  does not depend on how soon the next turn comes.

The three effects travel together: measured on 396 real turns (ADR-308), the
context after the question pays only when every tool is bound, and the history
blocks only when the prefix before them is read again.

The account stores the person's choice (``users.exchange_rhythm``); an account
that never chose follows ``REACT_CROSS_TURN_CACHE_ENABLED``, the operator's
default. This module is the one reader of that setting (guarded).
"""

from __future__ import annotations

from enum import StrEnum

from src.core.config import settings

__all__ = ["ExchangeRhythm", "effective_exchange_rhythm"]


class ExchangeRhythm(StrEnum):
    """The two rhythms a person can declare, as they are stored."""

    FREQUENT = "frequent"
    OCCASIONAL = "occasional"


_STORED_VALUES = frozenset(rhythm.value for rhythm in ExchangeRhythm)


def effective_exchange_rhythm(stored: str | None) -> ExchangeRhythm:
    """The rhythm a turn runs with: the person's choice, else the instance default.

    Reads are forgiving: a missing or unreadable value follows the default rather
    than failing a turn. Writes are strict (the API schema accepts the two values
    only).

    Args:
        stored: ``users.exchange_rhythm`` as stored, or None when never chosen.

    Returns:
        The effective rhythm.
    """
    if stored is not None and stored in _STORED_VALUES:
        return ExchangeRhythm(stored)
    if settings.react_cross_turn_cache_enabled:
        return ExchangeRhythm.FREQUENT
    return ExchangeRhythm.OCCASIONAL
