"""Briefing domain exceptions — lifted to status by BriefingService._section()."""

import httpx

from src.core.exceptions import ConnectorAPIError
from src.domains.briefing.constants import (
    ERROR_CODE_CONNECTOR_NETWORK,
    ERROR_CODE_CONNECTOR_NOT_CONFIGURED,
    ERROR_CODE_CONNECTOR_OAUTH_EXPIRED,
    ERROR_CODE_CONNECTOR_RATE_LIMIT,
    ERROR_CODE_LOCATION_NOT_CONFIGURED,
)


class ConnectorNotConfiguredError(Exception):
    """Raised when no active connector exists for the section's data source.

    Mapped to CardStatus.NOT_CONFIGURED by BriefingService — the card is then
    entirely hidden from the UI (frontend returns null), and the dashboard's
    setup line names it with a link to where it gets configured.

    Attributes:
        source: Logical source name (e.g. "openweathermap", "calendar").
        error_code: Stable code — ERROR_CODE_CONNECTOR_NOT_CONFIGURED here,
            the missing piece's own code in a subclass.
    """

    error_code: str = ERROR_CODE_CONNECTOR_NOT_CONFIGURED

    def __init__(self, source: str) -> None:
        self.source = source
        super().__init__(f"No active connector for source '{source}'")


class LocationNotConfiguredError(ConnectorNotConfiguredError):
    """The source is there, the person's address is not (the weather card).

    Since ADR-307 the weather has a provider on every instance that keeps its
    platform key, so what a new account lacks is an address — and sending the
    person to the connectors would point them at a page with nothing to do.
    """

    error_code = ERROR_CODE_LOCATION_NOT_CONFIGURED

    def __init__(self) -> None:
        super().__init__("location")


class ConnectorAccessError(Exception):
    """Raised when a connector exists but the access fails (token expired, etc.).

    Mapped to CardStatus.ERROR. The frontend uses ``error_code`` to select the
    appropriate localized CTA (e.g. "Reconnect", "Retry").

    Attributes:
        source: Logical source name.
        error_code: One of the ERROR_CODE_* constants.
        message: Localized human-readable message (or fallback raw error).
    """

    def __init__(self, source: str, error_code: str, message: str) -> None:
        self.source = source
        self.error_code = error_code
        self.message = message
        super().__init__(f"{source}: {error_code} — {message}")


def classify_http_error(exc: Exception) -> str:
    """Map an HTTP/network exception to a stable error_code."""
    # The API-key client hands a 429 it could not wait out back typed (ADR-108
    # amendment 2026-10-13). Only that status is read here: a 401 on Google
    # Weather is the instance's key, which nobody can reconnect (ADR-307).
    if isinstance(exc, ConnectorAPIError) and exc.upstream_status_code == 429:
        return ERROR_CODE_CONNECTOR_RATE_LIMIT
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 401:
            return ERROR_CODE_CONNECTOR_OAUTH_EXPIRED
        if status == 429:
            return ERROR_CODE_CONNECTOR_RATE_LIMIT
    return ERROR_CODE_CONNECTOR_NETWORK
