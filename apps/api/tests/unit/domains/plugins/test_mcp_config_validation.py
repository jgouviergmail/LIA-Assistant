"""Unit tests for Agent Plugins mcp.json validation (ADR-225).

Covers the normative requirements of the Agent Plugins specification v1.0.0
section 7.2 (MCP servers) and the LIA client policy layer:

- closed top-level schema (``$schema`` + ``mcpServers``, nothing else) —
  a violation disables MCP for the plugin but never the other components;
- closed server variants (stdio / streamable-http / sse) — an unknown field,
  an unknown ``type`` or a field from another variant invalidates the entry;
- URL semantics beyond the JSON schema (absolute http(s), no userinfo, no
  fragment, HTTPS unless loopback) and header field validity including the
  case-insensitive duplicate rule;
- reserved ``env`` names (§9.2) and ``cwd`` forms (§7.2.1) for stdio;
- the LIA policy layer: stdio and sse are valid-but-unsupported transports,
  spec-valid ``http://localhost`` URLs are refused by the HTTPS-only policy.

The nominal fixture is the specification's own mcp.json example (§7.2.1).
"""

from typing import Any

import pytest

from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.domains.plugins.mcp_config import validate_mcp_config
from src.domains.plugins.schemas import McpServerStatus, PluginIssueCode


def _config(servers: dict[str, Any]) -> dict[str, Any]:
    """Build an mcp.json document around the given mcpServers object."""
    return {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID, "mcpServers": servers}


def _http_server(**overrides: Any) -> dict[str, Any]:
    server: dict[str, Any] = {
        "type": "streamable-http",
        "url": "https://deploy.example.com/mcp",
    }
    server.update(overrides)
    return server


class TestSpecExample:
    def test_spec_example_classifies_every_transport(self) -> None:
        """The spec's own §7.2.1 example: stdio + streamable-http + sse."""
        result = validate_mcp_config(
            _config(
                {
                    "local-validator": {
                        "type": "stdio",
                        "command": "./bin/validator",
                        "args": ["--data", "${PLUGIN_DATA}/validator"],
                        "env": {"CONFIG": "${PLUGIN_ROOT}/config.json"},
                        "cwd": "${PLUGIN_ROOT}",
                    },
                    "deployment-api": _http_server(headers={"X-Tenant": "public-tenant"}),
                    "legacy-events": {"type": "sse", "url": "https://legacy.example.com/sse"},
                }
            )
        )

        assert result.valid is True
        by_key = {s.key: s for s in result.servers}
        assert by_key["local-validator"].status is McpServerStatus.UNSUPPORTED_TRANSPORT
        assert by_key["deployment-api"].status is McpServerStatus.SUPPORTED
        assert by_key["deployment-api"].url == "https://deploy.example.com/mcp"
        assert by_key["deployment-api"].headers == {"X-Tenant": "public-tenant"}
        assert by_key["legacy-events"].status is McpServerStatus.UNSUPPORTED_TRANSPORT

    def test_empty_mcp_servers_object_is_valid(self) -> None:
        result = validate_mcp_config(_config({}))

        assert result.valid is True
        assert result.servers == []


class TestConfigLevelValidity:
    """§7.2.2 rule 2: a top-level violation disables MCP for the plugin."""

    @pytest.mark.parametrize(
        "document",
        [
            "not an object",
            ["list"],
            None,
            {"mcpServers": {}},  # missing $schema
            {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID},  # missing mcpServers
            {
                "$schema": "https://agent-plugins.org/schemas/9.9.9/mcp.schema.json",
                "mcpServers": {},
            },
            {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID, "mcpServers": "flat"},
            {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID, "mcpServers": {}, "extra": True},
        ],
    )
    def test_top_level_violation_disables_mcp(self, document: Any) -> None:
        result = validate_mcp_config(document)

        assert result.valid is False
        assert result.servers == []
        assert result.issues, "a disabled config must carry at least one issue"


class TestServerEntryValidity:
    """§7.2.2 rule 3: an invalid entry is skipped, others keep loading."""

    @pytest.mark.parametrize(
        "entry",
        [
            "flat",
            {},  # no type
            {"type": "websocket", "url": "https://x.example"},  # unknown type
            {"type": "streamable-http"},  # missing url
            {"type": "stdio"},  # missing command
            {"type": "stdio", "command": "./x", "url": "https://x.example"},  # cross-variant
            {"type": "streamable-http", "url": "https://x.example", "command": "./x"},
            {"type": "streamable-http", "url": "https://x.example", "unknown": 1},
            {"type": "stdio", "command": ""},  # empty command token
        ],
    )
    def test_invalid_entry_is_reported_and_skipped(self, entry: Any) -> None:
        result = validate_mcp_config(_config({"bad": entry, "good": _http_server()}))

        assert result.valid is True
        by_key = {s.key: s for s in result.servers}
        assert by_key["bad"].status is McpServerStatus.INVALID
        assert by_key["bad"].issues, "an invalid entry must carry its reasons"
        assert by_key["good"].status is McpServerStatus.SUPPORTED

    def test_invalid_entry_issue_uses_the_taxonomy(self) -> None:
        result = validate_mcp_config(_config({"bad": {"type": "websocket"}}))

        [server] = result.servers
        assert [i.code for i in server.issues] == [PluginIssueCode.SERVER_ENTRY_INVALID]


