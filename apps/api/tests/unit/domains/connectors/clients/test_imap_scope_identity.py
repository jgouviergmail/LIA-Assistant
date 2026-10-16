"""A UID reused by another mailbox generation/account is never the old message."""

from collections.abc import Iterator
from email.message import EmailMessage
from types import MethodType
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from imap_tools.mailbox import BaseMailBox

from src.core.field_names import FIELD_MAILBOX_DRAFT_ID
from src.domains.connectors.clients.apple_email_client import AppleEmailClient
from src.domains.connectors.clients.email_attachments import EmailAttachmentNotFoundError
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    MailboxOperationUnavailableError,
)
from src.domains.connectors.schemas import AppleCredentials
from tests.unit.domains.connectors.clients.imap_fakes import FakeImap

pytestmark = pytest.mark.unit
EMAIL = "src.domains.connectors.clients.apple_email_client"
DRAFTS = "src.domains.connectors.clients.apple_drafts_mixin"


def _message(words: str) -> EmailMessage:
    message = EmailMessage()
    message["From"] = "bob@example.com"
    message["To"] = "paul@example.com"
    message["Subject"] = words
    message["Date"] = "Tue, 13 Oct 2026 09:00:00 +0000"
    message.set_content(words)
    message.add_attachment(b"%PDF", maintype="application", subtype="pdf", filename="b.pdf")
    return message


