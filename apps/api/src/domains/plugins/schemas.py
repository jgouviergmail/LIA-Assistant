"""Pydantic schemas for the Agent Plugins domain (ADR-225).

Models the Agent Plugins specification v1.0.0 documents (``plugin.json``,
``mcp.json``) and the structured validation results the import pipeline and
the API report to the user.

Design notes:

- Rejection reasons are a closed taxonomy (:class:`PluginIssueCode`), never
  free-form strings — the API layer maps codes to i18n messages (same
  doctrine as ``ToolErrorCode``).
- Server variants are a closed discriminated union with ``extra="forbid"``,
  mirroring the official ``mcp.schema.json`` ``oneOf``; semantic rules the
  JSON schema deliberately leaves to the spec text (URL semantics, header
  validity, cwd forms, reserved env names) live in ``mcp_config.py``.
"""

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PluginIssueCode(str, Enum):
    """Closed taxonomy of plugin validation/import issue reasons."""

    # plugin.json — fatal (§5.2/§5.3/§5.5)
    MANIFEST_NOT_AN_OBJECT = "manifest_not_an_object"
    MANIFEST_SCHEMA_UNSUPPORTED = "manifest_schema_unsupported"
    MANIFEST_NAME_INVALID = "manifest_name_invalid"
    MANIFEST_FIELD_INVALID = "manifest_field_invalid"
    # plugin.json — non-fatal, report and ignore (§5.2/§8.1)
    MANIFEST_UNKNOWN_FIELD = "manifest_unknown_field"
    MANIFEST_EXTENSIONS_NOT_OBJECT = "manifest_extensions_not_object"
    # mcp.json — config-level (§7.2.2 rule 2: MCP disabled for the plugin)
    MCP_CONFIG_INVALID = "mcp_config_invalid"
    MCP_SCHEMA_UNSUPPORTED = "mcp_schema_unsupported"
    # mcp.json — server-level (§7.2.2 rules 3-4 + LIA policy)
    SERVER_ENTRY_INVALID = "server_entry_invalid"
    SERVER_TRANSPORT_UNSUPPORTED = "server_transport_unsupported"
    SERVER_URL_POLICY_HTTPS = "server_url_policy_https"
    # import pipeline — per-component outcomes (§6.2/§7.1 + LIA quotas)
    COMPONENT_LOCATION_INVALID = "component_location_invalid"
    SKILL_INVALID = "skill_invalid"
    SKILL_NAME_CONFLICT = "skill_name_conflict"
    SERVER_NAME_CONFLICT = "server_name_conflict"
    SERVER_CREATE_FAILED = "server_create_failed"


class PluginIssue(BaseModel):
    """One reported validation issue, machine-readable first."""

    model_config = ConfigDict(frozen=True)

    code: PluginIssueCode = Field(description="Taxonomy code for this issue")
    field: str | None = Field(default=None, description="Offending field or member name")
    detail: str | None = Field(
        default=None,
        description="Technical detail for logs/debug (English, never shown raw to users)",
    )


class PluginAuthor(BaseModel):
    """§5.4 author object — only name, email and url, all strings."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, description="Author display name")
    email: str | None = Field(default=None, description="Author contact email")
    url: str | None = Field(default=None, description="Author URL")


class PluginManifest(BaseModel):
    """A validated ``plugin.json`` manifest (§5), unknown fields stripped."""

    model_config = ConfigDict(populate_by_name=True)

    schema_id: str = Field(alias="$schema", description="Canonical manifest schema identifier")
    name: str = Field(description="Plugin name (§5.5 constraints)")
    version: str | None = Field(default=None, description="Plugin version (SemVer recommended)")
    description: str | None = Field(default=None, description="Short plugin description")
    author: PluginAuthor | None = Field(default=None, description="Author object")
    homepage: str | None = Field(default=None, description="Documentation or homepage URL")
    repository: str | None = Field(default=None, description="Source repository URL")
    license: str | None = Field(default=None, description="License identifier")
    keywords: list[str] = Field(default_factory=list, description="Search and discovery tags")
    extensions: dict[str, dict] = Field(
        default_factory=dict,
        description="Client-specific data keyed by reverse-domain namespace (§8.1)",
    )


class ManifestValidationResult(BaseModel):
    """Outcome of validating a ``plugin.json`` document."""

    valid: bool = Field(description="False = the plugin MUST be rejected entirely (§5.2)")
    manifest: PluginManifest | None = Field(default=None, description="Parsed manifest when valid")
    errors: list[PluginIssue] = Field(default_factory=list, description="Fatal violations")
    warnings: list[PluginIssue] = Field(
        default_factory=list, description="Reported-and-ignored issues (§5.2/§8.1)"
    )


class StdioServerConfig(BaseModel):
    """§7.2.1 stdio variant — closed schema."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["stdio"] = Field(description="MCP stdio transport")
    command: str = Field(min_length=1, description="Single executable token")
    args: list[str] = Field(default_factory=list, description="Arguments for the executable")
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables for the process"
    )
    cwd: str | None = Field(default=None, description="Working directory for the process")


