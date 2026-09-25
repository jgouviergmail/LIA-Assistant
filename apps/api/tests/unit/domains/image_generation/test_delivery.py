"""A queued image card is delivered WHOEVER queued it (ADR-318).

The image tool used to be the only producer of image cards, so both touch
points of the stream sat behind ``image_generation_enabled``. The generated-files
lookup queues image cards too — a browser screenshot, an image kept from before
generation was switched off — and a card queued behind a closed gate is never
shown and never freed. The archived card and the live one carry one shape.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.image_generation.delivery import attach_archived_images, attach_done_images
from src.domains.image_generation.image_store import (
    GENERATED_IMAGES_METADATA_KEY,
    get_and_clear_pending_images,
    store_pending_image,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def conversation() -> Iterator[str]:
    key = str(uuid.uuid4())
    yield key
    get_and_clear_pending_images(key)


class TestTheCardIsDelivered:
    def test_whatever_the_generation_flag(self, conversation: str) -> None:
        archived: dict[str, Any] = {}
        done: dict[str, Any] = {}
        with patch("src.core.config.settings.image_generation_enabled", False):
            store_pending_image(
                conversation,
                url="/api/v1/attachments/screenshot",
                alt_text="The page I visited",
                expires_at="2026-09-26T08:00:00+00:00",
            )
            attach_archived_images(archived, conversation)
            attach_done_images(done, conversation)

        assert done[GENERATED_IMAGES_METADATA_KEY] == [
            {
                "url": "/api/v1/attachments/screenshot",
                "alt": "The page I visited",
                "expires_at": "2026-09-26T08:00:00+00:00",
            }
        ]
        assert archived[GENERATED_IMAGES_METADATA_KEY] == done[GENERATED_IMAGES_METADATA_KEY]

    def test_the_done_chunk_frees_the_queue(self, conversation: str) -> None:
        store_pending_image(conversation, url="/api/v1/attachments/a", alt_text="A cat")
        attach_done_images({}, conversation)
        again: dict[str, Any] = {}

        attach_done_images(again, conversation)

        assert again == {}

    def test_nothing_pending_adds_nothing(self, conversation: str) -> None:
        metadata: dict[str, Any] = {}

        attach_archived_images(metadata, conversation)
        attach_done_images(metadata, conversation)

        assert metadata == {}
