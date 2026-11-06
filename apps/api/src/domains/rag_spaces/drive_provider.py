"""Which drive a linked folder lives on (ADR-369, lot 11).

Google Drive and OneDrive speak one files contract, and a folder belongs to the drive it was linked
on: its id means nothing on the other. An account connects one drive at a time, so a folder of the
other is kept, its documents searchable, and its synchronisation waits for that drive to come back.
"""

from __future__ import annotations

from typing import Any, Final, Protocol
from uuid import UUID

from src.core.exceptions import BaseAPIException
from src.domains.connectors.clients.registry import ClientRegistry
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.provider_resolver import resolve_active_connector

#: The functional category a drive answers to.
_FILES: Final = "files"
#: What the screen reads when a folder's drive is not the one connected.
DRIVE_SOURCE_PAUSED_CODE: Final = "drive_source_paused"


class DriveSourcePausedError(BaseAPIException):
    """A folder's drive is not the one connected: it waits, which is no outage."""


class _LinkedFolder(Protocol):
    provider: str


def drive_client_of(provider: str, user_id: UUID, credentials: Any, connectors: Any) -> Any:
    """The client of the drive ``provider`` names.

    Args:
        provider: The ``ConnectorType`` value a source carries.
        user_id: The account.
        credentials: Its credentials for that drive.
        connectors: The service its token refreshes write through.

    Returns:
        The client; the caller closes it.

    Raises:
        ValueError: No such drive.
    """
    client_class = ClientRegistry.get_client_class(ConnectorType(provider))
    if client_class is None:
        raise ValueError(f"No client is registered for {provider}")
    return client_class(user_id, credentials, connectors)


async def active_drive_provider(user_id: UUID, service: Any) -> str | None:
    """The drive the account has connected now.

    Args:
        user_id: The account.
        service: The connector service it is read through.

    Returns:
        Its ``ConnectorType`` value; None when it has none.
    """
    connector_type = await resolve_active_connector(user_id, _FILES, service)
    return connector_type.value if connector_type is not None else None


def is_paused(source: _LinkedFolder, active_provider: str | None) -> bool:
    """Whether a folder waits for its drive to come back.

    Args:
        source: The linked folder.
        active_provider: The drive the account has connected now.

    Returns:
        True when no client can read it.
    """
    return source.provider != active_provider


__all__ = [
    "DRIVE_SOURCE_PAUSED_CODE",
    "DriveSourcePausedError",
    "active_drive_provider",
    "drive_client_of",
    "is_paused",
]
