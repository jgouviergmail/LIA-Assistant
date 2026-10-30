"""Monotonic delivery measurements; no content retention or model-duration sums.

The journey starts with the request — before the conversation setup and the
MCP preparation — so its first answer token is the wait a person actually has
(``chat_journey_first_token_seconds``), and a turn that ends without one says
why (``chat_journey_unanswered_seconds{outcome}``). Both go through the
latency door, which observes only a turn a person waits for.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal

import structlog

from src.domains.agents.services.streaming.latency_sli import (
    observe_journey_first_token,
    observe_journey_unanswered,
)

logger = structlog.get_logger(__name__)

JourneyOutcome = Literal["answered", "cancelled", "error", "interrupted"]

# A turn that stops on a HITL interrupt streams its question through these.
_QUESTION_KINDS = frozenset({"hitl_question_token", "hitl_interrupt_metadata"})


@dataclass
class JourneyTiming:
    """One stream invocation, including preparation; never persisted across turns."""

    started: float = field(default_factory=perf_counter)
    first_useful_ms: float | None = None
    first_token_ms: float | None = None
    first_preview_ms: float | None = None
    asked_question: bool = False
    closed: bool = False

    def observe(
        self,
        kind: str,
        content: str,
        metadata: Mapping[str, object],
        *,
        now: float | None = None,
    ) -> None:
        elapsed = ((perf_counter() if now is None else now) - self.started) * 1000
        useful = False
        if kind == "token" and content.strip():
            if self.first_token_ms is None:
                self.first_token_ms = elapsed
                observe_journey_first_token(elapsed / 1000)
            useful = True
        # Legacy JEV preview frames are no longer displayed in the discussion.
        # Keep their timing field empty so a hidden result cannot imply delivery.
        elif kind == "content_replacement" and content.strip():
            useful = True
        elif kind in _QUESTION_KINDS:
            self.asked_question = True
        if useful and self.first_useful_ms is None:
            self.first_useful_ms = elapsed

    def close(self, outcome: JourneyOutcome, *, now: float | None = None) -> None:
        """End the journey once; a turn without an answer token is observed by outcome.

        Idempotent: the first outcome stands, so a later cleanup path cannot
        relabel a turn. A turn whose answer had started is answered whatever
        ended it afterwards.

        Args:
            outcome: How the turn ended.
            now: The clock reading, for tests; ``perf_counter()`` by default.
        """
        if self.closed:
            return
        self.closed = True
        if outcome == "answered" or self.first_token_ms is not None:
            return
        observe_journey_unanswered(outcome, (perf_counter() if now is None else now) - self.started)

    def close_completed(self, *, now: float | None = None) -> None:
        """End a stream that ran to its end: interrupted when it asked instead of answering.

        Args:
            now: The clock reading, for tests; ``perf_counter()`` by default.
        """
        unanswered_question = self.first_token_ms is None and self.asked_question
        self.close("interrupted" if unanswered_question else "answered", now=now)

    def measurements(self) -> dict[str, float | None]:
        return {
            "first_useful_ms": self.first_useful_ms,
            "first_answer_token_ms": self.first_token_ms,
            "first_visible_preview_ms": self.first_preview_ms,
        }

    def log_completed(self, run_id: str, cost_eur: float) -> None:
        """Server delivery endpoint, after joins/accounting and immediately before done."""
        self.close_completed()
        logger.info(
            "chat_delivery_completed",
            run_id=run_id,
            duration_ms=(perf_counter() - self.started) * 1000,
            cost_eur=cost_eur,
            **self.measurements(),
        )
