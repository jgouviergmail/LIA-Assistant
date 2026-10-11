"""Selected-server MCP reference collection and line-boundary truncation."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from structlog.stdlib import BoundLogger

if TYPE_CHECKING:
    from src.core.config import Settings
    from src.infrastructure.mcp.schemas import MCPServerConfig


def _selected_server_keys(selected_domains: list[str]) -> set[str]:
    from src.domains.agents.constants import MCP_DOMAIN_PREFIX

    return {
        domain.removeprefix(MCP_DOMAIN_PREFIX).lower()
        for domain in selected_domains
        if domain.startswith(MCP_DOMAIN_PREFIX)
    }


def _iterative_server_names(configs: dict[str, MCPServerConfig], enabled: bool) -> set[str]:
    if not enabled:
        return set()
    return {
        name.lower() for name, config in configs.items() if getattr(config, "iterative_mode", False)
    }


def _admin_reference_content(
    server_keys: set[str], configuration: Settings
) -> tuple[dict[str, str], set[str]]:
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager

    manager = get_mcp_client_manager()
    if manager is None:
        return {}, set()
    references: dict[str, str] = {}
    admin_ref = manager.reference_content
    admin_keys_lower = {key.lower() for key in admin_ref}
    iterative = _iterative_server_names(manager.server_configs, configuration.mcp_react_enabled)
    for name, content in admin_ref.items():
        if name.lower() in iterative:
            continue
        if name.lower() in server_keys:
            references[name.lower()] = content
    return references, admin_keys_lower


def _add_user_references(server_keys: set[str], references: dict[str, str]) -> None:
    from src.core.context import user_mcp_tools_ctx

    context = user_mcp_tools_ctx.get()
    if not context or not context.server_reference_content:
        return
    for name, content in context.server_reference_content.items():
        if name.lower() in context.iterative_servers:
            continue
        if name.lower() in server_keys and name.lower() not in references:
            references[name.lower()] = content


def _truncate_reference(content: str, max_chars: int, marker: Callable[[], str]) -> str:
    """Cut at a complete line, using the character bound when no line fits."""
    if len(content) <= max_chars:
        return content
    cut_pos = content.rfind("\n", 0, max_chars)
    if cut_pos <= 0:
        cut_pos = max_chars
    return content[:cut_pos] + "\n" + marker()


def build_mcp_reference(
    selected_domains: list[str] | None,
    *,
    truncated_marker: Callable[[], str],
    render_reference: Callable[[str, str], str],
    logger: BoundLogger,
) -> str:
    """Build MCP reference documentation for planner prompt injection.

    Collects read_me content from admin MCP and per-user MCP, but ONLY
    for servers whose domain is among ``selected_domains``.  This avoids
    injecting large reference content into every planner call.

    Admin MCP takes priority; user MCP only adds servers not already
    present from admin (case-insensitive dedup by server key).

    Args:
        selected_domains: Domain slugs from the query analyzer
            (e.g. ``["mcp_excalidraw", "weather"]``).  Only MCP domains
            (prefixed ``mcp_``) are considered.

    Returns:
        Formatted reference string, or empty string if no relevant content.
    """
    from src.core.config import get_settings

    if not selected_domains:
        return ""

    # Extract server keys from selected MCP domains (e.g. "mcp_excalidraw" → "excalidraw")
    mcp_server_keys = _selected_server_keys(selected_domains)
    if not mcp_server_keys:
        return ""

    _settings = get_settings()
    max_ref_chars = _settings.mcp_reference_content_max_chars
    if max_ref_chars <= 0:
        return ""

    # Collect from admin MCP first, then user MCP (admin wins on conflict)
    all_references, admin_keys_lower = _admin_reference_content(mcp_server_keys, _settings)
    _add_user_references(mcp_server_keys, all_references)

    if not all_references:
        return ""

    sections: list[str] = []
    for server_name, ref_content in all_references.items():
        logger.info(
            "mcp_reference_content_stats",
            server_name=server_name,
            source="admin" if server_name in admin_keys_lower else "user",
            content_length=len(ref_content),
            max_ref_chars=max_ref_chars,
            will_truncate=len(ref_content) > max_ref_chars,
        )
        # Line-aware truncation: cut at last complete line boundary
        truncated = _truncate_reference(ref_content, max_ref_chars, truncated_marker)

        sections.append(render_reference(server_name, truncated))

    return "\n".join(sections)
