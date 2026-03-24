"""
User MCP Server Pydantic v2 schemas.

Input/output models for the user MCP servers CRUD API.

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.core.constants import MCP_DEFAULT_TIMEOUT_SECONDS
from src.domains.user_mcp.models import UserMCPAuthType, UserMCPServerStatus


class UserMCPServerCreate(BaseModel):
    """Schema for creating a new user MCP server."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="User-facing server name (unique per user)",
    )
    url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Streamable HTTP endpoint URL (must be HTTPS)",
    )

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        """MCP servers must use HTTPS for transport security."""
        if not v.startswith("https://"):
            raise ValueError("MCP server URL must use HTTPS")
        return v

    auth_type: UserMCPAuthType = Field(
        default=UserMCPAuthType.NONE,
        description="Authentication type for this server",
    )

    # Credentials (mutually exclusive based on auth_type)
    api_key: str | None = Field(
        default=None,
        min_length=1,
        description="API key value (for auth_type=api_key)",
    )
    header_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Header name for API key (default: X-API-Key)",
    )
    bearer_token: str | None = Field(
        default=None,
        min_length=1,
        description="Bearer token value (for auth_type=bearer)",
    )

    # OAuth 2.1 optional client credentials (for pre-registered clients)
    oauth_client_id: str | None = Field(
        default=None,
        description="Pre-registered OAuth client_id (if auth server requires it)",
    )
    oauth_client_secret: str | None = Field(
        default=None,
        description="Pre-registered OAuth client_secret (if auth server requires it)",
    )
    oauth_scopes: str | None = Field(
        default=None,
        max_length=500,
        description="OAuth scopes to request (space-separated, e.g. 'repo project read:org')",
    )

    # Domain description for query routing
    domain_description: str | None = Field(
        default=None,
        max_length=500,
        description="Describe what this server does so the assistant knows when to use it",
    )

    # Configuration
    timeout_seconds: int = Field(
        default=MCP_DEFAULT_TIMEOUT_SECONDS,
        ge=5,
        le=120,
        description="Timeout for tool calls on this server (seconds)",
    )
    hitl_required: bool | None = Field(
        default=None,
        description="Per-server HITL override. None = inherit global MCP_HITL_REQUIRED",
    )
    iterative_mode: bool = Field(
        default=False,
        description=(
            "Enable ReAct iterative mode. When true, the assistant interacts with "
            "this server's tools iteratively (multiple calls per request) for better "
            "results on complex tasks. Incurs additional LLM costs."
        ),
    )

    @model_validator(mode="after")
    def validate_credentials_match_auth_type(self) -> UserMCPServerCreate:
        """Validate that provided credentials match the declared auth_type."""
        if self.auth_type == UserMCPAuthType.API_KEY:
            if not self.api_key:
                raise ValueError("api_key is required when auth_type is 'api_key'")
        elif self.auth_type == UserMCPAuthType.BEARER:
            if not self.bearer_token:
                raise ValueError("bearer_token is required when auth_type is 'bearer'")
        elif self.auth_type == UserMCPAuthType.OAUTH2:
            if self.api_key or self.bearer_token:
                raise ValueError(
                    "api_key/bearer_token should not be provided when auth_type is 'oauth2'"
                )
        elif self.auth_type == UserMCPAuthType.NONE:
            if self.api_key or self.bearer_token:
                raise ValueError("Credentials should not be provided when auth_type is 'none'")
        return self


class UserMCPServerUpdate(BaseModel):
    """Schema for updating a user MCP server (all fields optional)."""

    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="User-facing server name",
    )
    url: str | None = Field(
        default=None,
        min_length=1,
        max_length=2048,
        description="Streamable HTTP endpoint URL",
    )

    @field_validator("url")
    @classmethod
    def validate_url_scheme(cls, v: str | None) -> str | None:
        """MCP servers must use HTTPS for transport security."""
        if v is not None and not v.startswith("https://"):
            raise ValueError("MCP server URL must use HTTPS")
        return v

    auth_type: UserMCPAuthType | None = Field(
        default=None,
        description="Authentication type",
    )
    api_key: str | None = Field(
        default=None,
        min_length=1,
        description="API key value (for auth_type=api_key)",
    )
    header_name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="Header name for API key",
    )
    bearer_token: str | None = Field(
        default=None,
        min_length=1,
        description="Bearer token value (for auth_type=bearer)",
    )
    oauth_client_id: str | None = Field(
        default=None,
        description="Pre-registered OAuth client_id",
    )
    oauth_client_secret: str | None = Field(
        default=None,
        description="Pre-registered OAuth client_secret",
    )
    oauth_scopes: str | None = Field(
        default=None,
        max_length=500,
        description="OAuth scopes to request (space-separated, e.g. 'repo project read:org')",
    )
    domain_description: str | None = Field(
        default=None,
        max_length=500,
        description="Describe what this server does so the assistant knows when to use it",
    )
    timeout_seconds: int | None = Field(
        default=None,
        ge=5,
        le=120,
        description="Timeout for tool calls (seconds)",
    )
    hitl_required: bool | None = Field(
        default=None,
        description="Per-server HITL override",
    )
    iterative_mode: bool | None = Field(
        default=None,
        description="Enable/disable ReAct iterative mode",
    )

    @model_validator(mode="after")
    def validate_credentials_match_auth_type(self) -> UserMCPServerUpdate:
        """Validate that provided credentials match the declared auth_type (if set)."""
        if self.auth_type is None:
            return self
        if self.auth_type == UserMCPAuthType.NONE:
            if self.api_key or self.bearer_token:
                raise ValueError("Credentials should not be provided when auth_type is 'none'")
        elif self.auth_type == UserMCPAuthType.OAUTH2:
            if self.api_key or self.bearer_token:
                raise ValueError(
                    "api_key/bearer_token should not be provided when auth_type is 'oauth2'"
                )
        # api_key / bearer: credentials can be None in update (keep existing)
        return self


