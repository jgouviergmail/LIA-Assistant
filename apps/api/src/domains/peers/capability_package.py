"""Bounded static transfer snapshots, with deterministic digests and secret refusal.

The scanner catches recognizable credential literals. It cannot certify that
arbitrary prose, opaque binary resources or endpoint paths contain no secret.
Known credential fields are removed structurally before the bytes are retained.
"""

import hashlib
import json
import re
import stat
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

from pydantic import JsonValue, ValidationError

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.domains.peers.capability_contracts import (
    CapabilityKind,
    PackageSnapshot,
    PortableFile,
    PortableMCPConfig,
    PortableServer,
)
from src.domains.plugins.mcp_config import validate_mcp_config
from src.domains.plugins.schemas import McpServerStatus
from src.domains.user_mcp.models import UserMCPAuthType
from src.infrastructure.archives.zip_budget import enforce_zip_budgets

_RUNTIME = frozenset(
    {
        ".git",
        ".env",
        ".venv",
        "node_modules",
        "__pycache__",
        "out",
        "output",
        ".cache",
        ".secrets",
    }
)
_PRIVATE_EXTENSIONS = frozenset({".pem", ".key", ".p12", ".pfx", ".sqlite", ".db", ".bak"})
_SECRET = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
    rb"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password)"
    rb"[\"']?\s*[=:]\s*[\"'](?!\$\{)[^\"'\r\n]{8,}[\"']|"
    rb"authorization\s*[:=]\s*[\"']?bearer\s+(?!\$\{)[A-Za-z0-9._~+/-]{8,}|"
    rb"\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b",
    re.IGNORECASE,
)
_SAFE_HEADERS = frozenset({"accept", "content-type", "mcp-protocol-version"})
_CREDENTIAL_FIELDS = frozenset(
    {
        "apikey",
        "accesstoken",
        "refreshtoken",
        "clientsecret",
        "password",
        "bearertoken",
        "privatekey",
    }
)


def refuse_embedded_secrets(content: bytes) -> None:
    if _SECRET.search(content):
        raise ValueError("Package contains a possible credential; remove it before sharing")
    try:
        document: JsonValue = json.loads(content)
    except json.JSONDecodeError, UnicodeError:
        return
    except RecursionError:
        raise ValueError("Package JSON exceeds the supported nesting depth") from None
    _refuse_json_credentials(document)


def _credential_literal(key: str, value: JsonValue) -> bool:
    return (
        re.sub(r"[^a-z0-9]", "", key.casefold()) in _CREDENTIAL_FIELDS
        and isinstance(value, str)
        and bool(value)
        and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}", value) is None
    )


def _refuse_json_credentials(document: JsonValue) -> None:
    pending = [document]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            if any(_credential_literal(key, item) for key, item in value.items()):
                raise ValueError("Package contains a credential field; remove it before sharing")
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)
        elif isinstance(value, str) and _SECRET.search(value.encode()):
            raise ValueError("Package contains a possible credential; remove it before sharing")


def _path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or ":" in name
        or "\0" in name
        or path.is_absolute()
        or ".." in path.parts
        or len(name) > 512
        or path.as_posix() != name
    ):
        raise ValueError("Package contains an unsafe path")
    return path


def _public_header_value(key: str, value: str) -> bool:
    if key.casefold() == "mcp-protocol-version":
        return re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None
    return all(
        part.strip() in {"application/json", "text/event-stream"} for part in value.split(",")
    )


def portable_headers(
    headers: dict[str, str],
) -> tuple[dict[str, str], str | None, UserMCPAuthType]:
    public = {key: value for key, value in headers.items() if key.casefold() in _SAFE_HEADERS}
    if any(not _public_header_value(key, value) for key, value in public.items()):
        raise ValueError("Nonstandard fixed headers must be removed before sharing")
    private = [key for key in headers if key.casefold() not in _SAFE_HEADERS]
    if len(private) > 1:
        raise ValueError("Multiple credential headers require a supported authentication profile")
    if not private:
        return public, None, UserMCPAuthType.NONE
    header = private[0]
    if header.casefold() != "authorization":
        return public, header, UserMCPAuthType.API_KEY
    if not headers[header].casefold().startswith("bearer "):
        raise ValueError("Unsupported authorization profile")
    return public, header, UserMCPAuthType.BEARER


