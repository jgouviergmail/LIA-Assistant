"""Mailbox drafts on Apple iCloud, over IMAP and SMTP (ADR-344).

iCloud has no draft API: a draft is a message APPENDed to the folder the server
flags ``\\Drafts``, with the ``\\Draft`` flag; editing one stores a NEW message
(a new UID) and removes the old; sending one is SMTP, after which it leaves the
drafts for the folder flagged ``\\Sent``. No iCloud account was available for a
live measurement (ADR-344 says so): ``imap_fakes.FakeImap`` is a plain IMAP
server — folders flagged per RFC 6154, UIDs per folder, APPENDUID when UIDPLUS
is on — handing out REAL ``imap_tools`` messages, parsed from FETCH data.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import mailbox_account_scope
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    MailboxDraftNotFoundError,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    message_handle,
    read_message_handle,
    scope_digest,
)
from src.domains.connectors.schemas import AppleCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

MIXIN = "src.domains.connectors.clients.apple_drafts_mixin"
ME = "jane@icloud.com"


def _handle(client: AppleEmailClient, uid: str) -> str:
    """An input handle under the fake server's published SELECT namespace."""
    if uid.startswith("d."):
        return uid
    return "d." + message_handle(
        "Drafts",
        uid,
        scope=scope_digest(mailbox_account_scope(client.credentials.apple_id), "Drafts", 1),
    )


def _uid(handle: str) -> str:
    location = read_message_handle(handle.removeprefix("d."))
    assert location is not None
    return location.uid


def _draft(*, to: str = "Paul <paul@example.com>", with_file: bool = False) -> EmailMessage:
    message = EmailMessage()
    message["From"] = ME
    message["To"] = to
    message["Subject"] = "Re: Budget"
    message["In-Reply-To"] = "<orig-1@example.com>"
    message["Message-ID"] = "<draft-1@icloud.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    message.set_content("Old words.\n\nOn Mon, Paul wrote:\n> Budget?")
    if with_file:
        message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="b.pdf")
    return message


@pytest.fixture
def imap() -> FakeImap:
    return FakeImap()


@pytest.fixture
def smtp() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(imap: FakeImap, smtp: AsyncMock) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id=ME, app_password="abcd-efgh-ijkl-mnop"),
        connector_service=MagicMock(),
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch(f"{MIXIN}.MailBox", imap),
        patch(f"{MIXIN}.get_redis_session", AsyncMock(return_value=AsyncMock())),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
        patch.object(instance, "_smtp_send", smtp),
        patch("asyncio.sleep", AsyncMock()),
    ):
        yield instance


