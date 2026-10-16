"""Bounded credential probes for every Apple protocol requested by activation."""

import asyncio
import ssl
from collections.abc import Awaitable, Callable, Sequence
from typing import Final

import httpx
import structlog
from caldav.lib.error import AuthorizationError
from imap_tools.errors import MailboxLoginError

from src.core.config import settings
from src.core.i18n_apple_connections import MessageKind, connection_message
from src.domains.connectors.models import ConnectorType

logger = structlog.get_logger(__name__)
_Probe = Callable[[str, str], Awaitable[tuple[bool, str]]]


def _failure(protocol: str, error: Exception) -> tuple[bool, str]:
    """Provider prose and account identifiers are not public connection diagnostics."""
    logger.warning(f"apple_{protocol.lower()}_test_failed", error_type=type(error).__name__)
    logger.debug("apple_connection_test_error", protocol=protocol, error=str(error))
    kind: MessageKind = "failed"
    if isinstance(error, ssl.SSLCertVerificationError):
        kind = "certificate"
    elif isinstance(error, MailboxLoginError | AuthorizationError):
        kind = "authentication"
    return False, connection_message(kind, protocol=protocol)


async def _imap(apple_id: str, app_password: str) -> tuple[bool, str]:
    def login() -> None:
        from imap_tools import MailBox

        from src.domains.connectors.clients.apple_imap import authenticated_imap_mailbox

        with authenticated_imap_mailbox(MailBox, apple_id, app_password):
            pass

    try:
        await asyncio.to_thread(login)
        return True, connection_message("success", protocol="IMAP")
    except Exception as error:
        return _failure("IMAP", error)


async def _caldav(apple_id: str, app_password: str) -> tuple[bool, str]:
    def login() -> None:
        import caldav

        with caldav.DAVClient(
            url=settings.apple_caldav_url,
            username=apple_id,
            password=app_password,
            timeout=settings.apple_connection_timeout,
        ) as client:
            principal = client.principal()
            principal.calendars()

    try:
        await asyncio.to_thread(login)
        return True, connection_message("success", protocol="CalDAV")
    except Exception as error:
        return _failure("CalDAV", error)


async def _carddav(apple_id: str, app_password: str) -> tuple[bool, str]:
    try:
        async with httpx.AsyncClient(
            auth=(apple_id, app_password), timeout=settings.apple_connection_timeout
        ) as client:
            response = await client.request(
                "PROPFIND",
                settings.apple_carddav_url,
                headers={"Depth": "0", "Content-Type": "application/xml"},
                content=(
                    '<?xml version="1.0" encoding="UTF-8"?>'
                    '<d:propfind xmlns:d="DAV:">'
                    "<d:prop><d:current-user-principal/></d:prop>"
                    "</d:propfind>"
                ),
            )
            if response.status_code in (207, 200):
                return True, connection_message("success", protocol="CardDAV")
            if response.status_code in (401, 403):
                return False, connection_message("authentication", protocol="CardDAV")
            return False, connection_message(
                "response", protocol="CardDAV", status_code=response.status_code
            )
    except Exception as error:
        return _failure("CardDAV", error)


_PROBES: Final[dict[ConnectorType, _Probe]] = {
    ConnectorType.APPLE_EMAIL: _imap,
    ConnectorType.APPLE_CALENDAR: _caldav,
    ConnectorType.APPLE_CONTACTS: _carddav,
}


async def probe_connection(
    apple_id: str, app_password: str, services: Sequence[ConnectorType]
) -> tuple[bool, str]:
    """A first success cannot vouch for a different protocol; duplicates run once."""
    messages: list[str] = []
    for connector in dict.fromkeys(services):
        probe = _PROBES.get(connector)
        if probe is None:
            continue
        success, message = await probe(apple_id, app_password)
        if not success:
            return False, message
        messages.append(message)
    if not messages:
        return False, connection_message("none")
    return True, "; ".join(messages)
