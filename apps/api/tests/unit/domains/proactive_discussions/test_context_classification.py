"""Semantic topic labels may only restrict already offered evidence, never introduce new facts."""

from datetime import UTC, datetime

import pytest

from src.domains.proactive_discussions.contextualization.classification import classified_evidence
from src.domains.proactive_discussions.llm_contracts import ContextInterpretation
from src.domains.shared.discussion_sources import DiscussionEvidence, SourceKey

pytestmark = pytest.mark.unit


def fact():
    return DiscussionEvidence(
        reference="calendar:one",
        source=SourceKey.CALENDAR,
        object_id="one",
        version="v1",
        observed_at=datetime.now(UTC),
        excerpt="Fictional appointment",
    )


def test_an_unclassified_reference_leaves_the_pass_never_read_as_unlabelled() -> None:
    # Production-shaped 2026-10-21: one forgotten label used to refuse the whole
    # answer, and the run, whatever model wrote it.
    output = ContextInterpretation.model_validate(
        {
            "proposals": [],
            "classifications": [],
            "resolution": {"status": "insufficient", "reason": "not enough context"},
        }
    )
    assert classified_evidence(output, (fact(),)) == ()


def test_a_reference_classified_twice_takes_both_labels_and_strangers_are_ignored() -> None:
    source = fact()
    output = ContextInterpretation.model_validate(
        {
            "proposals": [],
            "classifications": [
                {"reference": source.reference, "sensitive_topics": ["health"]},
                {"reference": source.reference, "sensitive_topics": ["finances"]},
                {"reference": "calendar:never-offered", "sensitive_topics": []},
            ],
            "resolution": {"status": "insufficient", "reason": "not enough context"},
        }
    )
    (result,) = classified_evidence(output, (source,))
    assert result.sensitive_topics == ("finances", "health")


def test_topic_labels_only_add_restrictions_without_changing_native_identity_or_content() -> None:
    source = fact()
    output = ContextInterpretation.model_validate(
        {
            "proposals": [],
            "classifications": [{"reference": source.reference, "sensitive_topics": ["health"]}],
            "resolution": {"status": "ready", "references": [source.reference]},
        }
    )
    result = classified_evidence(output, (source,))
    assert result[0].sensitive_topics == ("health",)
    assert result[0].version == source.version and result[0].excerpt == source.excerpt
