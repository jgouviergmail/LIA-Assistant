"""What the kept answer cost to PRODUCE (2026-10-03).

A bookmark showed one figure, the cost of indexing it into the « Kept
answers » space — a few embedding tokens — which reads as the answer's own
cost and is a tiny share of it. The answer's cost is its turn's
``message_token_summary`` row: the very row the chat bubble reads, joined by
the run id the bookmark copied at the click. Read through the chat
repository's batched lookup (one query per page), rendered as the dashboard's
``LLMUsage`` with the BILLED total (model, Maps Platform, generated images,
paid speech), exactly like the chat and the phone-call cards.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol

from src.core.llm_usage import LLMUsage


class TurnSummary(Protocol):
    """What the API reads on a turn's ``message_token_summary`` row."""

    total_prompt_tokens: int
    total_completion_tokens: int
    total_cached_tokens: int

    @property
    def billed_cost_eur(self) -> Decimal:
        """The turn's billed total in euros."""
        ...


def answer_usage_of(summary: TurnSummary | None) -> LLMUsage | None:
    """The answer's cost, or None when its turn left no summary.

    Absent rather than zero: an answer archived before token tracking, or a
    bookmark whose message carried no run id, has no known cost — showing
    « 0 € » would be a claim nobody measured.

    Args:
        summary: The turn's summary row, when one exists.

    Returns:
        The usage in the dashboard's vocabulary, the model left unnamed (a
        turn runs several), or None.
    """
    if summary is None:
        return None
    return LLMUsage(
        tokens_in=summary.total_prompt_tokens,
        tokens_out=summary.total_completion_tokens,
        tokens_cache=summary.total_cached_tokens,
        cost_eur=float(summary.billed_cost_eur),
        model_name=None,
    )
