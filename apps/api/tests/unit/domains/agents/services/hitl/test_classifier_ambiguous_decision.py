"""An AMBIGUOUS classification is returned as such, never lost to a metric.

Measured on dev 2026-09-19: `hitl_clarification_fallback_total` carries a
``reason`` label and was incremented without one, so the counter raised
INSIDE the classification, `hitl_classification_error` was logged, and the
caller's error fallback turned every answer that needed a clarification into
an EDIT. The behaviour under test is the decision that comes back, with the
counter labelled by why the clarification is needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.agents.services.hitl_classifier import (
    ClassificationResult,
    HitlResponseClassifier,
)

pytestmark = pytest.mark.unit

MODULE = "src.domains.agents.services.hitl_classifier"


def _classifier() -> HitlResponseClassifier:
    with (
        patch(f"{MODULE}.get_llm", return_value=MagicMock()),
        patch(
            f"{MODULE}.get_llm_config_for_agent",
            return_value=MagicMock(provider="openai", model="m", temperature=0.0),
        ),
    ):
        return HitlResponseClassifier()


@pytest.mark.parametrize(
    ("answer", "expected_reason"),
    [
        (
            ClassificationResult(
                decision="AMBIGUOUS",
                confidence=0.9,
                reasoning="unclear",
                clarification_question="Which one?",
            ),
            "classified",
        ),
        (
            ClassificationResult(
                decision="EDIT", confidence=0.95, reasoning="no params", edited_params={}
            ),
            "missing_params",
        ),
        (
            ClassificationResult(
                decision="EDIT", confidence=0.2, reasoning="unsure", edited_params=None
            ),
            "missing_params",
        ),
    ],
)
async def test_an_ambiguous_answer_comes_back_ambiguous_and_is_counted_by_reason(
    answer: ClassificationResult, expected_reason: str
) -> None:
    classifier = _classifier()
    with (
        patch(f"{MODULE}.get_structured_output", AsyncMock(return_value=answer)),
        patch("src.infrastructure.llm.instrumentation.create_instrumented_config", return_value={}),
        patch(
            "src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total"
        ) as counter,
    ):
        result = await classifier.classify("euh", [{"tool": "send_email"}])
    assert result.decision == "AMBIGUOUS"
    counter.labels.assert_called_once_with(reason=expected_reason)
    counter.labels.return_value.inc.assert_called_once()


async def test_an_edit_with_parameters_stays_an_edit_whatever_its_confidence() -> None:
    # Issue #60: « juste 2 » → EDIT {max_results: 2} is trusted even under the
    # confidence threshold; an EDIT without parameters is demoted above, so a
    # separate low-confidence demotion could never run and was removed.
    classifier = _classifier()
    kept = ClassificationResult(
        decision="EDIT", confidence=0.2, reasoning="ok", edited_params={"max_results": 2}
    )
    with (
        patch(f"{MODULE}.get_structured_output", AsyncMock(return_value=kept)),
        patch("src.infrastructure.llm.instrumentation.create_instrumented_config", return_value={}),
        patch(
            "src.infrastructure.observability.metrics_agents.hitl_clarification_fallback_total"
        ) as counter,
    ):
        result = await classifier.classify("juste 2", [{"tool": "search"}])
    assert result.decision == "EDIT"
    assert result.edited_params == {"max_results": 2}
    counter.labels.assert_not_called()
