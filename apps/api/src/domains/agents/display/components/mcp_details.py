"""Bounded, credential-aware rendering of schema-free external MCP snapshots."""

import json
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from math import isfinite

from src.core.credential_fields import is_credential_field
from src.core.i18n_cards import card_label
from src.domains.agents.display.components.base import RenderContext, escape_html, render_raw_block
from src.domains.agents.display.components.card_content import (
    render_details,
    render_folded_text,
    render_text_content,
)
from src.domains.agents.display.values import scalar_text

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]

# These bound presentation only. Tool execution, registry selection and model
# result budgets retain their own authorities; a cut is explicitly disclosed.
MAX_MCP_DISPLAY_CHARS = 64_000
MAX_MCP_DISPLAY_NODES = 512
MAX_MCP_DISPLAY_DEPTH = 8
MAX_MCP_JSON_PARSE_CHARS = 256_000


def _binary_keys(value: Mapping[str, object]) -> set[str]:
    if value.get("type") in ("image", "audio") and isinstance(value.get("data"), str):
        return {"data"}
    if scalar_text(value.get("mimeType")) and isinstance(value.get("blob"), str):
        return {"blob"}
    return set()


@dataclass
class MCPDisplaySnapshot:
    language: str
    remaining_chars: int = MAX_MCP_DISPLAY_CHARS
    remaining_nodes: int = MAX_MCP_DISPLAY_NODES
    limited: bool = False
    ancestors: set[int] = field(default_factory=set)

    def text(self, value: str) -> str:
        if len(value) > self.remaining_chars:
            self.limited = True
            value = value[: self.remaining_chars] + "…"
        self.remaining_chars = max(0, self.remaining_chars - len(value))
        return value

    def limit(self) -> str:
        self.limited = True
        return card_label("display_limited", self.language)

    def project(self, value: object, depth: int = 0) -> JsonValue:
        if self.remaining_nodes <= 0 or self.remaining_chars <= 0 or depth > MAX_MCP_DISPLAY_DEPTH:
            return self.limit()
        self.remaining_nodes -= 1
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            return self.text(value)
        if isinstance(value, int | float):
            return self.number(value)
        if not isinstance(value, dict | list):
            return None
        if id(value) in self.ancestors:
            return self.limit()
        self.ancestors.add(id(value))
        try:
            return (
                self.project_object(value, depth)
                if isinstance(value, dict)
                else self.array(value, depth)
            )
        finally:
            self.ancestors.remove(id(value))

    def project_object(self, value: Mapping[str, object], depth: int) -> JsonValue:
        hidden_binary = _binary_keys(value)
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str) or key.startswith("_"):
                continue
            if self.remaining_nodes <= 0 or self.remaining_chars <= 0:
                self.limited = True
                break
            label = self.text(key)
            if key in hidden_binary:
                item = card_label("binary_not_displayed", self.language)
            elif is_credential_field(key):
                item = card_label("field_redacted", self.language)
            result[label] = self.project(item, depth + 1)
        return result

    def number(self, value: int | float) -> JsonValue:
        if isinstance(value, float) and not isfinite(value):
            return None
        try:
            text = str(value)
        except ValueError:
            return self.limit()
        projected = self.text(text)
        return value if projected == text else projected

    def array(self, value: list[object], depth: int) -> list[JsonValue]:
        result: list[JsonValue] = []
        for item in value:
            if self.remaining_nodes <= 0 or self.remaining_chars <= 0:
                self.limited = True
                break
            result.append(self.project(item, depth + 1))
        return result

    def notice(self) -> str:
        return (
            f'<p class="lia-card__meta lia-card__limit-notice">{escape_html(card_label("display_limited", self.language))}</p>'
            if self.limited
            else ""
        )


def mcp_text(value: object, ctx: RenderContext, *, preview: int) -> str:
    text = scalar_text(value)
    if len(text) > preview and not any(mark in text[:preview] for mark in (".", "!", "?", "\n")):
        return render_details(render_text_content(text), ctx)
    return render_folded_text(text, ctx, preview_chars=preview)


def mcp_value(value: JsonValue, ctx: RenderContext) -> str:
    if isinstance(value, dict | list):
        return render_details(
            render_raw_block(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)), ctx
        )
    if isinstance(value, bool):
        return escape_html(card_label("yes" if value else "no", ctx.language))
    return mcp_text("null" if value is None else value, ctx, preview=120)


def mcp_fields(
    data: Mapping[str, object], used: set[str], snapshot: MCPDisplaySnapshot, ctx: RenderContext
) -> str:
    rows = []
    hidden_binary = _binary_keys(data)
    for key, raw in data.items():
        if not isinstance(key, str) or key in used or key.startswith("_"):
            continue
        if snapshot.remaining_nodes <= 0 or snapshot.remaining_chars <= 0:
            snapshot.limited = True
            break
        label = escape_html(snapshot.text(key.replace("_", " ").title()))
        if key in hidden_binary:
            raw = card_label("binary_not_displayed", ctx.language)
        elif is_credential_field(key):
            raw = card_label("field_redacted", ctx.language)
        value = snapshot.project(raw)
        rows.append(f"<div><dt>{label}</dt><dd>{mcp_value(value, ctx)}</dd></div>")
    lead = f'<dl class="lia-mcp-fields">{"".join(rows[:5])}</dl>' if rows else ""
    return (
        lead + render_details(f'<dl class="lia-mcp-fields">{"".join(rows[5:])}</dl>', ctx)
        if len(rows) > 5
        else lead
    )


def mcp_raw(value: object, snapshot: MCPDisplaySnapshot, ctx: RenderContext) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("{", "[")):
            if len(value) > MAX_MCP_JSON_PARSE_CHARS:
                snapshot.limited = True
                return ""
            with suppress(ValueError, RecursionError):
                value = json.loads(value)
    projected = snapshot.project(value)
    if isinstance(projected, dict | list):
        return render_raw_block(
            json.dumps(projected, ensure_ascii=False, indent=2, allow_nan=False)
        )
    return (
        mcp_value(projected, ctx)
        if projected is None or isinstance(projected, bool)
        else mcp_text(projected, ctx, preview=2000)
    )