def _rewrite_mcp(content: bytes) -> tuple[bytes, tuple[PortableServer, ...]]:
    result = validate_mcp_config(json.loads(content))
    if not result.valid:
        raise ValueError("Plugin MCP configuration is invalid")
    servers: list[PortableServer] = []
    document: dict[str, object] = {}
    for server in result.servers:
        if server.status is not McpServerStatus.SUPPORTED:
            # No unsupported process commands, environment or credential bytes
            # survive in the retained package, even though the importer skips them.
            raise ValueError("Plugin has an unsupported MCP entry")
        public, header, auth_type = portable_headers(server.headers)
        config = PortableMCPConfig(
            name=server.key,
            url=server.url or "",
            auth_type=auth_type,
            header_name=header,
            extra_headers=public,
        )
        servers.append(PortableServer(key=server.key, config=config))
        document[server.key] = {
            "type": "streamable-http",
            "url": config.url,
            "headers": public,
        }
    return json.dumps(
        {"$schema": AGENT_PLUGINS_MCP_SCHEMA_ID, "mcpServers": document},
        ensure_ascii=False,
        sort_keys=True,
    ).encode(), tuple(servers)


def _snapshot(
    kind: CapabilityKind,
    name: str,
    files: list[PortableFile],
    omitted: list[str],
    servers: tuple[PortableServer, ...],
) -> PackageSnapshot:
    ordered = tuple(sorted(files, key=lambda entry: entry.path))
    canonical = {
        "kind": kind.value,
        "name": name,
        "files": [(entry.path, hashlib.sha256(entry.content).hexdigest()) for entry in ordered],
        "servers": [entry.model_dump(mode="json") for entry in servers],
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return PackageSnapshot(
        kind=kind,
        name=name,
        digest=digest,
        files=ordered,
        omitted=tuple(sorted(omitted)),
        servers=servers,
    )


def verify_snapshot(package: PackageSnapshot, digest: str) -> bool:
    rebuilt = _snapshot(
        package.kind,
        package.name,
        list(package.files),
        list(package.omitted),
        package.servers,
    )
    return package.digest == digest == rebuilt.digest


def _portable_member(info: ZipInfo, prefix: str) -> str | None:
    # orig_filename keeps characters normalized by ZipInfo on Windows or at NUL.
    raw = info.orig_filename
    path = _path(raw)
    mode = stat.S_IFMT(info.external_attr >> 16)
    if mode not in (0, stat.S_IFREG) or info.flag_bits & 1:
        raise ValueError("Linked, special or encrypted resources are not shareable")
    if prefix and not raw.startswith(prefix):
        raise ValueError("Package member is outside the manifest root")
    if _RUNTIME.intersection(
        part.casefold() for part in path.parts
    ) or path.name.casefold().startswith(".env."):
        return None
    if path.suffix.casefold() in _PRIVATE_EXTENSIONS:
        raise ValueError("Package contains a private data or credential file")
    return raw[len(prefix) :]


def _archive_layout(
    archive: ZipFile, kind: CapabilityKind, name: str
) -> tuple[list[ZipInfo], str, int]:
    manifest = "SKILL.md" if kind is CapabilityKind.SKILL else "plugin.json"
    plugin = kind is CapabilityKind.PLUGIN
    budget = (
        settings.plugins_zip_max_decompressed_kb
        if plugin
        else settings.skills_zip_max_decompressed_kb
    ) * 1024
    enforce_zip_budgets(
        archive.infolist(),
        max_files=(settings.plugins_zip_max_files if plugin else settings.skills_zip_max_files),
        max_decompressed_bytes=budget,
    )
    infos = [info for info in archive.infolist() if not info.is_dir()]
    names = [info.orig_filename for info in infos]
    prefix = "" if manifest in names else f"{name}/"
    if prefix + manifest not in names or len(names) != len({name.casefold() for name in names}):
        raise ValueError("Package has no unique root manifest")
    return infos, prefix, budget


def sanitize_package(content: bytes, kind: CapabilityKind, name: str) -> PackageSnapshot:
    """Normalize a bounded archive without extracting paths or executing content."""
    files: list[PortableFile] = []
    omitted: list[str] = []
    servers: tuple[PortableServer, ...] = ()
    try:
        with ZipFile(BytesIO(content)) as archive:
            infos, prefix, budget = _archive_layout(archive, kind, name)
            for info in infos:
                relative = _portable_member(info, prefix)
                if relative is None:
                    omitted.append(info.orig_filename[len(prefix) :])
                    continue
                with archive.open(info) as resource:
                    data = resource.read(budget + 1)
                budget -= len(data)
                if budget < 0:
                    raise ValueError("Package expanded size exceeds the limit")
                if kind is CapabilityKind.PLUGIN and relative == "mcp.json":
                    data, servers = _rewrite_mcp(data)
                refuse_embedded_secrets(data)
                files.append(PortableFile(path=relative, content=data))
    except ValidationError:
        raise ValueError("Package contains an unsupported MCP configuration") from None
    except (BadZipFile, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Package cannot be safely shared") from exc
    return _snapshot(kind, name, files, omitted, servers)
