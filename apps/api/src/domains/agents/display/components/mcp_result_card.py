"""
McpResultCard Component - MCP Tool Result Display.

Renders data returned by user MCP tool servers.
Supports two modes:
  - **Structured**: Individual items with auto-detected title, description and detail
    fields (activated when the ``_mcp_structured`` flag is present in the payload).
  - **Raw**: Plain text or JSON content with auto-detection (original behaviour).

Phase: evolution F2.3 — MCP HTML Card
Created: 2026-03-01
"""

from __future__ import annotations

from typing import Any

from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    escape_html,
    render_card_top,
    render_chip,
    render_kv_rows,
    render_raw_block,
    truncate,
    wrap_with_response,
)
from src.domains.agents.display.icons import Icons

# Fields used to auto-detect a meaningful title for structured MCP items
_TITLE_FIELDS = ("name", "title", "subject", "label", "display_name", "full_name")

# Fields used to auto-detect a description
_DESCRIPTION_FIELDS = ("description", "summary", "body", "text")

# Fields excluded from the detail section (internal / rendering / low-value)
_EXCLUDED_FIELD_PREFIXES = ("_",)
_EXCLUDED_FIELDS = frozenset(
    {
        "id",
        "node_id",
        "url",
        "html_url",
        "api_url",
        "git_url",
        "ssh_url",
        "clone_url",
        "svn_url",
        "mirror_url",
        "hooks_url",
        "tool_name",
        "server_name",
    }
)

# Maximum number of detail fields shown per card
_MAX_DETAIL_FIELDS = 5

# Maximum length for a detail field value before truncation
_MAX_DETAIL_VALUE_LENGTH = 100

# Maximum length for description text
_MAX_DESCRIPTION_LENGTH = 200


def _humanise_field_name(name: str) -> str:
    """Convert ``snake_case`` field names to ``Title Case``.

    Example: ``stargazers_count`` → ``Stargazers Count``
    """
    return name.replace("_", " ").title()


class McpResultCard(BaseComponent):
    """
    MCP tool result card.

    Displays data from user MCP servers with:
    - Server name badge (identifies source MCP server)
    - Humanized tool name as title
    - Structured key-value fields or raw content depending on the payload
    """

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
        """Render MCP tool result as card (structured or raw)."""
        if data.get("_mcp_structured"):
            return self._render_structured(
                data,
                ctx,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                with_wrapper=with_wrapper,
                is_first_item=is_first_item,
                is_last_item=is_last_item,
            )
        return self._render_raw(
            data,
            ctx,
            assistant_comment=assistant_comment,
            suggested_actions=suggested_actions,
            with_wrapper=with_wrapper,
            is_first_item=is_first_item,
            is_last_item=is_last_item,
        )

    # --------------------------------------------------------------------- #
    # Structured rendering (evolution F2.4)
    # --------------------------------------------------------------------- #

    def _render_structured(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render a single structured MCP item with auto-detected fields."""
        server_name = data.get("server_name", "MCP")
        tool_name = data.get("tool_name", "")
        nested_class = self._nested_class(ctx)

        # v4: card-top + description + kv-rows
        title_value = None
        for field in _TITLE_FIELDS:
            candidate = data.get(field)
            if candidate and isinstance(candidate, str):
                title_value = candidate
                break
        if not title_value:
            title_value = tool_name.replace("_", " ").title() if tool_name else "MCP"

        title_html = f'<span class="lia-card-top__title">{escape_html(title_value)}</span>'
        server_badge = render_chip(server_name, "", Icons.EXTENSION)
        card_top_html = render_card_top("extension", "teal", title_html, badges_html=server_badge)

        # Description
        desc_html = ""
        used_fields = {f for f in _TITLE_FIELDS if data.get(f)}
        for field in _DESCRIPTION_FIELDS:
            candidate = data.get(field)
            if candidate and isinstance(candidate, str):
                used_fields.add(field)
                desc_truncated = truncate(candidate, _MAX_DESCRIPTION_LENGTH)
                desc_html = (
                    f'<p style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary);'
                    f'margin-top:var(--lia-space-xs)">{escape_html(desc_truncated)}</p>'
                )
                break

        # Detail fields as KV rows
        kv_pairs: list[tuple[str, str]] = []
        for key, value in data.items():
            if len(kv_pairs) >= _MAX_DETAIL_FIELDS:
                break
            if key in used_fields or key in _EXCLUDED_FIELDS:
                continue
            if any(key.startswith(p) for p in _EXCLUDED_FIELD_PREFIXES):
                continue
            if isinstance(value, dict | list):
                continue
            if value is None:
                continue
            str_value = str(value)
            if len(str_value) > _MAX_DETAIL_VALUE_LENGTH:
                str_value = str_value[:_MAX_DETAIL_VALUE_LENGTH] + "..."
            label = _humanise_field_name(key)
            kv_pairs.append((label, str_value))

        details_html = render_kv_rows(kv_pairs) if kv_pairs else ""

        card_html = (
            f'<div class="lia-card lia-mcp {nested_class}">'
            f"{card_top_html}"
            f"{desc_html}"
            f"{details_html}"
            f"</div>"
        )

        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain="mcp",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    # --------------------------------------------------------------------- #
    # Raw rendering (original behaviour)
    # --------------------------------------------------------------------- #

    def _render_raw(
        self,
        data: dict[str, Any],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        """Render MCP tool result as raw text/JSON card using v4 components."""
        tool_name = data.get("tool_name", "")
        server_name = data.get("server_name", "MCP")
        result = data.get("result", "")
        nested_class = self._nested_class(ctx)

        # v4 card-top
        display_name = tool_name.replace("_", " ").title() if tool_name else "MCP"
        title_html = f'<span class="lia-card-top__title">{escape_html(display_name)}</span>'
        server_badge = render_chip(server_name, "", Icons.EXTENSION)
        card_top_html = render_card_top("extension", "teal", title_html, badges_html=server_badge)

        # Content: use v4 raw-block for JSON, or plain text
        content_html = self._render_content_v4(result)

        card_html = (
            f'<div class="lia-card lia-mcp {nested_class}">'
            f"{card_top_html}"
            f"{content_html}"
            f"</div>"
        )

        if with_wrapper:
            return wrap_with_response(
                card_html=card_html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain="mcp",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
        return card_html

    def _render_content_v4(self, result: str) -> str:
        """Render result content using v4 raw-block for JSON, plain text otherwise."""
        if not result:
            return ""
        stripped = result.strip()
        if stripped and stripped[0] in "{[":
            return render_raw_block(result)
        truncated = truncate(result, 2000)
        formatted = escape_html(truncated).replace("\n", "<br>")
        return (
            f'<div style="font-size:var(--lia-text-sm);color:var(--lia-text-secondary);'
            f'margin-top:var(--lia-space-xs)">{formatted}</div>'
        )
