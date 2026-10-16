"""An Apple message id names its folder as well as its UID (2026-10-13).

A UID is unique within ONE folder only (RFC 3501): the INBOX's message 101 and
the Sent folder's message 101 are two different messages. The id used to be
the bare UID and every read began with the INBOX, so reading, trashing or
downloading a file of a message listed in Sent could reach the INBOX's message
of the same number — and a forward read the INBOX alone. The id now carries the
folder, as a digest of its name: a folder is a person's own label, and an id is
logged (ADR-317).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from email.message import EmailMessage
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.apple_imap import message_cache_key
from src.domains.connectors.clients.normalizers.imap_handles import (
    message_handle,
    read_message_handle,
)
from src.domains.connectors.schemas import AppleCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit

CLIENT = "src.domains.connectors.clients.apple_email_client"
MIXIN = "src.domains.connectors.clients.apple_drafts_mixin"
SENT = "Sent Messages"
UID = "101"


def _mail(subject: str, *, filename: str | None = None) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "Paul <paul@example.com>"
    message["To"] = "jane@icloud.com"
    message["Subject"] = subject
    message["Message-ID"] = f"<{subject.replace(' ', '-')}@example.com>"
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    message.set_content(f"{subject} body.")
    if filename:
        message.add_attachment(
            subject.encode(), maintype="application", subtype="pdf", filename=filename
        )
    return message


class _Redis:
    """An in-memory Redis for the per-message cache."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.store[key] = value

    async def delete(self, *keys: str) -> None:
        for key in keys:
            self.store.pop(key, None)


@pytest.fixture
def imap() -> FakeImap:
    imap = FakeImap()
    imap.put("INBOX", _mail("Inbox mail", filename="inbox.pdf"), uid=UID)
    imap.put(SENT, _mail("Sent mail", filename="sent.pdf"), uid=UID)
    return imap


@pytest.fixture
def redis() -> _Redis:
    return _Redis()


@pytest.fixture
def smtp() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def client(imap: FakeImap, redis: _Redis, smtp: AsyncMock) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        user_id=uuid4(),
        credentials=AppleCredentials(apple_id="jane@icloud.com", app_password="abcd-efgh-ijkl"),
        connector_service=MagicMock(),
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch(f"{CLIENT}.MailBox", imap),
        patch(f"{MIXIN}.MailBox", imap),
        patch(f"{CLIENT}.get_redis_session", AsyncMock(return_value=redis)),
        patch(f"{MIXIN}.get_redis_session", AsyncMock(return_value=redis)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", MagicMock(return_value=breaker)),
        patch.object(instance, "_smtp_send", smtp),
        patch("asyncio.sleep", AsyncMock()),
    ):
        yield instance


async def _sent_id(client: AppleEmailClient) -> str:
    listing = await client.search_emails("in:sent", max_results=5)
    (message,) = listing["messages"]
    assert message["subject"] == "Sent mail"
    return str(message["id"])


class TestTheId:
    def test_the_legacy_inbox_shape_is_still_parseable(self) -> None:
        """Parsing old history does not authorize using its unscoped IDs."""
        assert message_handle("INBOX", UID) == UID
        assert message_handle("inbox", UID) == UID

    def test_another_folder_is_named_by_a_digest_never_by_its_name(self) -> None:
        handle = message_handle("Clients — Dupont", UID)

        assert handle.startswith(f"{UID}.")
        assert "Dupont" not in handle and "Clients" not in handle
        assert message_handle("Clients — Dupont", UID) == handle

    def test_it_reads_back(self) -> None:
        location = read_message_handle(message_handle(SENT, UID))

        assert location is not None
        assert location.uid == UID
        assert location.folder_digest is not None
        assert read_message_handle(UID) == read_message_handle(message_handle("INBOX", UID))

    @pytest.mark.parametrize(
        "handle",
        [
            "",
            "abc",
            "101.",
            "101.xyz",
            "../101",
            "101.ABC.DEF",
            "0",
            "001",
            "4294967296",
            "١٠١",
            "１２",
        ],
    )
    def test_what_cannot_be_an_id_reads_as_none(self, handle: str) -> None:
        assert read_message_handle(handle) is None


