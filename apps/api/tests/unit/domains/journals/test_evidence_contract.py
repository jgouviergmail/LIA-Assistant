"""Confidence belongs to repeated evidence for the current rule revision."""

import pytest

from src.domains.journals.service import _clamp_confidence

pytestmark = pytest.mark.unit


def test_one_reaction_does_not_certify_repeated_evidence():
    assert _clamp_confidence("high", "L1", 1, "update") == "medium"


def test_two_reactions_can_certify_an_uncontradicted_rule():
    assert _clamp_confidence("high", "L1", 2, "update") == "high"
