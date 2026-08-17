"""Agent Plugins MCP configuration (``mcp.json``) validation (§7.2, ADR-225).

The shape of each server entry is validated by the closed discriminated union
in ``schemas.py`` (mirror of the official ``mcp.schema.json`` ``oneOf``); this
module adds the semantic rules the JSON schema deliberately leaves to the
specification text:

- URL semantics (§7.2.1): absolute http(s), no userinfo, no fragment, HTTPS
  unless the host is exactly ``localhost`` or a loopback IP literal;
- header field validity, including the case-insensitive duplicate rule;
- stdio ``command`` token form and ``cwd`` forms, reserved ``env`` names
  (§9.2) — LIA never launches stdio servers, but §7.2.2 requires telling a
  valid entry (skipped: unsupported transport) from an invalid one;
- the LIA policy layer (ADR-225 documented deviation): spec-valid
  ``http://localhost`` endpoints are refused server-side (SSRF), with a
  status distinct from invalidity so reports never blame the plugin.
"""

import ipaddress
import re
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlsplit

from pydantic import TypeAdapter, ValidationError

from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.domains.plugins.schemas import (
    McpConfigValidationResult,
    McpServerConfig,
    McpServerStatus,
    McpServerValidation,
    PluginIssue,
    PluginIssueCode,
    SseServerConfig,
    StdioServerConfig,
    StreamableHttpServerConfig,
)

_ALLOWED_TOP_LEVEL_FIELDS = frozenset({"$schema", "mcpServers"})
# RFC 7230 token (header field name) and field value (no CR/LF, no other CTLs).
_HEADER_NAME_RE = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_HEADER_VALUE_RE = re.compile(r"^[\t \x21-\x7e\x80-\xff]*$")
_CWD_PLACEHOLDER_PREFIXES = ("${PLUGIN_ROOT}", "${PLUGIN_DATA}")
_RESERVED_ENV_NAMES = frozenset({"PLUGIN_ROOT", "PLUGIN_DATA"})

_SERVER_ADAPTER: TypeAdapter[McpServerConfig] = TypeAdapter(McpServerConfig)


def _entry_invalid(key: str, transport: str | None, detail: str) -> McpServerValidation:
    """Build an INVALID server outcome with a single taxonomy issue."""
    return McpServerValidation(
        key=key,
        status=McpServerStatus.INVALID,
        transport=transport,
        issues=[PluginIssue(code=PluginIssueCode.SERVER_ENTRY_INVALID, field=key, detail=detail)],
    )


def _is_contained_relative(value: str) -> bool:
    """Check a ``./``-style plugin-relative path for static containment (§4.1).

    LIA never launches plugin subprocesses, so filesystem resolution never
    happens; the static approximation rejects absolute paths, backslash
    separators and any ``..`` segment.
    """
    if "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _validate_stdio_command(command: str) -> str | None:
    """§7.2.1: command is a single executable token — bare name or ./-relative."""
    if command.startswith("./"):
        if not _is_contained_relative(command):
            return f"command escapes the plugin root: {command!r}"
    elif "/" in command or "\\" in command or command in (".", ".."):
        # Path separators make it neither a bare name nor ./-prefixed; bare
        # "." / ".." are directory references, not executable tokens. Other
        # dot-prefixed values (".hidden") stay valid bare names.
        return f"command must be a bare name or start with './': {command!r}"
    return None


def _validate_stdio_cwd(cwd: str) -> str | None:
    """§7.2.1: cwd must be ./-relative, ${PLUGIN_ROOT}- or ${PLUGIN_DATA}-rooted."""
    if cwd.startswith("./"):
        return None if _is_contained_relative(cwd) else f"cwd escapes the plugin root: {cwd!r}"
    if cwd in _CWD_PLACEHOLDER_PREFIXES:
        return None
    if cwd.startswith(tuple(p + "/" for p in _CWD_PLACEHOLDER_PREFIXES)):
        suffix = cwd.split("/", 1)[1]
        if not _is_contained_relative(suffix):
            return f"cwd escapes its placeholder root: {cwd!r}"
        return None
    return f"cwd form not permitted by the specification: {cwd!r}"


def _validate_stdio_semantics(config: StdioServerConfig) -> str | None:
    """Return the first semantic violation of a stdio entry, if any."""
    violation = _validate_stdio_command(config.command)
    if violation:
        return violation

    # §9.2: reserved environment variable names are client-supplied.
    reserved = _RESERVED_ENV_NAMES & set(config.env)
    if reserved:
        return f"env must not define reserved names: {', '.join(sorted(reserved))}"

    if config.cwd is not None:
        return _validate_stdio_cwd(config.cwd)
    return None


def _is_loopback_host(hostname: str) -> bool:
    """§7.2.1: exactly ``localhost`` or an IP literal in a loopback range."""
    if hostname == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def _validate_remote_url(url: str) -> tuple[str | None, bool]:
    """Validate a remote endpoint URL against §7.2.1.

    Returns:
        Tuple of (violation detail or None, is_loopback_http). The second
        member is only meaningful when the URL is spec-valid: True marks the
        HTTP-on-loopback case the spec allows but LIA policy refuses.
    """
    if "#" in url:
        return f"url must not contain a fragment: {url!r}", False
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        username, password = parts.username, parts.password
    except ValueError as exc:
        return f"unparseable url: {exc}", False
    if parts.scheme not in ("http", "https"):
        return f"url must be absolute http(s): {url!r}", False
    if not hostname:
        return f"url has no host: {url!r}", False
    if username is not None or password is not None:
        return f"url must not contain user information: {url!r}", False
    if parts.scheme == "http" and not _is_loopback_host(hostname):
        return f"non-loopback endpoints must use https: {url!r}", False
    return None, parts.scheme == "http"


