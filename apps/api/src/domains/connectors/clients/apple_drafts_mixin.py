"""Mailbox drafts on Apple iCloud (IMAP/SMTP), mixed into ``AppleEmailClient`` (ADR-344).

iCloud has no draft API. A draft is a message APPENDed, with the ``\\Draft``
flag, to the folder the server flags ``\\Drafts`` (RFC 6154 — never a typed
name, ``apple_imap``); its opaque ``mailbox_draft_id`` binds its UID to the
account, folder and SELECT's UIDVALIDITY. IMAP cannot change a stored message, so an edit stores a NEW
message — a new UID, a new ``Message-ID`` — and removes the old one only once
the new one is in. Sending a draft is SMTP, its blind copies moved into the
envelope (``prepare_for_smtp``); the draft then leaves the drafts folder
FIRST (left behind, « send all my drafts » would send it twice) and a copy is
filed in the folder flagged ``\\Sent`` — the classic send files none.

A write is attempted once: an APPEND retried after a timeout could store two
drafts, an SMTP send retried could deliver twice. Draft reads bypass the
message cache; an edit, a trash and a send invalidate the corresponding
account-scoped message ID without touching other folders' messages.

No iCloud account was available for a live measurement (ADR-344 says so).
"""

from __future__ import annotations

import asyncio
import email
import hashlib
import re
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from email.message import Message
from email.utils import formatdate, make_msgid
from typing import Any, Final, NamedTuple, Protocol, TypeVar
from uuid import UUID

import structlog
from imap_tools import AND, MailBox, MailMessage, MailMessageFlags
from imap_tools.query import Header

from src.core.constants import SMTP_CANCELLATION_GRACE_ATTEMPTS
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.clients.apple_compose import (
    forward_message,
    new_message,
    reply_message,
)
from src.domains.connectors.clients.apple_imap import (
    DRAFTS_ROLE,
    SENT_ROLE,
    TRASH_ROLE,
    authenticated_imap_mailbox,
    mailbox_account_scope,
    mailbox_scope,
    message_cache_key,
    move_messages,
    page_offset,
    remove_messages,
    require_targeted_removal,
    special_folder,
)
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.mailbox_drafts import (
    TRASH_NOT_FOUND,
    MailboxDraftChangedError,
    MailboxDraftNotFoundError,
    edit_draft_message,
    ensure_draft_revision,
    prepare_for_smtp,
)
from src.domains.connectors.clients.normalizers.email_normalizer import (
    convert_imap_query,
    normalize_imap_message,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    MessageLocation,
    folder_digest,
    is_uid,
    read_message_handle,
    scope_digest,
)
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.async_utils import write_through_cancellation
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.email.outgoing import OutgoingAttachment
from src.infrastructure.email.recipients import encode_recipients

logger = structlog.get_logger(__name__)

_T = TypeVar("_T")

_APPENDUID: Final = re.compile(rb"\[APPENDUID ([0-9]{1,10}) ([0-9]{1,10})\]", re.IGNORECASE)
_APPEND_RESPONSE_MAX_BYTES: Final = 512
_DRAFT_FLAGS: Final = (MailMessageFlags.DRAFT, MailMessageFlags.SEEN)
_DRAFT_PREFIX: Final = "d."


class _DraftFiling(NamedTuple):
    draft_removed: bool
    sent_copy_filed: bool


class _AppleDraftsHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID
    credentials: AppleCredentials

    async def _execute_with_retry(
        self,
        operation: str,
        func: Any,
        *args: Any,
        max_retries: int = 3,
        base_delay: float = 1.0,
        **kwargs: Any,
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _smtp_send(self, recipients: list[str], msg: Message) -> None: ...

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]: ...

    async def _original_with_files(
        self, message_id: str, *, include_files: bool
    ) -> tuple[dict[str, Any], list[OutgoingAttachment]]: ...

    async def _in_drafts(
        self,
        operation: str,
        work: Callable[[MailBox, str], _T],
        *,
        max_retries: int = 3,
    ) -> _T: ...

    async def _store_draft(self, message: Message) -> dict[str, Any]: ...

    async def _forget_cached(self, draft_ids: Sequence[str]) -> None: ...

    async def _file_as_sent(self, draft_id: str, raw: bytes) -> _DraftFiling: ...