class TestCreate:
    async def test_a_draft_is_appended_flagged_to_the_drafts_folder(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        draft = await client.create_draft(
            "Élodie Exemple <elodie@example.com>", "Budget", "Bonjour", bcc="boss@example.com"
        )

        uid = draft[FIELD_MAILBOX_DRAFT_ID]
        raw, flags = imap.store["Drafts"][_uid(uid)]
        assert set(flags) == {"\\Draft", "\\Seen"}
        assert b"<elodie@example.com>" in raw
        assert imap.stored("Drafts", uid)["Bcc"] == "boss@example.com"
        assert (draft["subject"], draft["bcc"]) == ("Budget", "boss@example.com")
        assert "DRAFT" in draft["labelIds"]

    async def test_a_server_without_appenduid_is_read_back_by_message_id(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.uidplus = False

        draft = await client.create_draft("bob@example.com", "Budget", "Bonjour")

        assert _uid(draft[FIELD_MAILBOX_DRAFT_ID]) in imap.store["Drafts"]

    async def test_a_failed_append_is_not_retried(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        with (
            patch.object(imap, "append", side_effect=OSError("connection reset")),
            pytest.raises(OSError),
        ):
            await client.create_draft("bob@example.com", "Budget", "Bonjour")

        assert imap.sessions == 1

    async def test_a_reply_draft_is_threaded_and_quotes_the_original(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        original = {
            "from": "Bob <bob@example.com>",
            "to": f"{ME}, carol@example.com",
            "cc": "",
            "subject": "Budget",
            "date": "Mon, 20 Jul 2026",
            "body": "The figures?",
            "rfc_message_id": "<orig@example.com>",
        }
        with patch.object(client, "get_message", AsyncMock(return_value=original)):
            draft = await client.create_reply_draft("7", "Here they are.", reply_all=True)

        stored = imap.stored("Drafts", draft[FIELD_MAILBOX_DRAFT_ID])
        assert stored["In-Reply-To"] == "<orig@example.com>"
        assert stored["To"] == "Bob <bob@example.com>, carol@example.com"
        assert "> The figures?" in draft["body"]

    async def test_a_forward_draft_carries_the_files(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        from src.infrastructure.email.outgoing import OutgoingAttachment

        original = {"from": "Bob <bob@example.com>", "subject": "Budget", "body": "Figures"}
        files = [OutgoingAttachment("b.pdf", "application/pdf", b"%PDF")]
        with patch.object(
            client, "_original_with_files", AsyncMock(return_value=(original, files))
        ):
            draft = await client.create_forward_draft("7", "erin@example.com", body="FYI")

        stored = imap.stored("Drafts", draft[FIELD_MAILBOX_DRAFT_ID])
        assert [part.get_filename() for part in stored.walk() if part.get_filename()] == ["b.pdf"]
        assert stored["Subject"] == "Fwd: Budget"


class TestUpdate:
    async def test_a_current_revision_can_replace_the_message(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        revision = (await client.get_draft(_handle(client, uid)))["mailbox_draft_revision"]
        result = await client.update_draft(
            _handle(client, uid), body="Current words", expected_revision=revision
        )

        assert result["body"].strip() == "Current words"

    async def test_a_stale_revision_refuses_before_appending_or_removing_a_message(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        before = dict(imap.store["Drafts"])
        with pytest.raises(LookupError):
            await client.update_draft(
                _handle(client, uid), body="Stale words", expected_revision="old-version"
            )

        assert imap.store["Drafts"] == before

    async def test_an_edit_stores_a_new_message_and_removes_the_old(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        old = imap.put("Drafts", _draft(with_file=True), ("\\Draft", "\\Seen"))

        draft = await client.update_draft(
            _handle(client, old), to="Marie <marie@example.com>", body="New words."
        )

        new = draft[FIELD_MAILBOX_DRAFT_ID]
        assert new != old and old not in imap.store["Drafts"]
        stored = imap.stored("Drafts", new)
        assert stored["To"] == "Marie <marie@example.com>"
        assert stored["In-Reply-To"] == "<orig-1@example.com>"
        assert stored["Message-ID"] != "<draft-1@icloud.com>"
        assert [part.get_filename() for part in stored.walk() if part.get_filename()] == ["b.pdf"]
        assert draft["body"].strip() == "New words."

    async def test_an_invalid_address_changes_nothing(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        old = imap.put("Drafts", _draft(), ("\\Draft",))

        with pytest.raises(ValueError):
            await client.update_draft(_handle(client, old), cc="anne@")

        assert list(imap.store["Drafts"]) == [old]

    async def test_an_unknown_draft_is_not_found(self, client: AppleEmailClient) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.update_draft("999", subject="x")


class TestRead:
    async def test_the_listing_is_newest_first_with_an_exact_total(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        first = imap.put("Drafts", _draft(), ("\\Draft",))
        second = imap.put("Drafts", _draft(to="marie@example.com"), ("\\Draft",))
        imap.put("INBOX", _draft(to="marie@example.com"))

        listing = await client.list_drafts(max_results=1)

        assert [_uid(d[FIELD_MAILBOX_DRAFT_ID]) for d in listing["messages"]] == [second]
        assert listing["resultSizeEstimate"] == 2
        assert listing["next_page_token"] == "1"
        rest = await client.list_drafts(max_results=1, page_token="1")
        assert [_uid(d[FIELD_MAILBOX_DRAFT_ID]) for d in rest["messages"]] == [first]
        assert rest["next_page_token"] is None

    async def test_a_recipient_query_reads_the_drafts_only(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        imap.put("Drafts", _draft(), ("\\Draft",))
        wanted = imap.put("Drafts", _draft(to="marie@example.com"), ("\\Draft",))

        listing = await client.list_drafts("to:marie in:inbox")

        assert [_uid(d[FIELD_MAILBOX_DRAFT_ID]) for d in listing["messages"]] == [wanted]

    @pytest.mark.parametrize("handle", ["", "12a", "1:*", "1,2"])
    async def test_a_handle_that_is_not_a_uid_opens_no_session(
        self, client: AppleEmailClient, imap: FakeImap, handle: str
    ) -> None:
        with pytest.raises(MailboxDraftNotFoundError):
            await client.get_draft(handle)

        assert imap.sessions == 0

    async def test_a_draft_keeps_its_quoted_history(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        draft = await client.get_draft(_handle(client, imap.put("Drafts", _draft(), ("\\Draft",))))

        assert "> Budget?" in draft["body"]

    async def test_replacing_same_named_file_bytes_changes_the_confirmation_fingerprint(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        from src.domains.agents.tools.mailbox_draft_send_tools import live_digest

        message = _draft(with_file=True)
        uid = imap.put("Drafts", message, ("\\Draft",))
        before = await client.get_draft(_handle(client, uid))
        attachment = next(message.iter_attachments())
        attachment.set_payload("WFhYWA==")
        # A reused UID after a folder rebuild must not approve other bytes.
        _raw, flags = imap.store["Drafts"][uid]
        imap.store["Drafts"][uid] = (message.as_bytes(), flags)

        after = await client.get_draft(_handle(client, uid))

        assert before["body"] == after["body"]
        assert before["attachments"] == after["attachments"]
        assert live_digest(before) != live_digest(after)


class TestTrashAndSend:
    async def test_repeated_stops_retain_one_send_and_finish_its_filing(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        from src.infrastructure.async_utils import _background_tasks

        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        started, release = asyncio.Event(), asyncio.Event()

        async def pending_send(*_args: object) -> None:
            started.set()
            await release.wait()

        smtp.side_effect = pending_send
        task = asyncio.create_task(client.send_draft(_handle(client, uid)))
        await started.wait()
        for _ in range(4):
            task.cancel()
            checkpoint = asyncio.Event()
            asyncio.get_running_loop().call_soon(checkpoint.set)
            await checkpoint.wait()
        with pytest.raises(asyncio.CancelledError):
            await task

        held = [one for one in _background_tasks if one.get_name() == "mailbox_draft_send"]
        assert len(held) == 1
        assert uid in imap.store["Drafts"]
        release.set()
        await asyncio.gather(*held)
        assert smtp.await_count == 1
        assert uid not in imap.store["Drafts"]
        assert len(imap.store["Sent Messages"]) == 1

    async def test_invalid_uids_never_enter_a_bulk_imap_command(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        invalid = ["0", "001", "4294967296", "١٠١", "１２"]
        with patch.object(imap, "uids", wraps=imap.uids) as uids:
            result = await client.trash_drafts(invalid)

        uids.assert_not_called()
        assert result["trashed"] == []
        assert len(result["failed"]) == len(invalid)

    async def test_a_stopped_inflight_send_finishes_filing_without_sending_again(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        accepted = asyncio.Event()
        acknowledge = asyncio.Event()

        async def accepted_send(*args: object) -> None:
            accepted.set()
            await acknowledge.wait()

        smtp.side_effect = accepted_send
        task = asyncio.create_task(client.send_draft(_handle(client, uid)))
        await accepted.wait()
        task.cancel()
        acknowledge.set()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert smtp.await_count == 1
        assert uid not in imap.store["Drafts"]
        assert len(imap.store["Sent Messages"]) == 1

    async def test_a_missing_sent_copy_is_reported_without_retrying_smtp(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        with patch.object(imap, "append", side_effect=OSError("sent folder unavailable")):
            result = await client.send_draft(_handle(client, uid))

        assert result["draft_kept"] is False
        assert result["sent_copy_filed"] is False
        assert uid not in imap.store["Drafts"]
        assert smtp.await_count == 1

    async def test_drafts_move_to_the_flagged_trash(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        kept = imap.put("Drafts", _draft(), ("\\Draft",))
        trashed = imap.put("Drafts", _draft(), ("\\Draft",))

        result = await client.trash_drafts([_handle(client, trashed), "999", "x"])

        assert [_uid(handle) for handle in result["trashed"]] == [trashed]
        assert [f["status"] for f in result["failed"]] == [TRASH_NOT_FOUND, TRASH_NOT_FOUND]
        assert list(imap.store["Drafts"]) == [kept]
        assert len(imap.store["Deleted Messages"]) == 1

    async def test_a_draft_is_sent_once_its_blind_copies_in_the_envelope(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        message = _draft()
        message["Bcc"] = "boss@example.com"
        uid = imap.put("Drafts", message, ("\\Draft", "\\Seen"))

        result = await client.send_draft(_handle(client, uid))

        (call,) = smtp.await_args_list
        recipients, sent = call.args
        assert recipients == ["paul@example.com", "boss@example.com"]
        assert sent["Bcc"] is None
        assert result == {
            "id": None,
            FIELD_MAILBOX_DRAFT_ID: _handle(client, uid),
            "draft_kept": False,
            "sent_copy_filed": True,
        }
        assert uid not in imap.store["Drafts"]
        ((_, flags),) = imap.store["Sent Messages"].values()
        assert "\\Draft" not in flags

    async def test_a_failed_send_is_not_retried_and_keeps_the_draft(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))
        smtp.side_effect = OSError("smtp down")

        with pytest.raises(OSError):
            await client.send_draft(_handle(client, uid))

        assert smtp.await_count == 1
        assert uid in imap.store["Drafts"]

    async def test_a_draft_without_a_recipient_is_not_sent(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        message = _draft()
        del message["To"]
        uid = imap.put("Drafts", message, ("\\Draft",))

        with pytest.raises(ValueError):
            await client.send_draft(_handle(client, uid))

        smtp.assert_not_awaited()

    async def test_a_sent_draft_the_mailbox_could_not_file_is_said_kept(
        self, client: AppleEmailClient, imap: FakeImap, smtp: AsyncMock
    ) -> None:
        uid = imap.put("Drafts", _draft(), ("\\Draft",))

        with patch.object(imap.client, "uid", side_effect=OSError("NO")):
            result = await client.send_draft(_handle(client, uid))

        assert result["draft_kept"] is True
        assert smtp.await_count == 1
