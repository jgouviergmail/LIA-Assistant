"""Monotonic delivery measurements; no content retention or model-duration sums."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from time import perf_counter

import structlog

logger = structlog.get_logger(__name__)


def _visible_preview(metadata: Mapping[str, object]) -> bool:
    collection = metadata.get("collection")
    if not isinstance(collection, dict):
        return False
    items = collection.get("items")
    return isinstance(items, list) and any(
        isinstance(item, dict) and item.get("verdict") in ("match", "unknown") for item in items
    )


@dataclass
class JourneyTiming:
    """One stream invocation, including preparation; never persisted across turns."""

    started: float = field(default_factory=perf_counter)
    first_useful_ms: float | None = None
    first_token_ms: float | None = None
    first_preview_ms: float | None = None

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
            useful = True
        elif kind == "result_preview" and _visible_preview(metadata):
            if self.first_preview_ms is None:
                self.first_preview_ms = elapsed
            useful = True
        elif kind == "content_replacement" and content.strip():
            useful = True
        if useful and self.first_useful_ms is None:
            self.first_useful_ms = elapsed

    def measurements(self) -> dict[str, float | None]:
        return {
            "first_useful_ms": self.first_useful_ms,
            "first_answer_token_ms": self.first_token_ms,
            "first_visible_preview_ms": self.first_preview_ms,
        }

    def log_completed(self, run_id: str, cost_eur: float) -> None:
        """Server delivery endpoint, after joins/accounting and immediately before done."""
        logger.info(
            "chat_delivery_completed",
            run_id=run_id,
            duration_ms=(perf_counter() - self.started) * 1000,
            cost_eur=cost_eur,
            **self.measurements(),
        )