class StreamableHttpServerConfig(BaseModel):
    """§7.2.1 streamable-http variant — closed schema."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["streamable-http"] = Field(description="MCP Streamable HTTP transport")
    url: str = Field(min_length=1, description="MCP endpoint URL")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Fixed HTTP headers (§7.2.1, never secrets)"
    )


class SseServerConfig(BaseModel):
    """§7.2.1 legacy HTTP+SSE variant — closed schema."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["sse"] = Field(description="Deprecated MCP HTTP+SSE transport")
    url: str = Field(min_length=1, description="MCP endpoint URL")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Fixed HTTP headers (§7.2.1, never secrets)"
    )


McpServerConfig = Annotated[
    StdioServerConfig | StreamableHttpServerConfig | SseServerConfig,
    Field(discriminator="type"),
]


class McpServerStatus(str, Enum):
    """Classification of one ``mcpServers`` entry after validation."""

    SUPPORTED = "supported"
    UNSUPPORTED_TRANSPORT = "unsupported_transport"
    REFUSED_POLICY = "refused_policy"
    INVALID = "invalid"


class McpServerValidation(BaseModel):
    """Validation outcome for one server entry (feeds the import report)."""

    key: str = Field(description="Member name identifying the server in mcpServers")
    status: McpServerStatus = Field(description="Entry classification (§7.2.2)")
    transport: str | None = Field(
        default=None, description="Declared transport type when parseable"
    )
    url: str | None = Field(default=None, description="Endpoint URL for supported entries")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Fixed headers for supported entries"
    )
    issues: list[PluginIssue] = Field(
        default_factory=list, description="Reasons when not supported"
    )


class McpConfigValidationResult(BaseModel):
    """Outcome of validating an ``mcp.json`` document."""

    valid: bool = Field(
        description="False = MCP disabled for this plugin, other components keep loading"
    )
    issues: list[PluginIssue] = Field(
        default_factory=list, description="Config-level issues when invalid"
    )
    servers: list[McpServerValidation] = Field(
        default_factory=list, description="Per-server outcomes when the config is valid"
    )


class PluginComponentKind(str, Enum):
    """Component types standardized by Agent Plugins v1 (§7)."""

    SKILL = "skill"
    MCP_SERVER = "mcp_server"


class PluginComponentStatus(str, Enum):
    """Outcome of one component during a plugin install/update."""

    INSTALLED = "installed"
    UPDATED = "updated"
    SKIPPED = "skipped"
    REMOVED = "removed"


class PluginComponentReport(BaseModel):
    """One component's outcome in the import report (never silent — ADR-225)."""

    kind: PluginComponentKind = Field(description="Component type")
    key: str = Field(description="Skill name or mcp.json server key")
    status: PluginComponentStatus = Field(description="What happened to this component")
    issues: list[PluginIssue] = Field(default_factory=list, description="Reasons when skipped")


class PluginImportReport(BaseModel):
    """Full outcome of a plugin install or update (the SHOULD-report of §11.3)."""

    plugin_id: str = Field(description="Installed plugin row id")
    name: str = Field(description="Plugin name from the manifest")
    version: str | None = Field(default=None, description="Manifest version")
    description: str | None = Field(default=None, description="Manifest description")
    updated: bool = Field(
        default=False, description="True when an existing installation was replaced"
    )
    components: list[PluginComponentReport] = Field(
        default_factory=list, description="Per-component outcomes"
    )
    warnings: list[PluginIssue] = Field(
        default_factory=list,
        description="Manifest warnings and MCP config-level issues (§5.2/§7.2.2)",
    )


class PluginResponse(BaseModel):
    """One installed plugin in API responses (settings section)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Installed plugin row id")
    name: str = Field(description="Plugin name")
    version: str | None = Field(default=None, description="Manifest version")
    description: str | None = Field(default=None, description="Manifest description")
    spec_version: str = Field(description="Agent Plugins spec version targeted")
    skill_names: list[str] = Field(
        default_factory=list, description="Skills installed by this plugin"
    )
    server_names: list[str] = Field(
        default_factory=list, description="MCP servers installed by this plugin"
    )
    created_at: datetime | None = Field(default=None, description="Install timestamp")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp")


class PluginListResponse(BaseModel):
    """Installed plugins listing."""

    plugins: list[PluginResponse] = Field(default_factory=list)
    total: int = Field(default=0, description="Number of installed plugins")