def _validate_headers(headers: dict[str, str]) -> str | None:
    """Return the first header-field violation, if any (§7.2.1)."""
    seen_lower: set[str] = set()
    for name, value in headers.items():
        if not _HEADER_NAME_RE.match(name):
            return f"invalid header name: {name!r}"
        if not _HEADER_VALUE_RE.match(value):
            return f"invalid header value for {name!r}"
        lowered = name.lower()
        if lowered in seen_lower:
            return f"duplicate header name under different casing: {name!r}"
        seen_lower.add(lowered)
    return None


def _validate_server(key: str, entry: Any) -> McpServerValidation:
    """Classify one ``mcpServers`` entry per §7.2.2 + the LIA policy layer."""
    declared = entry.get("type") if isinstance(entry, dict) else None
    transport = declared if isinstance(declared, str) else None

    try:
        config = _SERVER_ADAPTER.validate_python(entry)
    except ValidationError as exc:
        summary = "; ".join(
            f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in exc.errors()[:3]
        )
        return _entry_invalid(key, transport, summary)

    if isinstance(config, StdioServerConfig):
        violation = _validate_stdio_semantics(config)
        if violation:
            return _entry_invalid(key, transport, violation)
        return McpServerValidation(
            key=key,
            status=McpServerStatus.UNSUPPORTED_TRANSPORT,
            transport=config.type,
            issues=[
                PluginIssue(
                    code=PluginIssueCode.SERVER_TRANSPORT_UNSUPPORTED,
                    field=key,
                    detail="stdio servers are not launched by LIA (multi-user server)",
                )
            ],
        )

    # Remote variants share URL + header semantics; validity is judged before
    # transport support so a broken sse entry reports as invalid, not as a
    # merely unsupported transport.
    assert isinstance(config, StreamableHttpServerConfig | SseServerConfig)
    violation, is_loopback_http = _validate_remote_url(config.url)
    if violation is None:
        violation = _validate_headers(config.headers)
    if violation:
        return _entry_invalid(key, transport, violation)

    if isinstance(config, SseServerConfig):
        return McpServerValidation(
            key=key,
            status=McpServerStatus.UNSUPPORTED_TRANSPORT,
            transport=config.type,
            issues=[
                PluginIssue(
                    code=PluginIssueCode.SERVER_TRANSPORT_UNSUPPORTED,
                    field=key,
                    detail="legacy HTTP+SSE transport is not supported (optional per spec)",
                )
            ],
        )

    if is_loopback_http:
        return McpServerValidation(
            key=key,
            status=McpServerStatus.REFUSED_POLICY,
            transport=config.type,
            issues=[
                PluginIssue(
                    code=PluginIssueCode.SERVER_URL_POLICY_HTTPS,
                    field=key,
                    detail="spec-valid loopback HTTP endpoint refused by LIA HTTPS-only policy",
                )
            ],
        )

    return McpServerValidation(
        key=key,
        status=McpServerStatus.SUPPORTED,
        transport=config.type,
        url=config.url,
        headers=dict(config.headers),
    )


def validate_mcp_config(raw: Any) -> McpConfigValidationResult:
    """Validate a parsed ``mcp.json`` document against the v1.0.0 contract.

    Args:
        raw: The JSON-decoded document (any JSON value).

    Returns:
        A :class:`McpConfigValidationResult`; ``valid=False`` disables MCP for
        the plugin while other component types keep loading (§7.2.2 rule 2).
    """
    issues: list[PluginIssue] = []

    if not isinstance(raw, dict):
        return McpConfigValidationResult(
            valid=False,
            issues=[
                PluginIssue(
                    code=PluginIssueCode.MCP_CONFIG_INVALID,
                    detail="mcp.json must contain a JSON object",
                )
            ],
        )

    # §7.2.1: closed top level — $schema + mcpServers, nothing else.
    for field in sorted(set(raw) - _ALLOWED_TOP_LEVEL_FIELDS):
        issues.append(
            PluginIssue(
                code=PluginIssueCode.MCP_CONFIG_INVALID,
                field=field,
                detail="mcp.json allows no top-level field beyond $schema and mcpServers",
            )
        )

    schema_id = raw.get("$schema")
    if schema_id != AGENT_PLUGINS_MCP_SCHEMA_ID:
        issues.append(
            PluginIssue(
                code=PluginIssueCode.MCP_SCHEMA_UNSUPPORTED,
                field="$schema",
                detail=f"expected {AGENT_PLUGINS_MCP_SCHEMA_ID}, got {schema_id!r}",
            )
        )

    servers_raw = raw.get("mcpServers")
    if not isinstance(servers_raw, dict):
        issues.append(
            PluginIssue(
                code=PluginIssueCode.MCP_CONFIG_INVALID,
                field="mcpServers",
                detail="mcpServers must be an object of server configurations",
            )
        )

    if issues:
        return McpConfigValidationResult(valid=False, issues=issues)

    assert isinstance(servers_raw, dict)
    servers = [_validate_server(key, entry) for key, entry in servers_raw.items()]
    return McpConfigValidationResult(valid=True, servers=servers)
