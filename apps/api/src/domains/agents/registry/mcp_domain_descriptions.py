"""Bounded routing descriptions from declared MCP capabilities, without a model."""

import re
from collections.abc import Sequence

from src.core.constants import (
    MCP_DESCRIPTION_MAX_SENTENCE_LENGTH,
    MCP_DESCRIPTION_MAX_TOTAL_LENGTH,
)


def _first_sentence(description: str) -> str:
    normalized = " ".join(description.split())
    sentence = re.split(r"(?<=[.!?])\s+", normalized, maxsplit=1)[0]
    return sentence[:MCP_DESCRIPTION_MAX_SENTENCE_LENGTH]


def _capabilities(descriptions: Sequence[str | None], names: Sequence[str] | None) -> list[str]:
    entries: list[str] = []
    for index in range(max(len(descriptions), len(names or ()))):
        name = names[index] if names and index < len(names) else ""
        description = descriptions[index] if index < len(descriptions) else None
        sentence = _first_sentence(description) if description else ""
        text = f"{name}: {sentence}" if name and sentence else name or sentence
        if text:
            entries.append(text)
    return entries


def _bounded_capabilities(entries: list[str], budget: int) -> str:
    """Spread a small budget across capabilities; disclose unavoidable omissions."""
    joined = "; ".join(entries)
    if len(joined) <= budget:
        return joined
    visible_count = min(len(entries), max(1, budget // 12))
    omitted = len(entries) - visible_count
    suffix = f"; +{omitted} more tools" if omitted else ""
    width = max(1, (budget - len(suffix) - 2 * (visible_count - 1)) // visible_count)
    visible = [
        entry if len(entry) <= width else entry[: max(0, width - 1)] + "…"
        for entry in entries[:visible_count]
    ]
    return ("; ".join(visible) + suffix)[:budget]


def auto_generate_server_description(
    tool_descriptions: list[str | None],
    server_name: str,
    tool_names: list[str] | None = None,
) -> str:
    """Represent all short capabilities; preserve periods inside URLs and decimals."""
    prefix = f"MCP {server_name[:80]}"
    entries = _capabilities(tool_descriptions, tool_names)
    if not entries:
        return prefix
    prefix += ": "
    return prefix + _bounded_capabilities(entries, MCP_DESCRIPTION_MAX_TOTAL_LENGTH - len(prefix))
