"""The mail screen's listing and reader (ADR-369, Task 4.2).

A listing is ONE search, read fresh — the person's own view, never the
assistant's minute-old cache — at the published page size, headers only; a
row says who, what, when, read or starred, and the page says how many hits
the provider listed but could not read (F11). The reader reads one message
whole and marks nothing read: reading is not an act. An attachment carries its
handle AND its name, because a Gmail handle expires between two reads.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.core.field_names import FIELD_SKIPPED_HITS
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.apple_imap import ImapMessageNotFoundError
from src.domains.connectors.clients.mail_folders import MailFolderNotFoundError
from src.domains.connectors.models import ConnectorType
from src.domains.workbench import mail_reading
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.mail_projection import has_attachments
from src.domains.workbench.schemas.mail import MailAddress, MailListing

pytestmark = pytest.mark.unit

USER = uuid4()
PARIS = ZoneInfo("Europe/Paris")
GMAIL, OUTLOOK = ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK
RECEIVED = datetime(2026, 10, 30, 8, 15, tzinfo=UTC)


def _door(client: Any, kind: ConnectorType) -> Any:
    @contextlib.asynccontextmanager
    async def opened(tool: Any, user_id: Any) -> AsyncIterator[ActiveClient]:
        yield ActiveClient(client=client, connector_type=kind, preferred_name=None)

    return patch.object(mail_reading, "open_tool_client", opened)


def _hit(**overrides: Any) -> dict[str, Any]:
    return {
        "id": "m1",
        "threadId": "t1",
        "from": '"Lima, Ana" <ana@example.org>',
        "subject": "Budget",
        "snippet": "Voici le budget",
        "labelIds": ["INBOX", "UNREAD", "STARRED"],
        "internalDate": str(int(RECEIVED.timestamp() * 1000)),
        **overrides,
    }


def _page(*hits: dict[str, Any], skipped: int = 0) -> dict[str, Any]:
    return {"messages": list(hits), "next_page_token": "p2", FIELD_SKIPPED_HITS: skipped}


class TestTheListing:
    async def test_one_fresh_search_and_rows_that_say_who_what_when(self) -> None:
        client = MagicMock(search_emails=AsyncMock(return_value=_page(_hit())))
        with _door(client, OUTLOOK):
            page = await mail_reading.list_messages(USER, PARIS, MailListing(unread=True))

        client.search_emails.assert_awaited_once_with(
            "is:unread in:inbox",
            max_results=listing_page_size(),
            use_cache=False,
            page_token=None,
            headers_only=True,
        )
        row = page.items[0]
        assert row.sender == MailAddress(name="Lima, Ana", address="ana@example.org")
        assert (row.subject, row.received_at, row.is_read, row.is_starred) == (
            "Budget",
            RECEIVED,
            False,
            True,
        )
        assert (page.next_page_token, page.skipped) == ("p2", 0)

    async def test_a_caller_showing_less_reads_no_more_than_it_shows(self) -> None:
        client = MagicMock(search_emails=AsyncMock(return_value=_page()))
        with _door(client, OUTLOOK):
            await mail_reading.list_messages(USER, PARIS, MailListing(), size=5)

        assert client.search_emails.await_args.kwargs["max_results"] == 5

    async def test_a_gmail_label_is_read_by_its_id(self) -> None:
        client = MagicMock(search_in_labels=AsyncMock(return_value=_page()))
        listing = MailListing(folder="Label_12", page_token="p2")
        with _door(client, GMAIL):
            await mail_reading.list_messages(USER, PARIS, listing)

        client.search_in_labels.assert_awaited_once_with(
            ("Label_12",),
            "",
            max_results=listing_page_size(),
            use_cache=False,
            page_token="p2",
            headers_only=True,
        )

    async def test_hits_the_provider_could_not_read_are_counted(self) -> None:
        client = MagicMock(search_emails=AsyncMock(return_value=_page(_hit(), skipped=2)))
        with _door(client, GMAIL):
            page = await mail_reading.list_messages(USER, PARIS, MailListing())

        assert (len(page.items), page.skipped) == (1, 2)

    async def test_a_folder_gone_since_the_pane_was_drawn_is_said(self) -> None:
        client = MagicMock(
            search_emails=AsyncMock(
                side_effect=MailFolderNotFoundError("Projets", [], complete=True)
            )
        )
        with _door(client, OUTLOOK), pytest.raises(BaseAPIException) as refused:
            await mail_reading.list_messages(USER, PARIS, MailListing(folder="Projets"))

        assert refused.value.detail == {"code": "item_gone"}

    @pytest.mark.parametrize("date", ["0", None, "not a date", "9" * 30])
    async def test_a_row_without_a_date_or_a_sender_is_still_drawn(self, date: object) -> None:
        bare = _hit(**{"from": "", "internalDate": date, "labelIds": []})
        client = MagicMock(search_emails=AsyncMock(return_value=_page(bare)))
        with _door(client, OUTLOOK):
            row = (await mail_reading.list_messages(USER, PARIS, MailListing())).items[0]

        assert (row.sender, row.received_at, row.is_read) == (None, None, True)


class TestThePaperclip:
    @pytest.mark.parametrize(
        ("hit", "expected"),
        [
            ({"hasAttachment": True}, True),
            ({"hasAttachment": False}, False),
            (
                {
                    "payload": {
                        "headers": [{"name": "Content-Type", "value": "multipart/mixed; b=1"}]
                    }
                },
                True,
            ),
            (
                {"payload": {"headers": [{"name": "content-type", "value": "multipart/related"}]}},
                False,
            ),
            ({"payload": {"headers": [{"name": "Subject", "value": "multipart/mixed"}]}}, False),
            ({}, False),
        ],
    )
    def test_a_row_says_what_its_headers_say(self, hit: dict[str, Any], expected: bool) -> None:
        assert has_attachments(hit) is expected


class TestTheReader:
    async def test_a_gmail_message_whole_its_attachments_from_its_parts(self) -> None:
        message = _hit(
            to="bob@example.org, Carla <carla@example.org>",
            body="Le budget est joint.",
            payload={
                "parts": [
                    {"mimeType": "text/plain", "body": {"size": 20}},
                    {
                        "filename": "budget.pdf",
                        "mimeType": "application/pdf",
                        "body": {"attachmentId": "ANGj", "size": 1234},
                    },
                ]
            },
        )
        client = MagicMock(get_message=AsyncMock(return_value=message))
        with _door(client, GMAIL):
            read = await mail_reading.read_message(USER, "m1")

        client.get_message.assert_awaited_once_with("m1", use_cache=False)
        assert [address.address for address in read.to] == ["bob@example.org", "carla@example.org"]
        assert read.body == "Le budget est joint."
        assert [(a.id, a.filename, a.size) for a in read.attachments] == [("1", "budget.pdf", 1234)]
        assert not client.mark_read.called, "reading is not an act"

    async def test_elsewhere_the_attachments_are_the_message_s_own_list(self) -> None:
        message = _hit(
            body="Voir pièce jointe.",
            attachments=[
                {"attachmentId": "AAMk", "filename": "a.txt", "mimeType": "text/plain", "size": 3}
            ],
        )
        client = MagicMock(get_message=AsyncMock(return_value=message))
        with _door(client, OUTLOOK):
            read = await mail_reading.read_message(USER, "m1")

        assert [(a.id, a.filename, a.mime_type) for a in read.attachments] == [
            ("AAMk", "a.txt", "text/plain")
        ]


class TestTheReplyRecipients:
    """Who an answer would reach: the one rule of the three clients, read for the composer."""

    ORIGINAL: ClassVar[dict[str, Any]] = {
        "id": "m1",
        "from": "Bob <bob@example.org>",
        "to": "me@example.org, Ann <ann@example.org>",
        "cc": "carl@example.org, ME@example.org",
    }

    def _client(self, **fields: Any) -> MagicMock:
        return MagicMock(
            get_message=AsyncMock(return_value={**self.ORIGINAL, **fields}),
            get_own_address=AsyncMock(return_value="me@example.org"),
        )

    async def test_a_reply_answers_the_sender(self) -> None:
        with _door(self._client(), GMAIL):
            read = await mail_reading.read_reply_recipients(USER, "m1", reply_all=False)

        assert [item.address for item in read.to] == ["bob@example.org"]
        assert read.cc == []

    async def test_reply_to_wins_over_the_sender(self) -> None:
        client = self._client(reply_to="List <list@example.org>")
        with _door(client, OUTLOOK):
            read = await mail_reading.read_reply_recipients(USER, "m1", reply_all=False)

        assert [item.address for item in read.to] == ["list@example.org"]

    async def test_a_reply_to_all_leaves_the_person_out(self) -> None:
        with _door(self._client(), OUTLOOK):
            read = await mail_reading.read_reply_recipients(USER, "m1", reply_all=True)

        assert [item.address for item in read.to] == ["bob@example.org", "ann@example.org"]
        assert [item.address for item in read.cc] == ["carl@example.org"]

    async def test_a_reply_to_one_s_own_message_answers_its_recipients(self) -> None:
        client = self._client(**{"from": "me@example.org", "to": "ann@example.org"})
        with _door(client, GMAIL):
            read = await mail_reading.read_reply_recipients(USER, "m1", reply_all=False)

        assert [item.address for item in read.to] == ["ann@example.org"]

    async def test_it_reads_the_message_fresh_as_the_reader_does(self) -> None:
        client = self._client()
        with _door(client, GMAIL):
            await mail_reading.read_reply_recipients(USER, "m1", reply_all=False)

        client.get_message.assert_awaited_once_with("m1", use_cache=False)


class TestTheConversation:
    async def test_its_rows_read_as_a_listing_s_and_the_cut_is_said(self) -> None:
        client = MagicMock(
            get_conversation=AsyncMock(
                return_value={"messages": [_hit(), _hit(id="m2")], "truncated": True}
            )
        )

        with _door(client, GMAIL):
            found = await mail_reading.read_conversation(USER, "m2")

        client.get_conversation.assert_awaited_once_with("m2", listing_page_size())
        assert [item.id for item in found.items] == ["m1", "m2"]
        assert found.items[0].sender == MailAddress(name="Lima, Ana", address="ana@example.org")
        assert found.items[0].received_at == RECEIVED
        assert found.truncated is True

    async def test_a_message_gone_is_said_gone(self) -> None:
        client = MagicMock(get_conversation=AsyncMock(side_effect=ImapMessageNotFoundError("x")))

        with _door(client, OUTLOOK), pytest.raises(BaseAPIException) as refused:
            await mail_reading.read_conversation(USER, "m1")

        assert refused.value.status_code == 404


class TestTheLabels:
    """A Gmail row names the person's own labels (the mock-up's chips); a system
    label is a flag or a place, never a chip; elsewhere there are none."""

    async def test_a_gmail_row_carries_the_person_s_labels_and_no_system_one(self) -> None:
        hit = _hit(labelIds=["INBOX", "UNREAD", "CATEGORY_UPDATES", "Label_7", "Label_12"])
        client = MagicMock(search_emails=AsyncMock(return_value=_page(hit)))
        with _door(client, GMAIL):
            row = (await mail_reading.list_messages(USER, PARIS, MailListing())).items[0]

        assert row.label_ids == ["Label_7", "Label_12"]

    async def test_an_outlook_row_carries_none(self) -> None:
        hit = _hit(labelIds=["STARRED", "Projets"])
        client = MagicMock(search_emails=AsyncMock(return_value=_page(hit)))
        with _door(client, OUTLOOK):
            row = (await mail_reading.list_messages(USER, PARIS, MailListing())).items[0]

        assert row.label_ids == []

    async def test_the_reader_names_them_too(self) -> None:
        client = MagicMock(get_message=AsyncMock(return_value=_hit(labelIds=["Label_7", "SENT"])))
        with _door(client, GMAIL):
            read = await mail_reading.read_message(USER, "m1")

        assert read.label_ids == ["Label_7"]


class TestTheHtml:
    """The message as its author laid it out (D3): served whole up to the
    published ceiling, cut on a character boundary past it and the cut said;
    a message without HTML answers none and the text reader shows."""

    async def test_the_html_is_served_whole_under_the_ceiling(self) -> None:
        client = MagicMock(get_message_html=AsyncMock(return_value="<p>Hello</p>"))
        with _door(client, GMAIL):
            html = await mail_reading.read_message_html(USER, "m1")

        client.get_message_html.assert_awaited_once_with("m1")
        assert (html.html, html.truncated) == ("<p>Hello</p>", False)

    async def test_past_the_ceiling_it_is_cut_on_a_character_and_the_cut_said(self) -> None:
        whole = "a" + "é" * 600  # 1 + 1200 bytes: the ceiling falls inside an « é »
        client = MagicMock(get_message_html=AsyncMock(return_value=whole))
        with (
            _door(client, OUTLOOK),
            patch.object(settings, "workbench_mail_html_max_bytes", 1024),
        ):
            html = await mail_reading.read_message_html(USER, "o1")

        assert html.truncated is True
        assert html.html == whole[: len(html.html or "")]
        assert len((html.html or "").encode()) == 1023

    async def test_a_message_without_html_answers_none(self) -> None:
        client = MagicMock(get_message_html=AsyncMock(return_value=None))
        with _door(client, OUTLOOK):
            html = await mail_reading.read_message_html(USER, "o1")

        assert (html.html, html.truncated) == (None, False)

    async def test_a_message_gone_is_said_gone(self) -> None:
        client = MagicMock(get_message_html=AsyncMock(side_effect=ImapMessageNotFoundError("gone")))
        with _door(client, ConnectorType.APPLE_EMAIL), pytest.raises(BaseAPIException) as caught:
            await mail_reading.read_message_html(USER, "101")

        assert caught.value.detail["code"] == "item_gone"

    def test_no_tool_of_the_assistant_reads_it(self) -> None:
        """Display only: the model reads text, never markup (ADR-287, D2)."""
        source = Path(mail_reading.__file__).parents[2]
        callers = sorted(
            str(path.relative_to(source)).replace("\\", "/")
            for path in source.rglob("*.py")
            if ".get_message_html(" in path.read_text(encoding="utf-8")
        )

        assert callers == ["domains/workbench/mail_reading.py"]
