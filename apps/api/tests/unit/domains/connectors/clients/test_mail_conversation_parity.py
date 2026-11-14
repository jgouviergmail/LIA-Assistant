"""A conversation, on the three providers (ADR-369, lot 8).

Gmail keeps threads and Graph a conversation id, and Graph refuses a sort beside that filter
unless the sort's own field leads it (measured on a real mailbox). iCloud keeps neither: its
headers do, ``References`` leading to the message that opened it. The answer is one shape:
oldest first, the newest kept when there are too many, and the cut said. A draft is the person's
unsent words, no part of what was said.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import GMAIL_FORMAT_METADATA
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import (
    ImapMessageNotFoundError,
    mailbox_account_scope,
)
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.normalizers.imap_handles import message_handle, scope_digest
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

ME = "jane@icloud.com"


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class TestGmail:
    def _message(self, message_id: str, *labels: str) -> dict[str, Any]:
        return {
            "id": message_id,
            "threadId": "t1",
            "labelIds": list(labels),
            "snippet": "Hi",
            "payload": {"headers": [{"name": "From", "value": f"{message_id}@example.com"}]},
        }

    def _client(self, *messages: dict[str, Any]) -> GoogleGmailClient:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        client.get_message = AsyncMock(return_value={"id": "m1", "threadId": "t1"})
        client.get_thread = AsyncMock(return_value={"messages": list(messages)})
        return client

    async def test_it_reads_the_thread_of_the_message_without_any_body(self) -> None:
        client = self._client(self._message("m1"), self._message("m2"))

        found = await client.get_conversation("m2", 10)

        client.get_thread.assert_awaited_once()
        asked_for = client.get_thread.await_args
        assert asked_for.args == ("t1",)
        assert asked_for.kwargs["format"] == GMAIL_FORMAT_METADATA
        # Named headers, never every header of every message (588 KB against 60 KB
        # for a thread of a hundred messages, measured 2026-11-11).
        assert "From" in asked_for.kwargs["metadata_headers"]
        assert [item["id"] for item in found["messages"]] == ["m1", "m2"]
        assert found["messages"][0]["from"] == "m1@example.com"
        assert found["truncated"] is False

    async def test_the_newest_are_kept_and_the_cut_said(self) -> None:
        client = self._client(*(self._message(f"m{i}") for i in range(4)))

        found = await client.get_conversation("m3", 2)

        assert [item["id"] for item in found["messages"]] == ["m2", "m3"]
        assert found["truncated"] is True

    async def test_a_draft_is_no_part_of_it(self) -> None:
        client = self._client(self._message("m1"), self._message("d1", "DRAFT"))

        found = await client.get_conversation("m1", 10)

        assert [item["id"] for item in found["messages"]] == ["m1"]

    async def test_the_oldest_comes_first_whatever_order_gmail_answers_in(self) -> None:
        later = {**self._message("m2"), "internalDate": "2000"}
        earlier = {**self._message("m1"), "internalDate": "1000"}
        client = self._client(later, earlier)

        found = await client.get_conversation("m2", 10)

        assert [item["id"] for item in found["messages"]] == ["m1", "m2"]


class TestOutlook:
    def _client(self, *messages: dict[str, Any]) -> tuple[MicrosoftOutlookClient, AsyncMock]:
        client = MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())
        request = AsyncMock(
            side_effect=[{"conversationId": "c'1=="}, {"value": list(messages)}],
        )
        client._make_request = request
        return client, request

    def _message(self, message_id: str, **fields: Any) -> dict[str, Any]:
        return {
            "id": message_id,
            "conversationId": "c'1==",
            "subject": "Budget",
            "from": {"emailAddress": {"address": f"{message_id}@example.com", "name": ""}},
            "receivedDateTime": "2026-11-02T09:00:00Z",
            **fields,
        }

    async def test_the_filter_leads_with_the_field_it_sorts_on(self) -> None:
        client, request = self._client(self._message("m2"), self._message("m1"))

        found = await client.get_conversation("m2", 10)

        params = request.await_args.kwargs["params"]
        assert params["$filter"] == (
            "receivedDateTime ge 1900-01-01T00:00:00Z "
            "and conversationId eq 'c''1==' and isDraft eq false"
        )
        assert params["$orderby"] == "receivedDateTime desc"
        assert [item["id"] for item in found["messages"]] == ["m1", "m2"]
        assert found["truncated"] is False

    async def test_one_more_than_kept_says_the_cut(self) -> None:
        client, request = self._client(
            self._message("m3"), self._message("m2"), self._message("m1")
        )

        found = await client.get_conversation("m3", 2)

        assert request.await_args.kwargs["params"]["$top"] == "3"
        assert [item["id"] for item in found["messages"]] == ["m2", "m3"]
        assert found["truncated"] is True

    async def test_the_global_ceiling_holds_and_a_next_page_says_the_cut(self) -> None:
        client = MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())
        client._make_request = AsyncMock(
            side_effect=[
                {"conversationId": "c1"},
                {"value": [self._message("m2")], "@odata.nextLink": "https://next"},
            ]
        )

        found = await client.get_conversation("m2", settings.api_max_items_per_request + 10)

        params = client._make_request.await_args.kwargs["params"]
        assert params["$top"] == str(settings.api_max_items_per_request)
        assert found["truncated"] is True


def _mail(message_id: str, *, references: str = "", day: int = 1) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "paul@example.com"
    message["To"] = ME
    message["Subject"] = "Budget"
    if message_id:
        message["Message-ID"] = message_id
    message["Date"] = f"Mon, {day:02d} Nov 2026 09:00:00 +0000"
    if references:
        message["References"] = references
        message["In-Reply-To"] = references.split()[-1]
    message.set_content("Words")
    return message


class TestApple:
    @pytest.fixture
    def imap(self) -> FakeImap:
        return FakeImap()

    @pytest.fixture
    def client(self, imap: FakeImap) -> Iterator[AppleEmailClient]:
        instance = AppleEmailClient(
            user_id=uuid4(),
            credentials=AppleCredentials(apple_id=ME, app_password="abcd-efgh-ijkl-mnop"),
            connector_service=MagicMock(),
        )
        breaker = MagicMock(
            check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock()
        )
        with (
            patch("src.domains.connectors.clients.apple_conversation_mixin.MailBox", imap),
            patch.object(instance, "_rate_limit", AsyncMock()),
            patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
            patch("asyncio.sleep", AsyncMock()),
        ):
            yield instance

    def _handle(self, client: AppleEmailClient, uid: str, folder: str = "INBOX") -> str:
        scope = scope_digest(mailbox_account_scope(client.credentials.apple_id), folder, 1)
        return message_handle(folder, uid, scope=scope)

    async def test_it_walks_back_to_what_opened_it_and_across_the_sent_folder(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put("Sent Messages", _mail("<b@x>", references="<a@x>", day=2))
        last = imap.put("INBOX", _mail("<c@x>", references="<a@x> <b@x>", day=3))
        imap.put("INBOX", _mail("<other@x>", day=4))

        found = await client.get_conversation(self._handle(client, last), 10)

        assert [item["rfc_message_id"] for item in found["messages"]] == [
            "<a@x>",
            "<b@x>",
            "<c@x>",
        ]
        assert found["truncated"] is False

    async def test_a_message_that_opened_one_finds_its_answers(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        first = imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put("INBOX", _mail("<b@x>", references="<a@x>", day=2))

        found = await client.get_conversation(self._handle(client, first), 10)

        assert len(found["messages"]) == 2

    async def test_a_message_alone_is_a_conversation_of_one(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        alone = imap.put("INBOX", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, alone), 10)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<a@x>"]

    async def test_one_message_in_two_folders_counts_once(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        kept = imap.put("INBOX", _mail("<a@x>"))
        imap.put("Sent Messages", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, kept), 10)

        assert len(found["messages"]) == 1

    async def test_the_newest_are_kept_and_the_cut_said(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put("INBOX", _mail("<b@x>", references="<a@x>", day=2))
        last = imap.put("INBOX", _mail("<c@x>", references="<a@x> <b@x>", day=3))

        found = await client.get_conversation(self._handle(client, last), 2)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<b@x>", "<c@x>"]
        assert found["truncated"] is True

    async def test_a_folder_holding_more_than_the_bound_gives_its_newest(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put("INBOX", _mail("<b@x>", references="<a@x>", day=2))
        imap.put("INBOX", _mail("<c@x>", references="<a@x>", day=3))
        last = imap.put("INBOX", _mail("<d@x>", references="<a@x>", day=4))

        found = await client.get_conversation(self._handle(client, last), 2)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<c@x>", "<d@x>"]

    async def test_read_from_the_sent_folder_it_finds_the_inbox(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", _mail("<a@x>", day=1))
        answer = imap.put("Sent Messages", _mail("<b@x>", references="<a@x>", day=2))

        found = await client.get_conversation(self._handle(client, answer, "Sent Messages"), 10)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<a@x>", "<b@x>"]

    async def test_no_body_is_read(self, client: AppleEmailClient, imap: FakeImap) -> None:
        alone = imap.put("INBOX", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, alone), 10)

        assert not found["messages"][0]["body"]

    async def test_reading_it_marks_nothing_read(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        alone = imap.put("INBOX", _mail("<a@x>"))
        fetch = MagicMock(side_effect=imap.fetch)
        imap.fetch = fetch

        await client.get_conversation(self._handle(client, alone), 10)

        assert fetch.call_args_list
        assert all(call.kwargs["mark_seen"] is False for call in fetch.call_args_list)

    async def test_a_draft_is_no_part_of_it(self, client: AppleEmailClient, imap: FakeImap) -> None:
        kept = imap.put("Drafts", _mail("<a@x>", day=1))
        imap.put("Drafts", _mail("<b@x>", references="<a@x>", day=2), ("\\Draft",))

        found = await client.get_conversation(self._handle(client, kept, "Drafts"), 10)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<a@x>"]

    async def test_a_message_naming_nothing_stands_alone(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        nameless = imap.put("INBOX", _mail(""))
        imap.put("INBOX", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, nameless), 10)

        assert len(found["messages"]) == 1
        assert found["messages"][0]["rfc_message_id"] is None

    async def test_a_sender_s_unreadable_header_names_nothing(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        raw = "Message-ID: <b@x>\nReferences: <naïve@x>\nSubject: Budget\n\nWords".encode()
        imap.store["INBOX"]["500"] = (raw, ())

        found = await client.get_conversation(self._handle(client, "500"), 10)

        assert [item["rfc_message_id"] for item in found["messages"]] == ["<b@x>"]

    async def test_a_cut_is_said_even_when_the_copies_hide_it(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        for _ in range(3):
            last = imap.put("INBOX", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, last), 2)

        assert len(found["messages"]) == 1
        assert found["truncated"] is True

    async def test_a_mailbox_with_no_sent_folder_still_answers(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        del imap.store["Sent Messages"]
        alone = imap.put("INBOX", _mail("<a@x>"))

        found = await client.get_conversation(self._handle(client, alone), 10)

        assert len(found["messages"]) == 1

    async def test_a_message_gone_is_refused(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        with pytest.raises(ImapMessageNotFoundError):
            await client.get_conversation(self._handle(client, "999"), 10)
