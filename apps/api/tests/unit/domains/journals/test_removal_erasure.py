"""A removal is observed as an erasure: no stored claim rests on a removed entry."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from src.domains.journals.removal_commands import _erasure_observed

pytestmark = pytest.mark.unit

STAMP = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)


def _claim(text: str, source: str, placement: str = "full") -> dict:
    return {"text": text, "placement": placement, "supports": [{"source": source}]}


def test_no_words_means_nothing_to_erase_whatever_the_provenance_says() -> None:
    # An explicit empty compilation stamps its date and keeps `claims: []`: a removal
    # after it must not be refused for a portrait that holds no words.
    assert _erasure_observed((None, None, STAMP, {"claims": []}), {str(uuid4())})
    assert _erasure_observed((None, None, None, None), None)


def test_words_with_no_readable_claims_must_have_been_wiped() -> None:
    assert not _erasure_observed(("legacy prose", None, STAMP, None), None)
    assert not _erasure_observed(("legacy prose", None, STAMP, {"claims": []}), None)


def test_kept_claims_must_rest_on_nothing_removed_and_match_their_formats() -> None:
    gone, kept = str(uuid4()), str(uuid4())
    on_kept = _claim("Rests on another entry.", f"journal:{kept}")
    on_memory = _claim("Rests on a memory.", "memories", placement="brief")
    good = (on_kept["text"], on_memory["text"], STAMP, {"claims": [on_kept, on_memory]})
    assert _erasure_observed(good, {gone})
    # Every journal-backed claim must have gone with the whole journal.
    assert not _erasure_observed(good, None)
    # A claim still resting on the removed entry.
    on_gone = _claim("Rests on the removed entry.", f"journal:{gone}")
    assert not _erasure_observed((on_gone["text"], None, STAMP, {"claims": [on_gone]}), {gone})
    # A format whose text does not match its claims.
    assert not _erasure_observed(
        (on_kept["text"], "stray brief", STAMP, {"claims": [on_kept]}), {gone}
    )
    assert not _erasure_observed(
        (None, on_memory["text"], STAMP, {"claims": [on_kept, on_memory]}), {gone}
    )
    # Words that remain keep their compilation date.
    assert not _erasure_observed((on_kept["text"], None, None, {"claims": [on_kept]}), {gone})
