"""Injected shared-preference owners; consumers cannot acquire domain business code."""

from dataclasses import dataclass

from src.core.exceptions import AuthorizationError
from src.infrastructure.mcp.preferences_contract import (
    SharedMCPPreferenceReader,
    SharedMCPPreferenceWriter,
)


@dataclass(frozen=True)
class SharedMCPPreferencesGateway:
    read: SharedMCPPreferenceReader
    write: SharedMCPPreferenceWriter


_gateway: SharedMCPPreferencesGateway | None = None


def configure_shared_mcp_preferences(
    gateway: SharedMCPPreferencesGateway | None,
) -> SharedMCPPreferencesGateway | None:
    global _gateway
    previous, _gateway = _gateway, gateway
    return previous


def get_shared_mcp_preferences() -> SharedMCPPreferencesGateway:
    if _gateway is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _gateway