class TestAMessageOutsideTheInbox:
    async def test_is_listed_under_an_id_of_its_own(self, client: AppleEmailClient) -> None:
        assert await _sent_id(client) != UID

    async def test_is_read_from_its_folder(self, client: AppleEmailClient) -> None:
        sent_id = await _sent_id(client)

        message = await client.get_message(sent_id, use_cache=False)

        assert message["subject"] == "Sent mail"
        assert message["id"] == sent_id

    async def test_is_cached_apart_from_the_inbox_message_of_the_same_uid(
        self, client: AppleEmailClient, redis: _Redis
    ) -> None:
        await _sent_id(client)  # the listing caches the Sent message under its id

        inbox_listing = await client.search_emails("in:inbox", max_results=5)
        inbox = await client.get_message(inbox_listing["messages"][0]["id"], use_cache=True)

        assert inbox["subject"] == "Inbox mail"

    async def test_is_the_one_trashed(self, client: AppleEmailClient, imap: FakeImap) -> None:
        sent_id = await _sent_id(client)

        await client.trash_email(sent_id)

        assert UID not in imap.store[SENT]
        assert UID in imap.store["INBOX"]
        (trashed,) = imap.store["Deleted Messages"]
        assert imap.stored("Deleted Messages", trashed)["Subject"] == "Sent mail"

    async def test_its_file_is_the_one_downloaded(self, client: AppleEmailClient) -> None:
        sent_id = await _sent_id(client)

        content = await client.download_attachment(sent_id, filename="sent.pdf")

        assert content.data == b"Sent mail"

    async def test_its_forward_reads_it_from_its_folder(
        self, client: AppleEmailClient, smtp: AsyncMock
    ) -> None:
        """The forward read the INBOX alone: a Sent message could not be forwarded,
        or the INBOX message of the same UID was forwarded in its place."""
        sent_id = await _sent_id(client)

        result = await client.forward_email(sent_id, to="erin@example.com")

        _recipients, message = smtp.await_args.args
        assert message["Subject"] == "Fwd: Sent mail"
        assert result["attachment_names"] == ["sent.pdf"]

    async def test_its_forward_draft_reads_it_from_its_folder(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        sent_id = await _sent_id(client)

        draft = await client.create_forward_draft(sent_id, to="erin@example.com")

        stored = imap.stored("Drafts", draft["mailbox_draft_id"])
        assert stored["Subject"] == "Fwd: Sent mail"


class TestAnIdThatNamesNothing:
    async def test_a_bare_uid_requires_a_new_listing(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        with pytest.raises(ValueError, match="list the messages again"):
            await client.get_message(UID, use_cache=False)
        assert imap.sessions == 0

    async def test_a_folder_gone_is_not_found(self, client: AppleEmailClient) -> None:
        with pytest.raises(ValueError, match="not found"):
            await client.get_message(f"{UID}.{'0' * 12}", use_cache=False)

    async def test_a_malformed_id_reaches_no_imap_command(
        self, client: AppleEmailClient, imap: FakeImap
    ) -> None:
        with pytest.raises(ValueError, match="not found"):
            await client.get_message("../101", use_cache=False)

        assert imap.sessions == 0


class TestADraftsMessage:
    async def test_has_distinct_draft_and_message_handles_for_the_same_resource(
        self, client: AppleEmailClient
    ) -> None:
        draft = await client.create_draft(to="paul@example.com", subject="Plan", body="Words.")

        assert draft["mailbox_draft_id"] == f"d.{draft['id']}"
        assert draft["id"] != UID
        assert (await client.get_message(draft["id"], use_cache=False))["subject"] == "Plan"

    async def test_an_edit_forgets_the_cached_copy_of_the_draft_itself(
        self, client: AppleEmailClient, redis: _Redis
    ) -> None:
        draft = await client.create_draft(to="paul@example.com", subject="Plan", body="Words.")
        key = message_cache_key(client.user_id, client.credentials.apple_id, draft["id"])
        redis.store[key] = json.dumps({"subject": "stale"})
        inbox = (await client.search_emails("in:inbox"))["messages"][0]
        inbox_key = message_cache_key(client.user_id, client.credentials.apple_id, inbox["id"])
        redis.store[inbox_key] = json.dumps({"subject": "an inbox message"})

        await client.update_draft(draft["mailbox_draft_id"], subject="Plan B")

        assert key not in redis.store
        assert inbox_key in redis.store, "the INBOX message of the same UID is not this draft"
