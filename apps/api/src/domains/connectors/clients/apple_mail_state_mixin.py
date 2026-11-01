"""Whether an iCloud message was read — the IMAP ``\\Seen`` flag (ADR-369, D2).

Out of ``apple_email_client.py``, which is close to its size cap. A message id
names its folder (``imap_handles``): the selection is flagged folder by folder,
each folder selected once, so the INBOX's message 101 is never mistaken for the
Sent folder's. An id that cannot be a current one, or names a message the folder
no longer holds, is reported ``not_found`` — the rest is still flagged.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Sequence
from typing import Any, Protocol
from uuid import UUID

import structlog
from imap_tools import AND, MailBox, MailMessageFlags

from src.domains.connectors.clients.apple_imap import (
    authenticated_imap_mailbox,
    message_cache_key,
    select_message_folder,
)
from src.domains.connectors.clients.mail_read_state import (
    READ_STATE_NOT_FOUND,
    read_state_result,
    unique_ids,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    MessageLocation,
    read_message_handle,
)
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)

#: The messages of one folder (and one account scope), with what each id says.
_Group = list[tuple[str, MessageLocation]]
_GroupKey = tuple[str | None, str | None]


class _AppleStateHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID
    credentials: AppleCredentials

    async def _execute_with_retry(
        self, operation: str, func: Any, *args: Any, max_retries: int = 3, **kwargs: Any
    ) -> Any: ...

    def _check_imap_auth_error(self, error: Exception) -> None: ...

    async def _mark_read_impl(self, ids: list[str], read: bool) -> dict[str, Any]: ...


class AppleMailStateMixin:
    """The read state of iCloud messages."""

    async def mark_read(
        self: _AppleStateHost, message_ids: Sequence[str], read: bool
    ) -> dict[str, Any]:
        """Mark messages read or unread, and say which could not be.

        Args:
            message_ids: The messages (each counted once).
            read: True to mark them read, False unread.

        Returns:
            ``{"updated": [ids], "failed": [{"id", "status"}]}``
            (``mail_read_state``).
        """
        # Setting a flag twice leaves it set once, but the session is the act: no replay.
        return await self._execute_with_retry(
            "mark_read", self._mark_read_impl, unique_ids(message_ids), read, max_retries=0
        )

    async def _mark_read_impl(self: _AppleStateHost, ids: list[str], read: bool) -> dict[str, Any]:
        """Flag each folder's messages in one selection of that folder."""
        groups, unreadable = _by_folder(ids)
        principal = self.credentials.apple_id

        def flag_each_folder() -> tuple[list[str], list[str]]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, principal, self.credentials.app_password
                ) as mailbox:
                    return _flag_groups(mailbox, groups, principal, read)
            except Exception as error:
                self._check_imap_auth_error(error)
                raise

        flagged, missing = await asyncio.to_thread(flag_each_folder)
        await _forget_cached(self, flagged)
        # Reported in the selection's own order, whatever folder each one was in.
        not_found = {*missing, *unreadable}
        flagged_set = set(flagged)
        result = read_state_result(
            [mid for mid in ids if mid in flagged_set],
            [(mid, READ_STATE_NOT_FOUND) for mid in ids if mid in not_found],
        )
        logger.info(
            "apple_read_state_changed",
            user_id=str(self.user_id),
            read=read,
            updated=len(result["updated"]),
            failed=len(result["failed"]),
        )
        return result


def _by_folder(ids: list[str]) -> tuple[dict[_GroupKey, _Group], list[str]]:
    """The ids grouped by the folder (and scope) they name; the unreadable ones apart."""
    groups: dict[_GroupKey, _Group] = defaultdict(list)
    unreadable: list[str] = []
    for message_id in ids:
        location = read_message_handle(message_id)
        if location is None or location.scope_digest is None:
            unreadable.append(message_id)
            continue
        groups[(location.folder_digest, location.scope_digest)].append((message_id, location))
    return groups, unreadable


def _flag_groups(
    mailbox: Any, groups: dict[_GroupKey, _Group], principal: str, read: bool
) -> tuple[list[str], list[str]]:
    """Flag every group in its own folder selection: (flagged ids, ids not there)."""
    flagged: list[str] = []
    missing: list[str] = []
    for members in groups.values():
        found, absent = _flag_one_folder(mailbox, members, principal, read)
        flagged += found
        missing += absent
    return flagged, missing


def _flag_one_folder(
    mailbox: Any, members: _Group, principal: str, read: bool
) -> tuple[list[str], list[str]]:
    """Select the members' folder, flag the UIDs it still holds: (flagged, absent)."""
    folder = select_message_folder(mailbox, members[0][1], principal=principal)
    if folder is None:
        return [], [message_id for message_id, _ in members]
    present = set(mailbox.uids(AND(uid=[location.uid for _, location in members])))
    found = [(mid, location) for mid, location in members if location.uid in present]
    if found:
        mailbox.flag([location.uid for _, location in found], MailMessageFlags.SEEN, read)
    return (
        [mid for mid, _ in found],
        [mid for mid, location in members if location.uid not in present],
    )


async def _forget_cached(host: _AppleStateHost, message_ids: list[str]) -> None:
    """Drop the cached copies of messages whose flags changed (they carry ``is_read``)."""
    if not message_ids:
        return
    try:
        redis = await get_redis_session()
        await redis.delete(
            *(
                message_cache_key(host.user_id, host.credentials.apple_id, message_id)
                for message_id in message_ids
            )
        )
    except Exception as error:  # a cache that could not forget expires by its TTL
        logger.debug("apple_read_state_cache_invalidation_failed", error_type=type(error).__name__)


__all__ = ["AppleMailStateMixin"]
