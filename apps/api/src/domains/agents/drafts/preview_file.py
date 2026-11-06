"""What a file's sharing card shows (ADR-369, lot 6): beside the renderer, at its size cap."""

from __future__ import annotations

from typing import Any

from src.domains.agents.drafts.card_spec import PreviewLine
from src.domains.agents.drafts.preview_rows import FormatDt, row


def render_file_share(
    content: dict[str, Any], lbl: dict[str, str], format_dt: FormatDt
) -> list[PreviewLine]:
    """Render a sharing: the item, who the drive tells, and what they may do."""
    return [
        row(lbl, "file", content.get("name") or "?"),
        row(lbl, "shared_with", content.get("email") or "?"),
        row(lbl, "access", lbl.get(f"access_{content.get('role')}", "?")),
    ]


__all__ = ["render_file_share"]
