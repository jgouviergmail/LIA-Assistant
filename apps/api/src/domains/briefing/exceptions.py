"""Briefing domain exceptions — lifted to status by BriefingService._section()."""

from src.domains.briefing.constants import (
    ERROR_CODE_CONNECTOR_NOT_CONFIGURED,
)


class ConnectorNotConfiguredError(Exception):
    """Raised when no active connector exists for the section's data source.

    Mapped to CardStatus.NOT_CONFIGURED by BriefingService — the card is then
    entirely hidden from the UI (frontend returns null).

    Attributes:
        source: Logical source name (e.g. "openweathermap", "calendar").
        error_code: Stable code (always ERROR_CODE_CONNECTOR_NOT_CONFIGURED).
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.error_code = ERROR_CODE_CONNECTOR_NOT_CONFIGURED
        super().__init__(f"No active connector for source '{source}'")


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
