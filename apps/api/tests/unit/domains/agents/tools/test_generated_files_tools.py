"""The generated-files lookup — found again, and SHOWN as the chat's cards (ADR-318).

The gallery statement is tested with the gallery (``tests/unit/domains/attachments``);
here the TOOL is: the families merged newest first under one cap with the EXACT
total beside it, every file queued as the card its producer would have queued
under the CONVERSATION's key, only files that can still be opened asked for, the
period read as whole days, and every refusal typed.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.domains.agents.generated_file.catalogue_manifests import (
    GENERATED_FILE_FAMILIES,
    GENERATED_FILE_ORIGINS,
    GENERATED_FILES_QUERY_DESCRIPTION,
)
from src.domains.agents.tools import generated_files_tools
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.attachments.gallery_queries import GalleryFilters
from src.domains.attachments.models import AttachmentOrigin
from src.domains.attachments.origin import GENERATED_ORIGINS
from tests.helpers.runtime_context import make_tool_runtime

pytestmark = pytest.mark.unit

PARIS = ZoneInfo("Europe/Paris")
CONVERSATION = "7d6c3b9e-2f1a-4c5d-8e9f-0a1b2c3d4e5f"
BASE = datetime(2026, 9, 24, 8, 0, tzinfo=UTC)


def _file(
    origin: AttachmentOrigin, minutes: int, name: str, title: str | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        origin=origin.value,
        title=title,
        original_filename=name,
        created_at=BASE + timedelta(minutes=minutes),
        expires_at=BASE + timedelta(hours=24, minutes=minutes),
        file_size=2048,
        shared_by_name=None,
    )


class _Gallery:
    """The gallery service, faked at its own boundary: one page per origin."""

    def __init__(self, pages: dict[AttachmentOrigin, tuple[list[SimpleNamespace], int]]) -> None:
        self.pages = pages
        self.asked: list[GalleryFilters] = []

    async def list_generated(
        self, user_id: uuid.UUID, filters: GalleryFilters
    ) -> tuple[list[SimpleNamespace], int, int]:
        self.asked.append(filters)
        rows, total = self.pages.get(filters.origin, ([], 0))
        return rows[: filters.limit], total, 0


async def _call(
    gallery: _Gallery, **kwargs: object
) -> tuple[UnifiedToolOutput, MagicMock, MagicMock]:
    @asynccontextmanager
    async def session() -> AsyncIterator[MagicMock]:
        yield MagicMock()

    images, documents = MagicMock(), MagicMock()
    with (
        patch.object(generated_files_tools, "AttachmentService", return_value=gallery),
        patch.object(generated_files_tools, "get_db_context", session),
        patch.object(generated_files_tools, "store_pending_image", images),
        patch.object(generated_files_tools, "store_pending_document", documents),
    ):
        output = await generated_files_tools.find_generated_files_tool.coroutine(
            runtime=make_tool_runtime(
                store=object(),
                timezone="Europe/Paris",
                conversation_id=CONVERSATION,
                thread_id="sub-agent-thread",
            ),
            **kwargs,
        )
    return output, images, documents


class TestFoundAndShown:
    async def test_the_families_merge_newest_first_under_one_cap(self) -> None:
        cat = _file(AttachmentOrigin.GENERATED_IMAGE, 30, "generated_cat.png", "A cat")
        report = _file(AttachmentOrigin.GENERATED_DOCUMENT, 20, "Quarterly report.pdf")
        page = _file(AttachmentOrigin.BROWSER_SCREENSHOT, 10, "browser_1.jpg")
        gallery = _Gallery(
            {
                AttachmentOrigin.GENERATED_IMAGE: ([cat], 4),
                AttachmentOrigin.GENERATED_DOCUMENT: ([report], 2),
                AttachmentOrigin.BROWSER_SCREENSHOT: ([page], 1),
            }
        )

        output, _images, _documents = await _call(gallery, max_results=2)

        data = output.structured_data or {}
        assert [item["title"] for item in data["files"]] == ["A cat", "Quarterly report.pdf"]
        assert (data["total"], data["shown"]) == (7, 2)
        assert "5 older matches are counted, not shown" in output.message
        assert {filters.origin for filters in gallery.asked} == set(GENERATED_ORIGINS)

    async def test_each_file_is_queued_as_its_producer_s_card_under_the_conversation(
        self,
    ) -> None:
        cat = _file(AttachmentOrigin.GENERATED_IMAGE, 30, "generated_cat.png", "A cat")
        report = _file(AttachmentOrigin.GENERATED_DOCUMENT, 20, "Quarterly report.PDF")
        gallery = _Gallery(
            {
                AttachmentOrigin.GENERATED_IMAGE: ([cat], 1),
                AttachmentOrigin.GENERATED_DOCUMENT: ([report], 1),
            }
        )

        _output, images, documents = await _call(gallery)

        images.assert_called_once_with(
            CONVERSATION,
            url=f"/api/v1/attachments/{cat.id}",
            alt_text="A cat",
            expires_at=cat.expires_at.isoformat(),
        )
        conversation, card = documents.call_args.args
        assert conversation == CONVERSATION
        assert (card.doc_type, card.filename) == ("pdf", "Quarterly report.PDF")

    async def test_only_what_can_still_be_opened_is_asked_for(self) -> None:
        gallery = _Gallery({})
        before = datetime.now(UTC)

        await _call(gallery, family="image")

        (filters,) = gallery.asked
        assert filters.origin is AttachmentOrigin.GENERATED_IMAGE
        assert filters.expires_after is not None and filters.expires_after >= before

    async def test_a_day_is_the_person_s_whole_day(self) -> None:
        gallery = _Gallery({})

        await _call(gallery, family="document", start_date="2026-09-21", end_date="2026-09-21")

        (filters,) = gallery.asked
        assert filters.created_after == datetime(2026, 9, 21, tzinfo=PARIS)
        assert filters.created_before == datetime(2026, 9, 22, tzinfo=PARIS) - timedelta(
            microseconds=1
        )

    async def test_nothing_found_says_how_long_files_are_kept(self) -> None:
        output, images, documents = await _call(_Gallery({}))

        assert output.success
        assert (output.structured_data or {})["total"] == 0
        assert f"{settings.attachments_ttl_hours} hours" in output.message
        images.assert_not_called()
        documents.assert_not_called()

    async def test_the_ceiling_is_the_setting(self) -> None:
        gallery = _Gallery({})

        await _call(gallery, family="image", max_results=10_000)

        assert gallery.asked[0].limit == settings.generated_files_search_max_results


class TestRefusals:
    async def test_an_unknown_family(self) -> None:
        output, _images, _documents = await _call(_Gallery({}), family="video")

        assert output.error_code == ToolErrorCode.INVALID_PARAM_VALUE.value

    async def test_an_unreadable_day(self) -> None:
        output, _images, _documents = await _call(_Gallery({}), start_date="hier")

        assert output.error_code == ToolErrorCode.INVALID_INPUT.value


class TestTheFamiliesAreTheGallerys:
    def test_every_generated_origin_has_one_family(self) -> None:
        assert set(GENERATED_FILE_ORIGINS.values()) == set(GENERATED_ORIGINS)
        assert tuple(GENERATED_FILE_ORIGINS) == GENERATED_FILE_FAMILIES


def test_the_react_schema_publishes_the_manifest_s_wording() -> None:
    description = generated_files_tools.find_generated_files_tool.args_schema.model_fields[
        "query"
    ].description

    assert description is not None and description.startswith(GENERATED_FILES_QUERY_DESCRIPTION)
