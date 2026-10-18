"""Non-secret MCP authentication requirements, including offline installations."""

from collections.abc import Mapping

from src.domains.user_mcp.models import UserMCPServer


def build_response_metadata(
    server: UserMCPServer, credentials: Mapping[str, object] | None
) -> dict[str, object]:
    header = (
        credentials.get("header_name", server.required_header_name)
        if credentials
        else server.required_header_name
    )
    scopes = (server.oauth_metadata or {}).get("requested_scopes")
    return {
        "header_name": header if isinstance(header, str) else None,
        "has_credentials": bool(server.credentials_encrypted),
        "has_oauth_credentials": bool(credentials and credentials.get("client_id")),
        "oauth_scopes": scopes if isinstance(scopes, str) else None,
    }
