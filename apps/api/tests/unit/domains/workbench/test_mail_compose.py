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

from src.core.constants import WORKBENCH_MAIL_ATTACHMENTS_MAX
from src.core.exceptions import BaseAPIException
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import idempotency, mail_compose, mail_files
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
            patch.object(mail_files, "outgoing_files", AsyncMock(return_value=files)) as read,
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


class TestADriveFile:
    async def test_it_leaves_with_the_message_after_the_person_s_own(self) -> None:
        own = OutgoingAttachment("own.pdf", "application/pdf", b"own")
        drive = OutgoingAttachment("Report.pdf", "application/pdf", b"drive")
        client = MagicMock(
            OUTGOING_FILE_MAX_BYTES=100,
            send_email=AsyncMock(return_value={"id": "m1"}),
        )
        with (
            _door(client),
            patch.object(mail_files, "outgoing_files", AsyncMock(return_value=(own,))),
            patch.object(mail_files, "drive_files", AsyncMock(return_value=(drive,))) as read,
        ):
            await mail_compose.send_message(USER, _new(drive_file_ids=["f1"]))

        read.assert_awaited_once_with(USER, ["f1"], max_bytes=97)
        assert client.send_email.await_args.kwargs["attachments"] == (own, drive)

    async def test_a_message_with_none_reads_no_drive(self) -> None:
        client = MagicMock(
            OUTGOING_FILE_MAX_BYTES=100, send_email=AsyncMock(return_value={"id": "m1"})
        )
        with _door(client), patch.object(mail_files, "drive_files", AsyncMock()) as read:
            await mail_compose.send_message(USER, _new())

        read.assert_not_awaited()

    async def test_a_file_that_cannot_be_read_stops_the_message(self) -> None:
        client = MagicMock(OUTGOING_FILE_MAX_BYTES=100, send_email=AsyncMock())
        refused = AsyncMock(side_effect=BaseAPIException(status_code=404, detail={}))
        with _door(client), patch.object(mail_files, "drive_files", refused):
            with pytest.raises(BaseAPIException):
                await mail_compose.send_message(USER, _new(drive_file_ids=["f1"]))

        client.send_email.assert_not_awaited()

    def test_a_message_carries_a_bounded_number_of_files_in_all(self) -> None:
        own = [str(uuid4()) for _ in range(WORKBENCH_MAIL_ATTACHMENTS_MAX)]

        with pytest.raises(ValidationError):
            _new(attachment_ids=own, drive_file_ids=["f1"])


class TestAnswers:
    async def test_a_reply_to_all(self) -> None:
        client = MagicMock(reply_email=AsyncMock(return_value={"id": "r1", "threadId": "t1"}))
        reply = Reply(message_id="m1", body="Merci.", reply_all=True, idempotency_key=uuid4())
        with _door(client):
            sent = await mail_compose.reply(USER, reply)

        client.reply_email.assert_awaited_once_with(
            "m1", "Merci.", reply_all=True, is_html=False, to=None, cc=None, attachments=()
        )
        assert sent.id == "r1"

    async def test_a_reply_goes_to_whom_the_person_left_in_it(self) -> None:
        client = MagicMock(reply_email=AsyncMock(return_value={"id": "r1"}))
        reply = Reply(
            message_id="m1",
            body="Merci.",
            to=["Ana Lima <ana@example.org>", "bob@example.org"],
            cc=[],
            idempotency_key=uuid4(),
        )
        with _door(client):
            await mail_compose.reply(USER, reply)

        call = client.reply_email.await_args.kwargs
        assert call["to"] == "Ana Lima <ana@example.org>, bob@example.org"
        assert call["cc"] == ""

    async def test_an_unreadable_copy_stops_the_reply(self) -> None:
        client = MagicMock(reply_email=AsyncMock())
        reply = Reply(
            message_id="m1", body="Merci.", cc=["pas une adresse"], idempotency_key=uuid4()
        )
        with _door(client), pytest.raises(BaseAPIException) as refused:
            await mail_compose.reply(USER, reply)

        assert "invalid_recipient" in str(refused.value.detail)
        client.reply_email.assert_not_awaited()

    async def test_a_reply_carries_the_person_s_files(self) -> None:
        client = MagicMock(
            reply_email=AsyncMock(return_value={"id": "r1"}), OUTGOING_FILE_MAX_BYTES=1000
        )
        own = OutgoingAttachment("a.pdf", "application/pdf", b"own")
        kept = OutgoingAttachment("b.pdf", "application/pdf", b"kept")
        ids = [uuid4()]
        reply = Reply(
            message_id="m1",
            body="Merci.",
            attachment_ids=ids,
            drive_file_ids=["f1"],
            idempotency_key=uuid4(),
        )
        with (
            _door(client),
            patch.object(mail_files, "outgoing_files", AsyncMock(return_value=(own,))) as read,
            patch.object(mail_files, "drive_files", AsyncMock(return_value=(kept,))) as drive,
        ):
            await mail_compose.reply(USER, reply)

        assert client.reply_email.await_args.kwargs["attachments"] == (own, kept)
        read.assert_awaited_once_with(USER, ids, max_bytes=1000)
        drive.assert_awaited_once_with(USER, ["f1"], max_bytes=1000 - len(own.data))

    async def test_a_forward_carries_the_person_s_files(self) -> None:
        client = MagicMock(forward_email=AsyncMock(return_value={}), OUTGOING_FILE_MAX_BYTES=1000)
        own = OutgoingAttachment("a.pdf", "application/pdf", b"own")
        ids = [uuid4()]
        forward = Forward(
            message_id="m1", to=["dan@example.org"], attachment_ids=ids, idempotency_key=uuid4()
        )
        with (
            _door(client),
            patch.object(mail_files, "outgoing_files", AsyncMock(return_value=(own,))),
        ):
            await mail_compose.forward(USER, forward)

        assert client.forward_email.await_args.kwargs["attachments"] == (own,)

    async def test_a_forward_reads_its_recipients_too(self) -> None:
        client = MagicMock(forward_email=AsyncMock(return_value={}))
        forward = Forward(
            message_id="m1", to=["dan@example.org"], body="Pour info.", idempotency_key=uuid4()
        )
        with _door(client):
            sent = await mail_compose.forward(USER, forward)

        client.forward_email.assert_awaited_once_with(
            "m1", "dan@example.org", body="Pour info.", cc=None, is_html=False, attachments=()
        )
        assert (sent.id, sent.thread_id) == (None, None)


