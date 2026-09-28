"""The e-mails the listener sent today, as drafts for the journal's « done » part.

Read from the listener's active mailbox through its sent folder — the Gmail-style
query every client translates (``in:sent``, native on Gmail, a folder on Graph and
IMAP), the headers alone (``headers_only``: no body reaches the station) — and kept
when the message's own date falls on the listener's today. Each shipped provider
exposes its sent folder; a client that cannot answer RAISES, and the day source
records the source as ``failed``: nothing here is ever read as « nothing sent ».

The client is open for the length of the read and closed before it returns
(ADR-304).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from email.utils import parsedate_to_datetime
from typing import Any, Final
from uuid import UUID

from src.domains.briefing.constants import ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.connectors.active_client import ActiveClient, ClientUnavailable, open_active_client
from src.domains.radio.facts import FactKind, Sensitivity, local_time_text
from src.domains.radio.personal import MAX_PER_SOURCE, JournalPart, PersonalDraft, PersonalSource

#: How many sent messages are listed for the day (the bound is applied after the filter).
_SCAN_MESSAGES: Final[int] = 20


@dataclass(frozen=True, slots=True)
class SentMail:
    """What the radio reads of one sent e-mail.

    Attributes:
        id: The provider's message id.
        to: The recipients, as the header names them.
        subject: The subject line.
        sent_at: When it was sent (aware), when the header could be read.
    """

    id: str
    to: str
    subject: str
    sent_at: datetime | None


def _sent_at(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except TypeError, ValueError, IndexError:
        return None
    return parsed if parsed.tzinfo is not None else None


def sent_mail_line(hit: Mapping[str, Any]) -> SentMail | None:
    """One search hit as the radio reads it, or ``None`` when it has no id."""
    message_id = hit.get("id")
    if not message_id:
        return None
    return SentMail(
        id=str(message_id),
        to=str(hit.get("to") or "").strip() or "an unnamed recipient",
        subject=str(hit.get("subject") or "").strip() or "(no subject)",
        sent_at=_sent_at(hit.get("date")),
    )


def sent_mail_drafts(
    lines: Sequence[SentMail], *, now: datetime, tz: tzinfo
) -> list[PersonalDraft]:
    """The e-mails sent today, as drafts.

    A message whose date cannot be read is kept — the folder was asked for today —
    and told without its time.

    Args:
        lines: The sent messages found.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        One draft per e-mail sent today.
    """
    today = now.astimezone(tz).date()
    drafts: list[PersonalDraft] = []
    for line in lines:
        sent = line.sent_at.astimezone(tz) if line.sent_at is not None else None
        if sent is not None and sent.date() != today:
            continue
        text = f'E-mail sent to {line.to}: "{line.subject}"'
        if sent is not None:
            text += f" on {local_time_text(sent)}"
        drafts.append(
            PersonalDraft(
                FactKind.EMAIL,
                text,
                f"done:email:{line.id}",
                Sensitivity.PERSONAL,
                JournalPart.DONE,
            )
        )
    return drafts


async def read_sent_mail(user_id: UUID, *, now: datetime, tz: tzinfo) -> list[PersonalDraft]:
    """The e-mails the listener sent today, from their active mailbox.

    Raises:
        ConnectorAccessError: The mailbox is connected but its credentials failed.

    Args:
        user_id: The listener.
        now: The current instant (aware).
        tz: The listener's timezone.

    Returns:
        The drafts, bounded like every personal source.
    """
    # The provider reads « after » as a date on its own clock: ask from yesterday, and
    # let the message's own date decide what is today for the listener.
    since = now.astimezone(tz).date() - timedelta(days=1)
    async with open_active_client("email", user_id) as opened:
        if opened is ClientUnavailable.NO_CREDENTIALS:
            raise ConnectorAccessError(
                "email", ERROR_CODE_CONNECTOR_OAUTH_EXPIRED, "credentials refused"
            )
        if not isinstance(opened, ActiveClient):
            return []  # no mailbox connected: nothing to read
        result = await opened.client.search_emails(
            f"in:sent after:{since:%Y/%m/%d}", max_results=_SCAN_MESSAGES, headers_only=True
        )
    hits = result.get("messages") or []
    lines = [line for hit in hits if isinstance(hit, dict) and (line := sent_mail_line(hit))]
    return sent_mail_drafts(lines, now=now, tz=tz)[: MAX_PER_SOURCE[PersonalSource.SENT_MAILS]]


__all__ = ["SentMail", "read_sent_mail", "sent_mail_drafts", "sent_mail_line"]
