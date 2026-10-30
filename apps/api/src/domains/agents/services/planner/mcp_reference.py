"""Selected-server MCP reference collection and line-boundary truncation.

Admin servers' references are fetched at startup; personal servers' guidance
(handshake instructions, ``read_me``) is collected at real use, for the
router-selected domains only, matched through the exact domain the
registration allocated (spec 2026-10-21 §5.5b, E9).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from structlog.stdlib import BoundLogger

from src.core.time_utils import now_utc
from src.infrastructure.mcp.reference_content import collect_user_references

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


def _admin_reference_content(server_keys: set[str], configuration: Settings) -> dict[str, str]:
    from src.infrastructure.mcp.client_manager import get_mcp_client_manager

    manager = get_mcp_client_manager()
    if manager is None:
        return {}
    references: dict[str, str] = {}
    admin_ref = manager.reference_content
    iterative = _iterative_server_names(manager.server_configs, configuration.mcp_react_enabled)
    for name, content in admin_ref.items():
        if name.lower() in iterative:
            continue
        if name.lower() in server_keys:
            references[name.lower()] = content
    return references


def _truncate_reference(content: str, max_chars: int, marker: Callable[[], str]) -> str:
    """Cut at a complete line, using the character bound when no line fits."""
    if len(content) <= max_chars:
        return content
    cut_pos = content.rfind("\n", 0, max_chars)
    if cut_pos <= 0:
        cut_pos = max_chars
    return content[:cut_pos] + "\n" + marker()


async def build_mcp_reference(
    selected_domains: list[str] | None,
    *,
    truncated_marker: Callable[[], str],
    render_reference: Callable[[str, str], str],
    logger: BoundLogger,
) -> str:
    """Build MCP reference documentation for planner prompt injection.

    Collects read_me content from admin MCP and per-user MCP, but ONLY
    for servers whose domain is among ``selected_domains``.  This avoids
    injecting large reference content into every planner call — and a
    personal server's ``read_me`` is only FETCHED for such a turn.

    Admin MCP takes priority; user MCP only adds servers not already
    present from admin (case-insensitive dedup by server name).

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

    # Admin server keys from the selected MCP domains ("mcp_excalidraw" → "excalidraw")
    mcp_server_keys = _selected_server_keys(selected_domains)
    if not mcp_server_keys:
        return ""

    _settings = get_settings()
    max_ref_chars = _settings.mcp_reference_content_max_chars
    if max_ref_chars <= 0:
        return ""

    # Collect from admin MCP first, then user MCP (admin wins on conflict)
    all_references = _admin_reference_content(mcp_server_keys, _settings)
    admin_present = set(all_references)
    user_references = await collect_user_references(selected_domains, now=now_utc())
    for name, content in user_references.items():
        if name.lower() not in admin_present:
            all_references[name] = content

    if not all_references:
        return ""

    sections: list[str] = []
    for server_name, ref_content in all_references.items():
        is_admin = server_name in admin_present
        logger.info(
            "mcp_reference_content_stats",
            # A personal server's name is the person's words (ADR-317).
            server_name=server_name if is_admin else None,
            source="admin" if is_admin else "user",
            content_length=len(ref_content),
            max_ref_chars=max_ref_chars,
            will_truncate=len(ref_content) > max_ref_chars,
        )
        # Line-aware truncation: cut at last complete line boundary
        truncated = _truncate_reference(ref_content, max_ref_chars, truncated_marker)

        sections.append(render_reference(server_name, truncated))

    return "\n".join(sections)
