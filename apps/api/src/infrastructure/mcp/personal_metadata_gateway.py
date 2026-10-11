"""Injected personal MCP metadata owner, following the shared settings port."""

from src.core.exceptions import AuthorizationError
from src.infrastructure.mcp.personal_metadata_contract import PersonalMCPMetadataReader

_reader: PersonalMCPMetadataReader | None = None


def configure_personal_mcp_metadata(
    reader: PersonalMCPMetadataReader | None,
) -> PersonalMCPMetadataReader | None:
    global _reader
    previous, _reader = _reader, reader
    return previous


def get_personal_mcp_metadata() -> PersonalMCPMetadataReader:
    if _reader is None:
        raise AuthorizationError(detail={"error_code": "SERVICE_UNAVAILABLE"})
    return _reader
