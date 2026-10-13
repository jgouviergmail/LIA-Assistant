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


def test_pending_work_survives_api_serialization_and_an_old_receipt_is_ignored() -> None:
    # A row compiled under the former semantic review carries a receipt this version
    # no longer reads: it is dropped at the boundary, never a crash (ADR-343, 2026-10-12 b).
    stored = {
        "version": 1,
        "journal_entries": 1,
        "sources": {},
        "portrait_pending": True,
        "portrait_review": {"policy": "old", "digest": "a" * 64, "model": "m", "reviewed_at": 1.0},
    }
    read = provenance_of(stored)
    assert read is not None and read.portrait_pending is True
    assert "portrait_review" not in read.model_dump()


def test_legacy_provenance_does_not_invent_a_pending_status() -> None:
    read = provenance_of({"version": 1, "journal_entries": 0, "sources": {}})
    assert read is not None
    assert read.portrait_pending is None


def test_omitted_incomplete_sources_survive_the_api_boundary() -> None:
    source = {"status": "empty", "used": 0, "total": 2, "omitted_incomplete": 2}
    read = provenance_of(
        {"version": 1, "journal_entries": 0, "sources": {"relation_debriefs": source}}
    )
    assert read is not None
    assert read.model_dump()["sources"]["relation_debriefs"]["omitted_incomplete"] == 2
