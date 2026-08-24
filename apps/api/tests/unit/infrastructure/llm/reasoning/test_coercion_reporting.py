"""T6: a coercion is never silent -- it is counted and logged (ADR-245 §7).

Coercing is the right behaviour (a level the model does not offer must not
become an outage), but it means the model is NOT doing what the admin asked.
Before this, the only trace of that gap was in the code.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.reasoning_intent import ReasoningIntent
from src.infrastructure.llm.reasoning.profiles import ReasoningProfile
from src.infrastructure.llm.reasoning.translate import translate
from src.infrastructure.observability.metrics_llm_config import llm_reasoning_coerced_total

pytestmark = pytest.mark.unit

#: A ladder without "medium" or "minimal", so a request for either must move.
_GAPPY = ReasoningProfile("openai", ("none", "low", "high"), False, None, True, True)


def _count(model: str, requested: str, applied: str) -> float:
    counter = llm_reasoning_coerced_total.labels(
        model=model, from_level=requested, to_level=applied
    )
    return float(counter._value.get())


def test_a_coercion_is_counted_with_both_levels() -> None:
    before = _count("gap-model", "medium", "high")
    translate(ReasoningIntent(level="medium"), _GAPPY, "gap-model", 4096)
    assert _count("gap-model", "medium", "high") == before + 1


def test_ties_are_counted_where_they_land_upward() -> None:
    """``minimal`` sits between ``none`` and ``low``: the tie breaks upward."""
    before = _count("gap-model", "minimal", "low")
    translate(ReasoningIntent(level="minimal"), _GAPPY, "gap-model", 4096)
    assert _count("gap-model", "minimal", "low") == before + 1


def test_a_level_on_the_ladder_is_not_counted() -> None:
    before = _count("gap-model", "high", "high")
    translate(ReasoningIntent(level="high"), _GAPPY, "gap-model", 4096)
    assert _count("gap-model", "high", "high") == before


def test_provider_default_never_counts() -> None:
    """It renders no kwarg at all, so there is nothing to coerce."""
    before = _count("gap-model", "provider_default", "none")
    assert translate(ReasoningIntent(), _GAPPY, "gap-model", 4096) == {}
    assert _count("gap-model", "provider_default", "none") == before


def test_the_coercion_is_logged_with_both_levels(caplog: Any) -> None:
    """A counter says how often; the log says which slot, for one incident."""
    import logging

    with caplog.at_level(logging.INFO):
        translate(ReasoningIntent(level="medium"), _GAPPY, "gap-model", 4096)

    assert any(
        "llm_reasoning_coerced" in record.getMessage()
        and "gap-model" in record.getMessage()
        and "medium" in record.getMessage()
        for record in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_a_broken_metrics_backend_never_breaks_the_call(monkeypatch: Any) -> None:
    """Observability is not allowed to take down an LLM instantiation."""

    def boom(**_kwargs: Any) -> Any:
        raise RuntimeError("registry exploded")

    monkeypatch.setattr(llm_reasoning_coerced_total, "labels", boom)
    assert translate(ReasoningIntent(level="medium"), _GAPPY, "gap-model", 4096) == {
        "reasoning_effort": "high"
    }