class TestFormattedWords:
    MARKED = "<b>Hi</b><script>alert(1)</script>"

    async def test_a_message_leaves_as_html_rebuilt_here(self) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "s1"}))
        with _door(client):
            await mail_compose.send_message(USER, _new(html=self.MARKED))

        call = client.send_email.await_args
        assert call.args[2] == "<b>Hi</b>"
        assert call.kwargs["is_html"] is True

    async def test_a_reply_too(self) -> None:
        client = MagicMock(reply_email=AsyncMock(return_value={"id": "r1"}))
        answer = Reply(message_id="m1", body="Hi", html=self.MARKED, idempotency_key=uuid4())
        with _door(client):
            await mail_compose.reply(USER, answer)

        call = client.reply_email.await_args
        assert call.args[1] == "<b>Hi</b>"
        assert call.kwargs["is_html"] is True

    async def test_a_forward_too(self) -> None:
        client = MagicMock(forward_email=AsyncMock(return_value={}))
        forwarded = Forward(
            message_id="m1", to=["d@example.org"], html=self.MARKED, idempotency_key=uuid4()
        )
        with _door(client):
            await mail_compose.forward(USER, forwarded)

        call = client.forward_email.await_args
        assert call.kwargs["body"] == "<b>Hi</b>"
        assert call.kwargs["is_html"] is True

    async def test_words_alone_leave_as_text(self) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "s1"}))
        with _door(client):
            await mail_compose.send_message(USER, _new())

        assert client.send_email.await_args.kwargs["is_html"] is False


class TestAnAddressChosen:
    async def test_it_is_settled_before_anything_leaves(self) -> None:
        order: list[str] = []
        client = MagicMock(
            send_email=AsyncMock(side_effect=lambda *a, **k: order.append("send") or {"id": "s1"})
        )
        chosen = AsyncMock(side_effect=lambda *a: order.append("alias"))
        with _door(client), patch.object(mail_compose, "apply_send_as", chosen):
            await mail_compose.send_message(USER, _new(send_as="work@example.com"))

        assert order == ["alias", "send"]
        assert chosen.await_args.args[1:] == (USER, "work@example.com")

    async def test_one_the_mailbox_refuses_sends_nothing(self) -> None:
        client = MagicMock(send_email=AsyncMock())
        refused = AsyncMock(side_effect=BaseAPIException(status_code=422, detail="no"))
        with (
            _door(client),
            patch.object(mail_compose, "apply_send_as", refused),
            pytest.raises(BaseAPIException),
        ):
            await mail_compose.send_message(USER, _new(send_as="stranger@example.com"))

        client.send_email.assert_not_awaited()

    async def test_none_asks_nothing_of_the_mailbox(self) -> None:
        client = MagicMock(send_email=AsyncMock(return_value={"id": "s1"}))
        chosen = AsyncMock()
        with _door(client), patch.object(mail_compose, "apply_send_as", chosen):
            await mail_compose.send_message(USER, _new())

        chosen.assert_not_awaited()

    async def test_a_reply_and_a_forward_take_one_too(self) -> None:
        client = MagicMock(
            reply_email=AsyncMock(return_value={"id": "r1"}),
            forward_email=AsyncMock(return_value={}),
        )
        chosen = AsyncMock()
        reply = Reply(message_id="m1", body="b", send_as="w@example.com", idempotency_key=uuid4())
        forward = Forward(
            message_id="m1", to=["d@example.org"], send_as="w@example.com", idempotency_key=uuid4()
        )
        with _door(client), patch.object(mail_compose, "apply_send_as", chosen):
            await mail_compose.reply(USER, reply)
            await mail_compose.forward(USER, forward)

        assert chosen.await_count == 2


class TestTheContract:
    def test_a_message_reaches_someone(self) -> None:
        with pytest.raises(ValidationError):
            _new(to=[], cc=[])
        _new(to=[], cc=[], bcc=["only@example.org"])

    def test_a_forward_names_its_recipient(self) -> None:
        with pytest.raises(ValidationError):
            Forward(message_id="m1", to=[], idempotency_key=uuid4())

    def test_a_reply_whose_recipients_were_chosen_still_reaches_someone(self) -> None:
        with pytest.raises(ValidationError):
            Reply(message_id="m1", body="Merci.", to=[], idempotency_key=uuid4())

    @pytest.mark.parametrize("answer", ["reply", "forward"])
    def test_an_answer_carries_a_bounded_number_of_files_in_all(self, answer: str) -> None:
        own = [uuid4() for _ in range(WORKBENCH_MAIL_ATTACHMENTS_MAX)]
        fields: dict[str, Any] = {
            "message_id": "m1",
            "body": "Merci.",
            "attachment_ids": own,
            "drive_file_ids": ["f1"],
            "idempotency_key": uuid4(),
        }
        with pytest.raises(ValidationError):
            if answer == "reply":
                Reply.model_validate(fields)
            else:
                Forward.model_validate({**fields, "to": ["dan@example.org"]})
