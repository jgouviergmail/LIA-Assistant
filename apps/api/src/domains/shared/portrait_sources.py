"""The four sources the user portrait reads, offered to ``journals`` without an edge.

The consolidation (``journals``) compiles a portrait of the person from the
journal entries and, since the 2026-09-16 design (part B), from four other
records LIA keeps: the long-term memories, the interests, the learned habits
and the relationship debriefs. ``journals`` cannot import those domains:
``interests`` and ``relations`` already import ``journals`` (the ambient
portrait block), so the reverse edge would close a runtime cycle the coupling
ratchet refuses — and the ratchet counts local imports too.

The dependency is therefore inverted, exactly as ``consultation_sink`` and
``peer_release_sink`` do it: this module holds a registry, each source
INSTALLS its reader here (from a module the boot imports explicitly, so the
installation is a declaration and never a side effect somebody reorders
away — ADR-270), and ``journals`` reads the registry. Nothing here imports
anything from a domain.

One mechanism for the four, on purpose: two of them could be imported by
``journals`` directly today, and two shapes for one question is the trap the
registries doctrine names.

The boot REFUSES an incomplete registry (``assert_portrait_sources_complete``):
a source nobody installed would make the portrait silently blind to a record
the person keeps reading, which is the class of defect ADR-280 measured.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Literal, Protocol
from uuid import UUID

from src.core.prompt_store import parse_prompt_sections, read_prompt_file

#: One ellipsis, never a cut that pretends to be the whole.
_ELLIPSIS: Final[str] = "…"

#: The closed vocabulary, in the order the prompt renders the sections.
PORTRAIT_SOURCE_KEYS: Final[tuple[str, ...]] = (
    "memories",
    "interests",
    "habits",
    "relation_debriefs",
)

SectionStatus = Literal["used", "empty", "disabled", "unavailable"]

#: ``SourceBudget.max_items`` for a source bounded by construction (the learned
#: habits: two day classes and a capped number of recurring rows) — the reader
#: applies the clamp and ignores the item count.
ITEMS_BOUNDED_BY_SOURCE: Final[int] = -1


@dataclass(frozen=True, slots=True)
class SourceBudget:
    """What one reader may render.

    Attributes:
        max_items: Items rendered at most (0 renders none;
            :data:`ITEMS_BOUNDED_BY_SOURCE` for a source bounded by construction).
        item_max_chars: Clamp applied to each rendered item.
    """

    max_items: int
    item_max_chars: int


@dataclass(frozen=True, slots=True)
class PortraitSourceSection:
    """What one source answers.

    Attributes:
        key: One of :data:`PORTRAIT_SOURCE_KEYS`.
        status: ``used`` (rendered), ``empty`` (nothing to say), ``disabled``
            (a gate refused — deployment ceiling, operator switch or the
            person's own preference) or ``unavailable`` (a read failed — a
            blind source is named, never read as empty).
        text: The rendered section, ``""`` unless ``status == "used"``.
        used: Items rendered.
        total: EXACT count over the whole set (ADR-185), 0 unless read.
    """

    key: str
    status: SectionStatus
    text: str
    used: int
    total: int


class PortraitSourceReader(Protocol):
    """What a source offers the consolidation: one bounded, gated, safe read."""

    async def __call__(
        self, *, user_id: UUID, language: str, budget: SourceBudget
    ) -> PortraitSourceSection:
        """Render the source for one account.

        Args:
            user_id: The account whose portrait is compiled.
            language: The account's language (dates, labels).
            budget: What may be rendered.

        Returns:
            The section; never raises (an exception is ``unavailable``).
        """


@dataclass(frozen=True, slots=True)
class FreshnessProbe:
    """Where a source's freshness is read, for the consolidation's eligibility.

    Attributes:
        table: The table name on ``Base.metadata``.
        user_column: The owner column.
        stamp_column: The column that moves when the record changes.
    """

    table: str
    user_column: str
    stamp_column: str


_REGISTRY: dict[str, tuple[PortraitSourceReader, FreshnessProbe]] = {}


@lru_cache(maxsize=1)
def portrait_lines() -> dict[str, str]:
    """The sections' scaffolds (``key|template``), read once from the store.

    Every reader renders through these lines and only its own keys; the
    placeholder guard credits the readers as renderers of the file.
    """
    return dict(parse_prompt_sections(read_prompt_file("journal_portrait_source_lines"), 2))


def clamp_item(text: str, max_chars: int) -> str:
    """One line of at most ``max_chars`` characters, ending in an ellipsis when cut.

    Args:
        text: The item's text (newlines collapsed).
        max_chars: The clamp.

    Returns:
        The bounded line.
    """
    flat = " ".join(text.split())
    if len(flat) <= max_chars:
        return flat
    return flat[: max(max_chars - 1, 0)].rstrip() + _ELLIPSIS


def empty_section(key: str, status: SectionStatus, *, total: int = 0) -> PortraitSourceSection:
    """A section with nothing to render — its status says why."""
    return PortraitSourceSection(key=key, status=status, text="", used=0, total=total)


def install_portrait_source(
    key: str, reader: PortraitSourceReader, freshness: FreshnessProbe
) -> None:
    """Let one source offer its reader to the portrait.

    Idempotent for the SAME reader (a module imported twice installs twice);
    a different reader for an installed key is a genuine conflict and refused.

    Args:
        key: One of :data:`PORTRAIT_SOURCE_KEYS`.
        reader: The source's reader.
        freshness: Where its freshness is read.

    Raises:
        RuntimeError: Unknown key, or a second reader for one key.
    """
    if key not in PORTRAIT_SOURCE_KEYS:
        raise RuntimeError(
            f"portrait source {key!r} is not in the declared vocabulary {PORTRAIT_SOURCE_KEYS}"
        )
    installed = _REGISTRY.get(key)
    if installed is not None and installed[0] is not reader:
        raise RuntimeError(f"portrait source {key!r} already has a reader; refusing a second one")
    _REGISTRY[key] = (reader, freshness)


def installed_portrait_sources() -> Mapping[str, tuple[PortraitSourceReader, FreshnessProbe]]:
    """The installed readers, in the declared order (missing ones absent)."""
    return {key: _REGISTRY[key] for key in PORTRAIT_SOURCE_KEYS if key in _REGISTRY}


def assert_portrait_sources_complete() -> None:
    """Refuse a registry that does not offer every declared source.

    Raises:
        RuntimeError: Naming the missing keys.
    """
    missing = [key for key in PORTRAIT_SOURCE_KEYS if key not in _REGISTRY]
    if missing:
        raise RuntimeError(
            "the portrait would be blind to a record the person keeps — "
            f"portrait sources missing: {missing}"
        )


__all__ = [
    "ITEMS_BOUNDED_BY_SOURCE",
    "PORTRAIT_SOURCE_KEYS",
    "FreshnessProbe",
    "PortraitSourceReader",
    "PortraitSourceSection",
    "SectionStatus",
    "SourceBudget",
    "assert_portrait_sources_complete",
    "clamp_item",
    "empty_section",
    "install_portrait_source",
    "installed_portrait_sources",
    "portrait_lines",
]
