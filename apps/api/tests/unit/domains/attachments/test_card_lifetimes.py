"""A chat card states the lifetime its file has NOW (ADR-319).

Pure half of the history read path: which cards a page names, and how each is
restated from its file — kept, re-deadlined, or gone. The batched read itself
is proven on PostgreSQL (``tests/integration/domains/attachments``).
"""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from src.domains.attachments.card_lifetimes import card_attachment_ids, with_current_lifetimes

pytestmark = pytest.mark.unit

KEPT = uuid.uuid4()
LIVE = uuid.uuid4()
GONE = uuid.uuid4()
DEADLINE = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
STORED = "2026-09-24T12:00:00+00:00"


def _image(card_id: uuid.UUID, expires_at: str | None = STORED) -> dict[str, object]:
    return {"url": f"/api/v1/attachments/{card_id}", "alt": "a cat", "expires_at": expires_at}


def _metadata() -> dict[str, object]:
    return {
        "run_id": "r1",
        "generated_images": [_image(KEPT), _image(GONE)],
        "generated_documents": [
            {
                "url": f"/api/v1/attachments/{LIVE}",
                "filename": "report.pdf",
                "doc_type": "pdf",
                "size_bytes": 10,
                "expires_at": STORED,
            }
        ],
    }


LIFETIMES = {KEPT: None, LIVE: DEADLINE}


def test_it_finds_every_card_of_a_page_whatever_its_key() -> None:
    assert card_attachment_ids([_metadata(), None, {"note": "no card"}]) == {KEPT, LIVE, GONE}


def test_a_kept_file_has_no_deadline_and_says_it_is_kept() -> None:
    restated = with_current_lifetimes(_metadata(), LIFETIMES)
    assert restated is not None
    kept_card = restated["generated_images"][0]
    assert (kept_card["expires_at"], kept_card["kept"], kept_card["gone"]) == (None, True, False)


def test_a_file_that_is_still_there_carries_its_current_deadline() -> None:
    restated = with_current_lifetimes(_metadata(), LIFETIMES)
    assert restated is not None
    document = restated["generated_documents"][0]
    assert document["expires_at"] == DEADLINE.isoformat()
    assert (document["kept"], document["gone"]) == (False, False)
    # Everything else of the card is left as written.
    assert (document["filename"], document["size_bytes"]) == ("report.pdf", 10)


def test_a_file_that_is_gone_says_so_instead_of_promising_a_deadline() -> None:
    restated = with_current_lifetimes(_metadata(), LIFETIMES)
    assert restated is not None
    gone_card = restated["generated_images"][1]
    assert (gone_card["gone"], gone_card["kept"]) == (True, False)
    assert gone_card["expires_at"] == STORED


def test_the_stored_metadata_is_never_mutated() -> None:
    metadata = _metadata()
    before = copy.deepcopy(metadata)
    with_current_lifetimes(metadata, LIFETIMES)
    assert metadata == before


def test_metadata_naming_no_card_comes_back_as_the_same_object() -> None:
    metadata = {"run_id": "r1", "psyche_state": {"mood": "calm"}}
    assert with_current_lifetimes(metadata, LIFETIMES) is metadata
    assert with_current_lifetimes(None, LIFETIMES) is None


@pytest.mark.parametrize(
    "card",
    [
        {"url": "https://elsewhere.example/api/v1/attachments/x", "expires_at": STORED},
        {"url": "/api/v1/attachments/not-a-uuid", "expires_at": STORED},
        {"url": f"/api/v1/attachments/{KEPT}"},  # a link, not a card: no deadline stated
        {"href": f"/api/v1/attachments/{KEPT}", "expires_at": STORED},
    ],
)
def test_what_is_not_a_file_card_is_left_alone(card: dict[str, object]) -> None:
    metadata = {"cards": [card]}
    assert card_attachment_ids([metadata]) == set()
    assert with_current_lifetimes(metadata, LIFETIMES) is metadata


def test_a_url_with_a_query_string_still_names_its_file() -> None:
    card = _image(KEPT)
    card["url"] = f"/api/v1/attachments/{KEPT}?v=2"
    assert card_attachment_ids([{"generated_images": [card]}]) == {KEPT}


def test_a_card_buried_past_the_bound_is_not_walked() -> None:
    deep: dict[str, object] = {"card": _image(KEPT)}
    for _ in range(6):
        deep = {"nested": deep}
    assert card_attachment_ids([deep]) == set()


def test_a_deadline_in_the_future_is_restated_to_the_row_s_value() -> None:
    later = DEADLINE + timedelta(days=1)
    restated = with_current_lifetimes({"generated_images": [_image(LIVE)]}, {LIVE: later})
    assert restated is not None
    assert restated["generated_images"][0]["expires_at"] == later.isoformat()
