"""
User MCP Server domain models.

Stores per-user MCP server configurations with encrypted credentials.
Each user can declare their own MCP servers (streamable_http only)
with independent authentication (none, API key, Bearer, OAuth 2.1).

Phase: evolution F2.1 — MCP Per-User
Created: 2026-02-28
"""

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.constants import MCP_DEFAULT_TIMEOUT_SECONDS
from src.infrastructure.database.models import BaseModel


class UserMCPAuthType(str, Enum):
    """Authentication type for a user MCP server."""

    NONE = "none"
    API_KEY = "api_key"
    BEARER = "bearer"
    OAUTH2 = "oauth2"


class UserMCPServerStatus(str, Enum):
    """Connection/auth status of a user MCP server."""

    ACTIVE = "active"  # Connected and operational
    INACTIVE = "inactive"  # Manually disabled by user
    AUTH_REQUIRED = "auth_required"  # OAuth token expired/revoked
    ERROR = "error"  # Connection or protocol error


class UserMCPServer(BaseModel):
    """
    Per-user MCP server configuration.

    Stores server URL, authentication credentials (Fernet-encrypted),
    discovered tools cache, and connection status. Only streamable_http
    transport is allowed for security (no stdio).

    Credential formats (encrypted JSON in credentials_encrypted):
    - API_KEY:  {"header_name": "X-API-Key", "api_key": "sk-..."}
    - BEARER:   {"token": "eyJ..."}
    - OAUTH2:   {"access_token": "...", "refresh_token": "...",
                  "expires_at": "ISO8601", "token_type": "Bearer", "scope": "..."}
    """

    __tablename__ = "user_mcp_servers"

    # Foreign key to user
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Server identity
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="User-facing server name (unique per user)",
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
        doc="Streamable HTTP endpoint URL",
    )
    domain_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="User-provided domain description for query routing (shown to LLM)",
    )

    # Authentication
    auth_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserMCPAuthType.NONE.value,
        server_default="none",
        doc="Authentication type: none, api_key, bearer, oauth2",
    )
    credentials_encrypted: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Fernet-encrypted JSON credentials (NEVER exposed via API)",
    )

    # OAuth 2.1 metadata (cached discovery results)
    oauth_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Cached OAuth authorization server metadata (RFC 8414/9728)",
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserMCPServerStatus.ACTIVE.value,
        server_default="active",
        doc="Server connection status",
    )
    is_enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
        doc="User toggle for enabling/disabling this server",
    )

    # Configuration
    timeout_seconds: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=MCP_DEFAULT_TIMEOUT_SECONDS,
        server_default=str(MCP_DEFAULT_TIMEOUT_SECONDS),
        doc="Timeout for tool calls on this server (seconds)",
    )
    hitl_required: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
        doc="Per-server HITL override. None = inherit global MCP_HITL_REQUIRED",
    )

    # Tool discovery cache
    discovered_tools_cache: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Cached list_tools() result for fast startup",
    )
    tool_embeddings_cache: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        doc="Pre-computed E5 embeddings for discovered tools (computed at registration)",
    )

    # Connection tracking
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Last successful connection timestamp",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Last connection/execution error message",
    )

    # NOTE: No ORM relationship to User — user_id FK is sufficient.
    # The User object is never needed when querying MCP servers.
    # A bidirectional relationship would force importing User before
    # mapper configuration, creating fragile import-order dependencies.

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_user_mcp_server_name"),
        Index(
            "ix_user_mcp_servers_user_enabled",
            "user_id",
            postgresql_where="is_enabled = true AND status = 'active'",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<UserMCPServer(id={self.id}, name='{self.name}', "
            f"auth_type={self.auth_type}, status={self.status})>"
        )
