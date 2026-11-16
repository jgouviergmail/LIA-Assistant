"""Every Gmail history record since an anchor, page after page (ADR-262, ADR-185 amendment).

``users.history.list`` answers a page at a time, and EVERY page carries the
mailbox's CURRENT history id, not the id after that page. Gmail's own rule:
store it only once no ``nextPageToken`` comes back. Keeping it from a page that
has a next one skips the pages never read — the heartbeat's delta did, and every
new message past its first page (25 records, the agents' per-request ceiling)
was gone for good.

One reader for every consumer of the history (the heartbeat's delta, the push
wake's preview, the mail source of a space). Each decides where it resumes:
:attr:`HistoryRead.history_id` exists only for a read that reached the end, and
:attr:`HistoryRead.last_record_id` names the last record a cut read did see.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.core.constants import GMAIL_HISTORY_PAGE_SIZE


class HistoryClient(Protocol):
    """What a mailbox needs to be read through its history (Gmail alone has one)."""

    async def get_history(
        self,
        start_history_id: str,
        max_results: int = ...,
        page_token: str | None = None,
        history_types: tuple[str, ...] = ...,
        label_id: str = ...,
    ) -> dict[str, Any]:
        """One page of history records after ``start_history_id``."""
        ...


@dataclass(frozen=True)
class HistoryRead:
    """The records a read gathered, and where the next read may start.

    Attributes:
        records: Every history record read, in Gmail's (chronological) order.
        complete: True when the last page came back without a next one.
        history_id: The mailbox's history id, ONLY when the read is complete.
        last_record_id: The id of the last record read, None when none was.
    """

    records: list[dict[str, Any]] = field(default_factory=list)
    complete: bool = True
    history_id: str | None = None
    last_record_id: str | None = None

    @property
    def resume_from(self) -> str | None:
        """Where the next read starts without losing a record.

        The mailbox's id after a whole read; after a cut, the last record this
        read saw (a history list returns the records AFTER its start), or None
        when it saw none — the anchor stays where it was.
        """
        return self.history_id if self.complete else self.last_record_id

    def added_message_ids(self) -> list[str]:
        """Message ids the records add, deduplicated, in chronological order."""
        seen: set[str] = set()
        ids: list[str] = []
        for record in self.records:
            for added in record.get("messagesAdded", []) or []:
                message_id = (added.get("message") or {}).get("id")
                if message_id and message_id not in seen:
                    seen.add(message_id)
                    ids.append(str(message_id))
        return ids


def _identifier(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


async def read_history(
    client: HistoryClient,
    start_history_id: str,
    *,
    pages_max: int,
    history_types: Sequence[str] = ("messageAdded",),
    label_id: str = "INBOX",
) -> HistoryRead:
    """Every record after ``start_history_id``, page after page, at most ``pages_max`` pages.

    Args:
        client: A Gmail client.
        start_history_id: The anchor: records after it are read.
        pages_max: Pages read at most; past them the read is cut, and says so.
        history_types: The record kinds asked.
        label_id: The label the records are about.

    Returns:
        The records, and where the next read may resume.

    Raises:
        ConnectorAPIError: Gmail refused the anchor (404 once it expired) or the read.
    """
    records: list[dict[str, Any]] = []
    token: str | None = None
    for _ in range(max(1, pages_max)):
        page = await client.get_history(
            start_history_id=start_history_id,
            max_results=GMAIL_HISTORY_PAGE_SIZE,
            page_token=token,
            history_types=tuple(history_types),
            label_id=label_id,
        )
        records.extend(record for record in page.get("history", []) or [] if record)
        token = page.get("nextPageToken")
        if not token:
            return HistoryRead(
                records=records,
                complete=True,
                history_id=_identifier(page.get("historyId")),
                last_record_id=_identifier(records[-1].get("id")) if records else None,
            )
    return HistoryRead(
        records=records,
        complete=False,
        history_id=None,
        last_record_id=_identifier(records[-1].get("id")) if records else None,
    )
