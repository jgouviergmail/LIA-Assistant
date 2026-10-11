"""Rejected portraits disclose actionable indices, never personal passages."""

import json

import pytest

from src.domains.journals.consolidation_output import (
    PortraitClaim,
    PortraitSupport,
    validate_portrait_claims,
)
from src.domains.journals.portrait_review import PortraitReviewInput, approve_portrait_review

pytestmark = pytest.mark.unit


def test_rejected_source_reports_claim_and_support_without_private_words():
    private = "A private factual detail."
    claim = PortraitClaim(
        facet="context",
        text="His working context helps situate advice.",
        supports=[PortraitSupport(source="memories", quote=private)],
    )
    with pytest.raises(ValueError) as caught:
        validate_portrait_claims([claim], [], {"memories": f"- [personal] {private}"})
    details = getattr(caught.value, "details", None)
    assert details == {
        "phase": "source_proof",
        "source": "memories",
        "exact_item": False,
        "has_item_prefix": False,
        "contains_ellipsis": False,
        "support_index": 0,
        "claim_index": 0,
    }
    assert private not in str(caught.value)
    assert private not in json.dumps(details)


def test_semantic_refusal_preserves_every_failed_axis_and_its_index():
    candidate = PortraitReviewInput(
        [{"text": "Private candidate one"}, {"text": "Private candidate two"}], "unused-test-digest"
    )
    verdicts = [
        {
            "index": index,
            "supported": True,
            "scope_preserved": index == 0,
            "uncertainty_preserved": True,
            "synthesized": index == 1,
        }
        for index in (1, 0)
    ]
    with pytest.raises(ValueError) as caught:
        approve_portrait_review(json.dumps({"reviews": verdicts}), candidate)
    details = getattr(caught.value, "details", None)
    assert details == {
        "phase": "semantic_review",
        "rejected": [
            {"claim_index": 0, "criteria": ["synthesized"]},
            {"claim_index": 1, "criteria": ["scope_preserved"]},
        ],
    }
    assert "Private candidate" not in json.dumps(details)
    assert "Private candidate" not in str(caught.value)
