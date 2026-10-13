"""A test-side view of what a claim resolves to: the evidence the publication would keep."""

from __future__ import annotations

from typing import Any

from src.domains.journals.consolidation_output import PortraitClaim, validate_portrait_claims
from src.domains.journals.models import JournalEntry


def evidence_view(
    claims: list[PortraitClaim], entries: list[JournalEntry], sections: dict[str, str]
) -> list[dict[str, Any]]:
    """Index, facet, text, resolved supports and the provisional flag of every proven claim."""
    return [
        {
            "index": index,
            "facet": supported.claim.facet,
            "text": supported.claim.text,
            "supports": supported.evidence,
            "provisional": supported.provisional,
        }
        for index, supported in enumerate(validate_portrait_claims(claims, entries, sections))
    ]