def _one(mailbox: MailBox, uid: str) -> MailMessage | None:
    """The message ``uid`` of the selected folder, or None."""
    return next(iter(mailbox.fetch(AND(uid=uid), mark_seen=False)), None)


def _draft_location(draft_id: str) -> MessageLocation:
    """A current scoped draft handle; a bare UID requires a fresh listing."""
    location = (
        read_message_handle(draft_id.removeprefix(_DRAFT_PREFIX))
        if draft_id.startswith(_DRAFT_PREFIX)
        else None
    )
    if location is None or location.scope_digest is None:
        raise MailboxDraftNotFoundError(draft_id)
    return location


def _draft_uid(location: MessageLocation, folder: str, scope: str) -> str:
    """Refuse a UID of another folder, generation or account before its command."""
    if location.folder_digest != folder_digest(folder) or location.scope_digest != scope:
        raise MailboxDraftNotFoundError("The draft's mailbox namespace changed.")
    return location.uid


def _as_draft(message: MailMessage, folder: str, scope: str) -> dict[str, Any]:
    """A scoped message ID and a distinct draft handle for the same immutable MIME."""
    draft = normalize_imap_message(message, folder, keep_quoted=True, scope=scope)
    draft[FIELD_MAILBOX_DRAFT_ID] = f"{_DRAFT_PREFIX}{draft['id']}"
    # IMAP messages are immutable, but a folder rebuild can reuse its UIDs.
    # Hash all MIME bytes so HTML-only and same-named file changes are seen.
    draft[FIELD_MAILBOX_DRAFT_REVISION] = hashlib.sha256(message.obj.as_bytes()).hexdigest()
    return draft


