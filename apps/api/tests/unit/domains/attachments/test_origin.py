"""Where a file came from (ADR-279).

Every file the assistant produced — an image, a document, a browser screenshot —
was stored as an ``Attachment`` indistinguishable from something the person
uploaded themselves. It lived in the conversation that produced it and nowhere
else: nothing listed them, nothing let a person download one back a day later,
and a conversation reset deleted the lot.

The column that fixes that is ``origin``, and the rules around it are the ones
this module pins:

- the vocabulary is CLOSED and every value is decided, so a fourth producer
  cannot arrive as an unlabelled row;
- ``upload`` is what a PERSON put in, and it is the only origin a conversation
  reset removes — a file LIA produced survives the conversation it was produced
  in (owner arbitration, 2026-09-10);
- the backfill reads the SHAPE the producers left behind, because the column
  did not exist when those rows were written.
"""

from __future__ import annotations

import pytest

from src.domains.attachments.models import AttachmentContentType, AttachmentOrigin
from src.domains.attachments.origin import (
    GENERATED_ORIGINS,
    backfilled_origin,
    content_type_of,
    is_generated,
)

pytestmark = pytest.mark.unit


class TestTheVocabularyIsClosedAndDecided:
    def test_every_origin_is_either_an_upload_or_generated(self) -> None:
        decided = {AttachmentOrigin.UPLOAD} | GENERATED_ORIGINS
        assert decided == set(AttachmentOrigin)

    def test_what_the_person_put_in_is_not_generated(self) -> None:
        assert is_generated(AttachmentOrigin.UPLOAD) is False

    @pytest.mark.parametrize(
        "origin",
        [
            AttachmentOrigin.GENERATED_IMAGE,
            AttachmentOrigin.GENERATED_DOCUMENT,
            AttachmentOrigin.BROWSER_SCREENSHOT,
        ],
    )
    def test_what_lia_produced_is_generated(self, origin: AttachmentOrigin) -> None:
        assert is_generated(origin) is True

    def test_a_raw_string_is_accepted_because_the_column_stores_one(self) -> None:
        assert is_generated("generated_image") is True
        assert is_generated("upload") is False

    def test_an_unknown_value_is_never_read_as_generated(self) -> None:
        """A value nobody declared must not silently join the gallery."""
        assert is_generated("who_knows") is False
        assert is_generated(None) is False


class TestEachOriginKnowsItsContentType:
    @pytest.mark.parametrize(
        ("origin", "expected"),
        [
            (AttachmentOrigin.GENERATED_IMAGE, AttachmentContentType.IMAGE),
            (AttachmentOrigin.BROWSER_SCREENSHOT, AttachmentContentType.IMAGE),
            (AttachmentOrigin.GENERATED_DOCUMENT, AttachmentContentType.DOCUMENT),
        ],
    )
    def test_a_generated_origin_declares_what_it_produces(
        self, origin: AttachmentOrigin, expected: str
    ) -> None:
        assert content_type_of(origin) == expected

    def test_an_upload_declares_nothing_it_can_be_either(self) -> None:
        assert content_type_of(AttachmentOrigin.UPLOAD) is None


class TestTheBackfillReadsWhatTheProducersLeftBehind:
    """The column did not exist when these rows were written, so the migration
    reads the SHAPE each producer stamped — never a guess."""

    def test_an_image_named_by_the_image_tool(self) -> None:
        assert (
            backfilled_origin("generated_a1b2c3.png", AttachmentContentType.IMAGE)
            == AttachmentOrigin.GENERATED_IMAGE
        )

    def test_a_browser_screenshot_named_by_the_stream(self) -> None:
        assert (
            backfilled_origin("browser_a1b2c3.jpg", AttachmentContentType.IMAGE)
            == AttachmentOrigin.BROWSER_SCREENSHOT
        )

    def test_anything_else_stays_an_upload(self) -> None:
        """Documents carry NO marker of their own — the generator names them
        after the person's request — so a document row can only be recognised
        by the message metadata that points at it. Everything the shape cannot
        prove stays what it always was."""
        assert (
            backfilled_origin("holiday.jpg", AttachmentContentType.IMAGE) == AttachmentOrigin.UPLOAD
        )
        assert (
            backfilled_origin("rapport.pdf", AttachmentContentType.DOCUMENT)
            == AttachmentOrigin.UPLOAD
        )

    def test_the_browser_prefix_does_not_leak_onto_a_document(self) -> None:
        """A person's own `browser_notes.txt` is not a screenshot."""
        assert (
            backfilled_origin("browser_notes.txt", AttachmentContentType.DOCUMENT)
            == AttachmentOrigin.UPLOAD
        )

    def test_a_prefix_in_the_MIDDLE_of_a_name_proves_nothing(self) -> None:
        assert (
            backfilled_origin("my_generated_pic.png", AttachmentContentType.IMAGE)
            == AttachmentOrigin.UPLOAD
        )
