"""MCP domain identities and availability, independent of static native domains."""

import re
from collections.abc import Collection, Mapping
from typing import TYPE_CHECKING

from src.domains.agents.constants import MCP_DOMAIN_PREFIX
from src.domains.agents.registry.mcp_domain_descriptions import auto_generate_server_description

if TYPE_CHECKING:
    from src.core.context import UserMCPToolsContext
    from src.domains.agents.registry.catalogue import ToolManifest


def slugify_mcp_server_name(name: str) -> str:
    """Keep the historical domain convention; exact server keys remain separate."""
    slug = re.sub(r"_+", "_", re.sub(r"[^a-z0-9]", "_", name.lower())).strip("_")[:40]
    return f"{MCP_DOMAIN_PREFIX}{slug or 'unnamed'}"


def deduplicate_mcp_slugs(
    server_names: list[str], *, reserved: Collection[str] = ()
) -> dict[str, str]:
    """Reserve literal domains before suffix allocation, including admin identities."""
    bases = {name: slugify_mcp_server_name(name) for name in server_names}
    natural = set(bases.values())
    allocated = set(reserved)
    result: dict[str, str] = {}
    for name, base in bases.items():
        candidate = base
        suffix = 2
        while candidate in allocated or (candidate != base and candidate in natural):
            candidate = f"{base}_{suffix}"
            suffix += 1
        result[name] = candidate
        allocated.add(candidate)
    return result


def is_mcp_domain(domain_name: str) -> bool:
    return domain_name.startswith(MCP_DOMAIN_PREFIX)


def _legacy_domain(manifest: ToolManifest) -> str:
    domain = manifest.agent.removesuffix("_agent")
    return domain if domain.startswith(MCP_DOMAIN_PREFIX) else ""


def filter_admin_mcp_disabled_manifests(
    manifests: list[ToolManifest], admin_disabled: set[str] | None = None
) -> list[ToolManifest]:
    """Respect exact admin keys; user-owned tools are never disabled by admin aliases."""
    from src.core.context import admin_mcp_disabled_ctx, user_mcp_tools_ctx

    disabled = admin_mcp_disabled_ctx.get() if admin_disabled is None else admin_disabled
    if not disabled:
        return manifests
    user_ctx = user_mcp_tools_ctx.get()
    user_names = {manifest.name for manifest in user_ctx.tool_manifests} if user_ctx else set()
    disabled_domains = {slugify_mcp_server_name(key) for key in disabled}
    return [
        manifest
        for manifest in manifests
        if not _admin_manifest_disabled(manifest, disabled, disabled_domains, user_names)
    ]


def _admin_manifest_disabled(
    manifest: ToolManifest, disabled: set[str], domains: set[str], user_names: set[str]
) -> bool:
    if manifest.mcp_origin == "user" or (
        manifest.mcp_origin is None and manifest.name in user_names
    ):
        return False
    if manifest.mcp_server_key is not None:
        return manifest.mcp_origin == "admin" and manifest.mcp_server_key in disabled
    domain = _legacy_domain(manifest)
    if domain:
        return domain in domains
    return any(manifest.name.startswith(f"{candidate}_") for candidate in domains)


def _disabled_domains(disabled: set[str], server_domains: Mapping[str, str] | None) -> set[str]:
    exact = server_domains or {}
    return {exact.get(key, slugify_mcp_server_name(key)) for key in disabled}


def _user_domains(ctx: UserMCPToolsContext | None) -> list[dict[str, str]]:
    if ctx is None:
        return []
    manifests = ctx.tool_manifests
    connected = {manifest.agent.removesuffix("_agent") for manifest in manifests}
    result: list[dict[str, str]] = []
    for server, domain in ctx.server_domains.items():
        if domain not in connected:
            continue
        tools = [manifest for manifest in manifests if manifest.agent == f"{domain}_agent"]
        description = ctx.server_descriptions.get(server) or auto_generate_server_description(
            [manifest.description for manifest in tools],
            server,
            [manifest.name for manifest in tools],
        )
        result.append({"name": domain, "description": description})
    return result


def collect_all_mcp_domains(
    admin_domains: dict[str, str],
    admin_disabled: set[str] | None,
    user_ctx: UserMCPToolsContext | None,
    *,
    admin_server_domains: Mapping[str, str] | None = None,
) -> list[dict[str, str]]:
    """Combine available server identities without inferring availability from names."""
    disabled = _disabled_domains(admin_disabled or set(), admin_server_domains)
    result = [
        {"name": domain, "description": description}
        for domain, description in admin_domains.items()
        if domain not in disabled
    ]
    occupied = {item["name"] for item in result}
    result.extend(item for item in _user_domains(user_ctx) if item["name"] not in occupied)
    return result
