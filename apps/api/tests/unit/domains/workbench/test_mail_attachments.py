"""A mail attachment downloaded by the person's own hand (ADR-369, Task 4.4).

One download at a time per account — a claim by its owner token, expiring on
its own — because the client reads the file into memory up to the published
ceiling, which it is HANDED: a part whose listed size passes it is refused
before it is read. Our own throttle never fails a download: an unreachable
cache lets it through. A Gmail handle expires between two reads, so the name
travels with it; a name two parts share is a stale handle.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import REDIS_KEY_WORKBENCH_DOWNLOAD_PREFIX
from src.core.exceptions import BaseAPIException
from src.domains.attachments.preview import DocumentPreview
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentContent,
    EmailAttachmentTooLargeError,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import downloads, mail_attachments
from src.domains.workbench.errors import (
    NOT_SUPPORTED_BY_PROVIDER,
    PROVIDER_RATE_LIMITED,
    TOO_LARGE,
)
from src.domains.workbench.mail_projection import attachments_of
from src.domains.workbench.schemas.mail import AttachmentRequest
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
KEY = f"{REDIS_KEY_WORKBENCH_DOWNLOAD_PREFIX}{USER}"
PDF = EmailAttachmentContent(filename="budget.pdf", mime_type="application/pdf", data=b"%PDF")


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name=None
        )

    return patch.object(mail_attachments, "open_tool_client", opened)


def _cache(redis: FakeRedis | Exception) -> Any:
    cache = (
        AsyncMock(side_effect=redis)
        if isinstance(redis, Exception)
        else AsyncMock(return_value=redis)
    )
    return patch.object(downloads, "get_redis_cache", cache)


def _impatient(seconds: float) -> Any:
    """A wait short enough for a test, its polling shorter still."""
    return patch.multiple(
        downloads, WORKBENCH_PREVIEW_WAIT_SECONDS=seconds, WORKBENCH_TRANSFER_POLL_SECONDS=0.01
    )


def _request() -> AttachmentRequest:
    return AttachmentRequest(message_id="m1", attachment_id="ANGj", filename="budget.pdf")


class TestTheDownload:
    async def test_it_is_read_under_the_published_ceiling_and_the_claim_released(self) -> None:
        redis = FakeRedis()
        client = MagicMock(download_attachment=AsyncMock(return_value=PDF))
        with _door(client), _cache(redis):
            content = await mail_attachments.download_attachment(USER, _request())

        assert content == PDF
        client.download_attachment.assert_awaited_once_with(
            "m1",
            attachment_id="ANGj",
            filename="budget.pdf",
            max_bytes=settings.workbench_download_max_bytes,
        )
        assert KEY not in redis.store

    async def test_a_second_one_while_the_first_runs_is_asked_to_wait(self) -> None:
        redis = FakeRedis()
        redis.store[KEY] = "another download's token"
        client = MagicMock(download_attachment=AsyncMock(return_value=PDF))
        with _door(client), _cache(redis), pytest.raises(BaseAPIException) as refused:
            await mail_attachments.download_attachment(USER, _request())

        assert refused.value.status_code == 429
        assert refused.value.detail["code"] == "provider_rate_limited"
        client.download_attachment.assert_not_awaited()
        assert redis.store[KEY] == "another download's token", "never released by another"

    @pytest.mark.parametrize("cache", [ConnectionError("down"), FakeRedis(broken=True)])
    async def test_an_unreachable_cache_never_fails_a_download(
        self, cache: FakeRedis | Exception
    ) -> None:
        client = MagicMock(download_attachment=AsyncMock(return_value=PDF))
        with _door(client), _cache(cache):
            assert await mail_attachments.download_attachment(USER, _request()) == PDF

    async def test_a_part_over_the_ceiling_is_refused_with_it(self) -> None:
        redis = FakeRedis()
        too_large = EmailAttachmentTooLargeError(size=30, max_bytes=20)
        client = MagicMock(download_attachment=AsyncMock(side_effect=too_large))
        with _door(client), _cache(redis), pytest.raises(BaseAPIException) as refused:
            await mail_attachments.download_attachment(USER, _request())

        assert refused.value.detail == {"code": "too_large", "max_bytes": 20}
        assert KEY not in redis.store

    async def test_a_name_two_parts_share_is_a_stale_handle(self) -> None:
        ambiguous = EmailAttachmentAmbiguousError("budget.pdf", [{}, {}])
        client = MagicMock(download_attachment=AsyncMock(side_effect=ambiguous))
        with _door(client), _cache(FakeRedis()), pytest.raises(BaseAPIException) as refused:
            await mail_attachments.download_attachment(USER, _request())

        assert refused.value.detail == {"code": "stale_handle"}


class TestThePreview:
    WORD = EmailAttachmentContent(
        filename="note.txt", mime_type="application/octet-stream", data=b"Hello"
    )

    def _client(self, content: EmailAttachmentContent) -> MagicMock:
        return MagicMock(download_attachment=AsyncMock(return_value=content))

    async def test_it_reads_under_the_published_ceiling(self) -> None:
        client = self._client(self.WORD)
        request = AttachmentRequest(message_id="m1", attachment_id="a1", filename="note.txt")

        with _door(client), _cache(FakeRedis()):
            await mail_attachments.preview_attachment(USER, request)

        client.download_attachment.assert_awaited_once_with(
            "m1",
            attachment_id="a1",
            filename="note.txt",
            max_bytes=settings.workbench_download_max_bytes,
        )

    async def test_what_it_is_comes_from_its_name_when_its_type_says_nothing(self) -> None:
        request = AttachmentRequest(message_id="m1", filename="note.txt")

        with _door(self._client(self.WORD)), _cache(FakeRedis()):
            shown = await mail_attachments.preview_attachment(USER, request)

        assert shown == DocumentPreview(b"Hello", "text/plain", False)

    async def test_the_name_the_client_gives_wins_over_the_one_asked(self) -> None:
        content = EmailAttachmentContent(
            filename="real.txt", mime_type="application/octet-stream", data=b"Hello"
        )
        request = AttachmentRequest(message_id="m1", filename="asked.bin")

        with _door(self._client(content)), _cache(FakeRedis()):
            shown = await mail_attachments.preview_attachment(USER, request)

        assert shown.content == b"Hello"

    async def test_what_nothing_can_show_is_refused(self) -> None:
        content = EmailAttachmentContent(
            filename="setup.exe", mime_type="application/octet-stream", data=b"MZ"
        )
        request = AttachmentRequest(message_id="m1", filename="setup.exe")

        with (
            _door(self._client(content)),
            _cache(FakeRedis()),
            pytest.raises(BaseAPIException) as refused,
        ):
            await mail_attachments.preview_attachment(USER, request)

        assert refused.value.detail["code"] == NOT_SUPPORTED_BY_PROVIDER

    async def test_a_part_past_the_ceiling_is_said_too_large(self) -> None:
        client = MagicMock(
            download_attachment=AsyncMock(
                side_effect=EmailAttachmentTooLargeError(size=2, max_bytes=1)
            )
        )
        request = AttachmentRequest(message_id="m1", filename="note.txt")

        with _door(client), _cache(FakeRedis()), pytest.raises(BaseAPIException) as refused:
            await mail_attachments.preview_attachment(USER, request)

        assert refused.value.detail["code"] == TOO_LARGE

    async def test_it_waits_for_the_transfer_under_way_rather_than_failing(self) -> None:
        """A read the page dropped runs on server side: the one after it must not be refused."""
        redis = FakeRedis()
        await redis.set(KEY, "someone-else")
        client = self._client(self.WORD)
        request = AttachmentRequest(message_id="m1", filename="note.txt")

        async def finished() -> None:
            await asyncio.sleep(0.05)
            del redis.store[KEY]

        with _door(client), _cache(redis), _impatient(1.0):
            shown, _ = await asyncio.gather(
                mail_attachments.preview_attachment(USER, request), finished()
            )

        assert shown.content == b"Hello"
        assert KEY not in redis.store

    async def test_its_wait_has_an_end(self) -> None:
        redis = FakeRedis()
        await redis.set(KEY, "someone-else")
        client = self._client(self.WORD)
        request = AttachmentRequest(message_id="m1", filename="note.txt")

        with (
            _door(client),
            _cache(redis),
            _impatient(0.05),
            pytest.raises(BaseAPIException) as refused,
        ):
            await mail_attachments.preview_attachment(USER, request)

        assert refused.value.detail["code"] == PROVIDER_RATE_LIMITED
        client.download_attachment.assert_not_awaited()
        assert redis.store[KEY] == "someone-else"


class TestWhatThePageIsTold:
    @pytest.mark.parametrize(
        ("name", "mime_type", "offered"),
        [
            ("note.md", "application/octet-stream", True),
            ("budget.xlsx", "application/vnd.ms-excel", True),
            ("photo.png", "image/png", True),
            ("logo.svg", "image/svg+xml", False),
            ("setup.exe", "application/octet-stream", False),
        ],
    )
    def test_each_part_says_whether_it_can_be_read(
        self, name: str, mime_type: str, offered: bool
    ) -> None:
        raw = {"attachments": [{"attachmentId": "a1", "filename": name, "mimeType": mime_type}]}

        listed = attachments_of(raw, ConnectorType.MICROSOFT_OUTLOOK)

        assert listed[0].previewable is offered

    def test_a_gmail_part_goes_by_its_place_in_the_message(self) -> None:
        """Gmail's attachment ids change at each read; a part's place in the message never does."""
        raw = {
            "payload": {
                "parts": [
                    {"partId": "0", "mimeType": "text/plain"},
                    {
                        "filename": "image.png",
                        "mimeType": "image/png",
                        "body": {"attachmentId": "changes-at-each-read", "size": 3},
                    },
                ]
            }
        }

        listed = attachments_of(raw, ConnectorType.GOOGLE_GMAIL)

        assert listed[0].id == "1"

    def test_a_gmail_part_says_it_too(self) -> None:
        raw = {
            "payload": {
                "parts": [
                    {
                        "filename": "note.md",
                        "mimeType": "application/octet-stream",
                        "body": {"attachmentId": "a1", "size": 3},
                    }
                ]
            }
        }

        listed = attachments_of(raw, ConnectorType.GOOGLE_GMAIL)

        assert listed[0].previewable is True


class TestTheRequest:
    def test_it_names_the_part_by_handle_or_by_name(self) -> None:
        AttachmentRequest(message_id="m1", filename="budget.pdf")
        AttachmentRequest(message_id="m1", attachment_id="ANGj")
        with pytest.raises(ValidationError):
            AttachmentRequest(message_id="m1")
