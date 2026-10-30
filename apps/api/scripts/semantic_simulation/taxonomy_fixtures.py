"""Full native domain menus and fictional MCP identities, with no tool execution."""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import patch

from scripts.semantic_simulation.taxonomy_corpus import MenuVariant
from src.core.context import (
    UserMCPToolsContext,
    admin_mcp_disabled_ctx,
    request_tool_manifests_ctx,
    user_mcp_tools_ctx,
)
from src.domains.agents.registry.catalogue import ToolManifest
from src.domains.agents.registry.semantic_inventory import collect_static_manifests
from src.domains.agents.services.analysis.domain_availability import (
    FLAG_GATED_DOMAINS,
    build_available_domains,
)
from src.infrastructure.mcp.registration import (
    build_mcp_react_task_manifest,
    build_mcp_tool_manifest,
)
from src.infrastructure.mcp.user_catalogue import describe_user_server, publish_user_server


def _read_manifest(name: str, domain: str, description: str, origin: str) -> ToolManifest:
    return build_mcp_tool_manifest(
        adapter_name=name,
        agent_name=f"{domain}_agent",
        tool_name="read_record",
        description=description,
        input_schema={"type": "object", "properties": {}},
        semantic_keywords=[domain],
        hitl_required=False,
        annotations={"readOnlyHint": True},
        mcp_origin="admin" if origin == "admin" else "user",
        mcp_server_key=(
            "Catalogue Polaris" if origin == "admin" else "00000001-0000-0000-0000-000000000001"
        ),
    )


def _user_server(variant: MenuVariant) -> UserMCPToolsContext:
    ctx = UserMCPToolsContext()
    iterative = variant == "user_mcp_iterative"
    name = "Canvas Orion" if iterative else "Archives Atlas"
    domain = "mcp_canvas_orion" if iterative else "mcp_archives_atlas"
    description = (
        "Create diagrams with boxes and arrows in the Canvas Orion workspace."
        if iterative
        else "Read private archive folders and dossier details by identifier on Archives Atlas."
    )
    if iterative:
        manifest = build_mcp_react_task_manifest(
            "mcp_user_00000001_task",
            f"{domain}_agent",
            name,
            description,
            [],
            [],
            hitl_required=True,
            mcp_origin="user",
            mcp_server_key="00000001-0000-0000-0000-000000000001",
        )
    else:
        manifest = _read_manifest("mcp_user_00000001_read_record", domain, description, "user")
    ctx.tool_manifests = [manifest]
    catalogue = describe_user_server(
        name,
        None,
        [{"name": "create_diagram" if iterative else "read_record", "description": description}],
    )
    publish_user_server(ctx, name, domain, catalogue)
    return ctx


@contextmanager
def full_domain_menu(variant: MenuVariant) -> Iterator[list[dict[str, str]]]:
    """Enable declared fixture features, preserving exact per-request tool availability."""
    native = collect_static_manifests()
    user_ctx = _user_server(variant) if variant in {"user_mcp", "user_mcp_iterative"} else None
    admin_domains: dict[str, str] = {}
    admin_keys: dict[str, str] = {}
    disabled: set[str] = set()
    if variant in {"admin_mcp", "disabled_mcp"}:
        key = "Catalogue Polaris" if variant == "admin_mcp" else "Archives Atlas"
        domain = "mcp_catalogue_polaris" if variant == "admin_mcp" else "mcp_archives_atlas"
        description = "Read and search book catalogue records and newest books."
        admin_domains[domain] = description
        admin_keys[key] = domain
        if variant == "admin_mcp":
            native.append(_read_manifest("mcp_polaris_read_record", domain, description, "admin"))
        else:
            disabled.add(key)
    offered = native + (user_ctx.tool_manifests if user_ctx else [])
    with ExitStack() as stack:
        for flag in FLAG_GATED_DOMAINS.values():
            stack.enter_context(patch(f"src.core.config.settings.{flag}", True))
        stack.enter_context(
            patch(
                "src.infrastructure.mcp.registration.get_admin_mcp_domains",
                return_value=admin_domains,
            )
        )
        stack.enter_context(
            patch(
                "src.infrastructure.mcp.registration.get_admin_mcp_server_domains",
                return_value=admin_keys,
            )
        )
        tokens = (
            user_mcp_tools_ctx.set(user_ctx),
            admin_mcp_disabled_ctx.set(disabled),
            request_tool_manifests_ctx.set(offered),
        )
        try:
            yield build_available_domains()
        finally:
            request_tool_manifests_ctx.reset(tokens[2])
            admin_mcp_disabled_ctx.reset(tokens[1])
            user_mcp_tools_ctx.reset(tokens[0])
