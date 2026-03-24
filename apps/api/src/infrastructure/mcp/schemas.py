"""
MCP Schema Definitions.

Data models for MCP server configuration, tool discovery, and health status.

Phase: evolution F2 — MCP Support
Created: 2026-02-28
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class MCPTransportType(str, Enum):
    """MCP transport protocol type."""

    STDIO = "stdio"
    STREAMABLE_HTTP = "streamable_http"


class MCPServerConfig(BaseModel):
    """
    Configuration for a single MCP server.

    Supports two transport types:
    - stdio: Local process communication (command + args)
    - streamable_http: Remote HTTP endpoint (url + optional headers)
    """

    transport: MCPTransportType
    command: str | None = Field(
        default=None,
        description="Stdio transport: executable command (e.g., 'npx', 'python', 'node')",
    )
    args: list[str] = Field(
        default_factory=list,
        description="Stdio transport: command arguments",
    )
    env: dict[str, str] | None = Field(
        default=None,
        repr=False,  # May contain secrets
        description="Stdio transport: environment variables for the process",
    )
    url: str | None = Field(
        default=None,
        description="Streamable HTTP transport: endpoint URL",
    )
    headers: dict[str, str] | None = Field(
        default=None,
        repr=False,  # May contain API keys
        description="Streamable HTTP transport: request headers",
    )
    timeout_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="Timeout for tool calls on this server (seconds)",
    )
    enabled: bool = Field(
        default=True,
        description="Whether this server is enabled",
    )
    hitl_required: bool | None = Field(
        default=None,
        description="Per-server HITL override. None = inherit global MCP_HITL_REQUIRED",
    )
    description: str | None = Field(
        default=None,
        description=(
            "Domain description for query routing. Helps the LLM select this server "
            "when analyzing user queries. Similar to domain_description on user MCP servers."
        ),
    )
    internal: bool = Field(
        default=False,
        description=(
            "Mark as internal Docker service. When true, skips SSRF validation "
            "(allows HTTP and private IPs). Only use for trusted admin-configured services."
        ),
    )
    iterative_mode: bool = Field(
        default=False,
        description=(
            "When true, the planner delegates to a ReAct sub-agent instead of "
            "generating tool parameters directly. The ReAct agent calls read_me "
            "first, then executes tools iteratively. Use for MCP servers that "
            "require multi-step interactions (e.g., Excalidraw: read format "
            "reference, then create diagram with correct elements)."
        ),
    )

    @model_validator(mode="after")
    def validate_transport_fields(self) -> MCPServerConfig:
        """Validate required fields based on transport type."""
        if self.transport == MCPTransportType.STDIO:
            if not self.command:
                raise ValueError(
                    "Stdio transport requires 'command' field " "(e.g., 'npx', 'python', 'node')"
                )
        elif self.transport == MCPTransportType.STREAMABLE_HTTP:
            if not self.url:
                raise ValueError(
                    "Streamable HTTP transport requires 'url' field "
                    "(e.g., 'https://mcp-server.example.com/mcp')"
                )
        return self


class MCPDiscoveredTool(BaseModel):
    """A tool discovered from an MCP server via list_tools()."""

    server_name: str = Field(description="Name of the MCP server that exposes this tool")
    tool_name: str = Field(description="Tool name as reported by the MCP server")
    description: str = Field(description="Tool description for LLM context")
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema for tool input parameters",
    )
    app_resource_uri: str | None = Field(
        default=None,
        description="MCP Apps UI resource URI (ui://...) from Tool.meta.ui.resourceUri",
    )
    app_visibility: list[str] | None = Field(
        default=None,
        description=(
            "MCP Apps visibility list from Tool.meta.ui.visibility. "
            "None or ['assistant','app'] = LLM + iframe. ['app'] = iframe-only."
        ),
    )

    @field_validator("app_visibility")
    @classmethod
    def validate_app_visibility(cls, v: list[str] | None) -> list[str] | None:
        """Validate that visibility values are within allowed set."""
        if v is not None:
            allowed = {"app", "assistant"}
            invalid = set(v) - allowed
            if invalid:
                raise ValueError(
                    f"Invalid visibility values {invalid}, must be subset of {allowed}"
                )
        return v


class MCPServerStatus(BaseModel):
    """Health status of an MCP server connection."""

    server_name: str
    connected: bool
    tool_count: int = 0
    last_health_check: str | None = None
    error: str | None = None
