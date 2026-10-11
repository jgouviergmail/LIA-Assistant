"""Snapshot-local references to exact complete portrait evidence.

References replace provider reproduction of presentation metadata. They never
match substrings, repair text or make an incomplete source item admissible.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from src.domains.journals.models import JournalEntry
from src.domains.shared.portrait_sources import PORTRAIT_SOURCE_KEYS

PORTRAIT_SUPPORT_QUOTE_MAX_CHARS = 5000


@dataclass(frozen=True)
class CatalogueItem:
    source: str
    item_id: str
    quote: str


def _identifier(source: str, quote: str, revision: int | None = None) -> str:
    payload = json.dumps([source, quote, revision], ensure_ascii=False, separators=(",", ":"))
    return "pi_" + hashlib.sha256(payload.encode()).hexdigest()


def _eligible_line(line: str) -> bool:
    return (
        line.startswith("- ")
        and bool(line[2:].strip())
        and "…" not in line
        and len(line) <= PORTRAIT_SUPPORT_QUOTE_MAX_CHARS
    )


def source_item_id(source: str, quote: str) -> str:
    """Identify one complete literal source line, including its metadata."""
    if (
        source not in PORTRAIT_SOURCE_KEYS
        or not _eligible_line(quote)
        or "\n" in quote
        or "\r" in quote
    ):
        raise ValueError("No catalogue reference for an incomplete or unknown source item")
    return _identifier(source, quote)


def eligible_source_items(source: str, section: str) -> list[CatalogueItem]:
    """Return the exact distinct admissible lines of this captured section."""
    if source not in PORTRAIT_SOURCE_KEYS:
        raise ValueError("Unknown portrait source")
    lines = dict.fromkeys(_complete_item_lines(section))
    return [CatalogueItem(source, source_item_id(source, line), line) for line in lines]


def _complete_item_lines(section: str) -> list[str]:
    """A continuation makes the whole preceding item ineligible, never a fragment."""
    complete: list[str] = []
    candidate: str | None = None
    for line in [*section.splitlines(), "- "]:
        if line.startswith("- ") or line.startswith("## "):
            if candidate is not None:
                complete.append(candidate)
            candidate = line if _eligible_line(line) else None
        elif line.strip():
            candidate = None
    return complete


def render_catalogue_sections(sections: dict[str, str]) -> dict[str, str]:
    """Expose references and whole items only; a fully omitted source is empty."""
    rendered: dict[str, str] = {}
    for source, section in sections.items():
        items = eligible_source_items(source, section)
        if not items:
            rendered[source] = ""
            continue
        headers = _render_headers(section, len(items))
        lines = [f"- [portrait_item_id={item.item_id}] {item.quote[2:]}" for item in items]
        rendered[source] = "\n".join([*headers, *lines])
    return rendered


def _render_headers(section: str, shown: int) -> list[str]:
    return [
        re.sub(r"\b\d+ of (\d+)\b", lambda match: f"{shown} of {match.group(1)}", line)
        for line in section.splitlines()
        if line.startswith("## ")
    ]


def journal_item_id(entry: JournalEntry) -> str | None:
    """An operational journal reference binds UUID, rule revision and whole text."""
    if (
        entry.level not in ("L1", "L2", "L3")
        or entry.confidence not in ("medium", "high")
        or entry.contradiction_count
    ):
        return None
    return _identifier(f"journal:{entry.id}", entry.content, entry.revision)


def resolve_source_item(source: str, item_id: str, section: str) -> str:
    """Resolve only a known unambiguous reference in this exact source snapshot."""
    quotes = {
        item.quote for item in eligible_source_items(source, section) if item.item_id == item_id
    }
    if len(quotes) != 1:
        raise ValueError("Unknown or ambiguous portrait catalogue reference")
    return quotes.pop()
