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
