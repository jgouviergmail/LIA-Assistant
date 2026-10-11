"""Reduced epistemic certainty must retire potentially unqualified derived prose."""

import pytest

from src.domains.journals.evidence import _invalidates_portrait

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("previous", "current", "invalidates"),
    [
        ("high", "medium", True),
        ("high", "low", True),
        ("medium", "high", False),
        ("medium", "medium", False),
    ],
)
def test_only_confidence_downgrades_retire_existing_portrait(previous, current, invalidates):
    assert (
        _invalidates_portrait({"confidence": current}, False, False, None, previous, current)
        is invalidates
    )


def test_positive_confirmation_preserves_existing_words():
    assert not _invalidates_portrait(
        {"evidence_count": 2}, False, True, "evidence", "medium", "medium"
    )
