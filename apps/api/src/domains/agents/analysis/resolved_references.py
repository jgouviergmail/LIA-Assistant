"""The turn's resolved references, and what each resolved VALUE is.

Two producers resolve references before planning: the memory resolver
(relational references such as « mon frère », from the person's memories — a
name, or an address for a location query) and the query analyzer (pronouns,
dates, earlier results, places). Their outputs used to be merged into a flat
``{reference: value}`` dict that lost what each value IS, and every reader
guessed: the semantic parameter guard read every value as a person's name and
blocked a places search on the city the person asked about (2026-10-11).

This module is the ONE place where the references are merged, read back from a
checkpoint, classified and rendered (ADR-120 amendment 2026-10-11). Each
producer DECLARES what its value is; a declaration nobody can read falls back to
what that producer meant before kinds existed. It imports the standard library
only, so the analysis, semantic and services layers can all depend on it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import assert_never

__all__ = [
    "AnalyzerReferenceType",
    "ReferenceSource",
    "ReferenceValueKind",
    "ResolvedReferenceEntry",
    "as_mapping",
    "fold_value",
    "kind_of_reference_type",
    "merge_resolved_references",
    "parse_reference_type",
    "parse_value_kind",
    "person_name_values",
    "read_resolved_references",
    "render_reference_lines",
]


class ReferenceValueKind(StrEnum):
    """What a resolved VALUE is — never what the reference was."""

    PERSON_NAME = "person_name"
    POSTAL_ADDRESS = "postal_address"
    PLACE = "place"
    DATETIME = "datetime"
    OTHER = "other"


class AnalyzerReferenceType(StrEnum):
    """What the query analyzer declares a resolved value to be (its ``type`` field)."""

    PERSON = "person"
    PLACE = "place"
    TEMPORAL = "temporal"
    CONTEXTUAL = "contextual"


class ReferenceSource(StrEnum):
    """Which producer resolved the reference."""

    MEMORY = "memory"
    ANALYZER = "analyzer"
    LEGACY = "legacy"


#: Kinds naming a location: a value declared one of them this turn is never a
#: person's name, whoever else declared it (a genuine homonym fails open).
_LOCATION_KINDS = frozenset({ReferenceValueKind.POSTAL_ADDRESS, ReferenceValueKind.PLACE})


def fold_value(text: str) -> str:
    """Whitespace-collapsed, case-folded form used for every value comparison.

    Args:
        text: A resolved value or a tool argument.

    Returns:
        The folded text.
    """
    return " ".join(text.split()).casefold()


def _parse_member[E: StrEnum](vocabulary: type[E], raw: object, default: E) -> E:
    """A vocabulary member read forgivingly — anything else is ``default``."""
    if isinstance(raw, vocabulary):
        return raw
    if isinstance(raw, str):
        try:
            return vocabulary(raw.strip().lower())
        except ValueError:
            return default
    return default


def parse_value_kind(raw: object, *, default: ReferenceValueKind) -> ReferenceValueKind:
    """Read a declared value kind; a producer's typo is never a failure.

    Args:
        raw: The declared kind (any shape a model or a checkpoint may hold).
        default: The kind to use when ``raw`` is not in the vocabulary.

    Returns:
        The declared kind, or ``default``.
    """
    return _parse_member(ReferenceValueKind, raw, default)


def parse_reference_type(raw: object) -> AnalyzerReferenceType:
    """Read the analyzer's declared type; anything outside the vocabulary is ``contextual``.

    Args:
        raw: The declared type.

    Returns:
        The type.
    """
    return _parse_member(AnalyzerReferenceType, raw, AnalyzerReferenceType.CONTEXTUAL)


def kind_of_reference_type(reference_type: AnalyzerReferenceType) -> ReferenceValueKind:
    """The value kind an analyzer type declares — exhaustive by construction.

    Args:
        reference_type: The analyzer's type.

    Returns:
        The kind (MyPy refuses a member this match forgets).
    """
    match reference_type:
        case AnalyzerReferenceType.PERSON:
            return ReferenceValueKind.PERSON_NAME
        case AnalyzerReferenceType.PLACE:
            return ReferenceValueKind.PLACE
        case AnalyzerReferenceType.TEMPORAL:
            return ReferenceValueKind.DATETIME
        case AnalyzerReferenceType.CONTEXTUAL:
            return ReferenceValueKind.OTHER
        case _:
            assert_never(reference_type)


def _clean(raw: object) -> str | None:
    """A non-blank string, stripped; anything else is ``None``."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


