"""What the portrait was compiled from is TYPED, never a bare dict (part B).

The provenance is JSON on the user row; the API reads it through one
tolerant door — a stored shape this version cannot read is None, so the
settings page renders nothing rather than the page crashing on a JSON a
future version wrote.
"""

from __future__ import annotations

import pytest

from src.domains.journals.schemas import PortraitProvenance, provenance_of

pytestmark = pytest.mark.unit


def test_a_stored_provenance_is_read_as_the_typed_shape() -> None:
    stored = {
        "version": 1,
        "journal_entries": 12,
        "sources": {
            "memories": {"status": "used", "used": 34, "total": 51},
            "habits": {"status": "disabled", "used": 0, "total": 0},
        },
    }
    read = provenance_of(stored)
    assert isinstance(read, PortraitProvenance)
    assert read.journal_entries == 12
    assert read.sources["memories"].total == 51
    assert read.sources["habits"].status == "disabled"


def test_nothing_or_an_unreadable_shape_is_none_never_a_crash() -> None:
    assert provenance_of(None) is None
    assert provenance_of({"version": 99, "sources": "not a mapping"}) is None
    assert provenance_of({"version": 1, "journal_entries": -1, "sources": {}}) is None


def test_pending_work_and_review_receipt_survive_api_serialization() -> None:
    receipt = {
        "policy": "natural-test-policy",
        "digest": "a" * 64,
        "model": "offline-model",
        "reviewed_at": 1791360000.5,
    }
    stored = {
        "version": 1,
        "journal_entries": 1,
        "sources": {},
        "portrait_pending": True,
        "portrait_review": receipt,
    }
    read = provenance_of(stored)
    assert read is not None and read.portrait_pending is True
    assert read.portrait_review is not None
    assert read.model_dump()["portrait_review"] == receipt
    assert read.model_dump()["portrait_pending"] is True


@pytest.mark.parametrize("receipt", [{"digest": "invalid"}, {"policy": "x", "digest": "a" * 64}])
def test_unreadable_review_receipt_uses_the_existing_lenient_boundary(receipt) -> None:
    assert (
        provenance_of(
            {"version": 1, "journal_entries": 0, "sources": {}, "portrait_review": receipt}
        )
        is None
    )


def test_legacy_provenance_does_not_invent_a_review_or_pending_status() -> None:
    read = provenance_of({"version": 1, "journal_entries": 0, "sources": {}})
    assert read is not None
    assert read.portrait_review is None
    assert read.portrait_pending is None


def test_omitted_incomplete_sources_survive_the_api_boundary() -> None:
    source = {"status": "empty", "used": 0, "total": 2, "omitted_incomplete": 2}
    read = provenance_of(
        {"version": 1, "journal_entries": 0, "sources": {"relation_debriefs": source}}
    )
    assert read is not None
    assert read.model_dump()["sources"]["relation_debriefs"]["omitted_incomplete"] == 2
