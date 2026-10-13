"""Rejected portraits disclose actionable indices, never personal passages."""

import json

import pytest

from src.domains.journals.consolidation_output import (
    PortraitClaim,
    PortraitSupport,
    validate_portrait_claims,
)

pytestmark = pytest.mark.unit


def test_rejected_source_reports_claim_and_support_without_private_words():
    private = "A private factual detail."
    claim = PortraitClaim(
        facet="context",
        text="His working context helps situate advice.",
        supports=[PortraitSupport(source="memories", quote=private)],
    )
    dropped: list[dict] = []
    assert (
        validate_portrait_claims(
            [claim], [], {"memories": f"- [personal] {private}"}, dropped=dropped
        )
        == []
    )
    assert dropped == [
        {
            "claim_index": 0,
            "reason": "portrait passage is not a complete authorized source item",
            "phase": "source_proof",
            "source": "memories",
            "exact_item": False,
            "has_item_prefix": False,
            "support_index": 0,
        }
    ]
    assert private not in json.dumps(dropped)
