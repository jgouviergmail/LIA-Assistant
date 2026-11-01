"""A message written by the person's own hand (ADR-369, Task 4.5).

« Send » is the confirmation (ADR-316's doctrine): a message leaves once per
submission — a second click is told what became of the first, never sends
again —, and a send whose answer was lost is « may have left », never « try
again » (ADR-221). Every recipient is read apart, strictly: one that cannot be
read refuses the message, naming its field and its place, before anything
leaves (a recipient dropped in silence never receives what the person wrote).
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError

from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_compose
from src.domains.workbench.schemas.mail_compose import Forward, NewMessage, Reply
from src.infrastructure.email.outgoing import OutgoingAttachment
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()


def _door(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(
            client=client, connector_type=ConnectorType.GOOGLE_GMAIL, preferred_name=None
        )

    return patch.object(mail_compose, "open_tool_client", opened)


@pytest.fixture(autouse=True)
def redis() -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=FakeRedis())):
        yield


def _new(**overrides: Any) -> NewMessage:
    fields: dict[str, Any] = {
        "to": ["Ana Lima <ana@example.org>", "bob@example.org"],
        "cc": ["carla@example.org"],
        "subject": "Budget",
        "body": "Ci-joint.",
        "idempotency_key": uuid4(),
    }
    return NewMessage.model_validate({**fields, **overrides})


class TestANewMessage:
    async def test_it_leaves_once_with_its_recipients_read_apart(self) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "s1", "threadId": "t1"}))
        with _door(client):
            sent = await mail_compose.send_message(USER, _new())

        client.send_email.assert_awaited_once_with(
            "Ana Lima <ana@example.org>, bob@example.org",
            "Budget",
            "Ci-joint.",
            cc="carla@example.org",
            bcc=None,
            is_html=False,
            attachments=(),
            single_attempt=True,
        )
        assert (sent.id, sent.thread_id) == ("s1", "t1")

    async def test_the_person_s_files_leave_with_it_under_the_provider_s_bound(self) -> None:
        """Read BEFORE the send: a file that cannot be read is no « may have left »."""
        client = MagicMock(send_email=AsyncMock(return_value={"id": "s1"}))
        client.OUTGOING_FILE_MAX_BYTES = 25_000_000
        files = (OutgoingAttachment("a.pdf", "application/pdf", b"%PDF"),)
        ids = [uuid4()]
        with (
            _door(client),
            patch.object(mail_compose, "outgoing_files", AsyncMock(return_value=files)) as read,
        ):
            await mail_compose.send_message(USER, _new(attachment_ids=ids))

        read.assert_awaited_once_with(USER, ids, max_bytes=25_000_000)
        assert client.send_email.await_args.kwargs["attachments"] == files

    async def test_an_unreadable_recipient_is_named_by_its_field_and_place(self) -> None:
        client = MagicMock(send_email=AsyncMock())
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_compose.send_message(USER, _new(cc=["carla@example.org", "not an address"]))

        assert refused.value.detail == {"code": "invalid_recipient", "field": "cc", "index": 1}
        client.send_email.assert_not_awaited()

    async def test_a_lost_answer_may_have_left_and_a_second_click_is_told_so(self) -> None:
        client = MagicMock(send_email=AsyncMock(side_effect=httpx.ReadTimeout("lost")))
        message = _new()
        with _door(client), pytest.raises(BaseAPIException) as lost:
            await mail_compose.send_message(USER, message)
        assert lost.value.detail == {"code": "outcome_unknown"}

        with _door(client), pytest.raises(BaseAPIException) as replayed:
            await mail_compose.send_message(USER, message)

        assert replayed.value.status_code == 409
        assert replayed.value.detail == {"code": "already_submitted", "outcome": "unknown"}
        client.send_email.assert_awaited_once()


class TestAnswers:
    async def test_a_reply_to_all(self) -> None:
        client = MagicMock(reply_email=AsyncMock(return_value={"id": "r1", "threadId": "t1"}))
        reply = Reply(message_id="m1", body="Merci.", reply_all=True, idempotency_key=uuid4())
        with _door(client):
            sent = await mail_compose.reply(USER, reply)

        client.reply_email.assert_awaited_once_with("m1", "Merci.", reply_all=True, is_html=False)
        assert sent.id == "r1"

    async def test_a_forward_reads_its_recipients_too(self) -> None:
        client = MagicMock(forward_email=AsyncMock(return_value={}))
        forward = Forward(
            message_id="m1", to=["dan@example.org"], body="Pour info.", idempotency_key=uuid4()
        )
        with _door(client):
            sent = await mail_compose.forward(USER, forward)

        client.forward_email.assert_awaited_once_with(
            "m1", "dan@example.org", body="Pour info.", cc=None, is_html=False
        )
        assert (sent.id, sent.thread_id) == (None, None)


class TestTheContract:
    def test_a_message_reaches_someone(self) -> None:
        with pytest.raises(ValidationError):
            _new(to=[], cc=[])
        _new(to=[], cc=[], bcc=["only@example.org"])

    def test_a_forward_names_its_recipient(self) -> None:
        with pytest.raises(ValidationError):
            Forward(message_id="m1", to=[], idempotency_key=uuid4())
