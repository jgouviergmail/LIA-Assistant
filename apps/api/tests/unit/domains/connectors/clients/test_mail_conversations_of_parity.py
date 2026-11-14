"""The conversations of listed messages, on the three providers (ADR-379).

One answer shape — :class:`Conversation`, keyed by each message's ``threadId`` — whatever
keeps the conversation: a Gmail thread, a Graph ``conversationId``, IMAP's headers. The
owner's messages carry ``SENT`` and their unsent ones stand apart on every provider, the
mailbox's own « answered » mark travels where the provider keeps one, and a conversation
that could not be read is ABSENT. Each provider's answer is fed to the one decider, which
is the real contract: the same exchange reads « answered » on the three.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from src.core.field_names import FIELD_MAIL_ANSWERED, FIELD_MAIL_ANSWERED_AT
from src.core.mail_reply_state import ReplyState
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import mailbox_account_scope
from src.domains.connectors.clients.conversation_replies import reply_state_of
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_conversation import Conversation
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.normalizers.imap_handles import message_handle, scope_digest
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

ME = "jane@icloud.com"
OBSERVED = datetime(2026, 11, 10, 12, 0, tzinfo=ZoneInfo("Europe/Paris"))


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


def _state(message: dict[str, Any], conversation: Conversation) -> ReplyState | None:
    return reply_state_of(
        message,
        conversation,
        observed_at=OBSERVED,
        validity=timedelta(minutes=2),
        excerpt_max_chars=200,
    )


# =============================================================================
# Gmail — a thread
# =============================================================================


def _gmail_message(
    message_id: str, minute: int, *labels: str, thread: str = "t1", **headers: str
) -> dict[str, Any]:
    named = {"From": "paul@example.com", "To": ME, **headers}
    return {
        "id": message_id,
        "threadId": thread,
        "labelIds": list(labels),
        "internalDate": str(1_762_761_600_000 + minute * 60_000),
        "snippet": f"words of {message_id}",
        "payload": {"headers": [{"name": k, "value": v} for k, v in named.items()]},
    }


class TestGmail:
    def _client(self, threads: dict[str, list[dict[str, Any]]]) -> GoogleGmailClient:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())

        async def _thread(thread_id: str, **_: object) -> dict[str, Any]:
            if thread_id not in threads:
                raise RuntimeError("gone")
            return {"messages": [dict(item) for item in threads[thread_id]]}

        client.get_thread = AsyncMock(side_effect=_thread)
        return client

    async def test_one_thread_is_read_per_conversation_whatever_the_messages_listed(self) -> None:
        asked = _gmail_message("m1", 0, "INBOX")
        again = _gmail_message("m3", 20, "INBOX")
        client = self._client({"t1": [asked, _gmail_message("m2", 10, "SENT"), again]})

        found = await client.conversations_of([asked, again], 10)

        assert client.get_thread.await_count == 1
        assert list(found) == ["t1"]
        assert [row["id"] for row in found["t1"].messages] == ["m1", "m2", "m3"]

    async def test_the_thread_is_read_by_its_named_headers_never_all_of_them(self) -> None:
        """A hundred messages weigh 60 KB that way against 588 KB (measured 2026-11-11)."""
        asked = _gmail_message("m1", 0, "INBOX")
        client = self._client({"t1": [asked]})

        await client.conversations_of([asked], 10)

        asked_for = client.get_thread.await_args.kwargs
        assert asked_for["format"] == "metadata"
        assert {"From", "To", "Cc", "Reply-To"} <= set(asked_for["metadata_headers"])
        assert "payload/headers" in asked_for["fields"]

    async def test_the_persons_unsent_words_stand_apart(self) -> None:
        asked = _gmail_message("m1", 0, "INBOX")
        client = self._client({"t1": [asked, _gmail_message("d1", 5, "DRAFT")]})

        found = await client.conversations_of([asked], 10)

        assert [row["id"] for row in found["t1"].messages] == ["m1"]
        assert [row["id"] for row in found["t1"].drafts] == ["d1"]

    async def test_the_newest_are_kept_and_the_cut_said(self) -> None:
        rows = [_gmail_message(f"m{i}", i, "INBOX") for i in range(4)]
        client = self._client({"t1": rows})

        found = await client.conversations_of([rows[-1]], 2)

        assert [row["id"] for row in found["t1"].messages] == ["m2", "m3"]
        assert found["t1"].truncated is True

    async def test_a_thread_that_cannot_be_read_is_absent_and_the_others_answer(self) -> None:
        kept = _gmail_message("m1", 0, "INBOX", thread="t1")
        lost = _gmail_message("x1", 0, "INBOX", thread="gone")
        client = self._client({"t1": [kept]})

        found = await client.conversations_of([lost, kept], 10)

        assert list(found) == ["t1"]

    async def test_no_listed_message_reads_nothing(self) -> None:
        client = self._client({})

        assert await client.conversations_of([], 10) == {}
        client.get_thread.assert_not_awaited()

    async def test_the_persons_later_message_reads_as_an_answer(self) -> None:
        asked = _gmail_message("m1", 0, "INBOX", From="Paul <paul@example.com>")
        reply = _gmail_message("m2", 30, "SENT", From=ME, To="Paul <paul@example.com>")
        client = self._client({"t1": [asked, reply]})
        listed = dict(asked)
        client._normalize_message_fields(listed, "metadata")

        found = await client.conversations_of([listed], 10)
        state = _state(listed, found["t1"])

        assert state is not None and state.message is not None
        assert (state.status, state.message.message_id) == ("answered", "m2")


# =============================================================================
# Outlook — a conversation id, one grouped request
# =============================================================================

SENT_FOLDER = "folder-sent"


def _graph_message(message_id: str, minute: int, **fields: Any) -> dict[str, Any]:
    return {
        "id": message_id,
        "conversationId": "c1",
        "internetMessageId": f"<{message_id}@graph>",
        "subject": "Budget",
        "from": {"emailAddress": {"address": "paul@example.com", "name": "Paul"}},
        "toRecipients": [{"emailAddress": {"address": "jane@outlook.com", "name": "Jane"}}],
        "bodyPreview": f"words of {message_id}",
        "receivedDateTime": f"2026-11-10T09:{minute:02d}:00Z",
        "parentFolderId": "folder-inbox",
        "isDraft": False,
        **fields,
    }


def _graph_sent(message_id: str, minute: int, **fields: Any) -> dict[str, Any]:
    return _graph_message(
        message_id,
        minute,
        parentFolderId=SENT_FOLDER,
        **{
            "from": {"emailAddress": {"address": "jane@outlook.com", "name": "Jane"}},
            "toRecipients": [{"emailAddress": {"address": "paul@example.com", "name": "Paul"}}],
            **fields,
        },
    )


class _Graph:
    """What Graph answers to ``POST /$batch``: one sub-answer per sub-request."""

    def __init__(self, conversations: dict[str, Any], *, sent_status: int = 200) -> None:
        self.conversations = conversations
        self.sent_status = sent_status
        self.batches: list[list[dict[str, Any]]] = []

    async def __call__(self, method: str, endpoint: str, *_: Any, **kwargs: Any) -> dict[str, Any]:
        assert (method, endpoint) == ("POST", "/$batch")
        requests = kwargs["json_data"]["requests"]
        self.batches.append(requests)
        return {"responses": [self._answer(request) for request in reversed(requests)]}

    def _answer(self, request: dict[str, Any]) -> dict[str, Any]:
        url = urlsplit(request["url"])
        if url.path.endswith("/mailFolders/sentitems"):
            return {"id": request["id"], "status": self.sent_status, "body": {"id": SENT_FOLDER}}
        asked = parse_qs(url.query)["$filter"][0]
        for conversation_id, answer in self.conversations.items():
            if f"conversationId eq '{conversation_id}'" in asked:
                if isinstance(answer, int):
                    return {"id": request["id"], "status": answer, "body": {}}
                return {"id": request["id"], "status": 200, "body": answer}
        return {"id": request["id"], "status": 200, "body": {"value": []}}


class TestOutlook:
    def _client(self, graph: _Graph) -> MicrosoftOutlookClient:
        client = MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())
        client._make_request = graph  # the fake IS the request seam
        return client

    def _listed(self, conversation_id: str = "c1", message_id: str = "m1") -> dict[str, Any]:
        return {"id": message_id, "threadId": conversation_id, "internalDate": "1"}

    async def test_every_conversation_of_the_page_is_read_in_one_request(self) -> None:
        graph = _Graph(
            {
                "c1": {"value": [_graph_message("m1", 0)]},
                "c2": {"value": [_graph_message("n1", 0, conversationId="c2")]},
            }
        )
        client = self._client(graph)

        found = await client.conversations_of(
            [self._listed("c1"), self._listed("c2", "n1"), self._listed("c1", "m9")], 10
        )

        assert len(graph.batches) == 1
        assert sorted(found) == ["c1", "c2"]

    async def test_the_filter_leads_with_the_field_it_sorts_on(self) -> None:
        """Graph refuses, or crawls through, a sort its filter does not lead with."""
        graph = _Graph({"c'1": {"value": []}})
        client = self._client(graph)

        await client.conversations_of([self._listed("c'1")], 10)

        url = next(r["url"] for r in graph.batches[0] if "/me/messages" in r["url"])
        query = parse_qs(urlsplit(url).query)
        assert query["$filter"] == [
            "receivedDateTime ge 1900-01-01T00:00:00Z and conversationId eq 'c''1'"
        ]
        assert query["$orderby"] == ["receivedDateTime desc"]
        assert query["$top"] == ["11"]

    async def test_more_conversations_than_a_batch_holds_are_read_in_several(self) -> None:
        graph = _Graph({})
        client = self._client(graph)
        listed = [self._listed(f"c{i}", f"m{i}") for i in range(25)]

        await client.conversations_of(listed, 10)

        assert len(graph.batches) == 2
        assert all(len(batch) <= 20 for batch in graph.batches)

    async def test_a_message_of_the_sent_folder_is_the_persons_own(self) -> None:
        graph = _Graph({"c1": {"value": [_graph_sent("m2", 10), _graph_message("m1", 0)]}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 10)

        rows = {row["id"]: row for row in found["c1"].messages}
        assert [row["id"] for row in found["c1"].messages] == ["m1", "m2"]  # oldest first
        assert "SENT" in rows["m2"]["labelIds"] and "SENT" not in rows["m1"]["labelIds"]
        assert rows["m2"]["rfc_message_id"] == "<m2@graph>"

    async def test_the_received_copy_of_a_message_the_person_sent_is_their_own_too(
        self,
    ) -> None:
        """A message sent to oneself exists twice under one Message-ID (measured on a
        real mailbox, 2026-11-11): the inbox copy is no stranger's message."""
        inbox_copy = _graph_message("m1", 1, internetMessageId="<same@graph>")
        sent_copy = _graph_sent("s1", 0, internetMessageId="<same@graph>")
        graph = _Graph({"c1": {"value": [inbox_copy, sent_copy]}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 10)

        assert all("SENT" in row["labelIds"] for row in found["c1"].messages)

    async def test_the_mark_exchange_keeps_on_an_answered_message_travels(self) -> None:
        marked = _graph_message(
            "m1",
            0,
            singleValueExtendedProperties=[
                {"id": "Integer 0x1081", "value": "102"},
                {"id": "SystemTime 0x1082", "value": "2026-11-10T09:45:00Z"},
            ],
        )
        forwarded = _graph_message(
            "m3",
            5,
            singleValueExtendedProperties=[{"id": "Integer 0x1081", "value": "104"}],
        )
        graph = _Graph({"c1": {"value": [forwarded, marked]}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 10)

        rows = {row["id"]: row for row in found["c1"].messages}
        stamped = datetime(2026, 11, 10, 9, 45, tzinfo=UTC)
        assert rows["m1"][FIELD_MAIL_ANSWERED] is True
        assert rows["m1"][FIELD_MAIL_ANSWERED_AT] == str(int(stamped.timestamp() * 1000))
        # A forward is no answer: its verb is not carried as one.
        assert FIELD_MAIL_ANSWERED not in rows["m3"]

    async def test_the_persons_unsent_words_stand_apart(self) -> None:
        graph = _Graph(
            {"c1": {"value": [_graph_sent("d1", 5, isDraft=True), _graph_message("m1", 0)]}}
        )
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 10)

        assert [row["id"] for row in found["c1"].messages] == ["m1"]
        assert [row["id"] for row in found["c1"].drafts] == ["d1"]

    async def test_one_more_than_kept_says_the_cut(self) -> None:
        rows = [_graph_message(f"m{i}", i) for i in (3, 2, 1)]
        graph = _Graph({"c1": {"value": rows}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 2)

        assert [row["id"] for row in found["c1"].messages] == ["m2", "m3"]
        assert found["c1"].truncated is True

    async def test_the_persons_unsent_words_never_say_a_cut(self) -> None:
        """Graph's bound counts every row it returns: two messages and a draft are whole."""
        rows = [
            _graph_sent("d1", 9, isDraft=True),
            _graph_message("m2", 2),
            _graph_message("m1", 1),
        ]
        graph = _Graph({"c1": {"value": rows}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 2)

        assert [row["id"] for row in found["c1"].messages] == ["m1", "m2"]
        assert found["c1"].truncated is False

    async def test_a_next_page_says_the_cut(self) -> None:
        graph = _Graph(
            {"c1": {"value": [_graph_message("m1", 1)], "@odata.nextLink": "https://next"}}
        )
        client = self._client(graph)

        found = await client.conversations_of([self._listed()], 10)

        assert found["c1"].truncated is True

    async def test_a_conversation_graph_refuses_is_absent_and_the_others_answer(self) -> None:
        graph = _Graph({"c1": 429, "c2": {"value": [_graph_message("n1", 0)]}})
        client = self._client(graph)

        found = await client.conversations_of([self._listed("c1"), self._listed("c2", "n1")], 10)

        assert list(found) == ["c2"]

    async def test_without_the_sent_folder_nobodys_message_can_be_told_from_the_persons(
        self,
    ) -> None:
        """No answer is better than one that calls the person's own reply a stranger's."""
        graph = _Graph({"c1": {"value": [_graph_message("m1", 0)]}}, sent_status=404)
        client = self._client(graph)

        assert await client.conversations_of([self._listed()], 10) == {}

    async def test_no_listed_message_reads_nothing(self) -> None:
        graph = _Graph({})
        client = self._client(graph)

        assert await client.conversations_of([], 10) == {}
        assert graph.batches == []

    async def test_the_persons_later_message_reads_as_an_answer(self) -> None:
        asked = _graph_message("m1", 0)
        graph = _Graph({"c1": {"value": [_graph_sent("m2", 30), asked]}})
        client = self._client(graph)
        from src.domains.connectors.clients.normalizers.microsoft_email_normalizer import (
            normalize_graph_message,
        )

        listed = normalize_graph_message(asked)
        found = await client.conversations_of([listed], 10)
        state = _state(listed, found["c1"])

        assert state is not None and state.message is not None
        assert (state.status, state.message.message_id) == ("answered", "m2")
        assert state.message.correspondents == "Paul"


# =============================================================================
# iCloud — the headers, one session
# =============================================================================


def _mail(
    message_id: str,
    *,
    references: str = "",
    day: int = 1,
    sender: str = "paul@example.com",
    to: str = ME,
) -> EmailMessage:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = to
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

    def _listed(
        self, client: AppleEmailClient, uid: str, thread: str, folder: str = "INBOX", day: int = 1
    ) -> dict[str, Any]:
        scope = scope_digest(mailbox_account_scope(client.credentials.apple_id), folder, 1)
        return {
            "id": message_handle(folder, uid, scope=scope),
            "threadId": thread,
            "rfc_message_id": thread,
            "labelIds": [folder],
            "from": "paul@example.com",
            "to": ME,
            "internalDate": str(int(datetime(2026, 11, day, 9, 0, tzinfo=UTC).timestamp() * 1000)),
        }

    async def test_the_sent_folder_holds_the_persons_own_messages(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put(
            "Sent Messages",
            _mail("<b@x>", references="<a@x>", day=2, sender=ME, to="paul@example.com"),
        )

        found = await client.conversations_of([self._listed(client, asked, "<a@x>")], 10)

        rows = found["<a@x>"].messages
        assert [row["rfc_message_id"] for row in rows] == ["<a@x>", "<b@x>"]
        assert "SENT" in rows[1]["labelIds"] and "SENT" not in rows[0]["labelIds"]

    async def test_a_message_found_again_in_the_sent_folder_is_the_persons_own(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        """A note sent to oneself sits in the inbox AND in the sent folder: the copy
        the listing named keeps its id, and says who wrote it."""
        note = imap.put("INBOX", _mail("<n@x>", sender=ME, to="paul@example.com"))
        imap.put("Sent Messages", _mail("<n@x>", sender=ME, to="paul@example.com"))
        listed = self._listed(client, note, "<n@x>")

        found = await client.conversations_of([listed], 10)

        rows = found["<n@x>"].messages
        assert [row["id"] for row in rows] == [listed["id"]]
        assert "SENT" in rows[0]["labelIds"]

    async def test_several_conversations_are_read_in_one_session(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        first = imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put("INBOX", _mail("<a2@x>", references="<a@x>", day=2))
        second = imap.put("INBOX", _mail("<z@x>", day=3))

        found = await client.conversations_of(
            [self._listed(client, first, "<a@x>"), self._listed(client, second, "<z@x>", day=3)],
            10,
        )

        assert imap.sessions == 1
        assert [row["rfc_message_id"] for row in found["<a@x>"].messages] == ["<a@x>", "<a2@x>"]
        assert [row["rfc_message_id"] for row in found["<z@x>"].messages] == ["<z@x>"]

    async def test_the_answered_flag_travels(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = imap.put("INBOX", _mail("<a@x>"), ("\\Seen", "\\Answered"))

        found = await client.conversations_of([self._listed(client, asked, "<a@x>")], 10)

        assert found["<a@x>"].messages[0][FIELD_MAIL_ANSWERED] is True

    async def test_the_persons_unsent_words_stand_apart(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put(
            "Drafts",
            _mail("<d@x>", references="<a@x>", day=2, sender=ME, to="paul@example.com"),
            ("\\Draft",),
        )

        found = await client.conversations_of([self._listed(client, asked, "<a@x>")], 10)

        assert [row["rfc_message_id"] for row in found["<a@x>"].messages] == ["<a@x>"]
        assert [row["rfc_message_id"] for row in found["<a@x>"].drafts] == ["<d@x>"]

    async def test_a_message_naming_nothing_stands_alone(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        nameless = imap.put("INBOX", _mail(""))
        listed = self._listed(client, nameless, "")
        listed["threadId"] = listed["id"]  # the normaliser's own fallback
        listed["rfc_message_id"] = None

        found = await client.conversations_of([listed], 10)

        assert [row["id"] for row in found[listed["id"]].messages] == [listed["id"]]

    async def test_reading_them_marks_nothing_read(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = imap.put("INBOX", _mail("<a@x>"))
        fetch = MagicMock(side_effect=imap.fetch)
        imap.fetch = fetch

        await client.conversations_of([self._listed(client, asked, "<a@x>")], 10)

        assert fetch.call_args_list
        assert all(call.kwargs["mark_seen"] is False for call in fetch.call_args_list)
        assert all(call.kwargs["headers_only"] is True for call in fetch.call_args_list)

    async def test_no_listed_message_opens_no_session(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        assert await client.conversations_of([], 10) == {}
        assert imap.sessions == 0

    async def test_the_persons_later_message_reads_as_an_answer(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        asked = imap.put("INBOX", _mail("<a@x>", day=1))
        imap.put(
            "Sent Messages",
            _mail("<b@x>", references="<a@x>", day=2, sender=ME, to="paul@example.com"),
        )
        listed = self._listed(client, asked, "<a@x>")

        found = await client.conversations_of([listed], 10)
        state = _state(listed, found["<a@x>"])

        assert state is not None and state.message is not None
        assert state.status == "answered"
        assert state.message.correspondents == "paul@example.com"

    async def test_a_reply_dated_before_what_it_answers_still_answers_it(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        """IMAP dates a message by its author's clock; the reply NAMES what it answers."""
        asked = imap.put("INBOX", _mail("<a@x>", day=5))
        imap.put(
            "Sent Messages",
            _mail("<b@x>", references="<a@x>", day=4, sender=ME, to="paul@example.com"),
        )
        listed = self._listed(client, asked, "<a@x>", day=5)

        found = await client.conversations_of([listed], 10)

        state = _state(listed, found["<a@x>"])
        assert state is not None and state.status == "answered"