class TestRemoteUrlSemantics:
    """§7.2.1 URL rules live in the spec text, deliberately beyond the schema."""

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com/mcp",  # not http(s)
            "/relative/path",  # not absolute
            "https://user:pass@example.com/mcp",  # userinfo
            "https://example.com/mcp#frag",  # fragment
            "http://example.com/mcp",  # http on a non-loopback host
            "https://",  # no host
        ],
    )
    def test_spec_invalid_url_invalidates_the_entry(self, url: str) -> None:
        result = validate_mcp_config(_config({"srv": _http_server(url=url)}))

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID, url

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:3000/mcp",
            "http://127.0.0.1/mcp",
            "http://[::1]:8080/mcp",
        ],
    )
    def test_spec_valid_loopback_http_is_refused_by_lia_policy(self, url: str) -> None:
        # Valid per the spec (§7.2.1), refused by LIA's HTTPS-only policy
        # (ADR-225 documented deviation) — a DISTINCT status so the import
        # report can say "refused by policy", never "invalid plugin".
        result = validate_mcp_config(_config({"srv": _http_server(url=url)}))

        [server] = result.servers
        assert server.status is McpServerStatus.REFUSED_POLICY, url
        assert [i.code for i in server.issues] == [PluginIssueCode.SERVER_URL_POLICY_HTTPS]

    def test_sse_with_spec_invalid_url_is_invalid_not_unsupported(self) -> None:
        # Entry validity is judged before transport support: a broken sse
        # entry reports as invalid, not as a merely unsupported transport.
        result = validate_mcp_config(
            _config({"srv": {"type": "sse", "url": "http://example.com/sse"}})
        )

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID


class TestHeaderRules:
    def test_duplicate_header_names_under_different_casing_invalidate(self) -> None:
        result = validate_mcp_config(
            _config({"srv": _http_server(headers={"X-Tenant": "a", "x-tenant": "b"})})
        )

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID

    @pytest.mark.parametrize("name", ["bad name", "bad:name", "", "bad\nname"])
    def test_invalid_header_name_invalidates(self, name: str) -> None:
        result = validate_mcp_config(_config({"srv": _http_server(headers={name: "v"})}))

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID

    def test_header_value_with_crlf_invalidates(self) -> None:
        result = validate_mcp_config(
            _config({"srv": _http_server(headers={"X-Ok": "bad\r\nInjected: 1"})})
        )

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID

    def test_non_string_header_value_invalidates(self) -> None:
        result = validate_mcp_config(_config({"srv": _http_server(headers={"X-N": 42})}))

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID


class TestStdioEntryValidity:
    """stdio entries are never launched by LIA but §7.2.2 requires telling a
    VALID entry (skipped: unsupported transport) from an INVALID one."""

    @pytest.mark.parametrize(
        "overrides",
        [
            {"env": {"PLUGIN_ROOT": "/x"}},  # §9.2 reserved name
            {"env": {"PLUGIN_DATA": "/x"}},
            {"cwd": "data"},  # §7.2.1: not a permitted cwd form
            {"cwd": "../out"},
            {"cwd": "${HOME}/x"},
            {"command": "../bin/server"},  # escapes the plugin root (§4.1)
            {"command": "bin/server"},  # neither bare nor ./-prefixed
            {"command": "."},  # a directory reference, not an executable token
            {"command": ".."},
            {"args": "not-a-list"},
            {"env": {"OK": 42}},
        ],
    )
    def test_invalid_stdio_entry_is_invalid_not_unsupported(
        self, overrides: dict[str, Any]
    ) -> None:
        entry: dict[str, Any] = {"type": "stdio", "command": "./bin/server"}
        entry.update(overrides)
        result = validate_mcp_config(_config({"srv": entry}))

        [server] = result.servers
        assert server.status is McpServerStatus.INVALID, overrides

    @pytest.mark.parametrize(
        "overrides",
        [
            {},
            {"command": "npx"},  # bare name: platform search
            {"command": ".hidden"},  # unusual but a legitimate bare name
            {"cwd": "./data"},
            {"cwd": "${PLUGIN_ROOT}"},
            {"cwd": "${PLUGIN_ROOT}/sub"},
            {"cwd": "${PLUGIN_DATA}"},
            {"cwd": "${PLUGIN_DATA}/cache"},
            {"args": ["--flag", "${PLUGIN_DATA}/x"], "env": {"A": "1"}},
        ],
    )
    def test_valid_stdio_entry_reports_unsupported_transport(
        self, overrides: dict[str, Any]
    ) -> None:
        entry: dict[str, Any] = {"type": "stdio", "command": "./bin/server"}
        entry.update(overrides)
        result = validate_mcp_config(_config({"srv": entry}))

        [server] = result.servers
        assert server.status is McpServerStatus.UNSUPPORTED_TRANSPORT, overrides
        assert [i.code for i in server.issues] == [PluginIssueCode.SERVER_TRANSPORT_UNSUPPORTED]
