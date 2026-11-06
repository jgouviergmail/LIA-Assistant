"""One door to a mailbox's settings, for the screen and the assistant (ADR-369, lot 12).

Gmail keeps them on a client of its own, on the mailbox's token; Outlook's client speaks the same
vocabulary itself (``OutlookMailboxSettingsMixin``). iCloud has no such settings.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID

from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.google_gmail_settings_client import (
    GoogleGmailSettingsClient,
)
from src.domains.connectors.clients.outlook_mailbox_settings_mixin import (
    MailboxSettingNotHeldError,
)
from src.domains.connectors.clients.protocols import MailboxSettingsProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.session_scope import DetachedConnectorService

#: The mailboxes that hold an automatic reply and rules a person can reach.
MAILBOX_SETTINGS_PROVIDERS: Final = frozenset(
    {ConnectorType.GOOGLE_GMAIL, ConnectorType.MICROSOFT_OUTLOOK}
)


@asynccontextmanager
async def mailbox_settings_of(
    mailbox: Any, user_id: UUID
) -> AsyncIterator[MailboxSettingsProtocol]:
    """The settings of a mailbox whose client is open, closed on every path.

    Args:
        mailbox: The mailbox's open client.
        user_id: The account.

    Yields:
        What speaks the settings' vocabulary.

    Raises:
        MailboxSettingNotHeldError: A mailbox with no such settings.
    """
    if hasattr(mailbox, "list_filters"):
        yield mailbox
        return
    if not isinstance(mailbox, GoogleGmailClient):
        raise MailboxSettingNotHeldError
    client = GoogleGmailSettingsClient(user_id, mailbox.credentials, DetachedConnectorService())
    try:
        yield client
    finally:
        await client.close()


__all__ = ["MAILBOX_SETTINGS_PROVIDERS", "mailbox_settings_of"]
