"""What the vendored registries say about this catalogue, right now.

One computation, three readers: the ``task llm:catalogue:sync`` CLI, the admin
API, and the tests. It answers the question an operator asks in front of the
catalogue screen — *how much of this was measured, and what is about to
retire?* — without writing anything.

The verdict itself is not computed here: ``sync_diff.compute_diff`` and
``field_mapping.is_retiring`` / ``is_retired`` remain the single implementations
of "what would change" and "what is going away". This module only assembles
their output into one reportable shape, so the CLI and the screen can never
disagree about the state of the same database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from src.infrastructure.llm.catalogue.field_mapping import (
    is_retired,
    is_retiring,
    registry_facts,
)
from src.infrastructure.llm.catalogue.snapshot_loader import snapshot_generated_at
from src.infrastructure.llm.catalogue.sync_diff import CatalogueRow, compute_diff

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.domains.llm.models import LLMModel

#: Retirement states, from the strongest evidence to the weakest. They are not
#: severities: ``disputed`` means the registries do not agree that the date has
#: passed, which is precisely why the model is still offered (ADR-244 measured
#: 4 such contradictions, including two rolling OpenAI aliases).
RETIREMENT_STATES = ("retired", "disputed", "announced", "flagged")


@dataclass(frozen=True)
class RetiringModel:
    """One model the registries report as going away, and on what evidence."""

    model_name: str
    provider: str
    state: str
    deprecation_date: date | None
    seen_by: tuple[str, ...]


@dataclass(frozen=True)
class CatalogueStatus:
    """The whole read-only verdict, ready to print or to serialise."""

    compared: int
    auto: int
    review: int
    retiring: tuple[RetiringModel, ...]
    provenance: dict[str, int]
    snapshot_generated_at: datetime | None


def rows_from_models(models: list[LLMModel]) -> list[CatalogueRow]:
    """Reduce ORM rows to what the diff compares.

    Shared with the CLI so a column added to the comparison is added once.
    """
    return [
        CatalogueRow(
            model_name=model.model_name,
            provider=model.provider.value,
            kind=model.kind.value,
            max_input_tokens=model.max_input_tokens,
            max_output_tokens=model.max_output_tokens,
            supports_tools=model.supports_tools,
            supports_structured_output=model.supports_structured_output,
            supports_vision=model.supports_vision,
            provenance=model.capability_provenance.value,
            deprecation_date=model.deprecation_date,
            is_active=model.is_active,
        )
        for model in models
    ]


def _retirement_state(facts_date: date | None, gone: bool, today: date) -> str:
    """Name the evidence behind a retirement, not its severity."""
    if gone:
        return "retired"
    if facts_date is not None and facts_date < today:
        return "disputed"
    if facts_date is not None:
        return "announced"
    return "flagged"


def status_from_rows(rows: list[CatalogueRow], *, today: date | None = None) -> CatalogueStatus:
    """Assemble the verdict for an already-loaded set of rows.

    Args:
        rows: The catalogue rows to examine.
        today: Reference date; defaults to the current UTC date. Injected so a
            test can pin a retirement horizon instead of drifting with the
            clock (the rule reads a published date, not "now").

    Returns:
        The counters, the retirement list and the provenance breakdown.
    """
    reference = today or datetime.now(UTC).date()
    changes = compute_diff(rows)

    retiring: list[RetiringModel] = []
    provenance: dict[str, int] = {}
    for row in rows:
        provenance[row.provenance] = provenance.get(row.provenance, 0) + 1
        facts = registry_facts(row.provider, row.model_name, kind=row.kind)
        if facts is None or not is_retiring(facts, today=reference):
            continue
        retiring.append(
            RetiringModel(
                model_name=row.model_name,
                provider=row.provider,
                state=_retirement_state(
                    facts.deprecation_date, is_retired(facts, today=reference), reference
                ),
                deprecation_date=facts.deprecation_date,
                seen_by=tuple(sorted(facts.matched_registries)),
            )
        )

    return CatalogueStatus(
        compared=len(rows),
        auto=sum(1 for change in changes if change.severity == "auto"),
        review=sum(1 for change in changes if change.severity == "review"),
        retiring=tuple(sorted(retiring, key=lambda entry: entry.model_name)),
        provenance=provenance,
        snapshot_generated_at=snapshot_generated_at(),
    )


async def catalogue_status(db: AsyncSession, *, today: date | None = None) -> CatalogueStatus:
    """Load the active catalogue and report what the registries say about it.

    Args:
        db: An open session.
        today: Reference date, forwarded to :func:`status_from_rows`.

    Returns:
        The read-only verdict. Nothing is written, by construction: this module
        imports no writer.
    """
    from sqlalchemy import select

    from src.domains.llm.models import LLMModel

    models = list((await db.execute(select(LLMModel).where(LLMModel.is_active))).scalars().all())
    return status_from_rows(rows_from_models(models), today=today)