async def test_a_message_without_a_date_is_read_with_an_unknown_date(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    message = _message("No Date header")
    del message["Date"]
    mailbox.put("INBOX", message, uid="42")
    result = await client.search_emails("", use_cache=False)
    assert result["messages"][0]["internalDate"] is None


@pytest.fixture
def mailbox() -> FakeImap:
    return FakeImap()


@pytest.fixture
def redis() -> AsyncMock:
    store: dict[str, str] = {}
    instance = AsyncMock()
    instance.get.side_effect = store.get

    async def save(key: str, value: str, **_kwargs: Any) -> None:
        store[key] = value

    instance.set.side_effect = save
    return instance


@pytest.fixture
def client(mailbox: FakeImap, redis: AsyncMock) -> Iterator[AppleEmailClient]:
    instance = AppleEmailClient(
        uuid4(),
        AppleCredentials(apple_id="jane@icloud.com", app_password="test-password"),
        MagicMock(),
    )
    breaker = MagicMock(check=AsyncMock(), record_success=AsyncMock(), record_failure=AsyncMock())
    with (
        patch(f"{EMAIL}.MailBox", mailbox),
        patch(f"{DRAFTS}.MailBox", mailbox),
        patch(f"{EMAIL}.get_redis_session", AsyncMock(return_value=redis)),
        patch(f"{DRAFTS}.get_redis_session", AsyncMock(return_value=redis)),
        patch.object(instance, "_rate_limit", AsyncMock()),
        patch.object(instance, "_get_circuit_breaker", return_value=breaker),
        patch.object(instance, "_smtp_send", AsyncMock()),
        patch("asyncio.sleep", AsyncMock()),
    ):
        yield instance


@pytest.mark.parametrize("action", ["read", "trash", "download", "forward"])
async def test_a_recreated_folder_cannot_retarget_a_listed_message(
    client: AppleEmailClient, mailbox: FakeImap, action: str
) -> None:
    mailbox.put("INBOX", _message("Original"), uid="42")
    original = (await client.search_emails("", use_cache=False))["messages"][0]
    mailbox.uid_validity["INBOX"] += 1
    mailbox.put("INBOX", _message("A different message"), uid="42")

    with pytest.raises((ValueError, EmailAttachmentNotFoundError)):
        if action == "read":
            await client.get_message(original["id"], use_cache=False)
        elif action == "trash":
            await client.trash_email(original["id"])
        elif action == "download":
            await client.download_attachment(original["id"], filename="b.pdf")
        else:
            await client.forward_email(original["id"], "erin@example.com")
    assert "42" in mailbox.store["INBOX"]
    assert not mailbox.store["Deleted Messages"]
    client._smtp_send.assert_not_awaited()


async def test_a_reconnected_account_cannot_read_the_previous_accounts_cached_mail(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("INBOX", _message("Original private contents"), uid="42")
    original = (await client.search_emails(""))["messages"][0]
    client.credentials.apple_id = "other@icloud.com"
    mailbox.put("INBOX", _message("The other account"), uid="42")

    with pytest.raises(ValueError):
        await client.get_message(original["id"])


async def test_a_recreated_drafts_folder_cannot_trash_a_different_draft(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    handle = original[FIELD_MAILBOX_DRAFT_ID]
    mailbox.uid_validity["Drafts"] += 1
    mailbox.put("Drafts", _message("Another draft"), ("\\Draft",), uid="42")

    result = await client.trash_drafts([handle])

    assert result["trashed"] == []
    assert "42" in mailbox.store["Drafts"]
    assert not mailbox.store["Deleted Messages"]


async def test_a_reconnected_account_cannot_send_the_same_uid_from_a_different_mailbox(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    client.credentials.apple_id = "other@icloud.com"
    mailbox.put("Drafts", _message("Another account's draft"), ("\\Draft",), uid="42")

    with pytest.raises(MailboxDraftNotFoundError):
        await client.send_draft(original[FIELD_MAILBOX_DRAFT_ID])
    client._smtp_send.assert_not_awaited()


async def test_filing_an_accepted_send_cannot_delete_a_reused_draft_uid(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]

    async def accept_and_recreate(*_args: object) -> None:
        mailbox.uid_validity["Drafts"] += 1
        mailbox.put("Drafts", _message("Another draft"), ("\\Draft",), uid="42")

    client._smtp_send.side_effect = accept_and_recreate
    result = await client.send_draft(original[FIELD_MAILBOX_DRAFT_ID])

    assert "42" in mailbox.store["Drafts"]
    assert result["draft_kept"] is True
    assert client._smtp_send.await_count == 1


async def test_a_folder_recreated_after_append_cannot_delete_a_reused_original_uid(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    append = mailbox.append

    def accepted_then_recreated(*args: Any, **kwargs: Any) -> tuple[str, list[bytes]]:
        acknowledgement = append(*args, **kwargs)
        mailbox.uid_validity["Drafts"] += 1
        mailbox.put("Drafts", _message("Another draft"), ("\\Draft",), uid="42")
        return acknowledgement

    with (
        patch.object(mailbox, "append", side_effect=accepted_then_recreated),
        pytest.raises(MailboxDraftChangedError) as changed,
    ):
        await client.update_draft(original[FIELD_MAILBOX_DRAFT_ID], subject="Updated")
    assert changed.value.copy_saved is True
    assert mailbox.stored("Drafts", "42")["Subject"] == "Another draft"


@pytest.mark.parametrize(
    "validity", [[], [None], [b"0"], [b"001"], [b"4294967296"], [b"\xff"], [b"1", b"2"]]
)
async def test_an_unusable_selected_namespace_never_fetches_a_message(
    client: AppleEmailClient, mailbox: FakeImap, validity: list[bytes | None]
) -> None:
    login = mailbox.login

    def selected_without_validity(*args: Any, **kwargs: Any) -> FakeImap:
        result = login(*args, **kwargs)
        result.client.untagged_responses["UIDVALIDITY"] = validity
        return result

    with (
        patch.object(mailbox, "login", side_effect=selected_without_validity),
        patch.object(mailbox, "fetch", wraps=mailbox.fetch) as fetch,
        pytest.raises(ValueError, match="UIDVALIDITY"),
    ):
        await client.search_emails("", use_cache=False)
    fetch.assert_not_called()


async def test_a_later_status_cannot_replace_the_selected_namespace(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("INBOX", _message("Original"), uid="42")
    original = (await client.search_emails("", use_cache=False))["messages"][0]
    # STATUS names the current folder; it need not describe this selected session.
    mailbox.folder.status.side_effect = AssertionError("No extra STATUS request is needed")
    result = await client.get_message(original["id"], use_cache=False)
    assert result["id"] == original["id"]
    assert result["subject"] == "Original"
    mailbox.folder.status.assert_not_called()


@pytest.mark.parametrize("operation", ["message", "drafts"])
async def test_a_lost_copy_acknowledgement_cannot_copy_the_message_twice(
    client: AppleEmailClient, mailbox: FakeImap, operation: str
) -> None:
    folder = "INBOX" if operation == "message" else "Drafts"
    mailbox.put(folder, _message("Original"), uid="42")
    if operation == "message":
        listed = (await client.search_emails("", use_cache=False))["messages"][0]
    else:
        listed = (await client.list_drafts(headers_only=False))["messages"][0]

    def copied_then_lost_ack(uids: list[str], destination: str) -> None:
        # imap_tools.move uses COPY + DELETE itself when MOVE is unavailable.
        mailbox.copy(uids, destination)
        raise ConnectionResetError("The COPY acknowledgement was lost")

    with patch.object(mailbox, "move", side_effect=copied_then_lost_ack):
        with pytest.raises(ConnectionResetError):
            if operation == "message":
                await client.trash_email(listed["id"])
            else:
                await client.trash_drafts([listed[FIELD_MAILBOX_DRAFT_ID]])
    assert "42" in mailbox.store[folder]
    assert len(mailbox.store["Deleted Messages"]) == 1


@pytest.mark.parametrize("operation", ["edit", "send", "trash"])
async def test_native_cleanup_never_expunge_another_clients_deleted_message(
    client: AppleEmailClient, mailbox: FakeImap, operation: str
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    mailbox.put("Drafts", _message("Another client's message"), ("\\Deleted",), uid="99")
    original = (await client.list_drafts(headers_only=False))["messages"][-1]
    assert original["subject"] == "Original"
    # Exercise the installed library's actual DELETE/MOVE implementation.
    mailbox.delete = MethodType(BaseMailBox.delete, mailbox)
    mailbox.move = MethodType(BaseMailBox.move, mailbox)
    mailbox.client.capabilities = ("IMAP4rev1", "UIDPLUS")
    handle = original[FIELD_MAILBOX_DRAFT_ID]

    if operation == "edit":
        await client.update_draft(handle, subject="Updated")
    elif operation == "send":
        await client.send_draft(handle)
    else:
        await client.trash_drafts([handle])
    assert "99" in mailbox.store["Drafts"], "EXPUNGE must target only the requested UID"
    assert "42" not in mailbox.store["Drafts"]


@pytest.mark.parametrize("operation", ["edit", "trash"])
async def test_an_unsafe_server_refuses_before_any_mailbox_write(
    client: AppleEmailClient, mailbox: FakeImap, operation: str
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    mailbox.client.capabilities = ("IMAP4rev1",)
    with (
        patch.object(mailbox, "append", wraps=mailbox.append) as append,
        patch.object(mailbox, "copy", wraps=mailbox.copy) as copy,
        pytest.raises(MailboxOperationUnavailableError),
    ):
        handle = original[FIELD_MAILBOX_DRAFT_ID]
        if operation == "edit":
            await client.update_draft(handle, subject="Updated")
        else:
            await client.trash_drafts([handle])
    append.assert_not_called()
    copy.assert_not_called()
    mailbox.client.uid.assert_not_called()
    assert mailbox.stored("Drafts", "42")["Subject"] == "Original"


async def test_a_lowercase_native_append_receipt_keeps_the_saved_identity(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    append = mailbox.append

    def acknowledged(*args: Any, **kwargs: Any) -> tuple[str, list[bytes]]:
        status, answer = append(*args, **kwargs)
        return status, [line.replace(b"APPENDUID", b"appenduid") for line in answer]

    with patch.object(mailbox, "append", side_effect=acknowledged):
        draft = await client.create_draft("paul@example.com", "Created", "Words")
    reread = await client.get_draft(draft[FIELD_MAILBOX_DRAFT_ID])
    assert reread["subject"] == "Created"
    assert len(mailbox.store["Drafts"]) == 1


async def test_native_move_does_not_require_uidplus(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    mailbox.client.capabilities = ("IMAP4rev1", "MOVE")
    result = await client.trash_drafts([original[FIELD_MAILBOX_DRAFT_ID]])
    assert result["trashed"] == [original[FIELD_MAILBOX_DRAFT_ID]]
    assert "42" not in mailbox.store["Drafts"]
    assert len(mailbox.store["Deleted Messages"]) == 1


@pytest.mark.parametrize(
    "response",
    [
        b"[APPENDUID 2 42] Saved",
        b"[APPENDUID 1 00042] Saved",
        b"[APPENDUID 1 4294967296] Saved",
        b"[APPENDUID 1 42] Saved",
    ],
)
async def test_a_mismatched_or_invalid_append_uid_never_removes_the_original_draft(
    client: AppleEmailClient, mailbox: FakeImap, response: bytes
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    append = mailbox.append

    def saved_with_unusable_identity(*args: Any, **kwargs: Any) -> tuple[str, list[bytes]]:
        append(*args, **kwargs)
        return "OK", [response]

    with (
        patch.object(mailbox, "append", side_effect=saved_with_unusable_identity),
        pytest.raises(MailboxDraftChangedError) as changed,
    ):
        await client.update_draft(original[FIELD_MAILBOX_DRAFT_ID], subject="Updated")
    assert changed.value.copy_saved is True
    assert mailbox.stored("Drafts", "42")["Subject"] == "Original"
    assert len(mailbox.store["Drafts"]) == 2
    mailbox.client.uid.assert_not_called()


@pytest.mark.parametrize("state", ["not_readable", "ambiguous_search"])
async def test_an_acknowledged_copy_that_cannot_be_identified_preserves_the_original(
    client: AppleEmailClient, mailbox: FakeImap, state: str
) -> None:
    mailbox.put("Drafts", _message("Original"), ("\\Draft",), uid="42")
    original = (await client.list_drafts(headers_only=False))["messages"][0]
    mailbox.uidplus = state != "ambiguous_search"
    with (
        patch.object(mailbox, "fetch", return_value=iter(())),
        patch.object(mailbox, "uids", return_value=["101", "102"]),
        pytest.raises(MailboxDraftChangedError) as changed,
    ):
        # The initial edit read must succeed; only the post-APPEND read is missing.
        fetch = FakeImap.fetch.__get__(mailbox)
        reads = iter([fetch("UID 42"), iter(())])
        mailbox.fetch.side_effect = lambda *_args, **_kwargs: next(reads)
        await client.update_draft(original[FIELD_MAILBOX_DRAFT_ID], subject="Updated")
    assert changed.value.copy_saved is True
    assert mailbox.stored("Drafts", "42")["Subject"] == "Original"
    assert len(mailbox.store["Drafts"]) == 2


@pytest.mark.parametrize("changed", ["host", "port"])
async def test_a_reconfigured_imap_endpoint_cannot_read_the_previous_endpoints_cached_mail(
    client: AppleEmailClient, mailbox: FakeImap, changed: str
) -> None:
    from src.core.config import settings

    mailbox.put("INBOX", _message("Original endpoint's private contents"), uid="42")
    original = (await client.search_emails(""))["messages"][0]
    mailbox.put("INBOX", _message("Different endpoint's message"), uid="42")
    setting = "apple_imap_host" if changed == "host" else "apple_imap_port"
    value = "different-imap.example.test" if changed == "host" else settings.apple_imap_port + 1
    with patch.object(settings, setting, value), pytest.raises(ValueError):
        await client.get_message(original["id"])


async def test_a_missing_account_identity_cannot_mint_a_qualified_message_id(
    client: AppleEmailClient, mailbox: FakeImap
) -> None:
    mailbox.put("INBOX", _message("Original"), uid="42")
    client.credentials.apple_id = " "
    with patch.object(mailbox, "fetch", wraps=mailbox.fetch) as fetch, pytest.raises(ValueError):
        await client.search_emails("", use_cache=False)
    fetch.assert_not_called()