class MCPDiscoveredToolResponse(BaseModel):
    """Schema for a single discovered MCP tool in API responses."""

    tool_name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)


class UserMCPServerResponse(BaseModel):
    """Schema for a single user MCP server response."""

    id: UUID
    name: str
    url: str
    auth_type: UserMCPAuthType
    status: UserMCPServerStatus
    is_enabled: bool
    domain_description: str | None = None
    timeout_seconds: int
    hitl_required: bool | None
    iterative_mode: bool = False
    # Non-sensitive credential metadata (extracted from encrypted blob)
    header_name: str | None = Field(
        default=None,
        description="Header name for API key auth (non-sensitive metadata)",
    )
    has_credentials: bool = Field(
        default=False,
        description="Whether encrypted credentials are stored for this server",
    )
    has_oauth_credentials: bool = Field(
        default=False,
        description="Whether OAuth client_id/client_secret are stored (for oauth2 auth type)",
    )
    oauth_scopes: str | None = Field(
        default=None,
        description="OAuth scopes configured for this server (space-separated)",
    )
    tool_count: int = 0
    tools: list[MCPDiscoveredToolResponse] = Field(default_factory=list)
    last_connected_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserMCPServerListResponse(BaseModel):
    """Schema for listing user MCP servers."""

    servers: list[UserMCPServerResponse]
    total: int


class UserMCPOAuthInitiateResponse(BaseModel):
    """Response for OAuth 2.1 authorization initiation."""

    authorization_url: str


class UserMCPTestConnectionResponse(BaseModel):
    """Response for testing an MCP server connection."""

    success: bool
    tool_count: int = 0
    tools: list[MCPDiscoveredToolResponse] = Field(default_factory=list)
    error: str | None = None
    domain_description: str | None = None


class UserMCPGenerateDescriptionResponse(BaseModel):
    """Response for force-generating a domain description."""

    domain_description: str
    tool_count: int


# ---------------------------------------------------------------------------
# Admin MCP schemas (evolution F2.5)
# ---------------------------------------------------------------------------


class AdminMCPToolInfo(BaseModel):
    """Tool info exposed by an admin MCP server (read-only)."""

    name: str
    description: str | None = None


class AdminMCPServerResponse(BaseModel):
    """Response for listing admin MCP servers with their status."""

    model_config = ConfigDict(from_attributes=True)

    server_key: str = Field(
        description="Server key from MCP_SERVERS_CONFIG (e.g., 'google_flights')"
    )
    name: str = Field(description="Human-readable display name")
    description: str | None = Field(default=None, description="Domain description for routing")
    tools_count: int = Field(description="Number of discovered tools")
    tools: list[AdminMCPToolInfo] = Field(default_factory=list, description="Discovered tools")
    enabled_for_user: bool = Field(description="True if not in user's admin_mcp_disabled_servers")


class AdminMCPToggleResponse(BaseModel):
    """Response for toggling an admin MCP server for the current user."""

    server_key: str
    enabled_for_user: bool


# ---------------------------------------------------------------------------
# MCP Apps proxy schemas (evolution F2.5 — interactive widgets)
# ---------------------------------------------------------------------------


class McpAppCallToolRequest(BaseModel):
    """Request for proxying a tool call from an MCP App iframe."""

    tool_name: str = Field(..., min_length=1, max_length=200)
    arguments: dict[str, Any] = Field(default_factory=dict)


class McpAppCallToolResponse(BaseModel):
    """Response for a proxied MCP App tool call."""

    success: bool
    result: str | None = None
    error: str | None = None


class McpAppReadResourceRequest(BaseModel):
    """Request for proxying a resource read from an MCP App iframe."""

    uri: str = Field(..., min_length=1, max_length=2048)


class McpAppReadResourceResponse(BaseModel):
    """Response for a proxied MCP App resource read."""

    success: bool
    content: str | None = None
    mime_type: str | None = None
    error: str | None = None
