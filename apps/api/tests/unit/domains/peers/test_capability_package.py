"""Portable snapshots must contain static capabilities and no transferable secrets."""

import json
import stat
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile, ZipInfo

import pytest
from pydantic import ValidationError

from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    CapabilityPreviewRequest,
)
from src.domains.peers.capability_package import sanitize_package


def package(files: dict[str, bytes]) -> bytes:
    result = BytesIO()
    with ZipFile(result, "w") as archive:
        for name, content in files.items():
            info = ZipInfo(name)
            info.filename = name
            archive.writestr(info, content)
    return result.getvalue()


def test_snapshot_is_deterministic_and_omits_runtime_files() -> None:
    files = {
        "example/SKILL.md": b"---\nname: example\ndescription: Example\n---\nRead the input.",
        "example/scripts/run.py": b"pass\n",
        "example/out/private.txt": b"private",
        "example/.env": b"TOKEN=secret",
    }
    snapshot = sanitize_package(package(files), CapabilityKind.SKILL, "example")
    assert {entry.path for entry in snapshot.files} == {"SKILL.md", "scripts/run.py"}
    assert set(snapshot.omitted) == {".env", "out/private.txt"}
    assert (
        snapshot.digest
        == sanitize_package(
            package(dict(reversed(list(files.items())))),
            CapabilityKind.SKILL,
            "example",
        ).digest
    )
    assert snapshot == type(snapshot).model_validate_json(snapshot.model_dump_json())


@pytest.mark.parametrize(
    "path", ["../escape", "/absolute", "C:/escape", "x/../../escape", "x\\escape"]
)
def test_archive_paths_cannot_escape(path: str) -> None:
    with pytest.raises(ValueError):
        sanitize_package(
            package({"SKILL.md": b"hello", path: b"bad"}),
            CapabilityKind.SKILL,
            "example",
        )


def test_archive_links_and_duplicate_members_are_refused() -> None:
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        info = ZipInfo("SKILL.md")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, b"/etc/passwd")
    with pytest.raises(ValueError):
        sanitize_package(content.getvalue(), CapabilityKind.SKILL, "example")


@pytest.mark.parametrize(
    "secret",
    [
        b'api_key = "abcdef0123456789"',
        b"Authorization: Bearer abcdef0123456789",
        b"-----BEGIN PRIVATE KEY-----",
    ],
)
def test_embedded_credentials_are_refused_without_echoing_them(secret: bytes) -> None:
    with pytest.raises(ValueError) as error:
        sanitize_package(package({"SKILL.md": secret}), CapabilityKind.SKILL, "example")
    assert secret.decode() not in str(error.value)


def test_plugin_retained_mcp_file_is_rewritten_without_header_credentials() -> None:
    raw = {
        "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
        "mcpServers": {
            "remote": {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {
                    "Authorization": "Bearer abcdef0123456789",
                    "Accept": "application/json",
                },
            }
        },
    }
    snapshot = sanitize_package(
        package({"plugin.json": b'{"name":"example"}', "mcp.json": json.dumps(raw).encode()}),
        CapabilityKind.PLUGIN,
        "example",
    )
    rewritten = next(entry.content for entry in snapshot.files if entry.path == "mcp.json")
    assert b"abcdef0123456789" not in rewritten
    assert b"Authorization" not in rewritten
    assert snapshot.servers[0].config.auth_type.value == "bearer"
    assert snapshot.servers[0].key == "remote"
    assert b"application/json" in rewritten
    assert json.loads(rewritten)["$schema"] == AGENT_PLUGINS_MCP_SCHEMA_ID


@pytest.mark.parametrize(
    "url",
    ["https://user:password@example.com/mcp", "https://example.com/?api_key=secret"],
)
def test_credential_bearing_urls_are_not_portable(url: str) -> None:
    raw = {
        "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
        "mcpServers": {"remote": {"type": "streamable-http", "url": url}},
    }
    with pytest.raises(ValueError):
        sanitize_package(
            package({"plugin.json": b"{}", "mcp.json": json.dumps(raw).encode()}),
            CapabilityKind.PLUGIN,
            "example",
        )


def test_client_cannot_choose_recipient_credentials_or_execution_policy() -> None:
    request = {
        "connection_id": str(uuid4()),
        "kind": "skill",
        "source_id": str(uuid4()),
        "idempotency_key": str(uuid4()),
    }
    CapabilityPreviewRequest.model_validate(request)
    for key in ("recipient_id", "credentials", "peer_authored", "is_enabled", "path"):
        with pytest.raises(ValidationError):
            CapabilityPreviewRequest.model_validate({**request, key: "injected"})


@pytest.mark.parametrize(
    "query",
    ["api-key=secret", "APIKEY=secret", "access.token=secret", "client_secret=secret"],
)
def test_credential_query_name_variants_are_not_portable(query: str) -> None:
    from src.domains.peers.capability_contracts import PortableMCPConfig

    with pytest.raises(ValidationError):
        PortableMCPConfig(name="Example", url=f"https://example.com/mcp?{query}")


def test_authentication_header_name_cannot_inject_another_header() -> None:
    from src.domains.peers.capability_contracts import PortableMCPConfig

    with pytest.raises(ValidationError):
        PortableMCPConfig(
            name="Example",
            url="https://example.com/mcp",
            header_name="X-Key\r\nX-Other",
        )


@pytest.mark.parametrize(
    "document",
    [
        {"api_key": "abcdef0123456789"},
        {"description": 'api_key = "abcdef0123456789"'},
        {"nested": [{"client_secret": "short"}]},
    ],
)
def test_json_quoting_and_nested_fields_cannot_hide_a_credential(
    document: object,
) -> None:
    with pytest.raises(ValueError):
        sanitize_package(
            package(
                {
                    "SKILL.md": b"instructions",
                    "data.json": json.dumps(document).encode(),
                }
            ),
            CapabilityKind.SKILL,
            "example",
        )


@pytest.mark.parametrize("path", ["./SKILL.md", "scripts//run.py", "scripts/./run.py", "SKILL.MD"])
def test_noncanonical_or_case_colliding_paths_are_refused(path: str) -> None:
    with pytest.raises(ValueError):
        sanitize_package(
            package({"SKILL.md": b"hello", path: b"other"}),
            CapabilityKind.SKILL,
            "example",
        )


def test_environment_placeholders_are_preserved_but_runtime_names_are_case_insensitive() -> None:
    result = sanitize_package(
        package({"SKILL.md": b'api_key = "${MY_API_KEY}"', ".ENV": b"secret"}),
        CapabilityKind.SKILL,
        "example",
    )
    assert [entry.path for entry in result.files] == ["SKILL.md"]
    assert result.omitted == (".ENV",)


@pytest.mark.parametrize(
    "header,value",
    [
        ("Accept", "arbitrary-private-value"),
        ("Authorization", "Basic abcdef0123456789"),
    ],
)
def test_unsupported_header_profiles_are_refused_instead_of_silently_changed(
    header: str, value: str
) -> None:
    raw = {
        "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
        "mcpServers": {
            "remote": {
                "type": "streamable-http",
                "url": "https://example.com/mcp",
                "headers": {header: value},
            }
        },
    }
    with pytest.raises(ValueError):
        sanitize_package(
            package({"plugin.json": b"{}", "mcp.json": json.dumps(raw).encode()}),
            CapabilityKind.PLUGIN,
            "example",
        )
