"""What the person signs with: one door for the composer and the assistant (ADR-369, lot 7, A3).

A signature belongs to a mailbox, in its connector's encrypted preferences. Only the active
one is read, from the database alone: no provider is called, so a card or a composer pays
nothing for it. It is free text a recipient reads, added to a message's body and shown to
the person there, never placed in a prompt.
"""

from __future__ import annotations

from html import escape
from typing import Final
from uuid import UUID

from src.domains.connectors.preferences.commands import update_owned_connector_preferences
from src.domains.connectors.preferences.owner_defaults import read_owner_preference_name
from src.domains.connectors.preferences.schemas import PreferencesRequest
from src.domains.connectors.provider_resolver import resolve_active_connector
from src.domains.connectors.repository import ConnectorRepository
from src.domains.connectors.session_scope import DetachedConnectorService

_MAIL_CATEGORY: Final = "email"
_SIGNATURE: Final = "signature"
#: What sets a signature off from the words above it (RFC 3676, section 4.3).
_DELIMITER: Final = "-- "


class NoActiveMailboxError(LookupError):
    """No mailbox is connected: a signature has nowhere to be kept."""


def signature_block(signature: str, *, is_html: bool = False) -> str:
    """What a body gains to carry a signature; nothing for none.

    Args:
        signature: The person's text.
        is_html: The body is HTML: the signature's words stay words.

    Returns:
        The text to append.
    """
    if not signature:
        return ""
    if is_html:
        lines = "<br>".join(escape(line) for line in signature.splitlines())
        return f"<br><br>{_DELIMITER}<br>{lines}"
    return f"\n\n{_DELIMITER}\n{signature}"


async def read_signature(user_id: UUID) -> str:
    """The active mailbox's signature; empty when nothing was written or none is connected."""
    connectors = DetachedConnectorService()
    async with connectors.unit_of_work() as service:
        connector_type = await resolve_active_connector(user_id, _MAIL_CATEGORY, service)
        if connector_type is None:
            return ""
        text = await read_owner_preference_name(service.db, user_id, connector_type, _SIGNATURE)
    return text or ""


async def save_signature(user_id: UUID, text: str) -> str:
    """Keep the active mailbox's signature; an empty text clears it.

    Args:
        user_id: Whose mailbox.
        text: What it signs with.

    Returns:
        The signature as it was kept.

    Raises:
        NoActiveMailboxError: No mailbox is connected.
    """
    connectors = DetachedConnectorService()
    async with connectors.unit_of_work() as service:
        connector_type = await resolve_active_connector(user_id, _MAIL_CATEGORY, service)
        connector = (
            await ConnectorRepository(service.db).get_by_user_and_type(user_id, connector_type)
            if connector_type is not None
            else None
        )
        if connector is None:
            raise NoActiveMailboxError
        saved = await update_owned_connector_preferences(
            service.db, user_id, connector.id, PreferencesRequest(signature=text)
        )
    return saved.preferences.get(_SIGNATURE) or ""
