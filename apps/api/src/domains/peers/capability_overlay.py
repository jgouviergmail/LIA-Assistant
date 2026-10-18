"""Overlay live owned plugin components onto the installed static package."""

import json
from pathlib import PurePosixPath

from src.core.config import settings
from src.core.constants import AGENT_PLUGINS_MCP_SCHEMA_ID
from src.domains.peers.capability_contracts import (
    PackageSnapshot,
    PortableFile,
    PortableServer,
)
from src.domains.peers.capability_package import _snapshot
from src.domains.skills.import_service import _parse_frontmatter_name


def _skill_roots(files: dict[str, PortableFile]) -> dict[str, str]:
    roots: dict[str, str] = {}
    for path, resource in files.items():
        parts = PurePosixPath(path).parts
        if len(parts) == 3 and parts[0] == "skills" and parts[2] == "SKILL.md":
            name = _parse_frontmatter_name(resource.content.decode("utf-8-sig"))
            if name in roots:
                raise ValueError("Duplicate plugin skill identity")
            roots[name] = f"skills/{parts[1]}/"
    return roots


def _overlay_skills(
    files: dict[str, PortableFile], skills: tuple[PackageSnapshot, ...]
) -> dict[str, PortableFile]:
    roots = _skill_roots(files)
    for skill in skills:
        if skill.name not in roots:
            raise ValueError("Owned plugin skill has no package identity")
        prefix = roots[skill.name]
        files = {path: resource for path, resource in files.items() if not path.startswith(prefix)}
        files.update(
            {
                prefix
                + resource.path: PortableFile(path=prefix + resource.path, content=resource.content)
                for resource in skill.files
            }
        )
    return files


def overlay_live_components(
    package: PackageSnapshot,
    skills: tuple[PackageSnapshot, ...],
    servers: tuple[PortableServer, ...],
) -> PackageSnapshot:
    files = _overlay_skills({resource.path: resource for resource in package.files}, skills)
    live_servers = {server.key: server for server in package.servers}
    live_servers.update({server.key: server for server in servers})
    if servers:
        content = json.dumps(
            {
                "$schema": AGENT_PLUGINS_MCP_SCHEMA_ID,
                "mcpServers": {
                    key: {
                        "type": "streamable-http",
                        "url": server.config.url,
                        "headers": server.config.extra_headers,
                    }
                    for key, server in sorted(live_servers.items())
                },
            },
            sort_keys=True,
        ).encode()
        files["mcp.json"] = PortableFile(path="mcp.json", content=content)
    if (
        len(files) > settings.plugins_zip_max_files
        or sum(len(resource.content) for resource in files.values())
        > settings.plugins_zip_max_decompressed_kb * 1024
    ):
        raise ValueError("Live plugin components exceed the package limit")
    return _snapshot(
        package.kind,
        package.name,
        list(files.values()),
        list(package.omitted),
        tuple(live_servers[key] for key in sorted(live_servers)),
    )
