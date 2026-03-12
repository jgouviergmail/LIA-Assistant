"""
McpAppSentinel Component — Placeholder for MCP Apps interactive widgets.

Renders a sentinel ``<div>`` that the frontend intercepts and replaces
with a sandboxed ``<iframe>`` running the MCP App HTML content.

The sentinel carries a ``data-registry-id`` attribute that the frontend
uses to look up the full payload (HTML, tool result, server info) from
the Data Registry via ``RegistryContext``.

Phase: evolution F2.5 — MCP Apps
Created: 2026-03-04
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
)
from src.domains.agents.display.icons import Icons, icon


class McpAppSentinel(BaseComponent):
    """Renders a placeholder div for MCP Apps — replaced by McpAppWidget on the frontend."""

    def render(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render MCP App sentinel placeholder.

        The frontend detects ``<div class="lia-mcp-app" data-registry-id="...">``
        and mounts the interactive ``McpAppWidget`` component in its place.
        """
        from src.core.field_names import FIELD_REGISTRY_ID

        registry_id = escape_html(str(data.get(FIELD_REGISTRY_ID, "")))
        server_name = escape_html(str(data.get("server_name", "MCP")))
        loading_text = V3Messages.get_mcp_app_loading(ctx.language)

        return (
            f'<div class="lia-mcp-app" data-registry-id="{registry_id}">'
            f'<div class="lia-mcp-app__placeholder">'
            f'<span class="lia-badge lia-badge--primary">'
            f"{icon(Icons.EXTENSION)} MCP Apps &middot; {server_name}"
            f"</span>"
            f'<div class="lia-mcp-app__loading">{escape_html(loading_text)}</div>'
            f"</div>"
            f"</div>"
        )