@dataclass(frozen=True, slots=True)
class ResolvedReferenceEntry:
    """One reference resolved this turn.

    Attributes:
        reference: The words of the query (« mon frère », « demain »).
        value: What they resolved to.
        kind: What the value IS.
        source: Which producer resolved it.
    """

    reference: str
    value: str
    kind: ReferenceValueKind
    source: ReferenceSource

    def to_dict(self) -> dict[str, str]:
        """Checkpoint-safe form (msgpack carries plain strings only)."""
        return {
            "reference": self.reference,
            "value": self.value,
            "kind": self.kind.value,
            "source": self.source.value,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> ResolvedReferenceEntry | None:
        """Rebuild an entry from its checkpoint form, forgivingly.

        Args:
            data: A dict written by :meth:`to_dict` (or something that claims to be).

        Returns:
            The entry, or None when its reference or value is unusable.
        """
        reference, value = _clean(data.get("reference")), _clean(data.get("value"))
        if reference is None or value is None:
            return None
        return cls(
            reference=reference,
            value=value,
            kind=parse_value_kind(data.get("kind"), default=ReferenceValueKind.OTHER),
            source=_parse_member(ReferenceSource, data.get("source"), ReferenceSource.LEGACY),
        )


def merge_resolved_references(
    memory_mappings: Mapping[str, object] | None,
    memory_kinds: Mapping[str, object] | None,
    analyzer_references: Sequence[Mapping[str, object]] | None,
) -> tuple[ResolvedReferenceEntry, ...]:
    """Merge both producers into one ordered, typed tuple.

    Memory comes first and wins on a shared reference (it is the dedicated
    resolver). A memory mapping that declares no readable kind is a person's
    name — the resolver's scope is relational references, an address is only
    ever declared (prompt rule 6). An analyzer reference is typed by its
    ``type`` (unreadable → ``contextual``). A value already present with the
    same kind (« mon frère » / "my brother", resolved in two languages) is kept
    once; within one producer the first occurrence wins. Unusable items are
    dropped.

    Args:
        memory_mappings: The memory resolver's ``{reference: value}``.
        memory_kinds: The memory resolver's ``{reference: kind}``.
        analyzer_references: The analyzer's ``[{original, resolved, type}]``.

    Returns:
        The turn's references.
    """
    entries: list[ResolvedReferenceEntry] = []
    seen_references: set[str] = set()
    seen_values: set[tuple[str, ReferenceValueKind]] = set()

    def add(entry: ResolvedReferenceEntry) -> None:
        key = (fold_value(entry.value), entry.kind)
        if entry.reference in seen_references or key in seen_values:
            return
        seen_references.add(entry.reference)
        seen_values.add(key)
        entries.append(entry)

    kinds = memory_kinds or {}
    for raw_reference, raw_value in (memory_mappings or {}).items():
        reference, value = _clean(raw_reference), _clean(raw_value)
        if reference is None or value is None:
            continue
        kind = parse_value_kind(kinds.get(raw_reference), default=ReferenceValueKind.PERSON_NAME)
        add(ResolvedReferenceEntry(reference, value, kind, ReferenceSource.MEMORY))
    for item in analyzer_references or ():
        reference, value = _clean(item.get("original")), _clean(item.get("resolved"))
        if reference is None or value is None:
            continue
        kind = kind_of_reference_type(parse_reference_type(item.get("type")))
        add(ResolvedReferenceEntry(reference, value, kind, ReferenceSource.ANALYZER))
    return tuple(entries)


def read_resolved_references(raw: object) -> tuple[ResolvedReferenceEntry, ...]:
    """Read the references back from a checkpointed QueryIntelligence value.

    Accepts the typed list :meth:`ResolvedReferenceEntry.to_dict` writes, and the
    flat ``{reference: value}`` dict written before kinds existed — read as
    ``legacy``/``other``, so a turn resumed across the upgrade never guards on a
    value nobody typed. Anything else is no reference: a malformed checkpoint
    never raises here.

    Args:
        raw: The checkpointed value.

    Returns:
        The references, possibly empty.
    """
    if isinstance(raw, Mapping):
        legacy: list[ResolvedReferenceEntry] = []
        for raw_reference, raw_value in raw.items():
            reference, value = _clean(raw_reference), _clean(raw_value)
            if reference is not None and value is not None:
                legacy.append(
                    ResolvedReferenceEntry(
                        reference, value, ReferenceValueKind.OTHER, ReferenceSource.LEGACY
                    )
                )
        return tuple(legacy)
    if isinstance(raw, list | tuple):
        parsed = (
            ResolvedReferenceEntry.from_dict(item) for item in raw if isinstance(item, Mapping)
        )
        return tuple(entry for entry in parsed if entry is not None)
    return ()


def as_mapping(entries: Sequence[ResolvedReferenceEntry]) -> dict[str, str]:
    """The ``{reference: value}`` view (debug panel contract)."""
    return {entry.reference: entry.value for entry in entries}


def person_name_values(entries: Sequence[ResolvedReferenceEntry]) -> tuple[str, ...]:
    """The values this turn resolved to a PERSON's name — the one predicate.

    A value counts when its producer declared it a person's name, unless any
    producer declared the same value a place or an address this turn.

    Args:
        entries: The turn's references.

    Returns:
        The person names, in order, without duplicates.
    """
    locations = {fold_value(entry.value) for entry in entries if entry.kind in _LOCATION_KINDS}
    names: dict[str, None] = {}
    for entry in entries:
        if (
            entry.kind is ReferenceValueKind.PERSON_NAME
            and fold_value(entry.value) not in locations
        ):
            names.setdefault(entry.value, None)
    return tuple(names)


def render_reference_lines(entries: Sequence[ResolvedReferenceEntry]) -> str:
    """One prompt line per reference: ``- "reference" = value [kind]``.

    The tag is the vocabulary value itself (technical English, explained by the
    prompt file that wraps it); ``other`` carries no tag. Each reference and
    value is collapsed to one line: a value holding a line break could
    otherwise forge a reference line of its own in the prompt.

    Args:
        entries: The turn's references.

    Returns:
        The lines, or an empty string.
    """
    lines = []
    for entry in entries:
        tag = "" if entry.kind is ReferenceValueKind.OTHER else f" [{entry.kind.value}]"
        reference, value = " ".join(entry.reference.split()), " ".join(entry.value.split())
        lines.append(f'- "{reference}" = {value}{tag}')
    return "\n".join(lines)
