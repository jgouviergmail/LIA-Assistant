"""What an e-mail of the assistant carries, from the card to the send (ADR-369, lot 7, D2).

The screen's composer attaches a file LIA holds and a file of the drive; the assistant does the
same through the same doors. The card names what the person confirms, and what they confirmed is
what is read when the message leaves. A forward works on every provider: the original is read in
the neutral vocabulary (ADR-287), never in a Gmail tree that Outlook and iCloud do not have.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.constants import WORKBENCH_MAIL_ATTACHMENTS_MAX
from src.core.exceptions import ConnectorAPIError
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_detailed_preview
from src.domains.agents.tools import email_files
from src.domains.agents.tools.email_draft_execution import (
    execute_email_draft,
    execute_email_forward_draft,
    execute_email_reply_draft,
)
from src.domains.agents.tools.emails_tools import (
    ForwardEmailDraftTool,
    ReplyEmailDraftTool,
    SendEmailDraftTool,
)
from src.domains.agents.tools.exceptions import EmailValidationError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable
from src.domains.connectors.models import ConnectorType
from src.infrastructure.email.outgoing import OutgoingAttachment

pytestmark = [pytest.mark.unit]

USER = uuid4()
HELD_ID = uuid4()
OWN = OutgoingAttachment("report.pdf", "application/pdf", b"own")
KEPT = OutgoingAttachment("plan.pdf", "application/pdf", b"kept")
ORIGINAL: dict[str, Any] = {
    "id": "m1",
    "threadId": "t1",
    "from": "Paul <paul@example.com>",
    "to": "me@example.com",
    "cc": "",
    "subject": "Budget",
}


def _row(**overrides: Any) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "id": HELD_ID,
        "title": None,
        "original_filename": "report.pdf",
        "mime_type": "application/pdf",
        "file_size": 2048,
    }
    return SimpleNamespace(**{**fields, **overrides})


def _database(*rows: SimpleNamespace) -> Any:
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalars=lambda: MagicMock(all=lambda: list(rows)))
    )

    @contextlib.asynccontextmanager
    async def opened() -> AsyncIterator[Any]:
        yield session

    return patch.object(email_files, "get_db_context", opened)


def _drive(client: Any) -> Any:
    @contextlib.asynccontextmanager
    async def opened(category: str, user_id: UUID) -> AsyncIterator[Any]:
        assert category == "files"
        yield client

    return patch.object(email_files, "open_active_client", opened)


def _active(**fields: Any) -> ActiveClient:
    return ActiveClient(
        client=MagicMock(**fields), connector_type=ConnectorType.GOOGLE_DRIVE, preferred_name=None
    )


def _mail_client(ceiling: int = 1000) -> AsyncMock:
    client = AsyncMock()
    client.OUTGOING_FILE_MAX_BYTES = ceiling
    client.get_message = AsyncMock(return_value=dict(ORIGINAL))
    client.get_own_address = AsyncMock(return_value="me@example.com")
    # A mailbox that tells no reply state (ADR-379): those are tested on their own.
    client.conversations_of = AsyncMock(return_value={})
    for act in ("send_email", "reply_email", "forward_email"):
        setattr(client, act, AsyncMock(return_value={"id": "s1", "threadId": "t1"}))
    return client


class TestAForwardOnEveryProvider:
    """Outlook and iCloud answer the neutral vocabulary and nothing else."""

    def _neutral_client(self, **fields: Any) -> Any:
        client = MagicMock(spec=["get_message"])
        client.get_message = AsyncMock(return_value={**ORIGINAL, **fields})
        return client

    async def test_the_card_names_the_original_where_no_gmail_tree_exists(self) -> None:
        client = self._neutral_client(
            attachments=[{"filename": "a.pdf", "mimeType": "application/pdf", "size": 7}]
        )

        card = await ForwardEmailDraftTool().execute_api_call(
            client, USER, message_id="m1", to="ann@example.com"
        )

        assert card["original_subject"] == "Budget"
        assert card["original_from"] == "Paul <paul@example.com>"
        assert card["attachments"] == [
            {"filename": "a.pdf", "mime_type": "application/pdf", "size": 7}
        ]

    async def test_gmail_s_files_still_come_from_its_parts(self) -> None:
        part = {
            "filename": "a.pdf",
            "mimeType": "application/pdf",
            "body": {"attachmentId": "x", "size": 7},
        }
        client = self._neutral_client(payload={"parts": [part]})

        card = await ForwardEmailDraftTool().execute_api_call(
            client, USER, message_id="m1", to="ann@example.com"
        )

        assert [item["filename"] for item in card["attachments"]] == ["a.pdf"]

    async def test_a_message_with_no_file_lists_none(self) -> None:
        card = await ForwardEmailDraftTool().execute_api_call(
            self._neutral_client(), USER, message_id="m1", to="ann@example.com"
        )

        assert card["attachments"] == []


class TestWhatTheCardNames:
    async def test_nothing_asked_reads_nothing(self) -> None:
        assert await email_files.card_files(_mail_client(), USER, None, None) == []

    async def test_a_file_held_is_found_by_its_name(self) -> None:
        with _database(_row()):
            files = await email_files.card_files(_mail_client(5000), USER, ["REPORT.pdf"], None)

        assert files == [
            {
                "id": str(HELD_ID),
                "filename": "report.pdf",
                "mime_type": "application/pdf",
                "size": 2048,
                "origin": email_files.HELD,
            }
        ]

    async def test_a_file_held_is_found_by_the_title_the_person_sees(self) -> None:
        with _database(_row(title="Rapport de mai")):
            files = await email_files.card_files(_mail_client(5000), USER, ["Rapport de mai"], None)

        assert files[0]["filename"] == "report.pdf"

    async def test_the_newest_of_a_name_answers_for_it(self) -> None:
        newest = uuid4()
        with _database(_row(id=newest), _row()):
            files = await email_files.card_files(_mail_client(5000), USER, ["report.pdf"], None)

        assert [item["id"] for item in files] == [str(newest)]

    async def test_a_name_nothing_answers_to_stops_the_card(self) -> None:
        with _database(), pytest.raises(EmailValidationError) as refused:
            await email_files.card_files(_mail_client(), USER, ["gone.pdf"], None)

        assert refused.value.field == "file_names"

    async def test_one_file_named_twice_is_one_file(self) -> None:
        with _database(_row(title="Rapport")):
            files = await email_files.card_files(
                _mail_client(5000), USER, ["Rapport", "report.pdf"], None
            )

        assert len(files) == 1

    async def test_a_drive_file_is_read_for_the_card(self) -> None:
        metadata = AsyncMock(
            return_value={"id": "f1", "name": "Plan", "mimeType": "text/plain", "size": "40"}
        )
        with _drive(_active(get_file_metadata=metadata)):
            files = await email_files.card_files(_mail_client(), USER, None, ["f1"])

        assert files == [
            {
                "id": "f1",
                "filename": "Plan",
                "mime_type": "text/plain",
                "size": 40,
                "origin": email_files.DRIVE,
            }
        ]

    async def test_a_document_with_no_size_of_its_own_counts_for_nothing_yet(self) -> None:
        metadata = AsyncMock(return_value={"id": "f1", "name": "Plan", "mimeType": "x/doc"})
        with _drive(_active(get_file_metadata=metadata)):
            files = await email_files.card_files(_mail_client(), USER, None, ["f1"])

        assert files[0]["size"] == 0

    async def test_a_drive_item_gone_stops_the_card(self) -> None:
        gone = ConnectorAPIError(connector_type="google_drive", status_code=404, detail="gone")
        with (
            _drive(_active(get_file_metadata=AsyncMock(side_effect=gone))),
            pytest.raises(EmailValidationError) as refused,
        ):
            await email_files.card_files(_mail_client(), USER, None, ["f1"])

        assert refused.value.field == "drive_file_ids"

    async def test_another_drive_failure_is_not_read_as_a_missing_file(self) -> None:
        down = ConnectorAPIError(connector_type="google_drive", status_code=403, detail="no")
        with (
            _drive(_active(get_file_metadata=AsyncMock(side_effect=down))),
            pytest.raises(ConnectorAPIError),
        ):
            await email_files.card_files(_mail_client(), USER, None, ["f1"])

    async def test_no_drive_connected_is_said(self) -> None:
        with _drive(ClientUnavailable.NO_CONNECTOR), pytest.raises(EmailValidationError):
            await email_files.card_files(_mail_client(), USER, None, ["f1"])

    async def test_a_message_carries_a_bounded_number_of_files(self) -> None:
        names = [f"{index}.pdf" for index in range(WORKBENCH_MAIL_ATTACHMENTS_MAX + 1)]

        with pytest.raises(EmailValidationError):
            await email_files.card_files(_mail_client(), USER, names, None)

    async def test_what_the_provider_cannot_carry_is_refused_on_the_card(self) -> None:
        with _database(_row(file_size=2000)), pytest.raises(EmailValidationError):
            await email_files.card_files(_mail_client(1000), USER, ["report.pdf"], None)


class TestTheDrafts:
    async def test_a_new_message_shows_its_files(self) -> None:
        tool = SendEmailDraftTool()
        with _database(_row()):
            result = await tool.execute_api_call(
                _mail_client(5000),
                USER,
                to="ann@example.com",
                subject="Budget",
                body="See attached.",
                file_names=["report.pdf"],
            )

        (item,) = tool.format_registry_response(result).registry_updates.values()
        assert [file["id"] for file in item.payload["content"]["files"]] == [str(HELD_ID)]

    async def test_a_reply_shows_its_files(self) -> None:
        tool = ReplyEmailDraftTool()
        with _database(_row()):
            result = await tool.execute_api_call(
                _mail_client(5000), USER, message_id="m1", body="Hi", file_names=["report.pdf"]
            )

        (item,) = tool.format_registry_response(result).registry_updates.values()
        assert item.payload["content"]["files"][0]["filename"] == "report.pdf"

    async def test_a_forward_shows_its_files_beside_the_original_s(self) -> None:
        tool = ForwardEmailDraftTool()
        with _database(_row()):
            result = await tool.execute_api_call(
                _mail_client(5000),
                USER,
                message_id="m1",
                to="ann@example.com",
                file_names=["report.pdf"],
            )

        (item,) = tool.format_registry_response(result).registry_updates.values()
        assert item.payload["content"]["files"][0]["filename"] == "report.pdf"

    @pytest.mark.parametrize(
        ("draft_type", "content"),
        [
            (DraftType.EMAIL, {"to": "a@example.org", "subject": "S", "body": "Words"}),
            (DraftType.EMAIL_REPLY, {"to": "a@example.org", "subject": "S", "body": "Words"}),
            (DraftType.EMAIL_FORWARD, {"to": "a@example.org", "subject": "S", "body": "Words"}),
        ],
    )
    def test_the_person_reads_what_leaves_before_the_words(
        self, draft_type: DraftType, content: dict[str, Any]
    ) -> None:
        draft = Draft(type=draft_type, content={**content, "files": [{"filename": "report.pdf"}]})

        card = render_detailed_preview(draft, "en")

        assert card.index("report.pdf") < card.index("Words")

    def test_a_forward_lists_the_original_s_files_then_the_person_s(self) -> None:
        draft = Draft(
            type=DraftType.EMAIL_FORWARD,
            content={
                "to": "a@example.org",
                "attachments": [{"filename": "first.pdf"}],
                "files": [{"filename": "second.pdf"}],
            },
        )

        card = render_detailed_preview(draft, "en")

        assert card.index("first.pdf") < card.index("second.pdf")

    def test_a_card_with_no_file_shows_no_row(self) -> None:
        draft = Draft(type=DraftType.EMAIL, content={"to": "a@example.org", "subject": "S"})

        assert "Attachments" not in render_detailed_preview(draft, "en")


class TestTheSignature:
    """It joins the body the card shows: the person reads it, and may change it."""

    SIGNED = "\n\n-- \nAna Lima"

    @pytest.fixture(autouse=True)
    def signs(self, person_signs_with_nothing: AsyncMock) -> None:
        person_signs_with_nothing.return_value = "Ana Lima"

    async def test_a_new_message_shows_it(self) -> None:
        result = await SendEmailDraftTool().execute_api_call(
            _mail_client(), USER, to="ann@example.com", subject="S", body="Hi"
        )

        assert result["body"] == f"Hi{self.SIGNED}"

    async def test_an_html_message_keeps_its_words_as_words(
        self, person_signs_with_nothing: AsyncMock
    ) -> None:
        person_signs_with_nothing.return_value = "Ana <b>"

        result = await SendEmailDraftTool().execute_api_call(
            _mail_client(), USER, to="ann@example.com", subject="S", body="<p>Hi</p>", is_html=True
        )

        assert result["body"] == "<p>Hi</p><br><br>-- <br>Ana &lt;b&gt;"

    async def test_a_reply_shows_it(self) -> None:
        result = await ReplyEmailDraftTool().execute_api_call(
            _mail_client(), USER, message_id="m1", body="Hi"
        )

        assert result["body"] == f"Hi{self.SIGNED}"

    async def test_a_forward_with_no_words_of_its_own_shows_it_too(self) -> None:
        result = await ForwardEmailDraftTool().execute_api_call(
            _mail_client(), USER, message_id="m1", to="ann@example.com"
        )

        assert result["body"] == self.SIGNED

    async def test_what_leaves_is_what_the_card_showed(self) -> None:
        client = _mail_client()
        content = {"to": "a@example.org", "subject": "S", "body": f"Hi{self.SIGNED}"}
        with patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, "email")),
        ):
            await execute_email_draft(content, USER, object())

        assert client.send_email.await_args.kwargs["body"] == f"Hi{self.SIGNED}"

    async def test_a_person_who_signs_with_nothing_changes_nothing(
        self, person_signs_with_nothing: AsyncMock
    ) -> None:
        person_signs_with_nothing.return_value = ""

        result = await ReplyEmailDraftTool().execute_api_call(
            _mail_client(), USER, message_id="m1", body="Hi"
        )

        assert result["body"] == "Hi"


class TestWhatLeaves:
    HELD = {"id": str(HELD_ID), "filename": "report.pdf", "origin": "held"}
    KEPT_ON_DRIVE = {"id": "f1", "filename": "plan.pdf", "origin": "drive"}

    def _read(self) -> Any:
        return patch.object(email_files, "carried_files", AsyncMock(return_value=(OWN, KEPT)))

    def _resolved(self, client: Any) -> Any:
        return patch(
            "src.domains.connectors.provider_resolver.resolve_client_for_category",
            AsyncMock(return_value=(client, "email")),
        )

    async def test_the_files_confirmed_are_read_with_the_provider_s_bound(self) -> None:
        client = _mail_client(1000)
        with self._read() as read:
            files = await email_files.files_to_send(
                {"files": [self.HELD, self.KEPT_ON_DRIVE]}, USER, client
            )

        assert files == (OWN, KEPT)
        read.assert_awaited_once_with(USER, [HELD_ID], ["f1"], max_bytes=1000)

    async def test_a_card_with_no_file_reads_nothing(self) -> None:
        with self._read() as read:
            assert await email_files.files_to_send({}, USER, _mail_client()) == ()

        read.assert_not_awaited()

    async def test_a_new_message_leaves_with_them(self) -> None:
        client = _mail_client()
        content = {"to": "a@example.org", "subject": "S", "body": "B", "files": [self.HELD]}
        with self._resolved(client), self._read():
            await execute_email_draft(content, USER, object())

        assert client.send_email.await_args.kwargs["attachments"] == (OWN, KEPT)

    async def test_a_reply_leaves_with_them_to_whom_the_card_showed(self) -> None:
        client = _mail_client()
        content = {
            "message_id": "m1",
            "to": "a@example.org",
            "cc": "b@example.org",
            "body": "B",
            "files": [self.HELD],
        }
        with self._resolved(client), self._read():
            await execute_email_reply_draft(content, USER, object())

        call = client.reply_email.await_args.kwargs
        assert call["attachments"] == (OWN, KEPT)
        assert call["cc"] == "b@example.org"

    async def test_a_forward_leaves_with_them(self) -> None:
        client = _mail_client()
        content = {"message_id": "m1", "to": "a@example.org", "files": [self.HELD]}
        with self._resolved(client), self._read():
            await execute_email_forward_draft(content, USER, object())

        assert client.forward_email.await_args.kwargs["attachments"] == (OWN, KEPT)
