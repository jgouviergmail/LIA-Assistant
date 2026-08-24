"""Compute a reviewable diff between the catalogue and the vendored snapshot.

Severity, not silence:

- ``auto``   — the row's provenance is ``declared`` (column defaults nobody
  curated). Applying the registry value can lose no human decision.
- ``review`` — the row is ``imported`` or ``verified``. A human decided; the
  sync may only propose.

Prices, reasoning metadata, streaming and ``kind`` are never examined — see
:mod:`src.infrastructure.llm.catalogue.field_mapping` for each exclusion and
the measurement behind it. Nothing here writes to the database:
``task llm:catalogue:sync`` prints the diff and the initial correction ships
as a versioned migration.

This module holds the pure logic on purpose. It has three consumers — the
developer CLI, this package's tests and the initial-correction migration — so
a copy in ``scripts/`` would be a third authority on what "the same value"
means, outside MyPy's and Ruff's reach (``task lint:backend`` runs on
``src tests`` only).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.core.constants import (
    CAPABILITY_PROVENANCE_DECLARED,
    CAPABILITY_PROVENANCE_IMPORTED,
)
from src.infrastructure.llm.catalogue.field_mapping import (
    RegistryFacts,
    is_retired,
    registry_facts,
)

#: Catalogue column -> the ``RegistryFacts`` attribute that may correct it.
COMPARED_FIELDS: tuple[tuple[str, str], ...] = (
    ("max_input_tokens", "max_input_tokens"),
    ("max_output_tokens", "max_output_tokens"),
    ("supports_tools", "supports_tools"),
    ("supports_structured_output", "supports_structured_output"),
    ("supports_vision", "supports_vision"),
    ("deprecation_date", "deprecation_date"),
)

#: Columns the initial correction may write on a ``declared`` row. Narrower
#: than :data:`COMPARED_FIELDS`: ``deprecation_date`` is stamped on EVERY row
#: whatever its provenance, because it records what the provider announced and
#: no human curates it.
CORRECTABLE_FIELDS: tuple[tuple[str, str], ...] = tuple(
    pair for pair in COMPARED_FIELDS if pair[0] != "deprecation_date"
)


def _is_curated(provenance: str) -> bool:
    """Whether something other than the column defaults filled this row.

    ``declared`` is the ONLY permissive value, checked positively: an
    unrecognised provenance must fall on the conservative side and be proposed
    to a human rather than silently overwritten (ADR-085 — a fallback on an
    unknown key is how a feature dies invisibly).
    """
    return provenance != CAPABILITY_PROVENANCE_DECLARED


@dataclass(frozen=True)
class CatalogueRow:
    """One ``llm_models`` row, reduced to what the diff compares."""

    model_name: str
    provider: str
    kind: str
    max_input_tokens: int
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    provenance: str
    deprecation_date: date | None
    is_active: bool


@dataclass(frozen=True)
class FieldChange:
    """One proposed correction."""

    model_name: str
    provider: str
    field: str
    current: object
    proposed: object
    source: str
    severity: str


def compute_diff(rows: list[CatalogueRow]) -> list[FieldChange]:
    """Compare every row against the vendored snapshot.

    Args:
        rows: The catalogue rows to examine.

    Returns:
        One :class:`FieldChange` per differing field, in row order then in
        :data:`COMPARED_FIELDS` order.
    """
    changes: list[FieldChange] = []
    for row in rows:
        facts = registry_facts(row.provider, row.model_name, kind=row.kind)
        if facts is None:
            continue
        severity = "review" if _is_curated(row.provenance) else "auto"
        for column, attribute in COMPARED_FIELDS:
            proposed = getattr(facts, attribute)
            if proposed is None:
                continue
            current = getattr(row, column)
            if current == proposed:
                continue
            changes.append(
                FieldChange(
                    model_name=row.model_name,
                    provider=row.provider,
                    field=column,
                    current=current,
                    proposed=proposed,
                    source=facts.sources.get(attribute, "?"),
                    severity=severity,
                )
            )
    return changes


@dataclass(frozen=True)
class RowCorrection:
    """What the initial correction must do to one catalogue row.

    Attributes:
        model_name: The row's model name.
        capability_updates: Column -> value, empty when nothing changes.
        set_provenance: ``"imported"`` when capabilities were rewritten, else
            ``None`` (a curated row keeps its provenance).
        deprecation_date: The registry date to stamp, or ``None`` when the row
            already carries it or the registry publishes none.
        deactivate: Whether the row may stop being offered.
        kept_because_referenced: The row is retired but something names it, so
            it stays active and gets reported instead.
    """

    model_name: str
    capability_updates: dict[str, object]
    set_provenance: str | None
    deprecation_date: date | None
    deactivate: bool
    kept_because_referenced: bool


def _capability_updates(row: CatalogueRow, facts: RegistryFacts) -> tuple[dict[str, object], bool]:
    """Return the columns to rewrite and whether the registry corroborated any.

    The two answers are separate on purpose: a row whose values already match
    needs no UPDATE but must still stop calling itself ``declared``.
    """
    updates: dict[str, object] = {}
    corroborated = False
    for column, attribute in CORRECTABLE_FIELDS:
        value = getattr(facts, attribute)
        if value is None:
            continue
        corroborated = True
        if getattr(row, column) != value:
            updates[column] = value
    return updates, corroborated


def _correction_for(
    row: CatalogueRow, *, today: date, referenced: frozenset[str]
) -> RowCorrection | None:
    """Decide what one row needs, or ``None`` when it needs nothing."""
    facts = registry_facts(row.provider, row.model_name, kind=row.kind)
    if facts is None:
        return None

    curated = _is_curated(row.provenance)
    updates, corroborated = ({}, False) if curated else _capability_updates(row, facts)

    stamp = facts.deprecation_date if facts.deprecation_date != row.deprecation_date else None
    retired = is_retired(facts, today=today)
    kept = retired and row.model_name in referenced

    # Provenance follows CORROBORATION, not change. A row whose values already
    # matched the registry needs no UPDATE but must still stop calling itself
    # ``declared``: ``get_effective_context_window`` trusts only a non-declared
    # row, so leaving it declared makes the runtime fall back to
    # MODEL_CONTEXT_WINDOWS, which is wrong on 10 of its 56 entries. Measured
    # 2026-08-24: 15 rows were in that state, including ``deepseek-v4-flash``,
    # the model the ``response`` slot runs on.
    promote = corroborated and not curated
    if not updates and not promote and stamp is None and not retired:
        return None
    return RowCorrection(
        model_name=row.model_name,
        capability_updates=updates,
        set_provenance=CAPABILITY_PROVENANCE_IMPORTED if promote else None,
        deprecation_date=stamp,
        deactivate=retired and not kept,
        kept_because_referenced=kept,
    )


def plan_correction(
    rows: list[CatalogueRow],
    *,
    today: date,
    referenced: frozenset[str],
) -> list[RowCorrection]:
    """Decide, for every row, what the initial correction writes.

    Pure on purpose: the migration executes this plan and the tests exercise
    it directly, so the decision has one implementation and does not need a
    seeded database to be verified.

    Three rules, each measured (see the design spec and the plan amendments):

    1. capability columns are rewritten only on a ``declared`` row — a curated
       row is proposed to a human, never overwritten;
    2. ``deprecation_date`` is stamped whatever the provenance: it records what
       the provider announced and no human curates it;
    3. a row is deactivated only when :func:`is_retired` holds — an
       uncontradicted date already in the past — AND nothing references it.
       Deactivating a referenced model drops it out of
       ``ModelCapabilitiesCache`` and falls back to ``CONSERVATIVE_DEFAULT``,
       whose ``is_reasoning_model=False`` makes the adapter send sampling
       parameters to a reasoning model.

    Args:
        rows: The active catalogue rows.
        today: Reference date (timezone-aware UTC date at the call site).
        referenced: Model names named by ``llm_config_overrides``,
            ``LLM_DEFAULTS`` or a constant.

    Returns:
        One :class:`RowCorrection` per row that needs something done, in row
        order.
    """
    planned = (_correction_for(row, today=today, referenced=referenced) for row in rows)
    return [correction for correction in planned if correction is not None]
