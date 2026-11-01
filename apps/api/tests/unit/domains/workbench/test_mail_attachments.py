"""A mail attachment downloaded by the person's own hand (ADR-369, Task 4.4).

One download at a time per account — a claim by its owner token, expiring on
its own — because the client reads the file into memory up to the published
ceiling, which it is HANDED: a part whose listed size passes it is refused
before it is read. Our own throttle never fails a download: an unreachable
cache lets it through. A Gmail handle expires between two reads, so the name
travels with it; a name two parts share is a stale handle.
"""

from __future__ import annotations

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
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentAmbiguousError,
    EmailAttachmentContent,
    EmailAttachmentTooLargeError,
)
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import downloads, mail_attachments
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


class TestTheRequest:
    def test_it_names_the_part_by_handle_or_by_name(self) -> None:
        AttachmentRequest(message_id="m1", filename="budget.pdf")
        AttachmentRequest(message_id="m1", attachment_id="ANGj")
        with pytest.raises(ValidationError):
            AttachmentRequest(message_id="m1")
