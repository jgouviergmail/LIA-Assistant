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

One property it owes on its own: **it is complete, per source, and it says so**
(ADR-273). It used to hold a per-source ceiling — a file that silently held
five thousand of eight thousand turns reads as a complete account of a period
it only samples — and the ceiling is gone rather than merely stated: the rows
are streamed under a header whose per-source counts are exact, so the reader
answers « is this the whole period? » from the header and gets « yes ».
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
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

#: The key that says which record a line belongs to. Namespaced so no source
#: column can shadow it — ``kind`` did, on the very first render against real
#: rows, because the integrity register has a column by that name.
RECORD_KEY: Final[str] = "lia_record"


@dataclass(frozen=True)
class SourceStream:
    """One source's contribution to the extraction.

    Attributes:
        spec: The source's contract.
        total: How many rows it holds for the period — counted over the same
            statement :attr:`rows` walks, because the header goes out before
            the first row and a streamed file cannot revise its own first line.
        rows: Its rows, produced progressively.
    """

    spec: TechnicalSpec
    total: int
    rows: AsyncIterator[Any]


def article12_header(
    sources: list[SourceStream],
    *,
    filters: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """The context line the extraction opens with.

    It names the five sources, what each one may show and how many lines each
    contributes. A reader must be able to answer « is this the whole period? »
    from the header alone — and since ADR-273 the answer is always yes, stated
    rather than implied.

    Args:
        sources: The five sources, each with its exact total.
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
        # Stated per source: they answer different questions and never add up,
        # so one total would invite exactly the arithmetic the registers refuse.
        "sources": {
            source.spec.slug: {
                "lines": source.total,
                "truncated": False,
                "columns": [*source.spec.exported, "user"],
                "excluded_columns": sorted(source.spec.forbidden),
            }
            for source in sources
        },
        "complete": True,
    }


async def stream_article12(
    sources: list[SourceStream],
    *,
    filters: dict[str, Any],
    generated_at: datetime | None = None,
) -> AsyncIterator[str]:
    """Render the whole extraction as JSON Lines, as the rows arrive.

    Args:
        sources: The five sources, each with its exact total and its rows.
        filters: What the operator asked for.
        generated_at: Override for the timestamp, for tests.

    Yields:
        One line at a time: the header, then one line per row, each carrying
        the ``lia_record`` that says which record it belongs to. The sources
        are read in order, so a reader can stop at the record they wanted.
    """
    import json

    header = article12_header(sources, filters=filters, generated_at=generated_at)
    yield json.dumps(header, ensure_ascii=False, sort_keys=True) + "\n"
    for source in sources:
        record = f"lia.{source.spec.slug}"
        async for row in source.rows:
            shaped = {**technical_row(row, source.spec), RECORD_KEY: record}
            yield json.dumps(shaped, ensure_ascii=False, sort_keys=True) + "\n"


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
    "SourceStream",
    "article12_filters",
    "article12_header",
    "known_sources",
    "pseudonymise",
    "stream_article12",
]
