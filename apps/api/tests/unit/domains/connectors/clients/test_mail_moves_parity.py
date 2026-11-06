"""Sorting the mail on the three providers — one contract (ADR-369, lot 4).

A place is named by its role or by a folder of the person's own, and each client
says it in its own words: Gmail moves labels, Graph moves the item and hands back a
new id, IMAP moves the message to another folder where it has another UID. The
caller reads one answer: each id moved, with its id afterwards when it is known, or
reported with why — never the whole selection lost to one message that left.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import AuthenticationError
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_folders import (
    MailFolderNameTakenError,
    MailFolderNotEmptyError,
    SystemFolderError,
)
from src.domains.connectors.clients.mail_moves import MailPlace, UnreadCounts
from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_FAILED,
    READ_STATE_NOT_FOUND,
    READ_STATE_UNANSWERED,
)
from src.domains.connectors.clients.microsoft_outlook_client import MicrosoftOutlookClient
from src.domains.connectors.schemas import AppleCredentials, ConnectorCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

APPLE = "src.domains.connectors.clients.apple_email_client"
APPLE_MIXIN = "src.domains.connectors.clients.apple_drafts_mixin"
APPLE_STATE = "src.domains.connectors.clients.apple_mail_state_mixin"
APPLE_MOVES = "src.domains.connectors.clients.apple_mailbox_acts_mixin"

INBOX = MailPlace(role="inbox")
ARCHIVE = MailPlace(role="archive")
SPAM = MailPlace(role="spam")
TRASH = MailPlace(role="trash")


def _credentials() -> ConnectorCredentials:
    return ConnectorCredentials(
        access_token="token",
        refresh_token="refresh",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )


class _Recorder:
    def __init__(self, answer: Callable[[httpx.Request], httpx.Response]) -> None:
        self.answer = answer
        self.calls: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.calls.append((request.method, request.url.raw_path.decode(), body))
        return self.answer(request)


async def _drive(client: Any, recorder: _Recorder, call: Callable[[], Any]) -> Any:
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as http:
        client._http_client = http
        with (
            patch.object(client, "_rate_limit", AsyncMock()),
            patch.object(client, "_is_circuit_breaker_enabled", return_value=False),
            patch("asyncio.sleep", AsyncMock()),
        ):
            return await call()


class TestMailPlace:
    def test_a_place_is_a_role_or_a_folder(self) -> None:
        assert MailPlace(role="archive").folder is None
        assert MailPlace(folder="Projects").role is None

    @pytest.mark.parametrize("named", [{}, {"role": "inbox", "folder": "Projects"}])
    def test_it_is_exactly_one_of_them(self, named: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            MailPlace(**named)


class TestGmail:
    @pytest.fixture
    def client(self) -> Iterator[GoogleGmailClient]:
        client = GoogleGmailClient(uuid4(), _credentials(), MagicMock())
        # No real Redis: the generation a write moves is the freshness suite's to prove.
        with patch(
            "src.domains.connectors.clients.google_gmail_client.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
        ):
            yield client

    @pytest.mark.parametrize(
        ("place", "origin", "add", "remove"),
        [
            (INBOX, None, ["INBOX"], ["SPAM"]),
            (ARCHIVE, None, [], ["INBOX", "SPAM"]),
            (SPAM, None, ["SPAM"], ["INBOX"]),
            (MailPlace(folder="Label_1"), None, ["Label_1"], ["INBOX", "SPAM"]),
            # Leaving a label of the person's own takes it off; arriving never does.
            (INBOX, MailPlace(folder="Label_2"), ["INBOX"], ["SPAM", "Label_2"]),
            (
                MailPlace(folder="Label_1"),
                MailPlace(folder="Label_2"),
                ["Label_1"],
                ["INBOX", "SPAM", "Label_2"],
            ),
            (
                MailPlace(folder="Label_1"),
                MailPlace(folder="Label_1"),
                ["Label_1"],
                ["INBOX", "SPAM"],
            ),
        ],
    )
    async def test_a_move_is_one_batch_of_labels_and_the_id_stays(
        self,
        client: GoogleGmailClient,
        place: MailPlace,
        origin: MailPlace | None,
        add: list[str],
        remove: list[str],
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        result = await _drive(
            client, recorder, lambda: client.move_emails(["m1", "m2"], place, origin)
        )

        assert result == {"updated": ["m1", "m2"], "failed": [], "moved": {"m1": "m1", "m2": "m2"}}
        ((method, path, body),) = recorder.calls
        assert (method, path) == ("POST", "/gmail/v1/users/me/messages/batchModify")
        assert body == {
            "ids": ["m1", "m2"],
            **({"addLabelIds": add} if add else {}),
            "removeLabelIds": remove,
        }

    async def test_a_refused_batch_finds_the_gone_message_one_by_one(
        self, client: GoogleGmailClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("batchModify"):
                return httpx.Response(400, json={"error": {"message": "Invalid id value"}})
            if "/messages/gone/" in request.url.path:
                return httpx.Response(404, json={"error": {"code": 404}})
            return httpx.Response(200, json={"id": "m1", "labelIds": []})

        result = await _drive(
            client, _Recorder(answer), lambda: client.move_emails(["m1", "gone"], ARCHIVE)
        )

        assert result == {
            "updated": ["m1"],
            "failed": [{"id": "gone", "status": READ_STATE_NOT_FOUND}],
            "moved": {"m1": "m1"},
        }

    async def test_the_trash_goes_through_the_provider_s_own_act(
        self, client: GoogleGmailClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if "/messages/gone/" in request.url.path:
                return httpx.Response(404, json={"error": {"code": 404}})
            return httpx.Response(200, json={"id": "m1", "labelIds": ["TRASH"]})

        recorder = _Recorder(answer)
        result = await _drive(client, recorder, lambda: client.move_emails(["m1", "gone"], TRASH))

        assert ("POST", "/gmail/v1/users/me/messages/m1/trash", None) in recorder.calls
        assert result == {
            "updated": ["m1"],
            "failed": [{"id": "gone", "status": READ_STATE_NOT_FOUND}],
            "moved": {"m1": "m1"},
        }

    async def test_leaving_the_trash_untrashes_then_places_the_message(
        self, client: GoogleGmailClient
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "m1", "labelIds": []}))

        result = await _drive(client, recorder, lambda: client.move_emails(["m1"], INBOX, TRASH))

        assert [(method, path) for method, path, _ in recorder.calls] == [
            ("POST", "/gmail/v1/users/me/messages/m1/untrash"),
            ("POST", "/gmail/v1/users/me/messages/m1/modify"),
        ]
        assert recorder.calls[1][2] == {"addLabelIds": ["INBOX"], "removeLabelIds": ["SPAM"]}
        assert result["moved"] == {"m1": "m1"}

    @pytest.mark.parametrize(
        ("place", "origin"),
        [(MailPlace(folder="TRASH"), None), (ARCHIVE, MailPlace(folder="SENT"))],
    )
    async def test_a_system_label_is_never_taken_for_a_folder_of_the_person(
        self, client: GoogleGmailClient, place: MailPlace, origin: MailPlace | None
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        with pytest.raises(ValueError):
            await _drive(client, recorder, lambda: client.move_emails(["m1"], place, origin))

        assert recorder.calls == []

    async def test_an_id_that_cannot_be_one_asks_nothing(self, client: GoogleGmailClient) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        result = await _drive(
            client, recorder, lambda: client.move_emails(["m1", "x/../drafts/y"], ARCHIVE)
        )

        assert result["failed"] == [{"id": "x/../drafts/y", "status": READ_STATE_NOT_FOUND}]
        assert recorder.calls[0][2]["ids"] == ["m1"]

    @pytest.mark.parametrize(
        ("starred", "expected"),
        [(True, {"addLabelIds": ["STARRED"]}), (False, {"removeLabelIds": ["STARRED"]})],
    )
    async def test_a_star_is_one_batch(
        self, client: GoogleGmailClient, starred: bool, expected: dict[str, list[str]]
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(204))

        result = await _drive(client, recorder, lambda: client.set_starred(["m1"], starred))

        assert result == {"updated": ["m1"], "failed": []}
        assert recorder.calls[0][2] == {"ids": ["m1"], **expected}

    async def test_unread_counts_read_each_label_s_own_figure(
        self, client: GoogleGmailClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/labels"):
                return httpx.Response(
                    200,
                    json={
                        "labels": [
                            {"id": "INBOX", "name": "INBOX", "type": "system"},
                            {"id": "SENT", "name": "SENT", "type": "system"},
                            {"id": "Label_1", "name": "Work", "type": "user"},
                        ]
                    },
                )
            unread = {"INBOX": 3, "SPAM": 1, "Label_1": 2}[request.url.path.rsplit("/", 1)[-1]]
            return httpx.Response(200, json={"messagesUnread": unread})

        recorder = _Recorder(answer)
        counts = await _drive(client, recorder, lambda: client.unread_counts(10))

        assert counts == UnreadCounts(
            roles={"inbox": 3, "spam": 1}, folders={"Label_1": 2}, complete=True
        )
        assert "/gmail/v1/users/me/labels/SENT" not in {path for _, path, _ in recorder.calls}

    async def test_unread_counts_state_their_cut(self, client: GoogleGmailClient) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/labels"):
                names = [{"id": f"Label_{n}", "name": str(n), "type": "user"} for n in range(5)]
                return httpx.Response(200, json={"labels": names})
            return httpx.Response(200, json={"messagesUnread": 1})

        counts = await _drive(client, _Recorder(answer), lambda: client.unread_counts(2))

        assert sorted(counts.folders) == ["Label_0", "Label_1"]
        assert counts.complete is False


class TestOutlook:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    @pytest.mark.parametrize(
        ("place", "destination"),
        [
            (INBOX, "inbox"),
            (ARCHIVE, "archive"),
            (SPAM, "junkemail"),
            (TRASH, "deleteditems"),
        ],
    )
    async def test_a_role_is_a_well_known_folder_and_the_answer_is_the_new_id(
        self, client: MicrosoftOutlookClient, place: MailPlace, destination: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(201, json={"id": "new-1"}))

        result = await _drive(client, recorder, lambda: client.move_emails(["o1"], place))

        assert result == {"updated": ["o1"], "failed": [], "moved": {"o1": "new-1"}}
        assert recorder.calls == [
            ("POST", "/v1.0/me/messages/o1/move", {"destinationId": destination})
        ]

    async def test_a_folder_of_the_person_s_own_is_found_by_its_path(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200, json={"value": [{"id": "f-9", "displayName": "Projects"}]}
                )
            return httpx.Response(201, json={"id": "new-1"})

        recorder = _Recorder(answer)
        result = await _drive(
            client, recorder, lambda: client.move_emails(["o1"], MailPlace(folder="Projects"))
        )

        assert result["moved"] == {"o1": "new-1"}
        assert recorder.calls[-1][2] == {"destinationId": "f-9"}

    async def test_a_gone_message_is_named_and_the_rest_still_moves(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if "gone" in request.url.path:
                return httpx.Response(404, json={"error": {"code": "ErrorItemNotFound"}})
            return httpx.Response(201, json={"id": "new-1"})

        result = await _drive(
            client, _Recorder(answer), lambda: client.move_emails(["o1", "gone"], ARCHIVE)
        )

        assert result == {
            "updated": ["o1"],
            "failed": [{"id": "gone", "status": READ_STATE_NOT_FOUND}],
            "moved": {"o1": "new-1"},
        }

    async def test_a_refusal_for_one_message_stays_its_own(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if "bad" in request.url.path:
                return httpx.Response(403, json={"error": {"code": "ErrorAccessDenied"}})
            return httpx.Response(201, json={"id": "new-1"})

        result = await _drive(
            client, _Recorder(answer), lambda: client.move_emails(["o1", "bad"], ARCHIVE)
        )

        assert result["failed"] == [{"id": "bad", "status": READ_STATE_FAILED}]

    async def test_a_failure_of_the_mailbox_before_anything_moved_is_the_act_s_own(
        self, client: MicrosoftOutlookClient
    ) -> None:
        with (
            patch.object(
                client, "_make_request", AsyncMock(side_effect=AuthenticationError("expired"))
            ),
            pytest.raises(AuthenticationError),
        ):
            await client.move_emails(["o1", "o2"], ARCHIVE)

    async def test_after_one_moved_the_rest_are_unanswered_never_hidden(
        self, client: MicrosoftOutlookClient
    ) -> None:
        answers: list[Any] = [{"id": "new-1"}, AuthenticationError("expired")]

        async def request(*args: Any, **kwargs: Any) -> dict[str, Any]:
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

        with patch.object(client, "_make_request", request):
            result = await client.move_emails(["o1", "o2"], ARCHIVE)

        assert result == {
            "updated": ["o1"],
            "failed": [{"id": "o2", "status": READ_STATE_UNANSWERED}],
            "moved": {"o1": "new-1"},
        }

    @pytest.mark.parametrize(("starred", "status"), [(True, "flagged"), (False, "notFlagged")])
    async def test_a_star_is_the_message_s_flag(
        self, client: MicrosoftOutlookClient, starred: bool, status: str
    ) -> None:
        recorder = _Recorder(lambda request: httpx.Response(200, json={"id": "o1"}))

        result = await _drive(client, recorder, lambda: client.set_starred(["o1"], starred))

        assert result == {"updated": ["o1"], "failed": []}
        assert recorder.calls == [
            ("PATCH", "/v1.0/me/messages/o1", {"flag": {"flagStatus": status}})
        ]

    async def test_forever_reaches_only_a_message_of_the_trash(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if path.endswith("/mailFolders/deleteditems"):
                return httpx.Response(200, json={"id": "trash-id"})
            if request.method == "GET":
                parent = "inbox-id" if "kept" in path else "trash-id"
                return httpx.Response(200, json={"parentFolderId": parent})
            return httpx.Response(204)

        recorder = _Recorder(answer)
        result = await _drive(
            client, recorder, lambda: client.delete_emails_forever(["t1", "kept"])
        )

        assert result == {
            "updated": ["t1"],
            "failed": [{"id": "kept", "status": READ_STATE_FAILED}],
        }
        posted = [path for method, path, _ in recorder.calls if method == "POST"]
        assert posted == ["/v1.0/me/messages/t1/permanentDelete"]

    async def test_the_trash_is_emptied_within_its_bound_and_what_remains_is_said(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.method == "GET":
                return httpx.Response(
                    200,
                    json={
                        "value": [{"id": "t1"}, {"id": "t2"}],
                        "@odata.nextLink": "https://graph.microsoft.com/v1.0/next",
                    },
                )
            return httpx.Response(204)

        recorder = _Recorder(answer)
        result = await _drive(client, recorder, lambda: client.empty_trash(2))

        assert result == {"deleted": 2, "remaining": True}
        assert sorted(path for method, path, _ in recorder.calls if method == "POST") == [
            "/v1.0/me/messages/t1/permanentDelete",
            "/v1.0/me/messages/t2/permanentDelete",
        ]

    async def test_unread_counts_come_with_the_folder_walk(
        self, client: MicrosoftOutlookClient
    ) -> None:
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/mailFolders/inbox"):
                return httpx.Response(200, json={"unreadItemCount": 4})
            if request.url.path.endswith("/mailFolders/junkemail"):
                return httpx.Response(200, json={"unreadItemCount": 1})
            return httpx.Response(
                200,
                json={"value": [{"id": "f-9", "displayName": "Projects", "unreadItemCount": 2}]},
            )

        counts = await _drive(client, _Recorder(answer), lambda: client.unread_counts(10))

        assert counts == UnreadCounts(
            roles={"inbox": 4, "spam": 1}, folders={"Projects": 2}, complete=True
        )


class TestApple:
    @pytest.fixture
    def imap(self) -> Iterator[FakeImap]:
        server = FakeImap()
        server.store["Archive"] = {}
        server.store["Junk"] = {}
        server.store["Projects"] = {}
        with (
            patch(f"{APPLE}.MailBox", server),
            patch(f"{APPLE_MIXIN}.MailBox", server),
            patch(f"{APPLE_STATE}.MailBox", server),
            patch(f"{APPLE_MOVES}.MailBox", server),
            patch(f"{APPLE_STATE}.get_redis_session", AsyncMock(side_effect=ConnectionError())),
        ):
            yield server

    @pytest.fixture
    def client(self, imap: FakeImap) -> AppleEmailClient:
        return AppleEmailClient(
            uuid4(),
            AppleCredentials(apple_id="me@icloud.com", app_password="abcd-efgh-ijkl-mnop"),
            MagicMock(),
        )

    def _message(self, subject: str, message_id: str | None = "<one@example.org>") -> EmailMessage:
        message = EmailMessage()
        message["From"] = "alice@example.org"
        message["To"] = "me@icloud.com"
        message["Subject"] = subject
        if message_id:
            message["Message-ID"] = message_id
        message.set_content("Hello")
        return message

    async def _id(self, client: AppleEmailClient, folder: str, subject: str) -> str:
        hits = await client.search_emails(f"in:{folder}", use_cache=False, headers_only=True)
        return next(hit["id"] for hit in hits["messages"] if hit["subject"] == subject)

    @pytest.mark.parametrize(
        ("place", "folder"),
        [
            (ARCHIVE, "Archive"),
            (SPAM, "Junk"),
            (TRASH, "Deleted Messages"),
            (MailPlace(folder="Projects"), "Projects"),
        ],
    )
    async def test_a_move_lands_in_the_folder_and_the_new_id_is_read_there(
        self, client: AppleEmailClient, imap: FakeImap, place: MailPlace, folder: str
    ) -> None:
        imap.put("INBOX", self._message("Move me"))
        message_id = await self._id(client, "inbox", "Move me")

        result = await client.move_emails([message_id], place)

        assert list(imap.store[folder]) and not imap.store["INBOX"]
        assert result["updated"] == [message_id]
        new_id = result["moved"][message_id]
        assert new_id != message_id
        # What the answer calls the message reads it where it now is.
        assert (await client.get_message(new_id, use_cache=False))["subject"] == "Move me"

    async def test_a_message_with_no_id_of_its_own_moves_with_no_new_id_to_tell(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("Anonymous", None))
        message_id = await self._id(client, "inbox", "Anonymous")

        result = await client.move_emails([message_id], ARCHIVE)

        assert result == {"updated": [message_id], "failed": [], "moved": {message_id: None}}
        assert list(imap.store["Archive"])

    async def test_a_hostile_header_is_never_searched(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("Hostile", '<a"b) OR ALL@example.org>'))
        message_id = await self._id(client, "inbox", "Hostile")

        with patch.object(imap, "uids", wraps=imap.uids) as searched:
            result = await client.move_emails([message_id], ARCHIVE)

        assert result["moved"] == {message_id: None}
        assert not any("HEADER" in str(call) for call in searched.call_args_list)

    async def test_a_selection_of_two_folders_opens_one_session(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("First", "<first@example.org>"))
        imap.put("Projects", self._message("Second", "<second@example.org>"))
        first = await self._id(client, "inbox", "First")
        second = await self._id(client, "Projects", "Second")
        before = imap.sessions

        result = await client.move_emails([first, second], ARCHIVE)

        assert imap.sessions == before + 1
        assert result["updated"] == [first, second]
        assert len(imap.store["Archive"]) == 2

    async def test_a_gone_message_is_named_and_the_rest_still_moves(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("Stays", "<stays@example.org>"))
        imap.put("INBOX", self._message("Leaves", "<leaves@example.org>"))
        stays = await self._id(client, "inbox", "Stays")
        leaves = await self._id(client, "inbox", "Leaves")
        imap.store["INBOX"].pop(leaves.split(".", 1)[0])

        result = await client.move_emails([stays, leaves, "not-an-id"], ARCHIVE)

        assert result["updated"] == [stays]
        assert result["failed"] == [
            {"id": leaves, "status": READ_STATE_NOT_FOUND},
            {"id": "not-an-id", "status": READ_STATE_NOT_FOUND},
        ]

    async def test_a_message_already_there_stays_as_it_is(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("Archive", self._message("Already"))
        message_id = await self._id(client, "archive", "Already")

        result = await client.move_emails([message_id], ARCHIVE)

        assert result == {"updated": [message_id], "failed": [], "moved": {message_id: message_id}}

    async def test_a_failure_after_a_folder_moved_leaves_the_rest_unanswered(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("First", "<first@example.org>"))
        imap.put("Projects", self._message("Second", "<second@example.org>"))
        first = await self._id(client, "inbox", "First")
        second = await self._id(client, "Projects", "Second")
        real_move = imap.move
        calls: list[str] = []

        def move(uids: list[str], destination: str) -> None:
            calls.append(destination)
            if len(calls) > 1:
                raise ConnectionError("dropped")
            real_move(uids, destination)

        with patch.object(imap, "move", move):
            result = await client.move_emails([first, second], ARCHIVE)

        assert result["updated"] == [first]
        assert result["failed"] == [{"id": second, "status": READ_STATE_UNANSWERED}]

    async def test_a_failure_before_anything_moved_is_the_act_s_own(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("First"))
        first = await self._id(client, "inbox", "First")

        with (
            patch.object(imap, "move", side_effect=ConnectionError("dropped")),
            pytest.raises(ConnectionError),
        ):
            await client.move_emails([first], ARCHIVE)

    @pytest.mark.parametrize("starred", [True, False])
    async def test_a_star_is_the_flagged_flag(
        self, client: AppleEmailClient, imap: FakeImap, starred: bool
    ) -> None:
        uid = imap.put("INBOX", self._message("Star me"), () if starred else ("\\Flagged",))
        message_id = await self._id(client, "inbox", "Star me")

        result = await client.set_starred([message_id], starred)

        assert result == {"updated": [message_id], "failed": []}
        assert ("\\Flagged" in imap.store["INBOX"][uid][1]) is starred

    async def test_forever_reaches_only_a_message_of_the_trash(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("Deleted Messages", self._message("Bin"))
        imap.put("INBOX", self._message("Kept"))
        binned = await self._id(client, "trash", "Bin")
        kept = await self._id(client, "inbox", "Kept")

        result = await client.delete_emails_forever([binned, kept])

        assert result == {
            "updated": [binned],
            "failed": [{"id": kept, "status": READ_STATE_FAILED}],
        }
        assert not imap.store["Deleted Messages"]
        assert len(imap.store["INBOX"]) == 1

    async def test_the_trash_is_emptied_within_its_bound_and_what_remains_is_said(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        for number in range(3):
            imap.put("Deleted Messages", self._message(str(number)))

        result = await client.empty_trash(2)

        assert result == {"deleted": 2, "remaining": True}
        assert len(imap.store["Deleted Messages"]) == 1

    async def test_an_emptied_trash_says_nothing_remains(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("Deleted Messages", self._message("Last"))

        assert await client.empty_trash(2) == {"deleted": 1, "remaining": False}

    async def test_unread_counts_ask_each_folder_in_one_session(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("INBOX", self._message("One"))
        imap.put("INBOX", self._message("Read"), ("\\Seen",))
        imap.put("Junk", self._message("Two"))
        imap.put("Projects", self._message("Three"))
        before = imap.sessions

        counts = await client.unread_counts(10)

        assert imap.sessions == before + 1
        assert counts.roles == {"inbox": 1, "spam": 1}
        assert counts.folders["Projects"] == 1
        assert counts.complete is True

    async def test_unread_counts_state_their_cut(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.store["Clients"] = {}
        imap.store["Family"] = {}

        counts = await client.unread_counts(2)

        assert len(counts.folders) == 2
        assert counts.complete is False


class TestOutlookFolders:
    @pytest.fixture
    def client(self) -> MicrosoftOutlookClient:
        return MicrosoftOutlookClient(uuid4(), _credentials(), MagicMock())

    @staticmethod
    def _folders(request: httpx.Request) -> httpx.Response:
        name = request.url.path.rsplit("/", 1)[-1]
        if request.method != "GET":
            return httpx.Response(201 if request.method == "POST" else 200, json={"id": "new"})
        if name == "mailFolders":
            return httpx.Response(
                200,
                json={
                    "value": [
                        {"id": "f-1", "displayName": "Projects", "childFolderCount": 1},
                        {"id": "sys-inbox", "displayName": "Boîte de réception"},
                    ]
                },
            )
        if name == "childFolders":
            return httpx.Response(200, json={"value": [{"id": "f-2", "displayName": "2026"}]})
        return httpx.Response(200, json={"id": "sys-inbox" if name == "inbox" else f"sys-{name}"})

    async def test_a_new_folder_sits_at_the_top(self, client: MicrosoftOutlookClient) -> None:
        recorder = _Recorder(self._folders)

        name = await _drive(client, recorder, lambda: client.create_folder("Clients"))

        assert name == "Clients"
        assert recorder.calls == [("POST", "/v1.0/me/mailFolders", {"displayName": "Clients"})]

    async def test_a_path_nests_it_in_its_parent(self, client: MicrosoftOutlookClient) -> None:
        recorder = _Recorder(self._folders)

        name = await _drive(client, recorder, lambda: client.create_folder("Projects/2027"))

        assert name == "Projects/2027"
        assert recorder.calls[-1] == (
            "POST",
            "/v1.0/me/mailFolders/f-1/childFolders",
            {"displayName": "2027"},
        )

    async def test_a_rename_keeps_the_parent(self, client: MicrosoftOutlookClient) -> None:
        recorder = _Recorder(self._folders)

        name = await _drive(client, recorder, lambda: client.rename_folder("Projects/2026", "Old"))

        assert name == "Projects/Old"
        assert recorder.calls[-1] == ("PATCH", "/v1.0/me/mailFolders/f-2", {"displayName": "Old"})

    async def test_an_empty_folder_is_deleted(self, client: MicrosoftOutlookClient) -> None:
        recorder = _Recorder(self._folders)

        await _drive(client, recorder, lambda: client.delete_folder("Projects/2026"))

        assert recorder.calls[-1] == ("DELETE", "/v1.0/me/mailFolders/f-2", None)

    @pytest.mark.parametrize(
        "held",
        [
            {"totalItemCount": 1, "childFolderCount": 0},
            {"totalItemCount": 0, "childFolderCount": 2},
        ],
    )
    async def test_a_folder_holding_anything_is_refused(
        self, client: MicrosoftOutlookClient, held: dict[str, int]
    ) -> None:
        # Measured on outlook.com: what a deleted folder holds reaches no folder the person
        # can open, not even Deleted Items.
        def answer(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/mailFolders/f-2"):
                return httpx.Response(200, json=held)
            return self._folders(request)

        recorder = _Recorder(answer)

        with pytest.raises(MailFolderNotEmptyError):
            await _drive(client, recorder, lambda: client.delete_folder("Projects/2026"))

        assert {method for method, _, _ in recorder.calls} == {"GET"}

    @pytest.mark.parametrize("act", ["rename", "delete"])
    async def test_a_system_folder_is_never_touched(
        self, client: MicrosoftOutlookClient, act: str
    ) -> None:
        recorder = _Recorder(self._folders)

        def call() -> Any:
            if act == "rename":
                return client.rename_folder("Boîte de réception", "Old")
            return client.delete_folder("Boîte de réception")

        with pytest.raises(SystemFolderError):
            await _drive(client, recorder, call)

        assert {method for method, _, _ in recorder.calls} == {"GET"}


class TestAppleFolders:
    @pytest.fixture
    def imap(self) -> Iterator[FakeImap]:
        server = FakeImap()
        server.store["Projects"] = {}
        server.store["Projects/2026"] = {}
        with (
            patch(f"{APPLE}.MailBox", server),
            patch(f"{APPLE_MOVES}.MailBox", server),
        ):
            yield server

    @pytest.fixture
    def client(self, imap: FakeImap) -> AppleEmailClient:
        return AppleEmailClient(
            uuid4(),
            AppleCredentials(apple_id="me@icloud.com", app_password="abcd-efgh-ijkl-mnop"),
            MagicMock(),
        )

    async def test_a_new_folder_is_created_where_its_path_says(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        assert await client.create_folder("Projects/2027") == "Projects/2027"
        assert "Projects/2027" in imap.store

    async def test_a_taken_name_is_said(self, client: AppleEmailClient, imap: FakeImap) -> None:
        with pytest.raises(MailFolderNameTakenError):
            await client.create_folder("projects")

    async def test_a_rename_keeps_the_parent(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        assert await client.rename_folder("Projects/2026", "Old") == "Projects/Old"
        assert "Projects/Old" in imap.store and "Projects/2026" not in imap.store

    async def test_a_taken_name_is_said_on_a_rename(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.store["Projects/Old"] = {}

        with pytest.raises(MailFolderNameTakenError):
            await client.rename_folder("Projects/2026", "old")

    async def test_an_empty_folder_is_deleted(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        await client.delete_folder("Projects/2026")

        assert "Projects/2026" not in imap.store

    async def test_a_folder_holding_messages_is_refused(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        message = EmailMessage()
        message["Subject"] = "Kept"
        message.set_content("Hello")
        imap.put("Projects/2026", message)

        with pytest.raises(MailFolderNotEmptyError):
            await client.delete_folder("Projects/2026")

        assert len(imap.store["Projects/2026"]) == 1

    async def test_a_folder_holding_folders_is_refused(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        with pytest.raises(MailFolderNotEmptyError):
            await client.delete_folder("Projects")

        assert "Projects" in imap.store

    @pytest.mark.parametrize("name", ["INBOX", "Drafts", "Deleted Messages"])
    async def test_a_system_folder_is_never_touched(
        self, client: AppleEmailClient, imap: FakeImap, name: str
    ) -> None:
        with pytest.raises(SystemFolderError):
            await client.delete_folder(name)
        with pytest.raises(SystemFolderError):
            await client.rename_folder(name, "Old")

        assert name in imap.store
