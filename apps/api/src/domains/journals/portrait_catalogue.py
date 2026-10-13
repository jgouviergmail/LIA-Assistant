"""Snapshot-local references to exact complete portrait evidence.

References replace provider reproduction of presentation metadata. They never
match substrings, repair text or make an incomplete source item admissible.
An item is one ``- `` line: a continuation line makes its item incomplete. No
reader clamps with an ellipsis any more (2026-10-12), so an ellipsis is text,
and the length bound is the seam's ``PORTRAIT_ITEM_MAX_CHARS`` — the assembler
cuts at it before anything reaches here, so nothing is dropped for its length.
"""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass

from src.domains.journals.models import JournalEntry
from src.domains.shared.portrait_sources import PORTRAIT_ITEM_MAX_CHARS, PORTRAIT_SOURCE_KEYS

#: A legacy ``quote`` support is bounded like a rendered item line.
PORTRAIT_SUPPORT_QUOTE_MAX_CHARS = PORTRAIT_ITEM_MAX_CHARS


@dataclass(frozen=True)
class CatalogueItem:
    source: str
    item_id: str
    quote: str


def _identifier(source: str, quote: str, revision: int | None = None) -> str:
    payload = json.dumps([source, quote, revision], ensure_ascii=False, separators=(",", ":"))
    return "pi_" + hashlib.sha256(payload.encode()).hexdigest()


def _eligible_line(line: str) -> bool:
    return line.startswith("- ") and bool(line[2:].strip()) and len(line) <= PORTRAIT_ITEM_MAX_CHARS


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
    lines = dict.fromkeys(complete_item_lines(section))
    return [CatalogueItem(source, source_item_id(source, line), line) for line in lines]


def complete_item_lines(section: str) -> list[str]:
    """The complete item lines of a section, in order, duplicates included.

    A continuation makes the whole preceding item ineligible, never a fragment.
    """
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


class CatalogueIndex:
    """The eligible items of each captured section, parsed and hashed ONCE.

    Resolving every support against a freshly parsed section cost 0.8 s on a
    150-item section and 10.6 s on 2000 items for one batch of 32 claims x 40
    supports (measured 2026-10-12 c) — synchronous CPU under the owner lock. A
    validation pass builds one index and every support reads it.
    """

    def __init__(self, sections: Mapping[str, str]) -> None:
        self._sections = sections
        self._by_quote: dict[str, dict[str, CatalogueItem]] = {}
        self._by_id: dict[str, dict[str, set[str]]] = {}

    def items(self, source: str) -> Mapping[str, CatalogueItem]:
        """The eligible items of one source keyed by quote, parsed on first use."""
        if source not in self._by_quote:
            items = eligible_source_items(source, self._sections.get(source, ""))
            self._by_quote[source] = {item.quote: item for item in items}
            by_id: dict[str, set[str]] = {}
            for item in items:
                by_id.setdefault(item.item_id, set()).add(item.quote)
            self._by_id[source] = by_id
        return self._by_quote[source]

    def resolve(self, source: str, item_id: str) -> str:
        """Resolve only a known unambiguous reference in this exact source snapshot."""
        self.items(source)
        quotes = self._by_id[source].get(item_id, set())
        if len(quotes) != 1:
            raise ValueError("Unknown or ambiguous portrait catalogue reference")
        return next(iter(quotes))


def resolve_source_item(source: str, item_id: str, section: str) -> str:
    """Resolve one reference against one section (the index's rule, for one lookup)."""
    return CatalogueIndex({source: section}).resolve(source, item_id)