def _renewed(message: Message, sender: str) -> Message:
    """The message dated now under a new ``Message-ID``: each save is a new message."""
    del message["Message-ID"]
    del message["Date"]
    message["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    message["Date"] = formatdate(usegmt=True)
    return message


def _encoded(addresses: str | None) -> str | None:
    """Recipients ready for a header; None (keep) and "" (clear) pass unchanged."""
    return encode_recipients(addresses) if addresses else addresses


def _appended_uid(
    answer: Sequence[bytes | None], folder: str, principal: str, scope: str
) -> str | None:
    """Read a bounded UIDPLUS receipt only for this selected namespace."""
    for line in answer:
        if not isinstance(line, bytes):
            continue
        prefix = line[:_APPEND_RESPONSE_MAX_BYTES]
        if b"[APPENDUID" not in prefix.upper():
            continue
        match = _APPENDUID.search(prefix)
        if match is None:
            raise MailboxDraftChangedError("The APPEND identity is malformed.", copy_saved=True)
        validity, uid = (value.decode("ascii") for value in match.groups())
        if not is_uid(validity) or not is_uid(uid):
            raise MailboxDraftChangedError("The APPEND identity is invalid.", copy_saved=True)
        if scope_digest(mailbox_account_scope(principal), folder, int(validity)) != scope:
            raise MailboxDraftChangedError("The APPEND namespace changed.", copy_saved=True)
        return uid
    return None


def _append(
    mailbox: MailBox, drafts: str, message: Message, *, principal: str, replacing: str | None = None
) -> dict[str, Any]:
    """APPEND ``message`` as a draft, drop ``replacing`` once it is in, read it back."""
    if replacing:
        require_targeted_removal(mailbox)
    before_scope = mailbox_scope(mailbox, drafts, principal)
    _status, answer = mailbox.append(
        message.as_bytes(), drafts, dt=datetime.now(UTC), flag_set=_DRAFT_FLAGS
    )
    mailbox.folder.set(drafts)
    after_scope = mailbox_scope(mailbox, drafts, principal)
    if before_scope != after_scope:
        raise MailboxDraftChangedError("The mailbox changed after APPEND.", copy_saved=True)
    uid = _appended_uid(answer or (), drafts, principal, after_scope)
    if uid is None:
        # No UIDPLUS: the new Message-ID finds it.
        found = mailbox.uids(AND(header=Header("Message-ID", str(message["Message-ID"]))))
        uid = found[0] if len(found) == 1 and is_uid(found[0]) else None
    saved = _one(mailbox, uid) if uid else None
    if saved is None or saved.obj["Message-ID"] != message["Message-ID"]:
        raise MailboxDraftChangedError(
            "The saved draft's identity could not be verified.", copy_saved=True
        )
    if replacing:
        remove_messages(mailbox, [replacing])
    return _as_draft(saved, drafts, after_scope)


class AppleDraftsMixin:
    """The person's own unsent messages in an iCloud mailbox."""

    async def _in_drafts(
        self: _AppleDraftsHost,
        operation: str,
        work: Callable[[MailBox, str], _T],
        *,
        max_retries: int = 3,
    ) -> _T:
        """Run ``work(mailbox, drafts_folder)`` in one IMAP session, off the loop."""

        def run() -> _T:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    drafts = special_folder(mailbox, DRAFTS_ROLE)
                    mailbox.folder.set(drafts)
                    return work(mailbox, drafts)
            except LookupError:
                raise
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        result: _T = await self._execute_with_retry(
            operation, asyncio.to_thread, run, max_retries=max_retries
        )
        return result

    async def _store_draft(self: _AppleDraftsHost, message: Message) -> dict[str, Any]:
        draft: dict[str, Any] = await self._in_drafts(
            "save_draft",
            lambda mailbox, drafts: _append(
                mailbox, drafts, message, principal=self.credentials.apple_id
            ),
            max_retries=0,
        )
        logger.info("apple_mailbox_draft_saved", user_id=str(self.user_id))
        return draft

    async def _forget_cached(self: _AppleDraftsHost, draft_ids: Sequence[str]) -> None:
        """Invalidate the account-scoped message IDs corresponding to these drafts."""
        if not draft_ids:
            return
        try:
            redis = await get_redis_session()
            await redis.delete(
                *(
                    message_cache_key(
                        self.user_id, self.credentials.apple_id, handle.removeprefix(_DRAFT_PREFIX)
                    )
                    for handle in draft_ids
                )
            )
        except Exception as error:
            logger.debug("apple_draft_cache_invalidation_failed", error_type=type(error).__name__)

    async def list_drafts(
        self: _AppleDraftsHost,
        query: str = "",
        max_results: int = 10,
        page_token: str | None = None,
        headers_only: bool = True,
    ) -> dict[str, Any]:
        """The drafts folder, last saved first, with its EXACT count.

        Args:
            query: Gmail-style query; a folder it names is ignored — the drafts
                folder is the only one read.
            max_results: Page size.
            page_token: The ``next_page_token`` of a previous page (an offset).
            headers_only: Fetch the envelopes only.

        Returns:
            ``messages`` (each with its ``mailbox_draft_id``), the exact
            ``resultSizeEstimate`` and ``next_page_token``.
        """
        criteria, _folder = convert_imap_query(query)
        size = apply_max_items_limit(max_results)
        offset = page_offset(page_token)

        def work(mailbox: MailBox, drafts: str) -> tuple[list[dict[str, Any]], int]:
            scope = mailbox_scope(mailbox, drafts, self.credentials.apple_id)
            total = len(mailbox.uids(criteria))
            page = [
                _as_draft(message, drafts, scope)
                for message in mailbox.fetch(
                    criteria,
                    limit=slice(offset, offset + size),
                    mark_seen=False,
                    reverse=True,
                    headers_only=headers_only,
                )
            ]
            return page, total

        page, total = await self._in_drafts("list_drafts", work)
        end = offset + len(page)
        return {
            "messages": page,
            "resultSizeEstimate": total,
            "next_page_token": str(end) if end < total else None,
        }

    async def get_draft(self: _AppleDraftsHost, draft_id: str) -> dict[str, Any]:
        """One draft, whole, its quoted history kept."""
        location = _draft_location(draft_id)

        def work(mailbox: MailBox, drafts: str) -> dict[str, Any]:
            scope = mailbox_scope(mailbox, drafts, self.credentials.apple_id)
            uid = _draft_uid(location, drafts, scope)
            message = _one(mailbox, uid)
            if message is None:
                raise MailboxDraftNotFoundError(draft_id)
            return _as_draft(message, drafts, scope)

        draft: dict[str, Any] = await self._in_drafts("get_draft", work)
        return draft

    async def create_draft(
        self: _AppleDraftsHost,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save a new draft; an empty ``to`` leaves the recipient unset."""
        message = new_message(
            sender=self.credentials.apple_id,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            is_html=is_html,
        )
        return await self._store_draft(message)

    async def create_reply_draft(
        self: _AppleDraftsHost,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the reply to ``message_id`` as a draft — the reply ``reply_email`` sends."""
        original = await self.get_message(message_id)
        message = reply_message(
            original, body, sender=self.credentials.apple_id, reply_all=reply_all, is_html=is_html
        )
        return await self._store_draft(message)

    async def create_forward_draft(
        self: _AppleDraftsHost,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the forward of ``message_id`` as a draft, with its files."""
        original, files = await self._original_with_files(message_id, include_files=True)
        message = forward_message(
            original,
            files,
            sender=self.credentials.apple_id,
            to=to,
            body=body,
            cc=cc,
            is_html=is_html,
        )
        return await self._store_draft(message)

    async def update_draft(
        self: _AppleDraftsHost,
        draft_id: str,
        *,
        to: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Change the fields given (None keeps one, "" clears it), keep the rest.

        The edited message is stored as a new draft — a NEW ``mailbox_draft_id``
        — and the old one removed once the new one is in.

        Raises:
            MailboxDraftNotFoundError: No such draft.
            ValueError: An address that cannot be read (nothing is stored).
        """
        location = _draft_location(draft_id)
        changes: dict[str, str | None] = {
            "to": _encoded(to),
            "cc": _encoded(cc),
            "bcc": _encoded(bcc),
            "subject": subject,
            "body": body,
        }
        sender = self.credentials.apple_id

        def work(mailbox: MailBox, drafts: str) -> tuple[dict[str, Any], str]:
            scope = mailbox_scope(mailbox, drafts, self.credentials.apple_id)
            uid = _draft_uid(location, drafts, scope)
            current = _one(mailbox, uid)
            if current is None:
                raise MailboxDraftNotFoundError(draft_id)
            raw = current.obj.as_bytes()
            revision = hashlib.sha256(raw).hexdigest() if expected_revision is not None else None
            ensure_draft_revision({FIELD_MAILBOX_DRAFT_REVISION: revision}, expected_revision)
            edited = edit_draft_message(raw, **changes)
            return (
                _append(mailbox, drafts, _renewed(edited, sender), principal=sender, replacing=uid),
                drafts,
            )

        draft, drafts = await self._in_drafts("update_draft", work, max_retries=0)
        await self._forget_cached([draft_id])
        logger.info("apple_mailbox_draft_updated", user_id=str(self.user_id))
        return draft

    async def trash_drafts(self: _AppleDraftsHost, draft_ids: Sequence[str]) -> dict[str, Any]:
        """Move drafts to the folder the server flags as its trash, in one command.

        Returns:
            ``{"trashed": [ids], "failed": [{"mailbox_draft_id", "status"}]}``.
        """
        requested = list(dict.fromkeys(draft_ids))
        locations: dict[str, MessageLocation] = {}
        for handle in requested:
            try:
                locations[handle] = _draft_location(handle)
            except MailboxDraftNotFoundError:
                continue

        def work(mailbox: MailBox, drafts: str) -> tuple[list[str], str]:
            scope = mailbox_scope(mailbox, drafts, self.credentials.apple_id)
            current = {
                handle: location.uid
                for handle, location in locations.items()
                if location.folder_digest == folder_digest(drafts)
                and location.scope_digest == scope
            }
            uids = list(current.values())
            present = set(mailbox.uids(AND(uid=uids))) if uids else set()
            moving = [handle for handle, uid in current.items() if uid in present]
            if moving:
                move_messages(
                    mailbox,
                    [current[handle] for handle in moving],
                    special_folder(mailbox, TRASH_ROLE),
                )
            return moving, drafts

        trashed, drafts = await self._in_drafts("trash_drafts", work, max_retries=0)
        await self._forget_cached(trashed)
        failed = [
            {FIELD_MAILBOX_DRAFT_ID: handle, "status": TRASH_NOT_FOUND}
            for handle in requested
            if handle not in trashed
        ]
        logger.info(
            "apple_mailbox_drafts_trashed",
            user_id=str(self.user_id),
            trashed=len(trashed),
            failed=len(failed),
        )
        return {"trashed": trashed, "failed": failed}

    async def send_draft(self: _AppleDraftsHost, draft_id: str) -> dict[str, Any]:
        """Send a draft as it is stored — one attempt, never retried.

        Returns:
            ``id`` (None: SMTP names no stored message), ``mailbox_draft_id``
            and ``draft_kept`` — True when the message left but the mailbox
            could not take the draft out of the drafts folder.

        Raises:
            MailboxDraftNotFoundError: No such draft.
            ValueError: A draft without a recipient, or one that cannot be read.
        """
        location = _draft_location(draft_id)

        def read(mailbox: MailBox, _drafts: str) -> bytes:
            scope = mailbox_scope(mailbox, _drafts, self.credentials.apple_id)
            uid = _draft_uid(location, _drafts, scope)
            message = _one(mailbox, uid)
            if message is None:
                raise MailboxDraftNotFoundError(draft_id)
            raw: bytes = message.obj.as_bytes()
            return raw

        raw = await self._in_drafts("read_draft", read)
        # As stored (compat32): the modern policy re-reads a malformed header.
        outgoing = email.message_from_bytes(raw)
        recipients = prepare_for_smtp(outgoing)
        if not recipients:
            raise ValueError("A draft without a recipient cannot be sent.")
        filing = _DraftFiling(False, False)

        async def send_and_file() -> None:
            nonlocal filing
            await self._execute_with_retry(
                "send_draft", self._smtp_send, recipients, outgoing, max_retries=0
            )
            filing = await self._file_as_sent(draft_id, raw)

        # SMTP runs on an uninterruptible worker. Finish this already-started
        # write and its filing rather than lose its acknowledgement on a stop.
        # The shared task registry retains it even after repeated cancellations.
        if await write_through_cancellation(
            send_and_file, attempts=SMTP_CANCELLATION_GRACE_ATTEMPTS, label="mailbox_draft_send"
        ):
            raise asyncio.CancelledError
        logger.info("apple_mailbox_draft_sent", user_id=str(self.user_id), filing=filing._asdict())
        return {
            "id": None,
            FIELD_MAILBOX_DRAFT_ID: draft_id,
            "draft_kept": not filing.draft_removed,
            "sent_copy_filed": filing.sent_copy_filed,
        }

    async def _file_as_sent(self: _AppleDraftsHost, draft_id: str, raw: bytes) -> _DraftFiling:
        """Take a sent draft out of the drafts folder, then file a copy as sent.

        The message has left: nothing here may fail the send. Report draft
        removal and the stored sent copy separately; neither implies the other.
        """

        def work(mailbox: MailBox, drafts: str) -> tuple[str, _DraftFiling]:
            scope = mailbox_scope(mailbox, drafts, self.credentials.apple_id)
            uid = _draft_uid(_draft_location(draft_id), drafts, scope)
            remove_messages(mailbox, [uid])
            copied = True
            try:
                mailbox.append(
                    raw,
                    special_folder(mailbox, SENT_ROLE),
                    dt=datetime.now(UTC),
                    flag_set=(MailMessageFlags.SEEN,),
                )
            except Exception as error:
                copied = False
                logger.warning("apple_sent_copy_not_filed", error_type=type(error).__name__)
            return drafts, _DraftFiling(True, copied)

        try:
            drafts, filing = await self._in_drafts("file_sent_draft", work, max_retries=0)
        except Exception as error:
            logger.warning("apple_sent_draft_not_removed", error_type=type(error).__name__)
            return _DraftFiling(False, False)
        await self._forget_cached([draft_id])
        return filing


__all__ = ["AppleDraftsMixin"]
