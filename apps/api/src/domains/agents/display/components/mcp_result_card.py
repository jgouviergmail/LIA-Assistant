"""Lossless progressive rendering of bounded, external MCP result snapshots."""

from collections.abc import Mapping

from src.domains.agents.data_registry.mcp_metadata import source_identity
from src.domains.agents.display.components.base import (
    BaseComponent,
    RenderContext,
    render_card_top,
    render_chip,
    wrap_with_response,
)
from src.domains.agents.display.components.card_content import render_linked_title
from src.domains.agents.display.components.mcp_details import (
    MCPDisplaySnapshot,
    mcp_fields,
    mcp_raw,
    mcp_text,
)
from src.domains.agents.display.icons import Icons
from src.domains.agents.display.values import scalar_text

_TITLE_FIELDS = ("name", "title", "subject", "label", "display_name", "full_name")
_DESCRIPTION_FIELDS = ("description", "summary", "body", "text")


def _selected_text(data: Mapping[str, object], fields: tuple[str, ...]) -> tuple[str, str]:
    for key in fields:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return key, value
    return "", ""


def _identity(data: Mapping[str, object]) -> tuple[str, str]:
    if source := source_identity(data.get("_mcp_source")):
        return source["server_name"], source["tool_name"]
    return scalar_text(data.get("server_name")) or "MCP", scalar_text(data.get("tool_name"))


def _structured_body(
    data: Mapping[str, object],
    snapshot: MCPDisplaySnapshot,
    ctx: RenderContext,
    server: str,
    tool: str,
) -> tuple[str, str]:
    title_key, title = _selected_text(data, _TITLE_FIELDS)
    description_key, description = _selected_text(data, _DESCRIPTION_FIELDS)
    used = {title_key, description_key}
    for key, identity in (("server_name", server), ("tool_name", tool)):
        if data.get(key) == identity:
            used.add(key)
    url = scalar_text(data.get("html_url") or data.get("url"))
    title_html = render_linked_title(
        snapshot.text(title or tool.replace("_", " ").title() or "MCP"),
        url if len(url) <= 2048 else "",
    )
    content = mcp_text(snapshot.project(description), ctx, preview=200)
    return title_html, content + mcp_fields(data, used, snapshot, ctx)


class McpResultCard(BaseComponent):
    """Source identity comes from application metadata; external fields stay data."""

    def render(
        self,
        data: dict[str, object],
        ctx: RenderContext,
        assistant_comment: str | None = None,
        suggested_actions: list[dict[str, str]] | None = None,
        with_wrapper: bool = True,
        is_first_item: bool = True,
        is_last_item: bool = True,
    ) -> str:
        snapshot = MCPDisplaySnapshot(ctx.language)
        server, tool = _identity(data)
        # Identity consumes the same budget as content, including historical data.
        badge = render_chip(snapshot.text(server), "", Icons.EXTENSION)
        if data.get("_mcp_structured") is True:
            title, content = _structured_body(data, snapshot, ctx, server, tool)
        else:
            title = render_linked_title(snapshot.text(tool.replace("_", " ").title() or "MCP"), "")
            content = mcp_raw(data.get("result", ""), snapshot, ctx)
        top = render_card_top("extension", "teal", title, badges_html=badge)
        html = f'<div class="lia-card lia-mcp {self._nested_class(ctx)}">{top}{content}{snapshot.notice()}</div>'
        return (
            wrap_with_response(
                card_html=html,
                assistant_comment=assistant_comment,
                suggested_actions=suggested_actions,
                domain="mcp",
                with_top_separator=is_first_item,
                with_bottom_separator=is_last_item,
            )
            if with_wrapper
            else html
        )
