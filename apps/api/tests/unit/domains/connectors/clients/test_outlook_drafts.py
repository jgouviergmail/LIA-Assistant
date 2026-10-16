"""Mailbox drafts on Outlook through Microsoft Graph (ADR-344).

The fake honours Graph's DOCUMENTED contract (the Outlook connector of the test
account could not be reconnected for a live measurement): a draft is a message
with ``isDraft`` in the Drafts folder; ``createReply``/``createReplyAll``/
``createForward`` answer 201 with the draft, whose body quotes the original —
and the ``comment`` parameter is NOT written into that body (a documented known
issue), so the person's words are written by a PATCH; ``createForward`` refuses
a draft without a recipient; ``move`` gives the message a new id; ``send``
answers 202 with no body; an unknown id is a 404.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_SET_ASIDE_ON_PAGE
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    MailboxDraftNotFoundError,
)
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.clients.outlook_drafts_mixin import with_own_words
from src.domains.connectors.schemas import ConnectorCredentials

pytestmark = pytest.mark.unit

DRAFTS = "folder-drafts"
DELETED = "folder-deleted"
INBOX = "folder-inbox"


def _recipient(address: str, name: str = "") -> dict[str, Any]:
    return {"emailAddress": {"address": address, "name": name}}


class FakeGraph:
    """The messages and folders a draft lives among, in memory."""

    def __init__(self) -> None:
        self.messages: dict[str, dict[str, Any]] = {}
        self.calls: list[dict[str, Any]] = []
        self.fail_patch = False
        self._serial = 0
        self._clock = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)

    def _id(self) -> str:
        self._serial += 1
        return f"AAMk-{self._serial}="

    def _stamp(self) -> str:
        self._clock += timedelta(minutes=1)
        return self._clock.isoformat().replace("+00:00", "Z")

    def add(self, *, folder: str, is_draft: bool, **fields: Any) -> str:
        message_id = self._id()
        self.messages[message_id] = {
            "id": message_id,
            "conversationId": "conv-1",
            "subject": "",
            "toRecipients": [],
            "ccRecipients": [],
            "bccRecipients": [],
            "body": {"contentType": "text", "content": ""},
            "receivedDateTime": "2026-10-01T08:00:00Z",
            "lastModifiedDateTime": self._stamp(),
            "isDraft": is_draft,
            "isRead": True,
            "parentFolderId": folder,
            "webLink": f"https://outlook.live.com/owa/?ItemID={message_id}",
            **fields,
        }
        return message_id

    @staticmethod
    def missing() -> ConnectorAPIError:
        return ConnectorAPIError(connector_type="microsoft_outlook", status_code=404, detail="nf")

    def _get(self, message_id: str) -> dict[str, Any]:
        if message_id not in self.messages:
            raise self.missing()
        return self.messages[message_id]

    def _quoting_draft(self, original: dict[str, Any], **fields: Any) -> dict[str, Any]:
        quoted = (
            "<html><head></head><body><div></div><hr>"
            '<div id="divRplyFwdMsg"><b>From:</b> Paul<br><b>Subject:</b> '
            f"{original['subject']}</div><div>Voici le budget.</div></body></html>"
        )
        draft_id = self.add(
            folder=DRAFTS,
            is_draft=True,
            body={"contentType": "html", "content": quoted},
            **fields,
        )
        return self.messages[draft_id]

    async def request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "endpoint": endpoint,
                "params": params or {},
                "json": json_data,
                "max_retries": max_retries,
            }
        )
        if method == "GET" and endpoint == "/me/mailFolders/drafts":
            return {"id": DRAFTS}
        if method == "GET" and endpoint == "/me/mailFolders/drafts/messages":
            listed = sorted(
                (m for m in self.messages.values() if m["parentFolderId"] == DRAFTS),
                key=lambda m: m["lastModifiedDateTime"],
                reverse=True,
            )
            return {"value": listed, "@odata.nextLink": "https://graph.microsoft.com/v1.0/next"}
        if method == "GET" and endpoint.startswith("/me/messages/"):
            return self._get(endpoint.rsplit("/", 1)[1])
        if method == "POST" and endpoint == "/me/messages":
            payload = dict(json_data or {})
            payload["body"] = {
                **payload["body"],
                "contentType": payload["body"]["contentType"].lower(),
            }
            return self.messages[self.add(folder=DRAFTS, is_draft=True, **payload)]
        match = re.fullmatch(r"/me/messages/([^/]+)/(\w+)", endpoint)
        if method == "POST" and match:
            message_id, action = match.groups()
            original = self._get(message_id)
            if action in {"createReply", "createReplyAll"}:
                answered = [original["from"]]
                if action == "createReplyAll":
                    answered += original["toRecipients"]
                return self._quoting_draft(
                    original, subject=f"RE: {original['subject']}", toRecipients=answered
                )
            if action == "createForward":
                message = (json_data or {}).get("message", {})
                if not message.get("toRecipients"):
                    raise ConnectorAPIError(
                        connector_type="microsoft_outlook", status_code=400, detail="to"
                    )
                return self._quoting_draft(
                    original, subject=f"FW: {original['subject']}", **message
                )
            if action == "move":
                moved = self.messages.pop(message_id)
                moved_id = self._id()
                self.messages[moved_id] = {**moved, "id": moved_id, "parentFolderId": DELETED}
                return self.messages[moved_id]
            if action == "send":
                if not original["isDraft"]:
                    raise ConnectorAPIError(
                        connector_type="microsoft_outlook", status_code=400, detail="sent"
                    )
                self.messages.pop(message_id)
                return {}
        if method == "PATCH" and endpoint.startswith("/me/messages/"):
            if self.fail_patch:
                raise ConnectorAPIError(
                    connector_type="microsoft_outlook", status_code=400, detail="bad"
                )
            message = self._get(endpoint.rsplit("/", 1)[1])
            message.update(json_data or {})
            if "body" in message:  # Graph answers the body type in lower case
                body = message["body"]
                message["body"] = {**body, "contentType": body["contentType"].lower()}
            message["lastModifiedDateTime"] = self._stamp()
            return message
        if method == "DELETE" and endpoint.startswith("/me/messages/"):
            self.messages.pop(endpoint.rsplit("/", 1)[1], None)
            return {}
        raise AssertionError(f"unexpected {method} {endpoint}")


@pytest.fixture
def graph() -> FakeGraph:
    return FakeGraph()


@pytest.fixture
def client(graph: FakeGraph) -> Iterator[MicrosoftOutlookClient]:
    instance = MicrosoftOutlookClient(
        user_id=uuid4(),
        credentials=ConnectorCredentials(
            access_token="token",
            refresh_token="refresh",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        ),
        connector_service=MagicMock(),
    )
    with patch.object(instance, "_make_request", side_effect=graph.request):
        yield instance


def _original(graph: FakeGraph) -> str:
    return graph.add(
        folder=INBOX,
        is_draft=False,
        subject="Budget 2027",
        **{"from": _recipient("paul@example.com", "Paul Durand")},
        toRecipients=[_recipient("me@example.com"), _recipient("marie@example.com")],
    )


def _calls(graph: FakeGraph, method: str, suffix: str = "") -> list[dict[str, Any]]:
    return [c for c in graph.calls if c["method"] == method and c["endpoint"].endswith(suffix)]


class TestWithOwnWords:
    def test_the_words_open_the_html_body_above_the_quote(self) -> None:
        body = with_own_words(
            {"contentType": "html", "content": "<html><body dir='ltr'><hr>quote</body></html>"},
            "Bonjour <Paul>,\nOk.",
            is_html=False,
        )

        assert body == {
            "contentType": "HTML",
            "content": "<html><body dir='ltr'><div>Bonjour &lt;Paul&gt;,<br>Ok.</div>"
            "<hr>quote</body></html>",
        }

    def test_a_text_body_keeps_its_text(self) -> None:
        assert with_own_words(
            {"contentType": "text", "content": "> quote"}, "Ok.", is_html=False
        ) == {"contentType": "Text", "content": "Ok.\n\n> quote"}


class TestCreate:
    async def test_a_new_draft_is_saved_in_the_drafts_folder(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft = await client.create_draft(
            '"Durand, Paul" <paul@example.com>', "Budget", "Bonjour", bcc="boss@example.com"
        )

        (post,) = _calls(graph, "POST", "/me/messages")
        assert post["max_retries"] == 1
        assert post["json"]["toRecipients"] == [_recipient("paul@example.com", "Durand, Paul")]
        assert post["json"]["body"] == {"contentType": "Text", "content": "Bonjour"}
        assert draft[FIELD_MAILBOX_DRAFT_ID] == draft["id"]
        assert (draft["subject"], draft["bcc"]) == ("Budget", "boss@example.com")

    async def test_a_new_draft_may_have_no_recipient_yet(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        await client.create_draft("", "Idée", "À compléter")

        (post,) = _calls(graph, "POST", "/me/messages")
        assert "toRecipients" not in post["json"]

    async def test_a_reply_draft_writes_the_words_above_the_quote(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        original = _original(graph)

        draft = await client.create_reply_draft(original, "Validé.", reply_all=True)

        (create,) = _calls(graph, "POST", "/createReplyAll")
        assert create["max_retries"] == 1
        assert "comment" not in (create["json"] or {})
        assert draft["body"].startswith("Validé.")
        assert "Voici le budget." in draft["body"]
        assert draft["to"] == "Paul Durand <paul@example.com>, me@example.com, marie@example.com"

    async def test_a_reply_draft_that_cannot_take_its_words_is_removed(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        original = _original(graph)
        graph.fail_patch = True

        with pytest.raises(ConnectorAPIError):
            await client.create_reply_draft(original, "Validé.")

        assert not [m for m in graph.messages.values() if m["isDraft"]]

    async def test_a_forward_draft_names_its_recipients(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        original = _original(graph)

        draft = await client.create_forward_draft(
            original, "marie@example.com", body="Pour info.", cc="anne@example.com"
        )

        (create,) = _calls(graph, "POST", "/createForward")
        assert create["json"] == {
            "message": {
                "toRecipients": [_recipient("marie@example.com")],
                "ccRecipients": [_recipient("anne@example.com")],
            }
        }
        assert draft["body"].startswith("Pour info.")


class TestUpdate:
    async def test_a_current_revision_can_patch_the_message(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft_id = graph.add(folder=DRAFTS, is_draft=True, changeKey="current")
        revision = (await client.get_draft(draft_id))["mailbox_draft_revision"]
        result = await client.update_draft(
            draft_id, body="Current words", expected_revision=revision
        )

        assert result["body"] == "Current words"

    async def test_a_stale_revision_refuses_before_patching_the_message(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft_id = graph.add(folder=DRAFTS, is_draft=True, changeKey="current")
        with pytest.raises(LookupError):
            await client.update_draft(draft_id, body="Stale words", expected_revision="old-version")

        assert _calls(graph, "PATCH") == []
        reads = _calls(graph, "GET")
        assert "changeKey" in reads[0]["params"]["$select"].split(",")

    async def test_only_the_fields_given_are_written(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft_id = graph.add(
            folder=DRAFTS,
            is_draft=True,
            subject="Budget",
            toRecipients=[_recipient("paul@example.com")],
            ccRecipients=[_recipient("anne@example.com")],
        )

        draft = await client.update_draft(draft_id, cc="", body="New words.")

        (patch_call,) = _calls(graph, "PATCH")
        assert patch_call["json"] == {
            "ccRecipients": [],
            "body": {"contentType": "Text", "content": "New words."},
        }
        assert (draft["cc"], draft["to"]) == ("", "paul@example.com")

    @pytest.mark.parametrize(("folder", "is_draft"), [(DELETED, True), (INBOX, False)])
    async def test_a_message_that_is_not_a_live_draft_is_never_edited(
        self, client: MicrosoftOutlookClient, graph: FakeGraph, folder: str, is_draft: bool
    ) -> None:
        message_id = graph.add(folder=folder, is_draft=is_draft, subject="x")

        with pytest.raises(MailboxDraftNotFoundError):
            await client.update_draft(message_id, subject="changed")

        assert not _calls(graph, "PATCH")


class TestRead:
    async def test_an_invisible_revision_change_changes_the_confirmation_fingerprint(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        from src.domains.agents.tools.mailbox_draft_send_tools import live_digest

        handle = graph.add(folder=DRAFTS, is_draft=True, changeKey="first")
        before = await client.get_draft(handle)
        graph.messages[handle]["changeKey"] = "replacement"

        after = await client.get_draft(handle)

        assert before["body"] == after["body"]
        assert live_digest(before) != live_digest(after)
        read = _calls(graph, "GET", f"/me/messages/{handle}")[0]
        assert "changeKey" in read["params"]["$select"].split(",")

    async def test_the_listing_reads_the_drafts_folder_newest_first(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        first = graph.add(folder=DRAFTS, is_draft=True, subject="1")
        second = graph.add(folder=DRAFTS, is_draft=True, subject="2")

        listing = await client.list_drafts(max_results=5)

        (call,) = _calls(graph, "GET", "/me/mailFolders/drafts/messages")
        assert call["params"]["$orderby"] == "lastModifiedDateTime desc"
        assert call["params"]["$top"] == 5
        assert [d[FIELD_MAILBOX_DRAFT_ID] for d in listing["messages"]] == [second, first]
        assert listing["messages"][0]["date"] == graph.messages[second]["lastModifiedDateTime"]
        assert listing["next_page_token"] == "https://graph.microsoft.com/v1.0/next"

    async def test_a_recipient_query_searches_without_ordering(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        await client.list_drafts("to:marie")

        (call,) = _calls(graph, "GET", "/me/mailFolders/drafts/messages")
        assert call["params"]["$search"] == '"to:marie"'
        assert "$orderby" not in call["params"]

    async def test_a_filter_is_led_by_the_sort_property(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        await client.list_drafts("has:attachment")

        (call,) = _calls(graph, "GET", "/me/mailFolders/drafts/messages")
        assert call["params"]["$filter"].startswith("lastModifiedDateTime ge ")
        assert call["params"]["$filter"].endswith(" and hasAttachments eq true")
        assert call["params"]["$orderby"] == "lastModifiedDateTime desc"

    async def test_a_date_reads_the_draft_s_last_save(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        """The listing sorts on the last save and shows it as the draft's date:
        « my drafts since Monday » filters on it too, never on the reception
        date Graph gives a draft."""
        await client.list_drafts("after:2026/10/01")

        (call,) = _calls(graph, "GET", "/me/mailFolders/drafts/messages")
        assert call["params"]["$filter"] == "lastModifiedDateTime ge 2026-10-01T00:00:00Z"

    async def test_a_search_keeps_its_terms_and_checks_the_date_on_its_page(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        """A date beside a recipient used to be dropped with the whole filter:
        « my drafts to Marie since the 1st » listed every draft to Marie, and a
        deletion by search trashed drafts outside the range (RC3.1)."""
        graph.add(folder=DRAFTS, is_draft=True, lastModifiedDateTime="2026-09-01T08:00:00Z")
        recent = graph.add(
            folder=DRAFTS, is_draft=True, lastModifiedDateTime="2026-10-12T08:00:00Z"
        )

        listing = await client.list_drafts("to:marie after:2026/10/01")

        (call,) = _calls(graph, "GET", "/me/mailFolders/drafts/messages")
        assert call["params"]["$search"] == '"to:marie"'
        assert [d[FIELD_MAILBOX_DRAFT_ID] for d in listing["messages"]] == [recent]
        assert listing[FIELD_SET_ASIDE_ON_PAGE] == 1

    async def test_a_foreign_page_token_is_refused(self, client: MicrosoftOutlookClient) -> None:
        with pytest.raises(ValueError):
            await client.list_drafts(page_token="https://evil.example.com/v1.0/me")

    @pytest.mark.parametrize("handle", ["", "../me", "AAMk/1", "AAMk 1"])
    async def test_a_handle_that_cannot_be_an_id_reaches_no_endpoint(
        self, client: MicrosoftOutlookClient, graph: FakeGraph, handle: str
    ) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.get_draft(handle)

        assert graph.calls == []

    async def test_an_unknown_draft_is_not_found(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.get_draft("AAMk+404=")

        assert _calls(graph, "GET", "/me/messages/AAMk+404=")


class TestTrashAndSend:
    async def test_drafts_move_to_deleted_items(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft_id = graph.add(folder=DRAFTS, is_draft=True)
        received = graph.add(folder=INBOX, is_draft=False)

        result = await client.trash_drafts([draft_id, received, "AAMk-404="])

        assert result["trashed"] == [draft_id]
        assert [f["status"] for f in result["failed"]] == [TRASH_NOT_FOUND, TRASH_NOT_FOUND]
        assert [m["parentFolderId"] for m in graph.messages.values() if m["isDraft"]] == [DELETED]
        assert received in graph.messages

    async def test_a_draft_is_sent_once(
        self, client: MicrosoftOutlookClient, graph: FakeGraph
    ) -> None:
        draft_id = graph.add(folder=DRAFTS, is_draft=True)

        result = await client.send_draft(draft_id)

        (send,) = _calls(graph, "POST", "/send")
        assert send["max_retries"] == 1
        assert result == {"id": None, FIELD_MAILBOX_DRAFT_ID: draft_id, "draft_kept": False}

    async def test_sending_an_unknown_draft_is_not_found(
        self, client: MicrosoftOutlookClient
    ) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.send_draft("AAMk-404=")
