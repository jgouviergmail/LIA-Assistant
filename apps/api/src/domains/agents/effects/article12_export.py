"""One extraction over everything LIA records (ADR-263, lot 9).

Article 12 asks for records that can be read as a whole. LIA holds five, and
each already has a contract: what it may show, what it must never show, and
what it can be asked. This module composes them; it renders nothing new.

The file is JSON Lines with a ``lia_record`` discriminator on every line, because
the five sources answer five different questions and **must never be added up**:

- ``lia.decisions`` — one line per TURN;
- ``lia.actions`` — one line per external EFFECT;
- ``lia.consultations`` — one line per capability CONSULTED;
- ``lia.inference`` — one line per LLM CALL;
- ``lia.integrity`` — one line per GAP in the record itself.

The discriminator is namespaced, and that is not decoration: the integrity
register has a business column literally called ``kind``, which silently
overwrote a plain discriminator the first time this file was rendered against
real rows. A key that belongs to the FILE must be immune to every source column
name, including the ones a sixth record will bring. A guard pins it.

Two properties it inherits rather than reimplements: every identifier is
pseudonymised with the same key across all five, so correlation survives and
identity does not; and every column is an allowlist, so a column added tomorrow
is absent until someone classifies it.

One property it owes on its own: the ceiling is **per source and stated**. A
file that silently held five thousand of eight thousand turns would be read as
a complete account of a period it only samples.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final

from src.domains.agents.effects.technical_export import (
    TECHNICAL_SPECS,
    TechnicalSpec,
    _stated_filters,
    pseudonymise,
    technical_row,
)

#: Reader of one source, in the shape all five already offer.
SourceReader = Callable[..., Awaitable[list[Any]]]

#: The key that says which record a line belongs to. Namespaced so no source
#: column can shadow it — ``kind`` did, on the very first render against real
#: rows, because the integrity register has a column by that name.
RECORD_KEY: Final[str] = "lia_record"


@dataclass(frozen=True)
class SourceExtract:
    """What one source contributed, and whether it was complete.

    Attributes:
        spec: The source's contract.
        rows: Its exported rows.
        capped: Whether the ceiling truncated it — stated per source, because a
            file complete in four of five is not a complete file.
    """

    spec: TechnicalSpec
    rows: list[dict[str, Any]]
    capped: bool


def extract_of(spec: TechnicalSpec, rows: list[Any], *, cap: int) -> SourceExtract:
    """Shape one source's rows through its own contract.

    Args:
        spec: The source's contract.
        rows: What its repository returned.
        cap: The ceiling that was applied to the read.

    Returns:
        The extract. ``capped`` is true when the read came back full, which is
        the only honest way to say « there may be more ».
    """
    return SourceExtract(
        spec=spec,
        rows=[technical_row(row, spec) for row in rows],
        capped=len(rows) >= cap,
    )


def article12_header(
    extracts: list[SourceExtract],
    *,
    cap: int,
    filters: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """The context line the extraction opens with.

    It names the five sources, what each one may show, how many lines each
    contributed and whether any of them hit the ceiling. A reader must be able
    to answer « is this the whole period? » from the header alone.

    Args:
        extracts: The five sources' contributions.
        cap: The per-source ceiling.
        filters: What the operator asked for; identifiers are pseudonymised
            with the same key as the rows.
        generated_at: Override for the timestamp, for tests.

    Returns:
        The header mapping.
    """
    return {
        RECORD_KEY: "lia.article12",
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        "pseudonymised": True,
        "identifiers": "HMAC-SHA256 keyed by the instance secret, truncated",
        "filters": _stated_filters(filters),
        "cap_per_source": cap,
        # Stated per source: they answer different questions and never add up,
        # so one total would invite exactly the arithmetic the registers refuse.
        "sources": {
            extract.spec.slug: {
                "lines": len(extract.rows),
                "truncated": extract.capped,
                "columns": [*extract.spec.exported, "user"],
                "excluded_columns": sorted(extract.spec.forbidden),
            }
            for extract in extracts
        },
        "complete": not any(extract.capped for extract in extracts),
    }


def render_article12(
    extracts: list[SourceExtract],
    *,
    cap: int,
    filters: dict[str, Any],
    generated_at: datetime | None = None,
) -> str:
    """Render the whole extraction as JSON Lines.

    Args:
        extracts: The five sources' contributions.
        cap: The per-source ceiling.
        filters: What the operator asked for.
        generated_at: Override for the timestamp, for tests.

    Returns:
        The file content: one header line, then one line per row, each carrying
        the ``kind`` that says which record it belongs to.
    """
    import json

    header = article12_header(extracts, cap=cap, filters=filters, generated_at=generated_at)
    lines = [json.dumps(header, ensure_ascii=False, sort_keys=True)]
    for extract in extracts:
        record = f"lia.{extract.spec.slug}"
        lines.extend(
            json.dumps({**row, RECORD_KEY: record}, ensure_ascii=False, sort_keys=True)
            for row in extract.rows
        )
    return "\n".join(lines) + "\n"


def article12_filters(
    *,
    since: datetime | None,
    until: datetime | None,
    user_ids: list[uuid.UUID] | None,
) -> dict[str, Any]:
    """What the extraction says was asked of it.

    Args:
        since: Inclusive lower bound.
        until: Exclusive upper bound.
        user_ids: The accounts covered, or None for every one of them.

    Returns:
        The stated filters. Account ids are pseudonymised downstream, with the
        same key as the rows — an extraction that promised « pseudonymised by
        construction » and printed a raw id in its own header would be exactly
        the defect lot 4 found.
    """
    return {
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
        "user_ids": [str(one) for one in user_ids] if user_ids else None,
    }


def known_sources() -> tuple[TechnicalSpec, ...]:
    """Every contract the extraction covers, in reading order.

    Read from the registry rather than listed here: a sixth record declared
    tomorrow joins the extraction without anyone remembering to add it, which
    is the whole reason the contracts live in one place.

    Returns:
        The specs, decisions first — the turn is the spine the others hang off.
    """
    order = ("decisions", "actions", "consultations", "inference", "integrity")
    return tuple(TECHNICAL_SPECS[slug] for slug in order if slug in TECHNICAL_SPECS) + tuple(
        spec for slug, spec in sorted(TECHNICAL_SPECS.items()) if slug not in order
    )


__all__ = [
    "RECORD_KEY",
    "SourceExtract",
    "article12_filters",
    "article12_header",
    "extract_of",
    "known_sources",
    "pseudonymise",
    "render_article12",
]
