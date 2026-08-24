"""Apply the audited catalogue correction (ADR-244, Lot 0a).

Four operations, all derived from ``task llm:catalogue:sync`` and reviewed
before this migration was written:

1. the missing ``gpt-image-2`` row is created. ``llm_config_seed.sql`` pins the
   ``image_generation`` slot to it and ``image_generation_pricing_seed.sql``
   prices it, but ``llm_pricing_seed.sql`` never created its ``llm_models``
   row, so every instance resolved that slot to ``CONSERVATIVE_DEFAULT``;
2. capability fields of ``provenance='declared'`` rows are replaced by the
   registry values and the row becomes ``imported``;
3. ``deprecation_date`` is stamped from the snapshot, whatever the provenance:
   it records what the provider announced and no human curates it;
4. a model is deactivated only when ``is_retired`` holds — an uncontradicted
   published date already in the past — AND nothing references it: no
   ``llm_config_overrides`` row, no ``LLM_DEFAULTS`` entry, no constant. A
   referenced one stays active and is reported instead: deactivating it would
   drop it out of ``ModelCapabilitiesCache`` and fall back to
   ``CONSERVATIVE_DEFAULT``, whose ``is_reasoning_model=False`` makes the
   adapter send sampling parameters to a reasoning model.

The decision itself lives in ``sync_diff.plan_correction`` so the migration,
the CLI and the unit tests share one implementation. That is a deliberate
coupling between a frozen migration and evolving code: the alternative was a
third copy of "what counts as the same value". It is monitored rather than
assumed — ``task db:migrate:replay-check`` runs the whole chain against a
virgin database in CI, so a signature change breaks the build instead of a
deployment.

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-08-24 09:30:00.000000
"""

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a0b1c2d3e4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit
# F047). Use the Alembic logger with ASCII-only messages instead.
logger = logging.getLogger("alembic.runtime.migration")

_MISSING_ROW = sa.text(
    """
    INSERT INTO llm_models (
        id, provider, model_name, max_input_tokens, max_output_tokens,
        supports_tools, supports_structured_output, supports_strict_mode,
        supports_streaming, supports_vision, is_reasoning_model,
        supports_temperature, supports_top_p, supports_frequency_penalty,
        supports_presence_penalty, kind, reasoning_widget, is_active,
        capability_provenance, created_at, updated_at
    )
    VALUES (
        gen_random_uuid(), 'openai', 'gpt-image-2', 8192, 4096,
        true, true, false, true, false, false,
        true, true, true, true, 'image', 'none', true,
        'declared', NOW(), NOW()
    )
    ON CONFLICT (model_name) DO NOTHING
    """
)


def _referenced_models(bind: sa.engine.Connection) -> frozenset[str]:
    """Every model name something in this deployment points at."""
    from src.core.constants import FALLBACK_MODELS_DEFAULT, SUMMARIZATION_MODEL_DEFAULT
    from src.domains.llm_config.constants import LLM_DEFAULTS

    rows = bind.execute(
        sa.text("SELECT DISTINCT model FROM llm_config_overrides WHERE model IS NOT NULL")
    ).fetchall()
    names = {row[0] for row in rows}
    names.update(config.model for config in LLM_DEFAULTS.values() if config.model)
    names.add(SUMMARIZATION_MODEL_DEFAULT)
    names.update(part.strip() for part in FALLBACK_MODELS_DEFAULT.split(",") if part.strip())
    return frozenset(names)


def upgrade() -> None:
    """Create the missing row, correct declared rows, deactivate the retired."""
    from src.infrastructure.llm.catalogue.sync_diff import CatalogueRow, plan_correction

    bind = op.get_bind()
    inserted = bind.execute(_MISSING_ROW).rowcount

    rows = [
        CatalogueRow(
            model_name=r.model_name,
            provider=r.provider,
            kind=r.kind,
            max_input_tokens=r.max_input_tokens,
            max_output_tokens=r.max_output_tokens,
            supports_tools=r.supports_tools,
            supports_structured_output=r.supports_structured_output,
            supports_vision=r.supports_vision,
            provenance=r.capability_provenance,
            deprecation_date=r.deprecation_date,
            is_active=r.is_active,
        )
        for r in bind.execute(
            sa.text(
                "SELECT provider::text AS provider, model_name, kind::text AS kind, "
                "max_input_tokens, max_output_tokens, supports_tools, "
                "supports_structured_output, supports_vision, "
                "capability_provenance::text AS capability_provenance, "
                "deprecation_date, is_active FROM llm_models WHERE is_active"
            )
        ).fetchall()
    ]

    plan = plan_correction(
        rows,
        today=datetime.now(UTC).date(),
        referenced=_referenced_models(bind),
    )

    corrected = promoted = stamped = deactivated = kept = 0
    for correction in plan:
        updates: dict[str, object] = dict(correction.capability_updates)
        if correction.set_provenance is not None:
            updates["capability_provenance"] = correction.set_provenance
        if updates:
            # The column names are interpolated, the values are bound. The keys
            # can only come from CORRECTABLE_FIELDS plus the literal
            # ``capability_provenance`` -- a frozen tuple in code, never input.
            assignments = ", ".join(f"{column} = :{column}" for column in updates)
            bind.execute(
                sa.text(f"UPDATE llm_models SET {assignments} WHERE model_name = :model_name"),
                {**updates, "model_name": correction.model_name},
            )
            if correction.capability_updates:
                corrected += 1
            else:
                promoted += 1
        if correction.deprecation_date is not None:
            bind.execute(
                sa.text(
                    "UPDATE llm_models SET deprecation_date = :value WHERE model_name = :model_name"
                ),
                {"value": correction.deprecation_date, "model_name": correction.model_name},
            )
            stamped += 1
        if correction.deactivate:
            bind.execute(
                sa.text("UPDATE llm_models SET is_active = false WHERE model_name = :model_name"),
                {"model_name": correction.model_name},
            )
            deactivated += 1
        if correction.kept_because_referenced:
            kept += 1
            logger.warning(
                "catalogue correction: %s is retired but referenced - kept active",
                correction.model_name,
            )

    logger.info(
        "catalogue correction: rows=%d inserted=%d corrected=%d promoted=%d stamped=%d "
        "deactivated=%d kept_because_referenced=%d",
        len(rows),
        inserted,
        corrected,
        promoted,
        stamped,
        deactivated,
        kept,
    )


def downgrade() -> None:
    """Reverse only what is reversible: provenance and activation.

    Capability values are not restored - the pre-migration values were column
    defaults, and re-installing a known-wrong 8192 would be a regression, not a
    rollback. The inserted ``gpt-image-2`` row is not removed either: the
    configuration seed names it, so dropping it would recreate the orphan this
    migration exists to close.
    """
    op.execute(
        sa.text(
            "UPDATE llm_models SET capability_provenance = 'declared' "
            "WHERE capability_provenance = 'imported'"
        )
    )
    op.execute(
        sa.text("UPDATE llm_models SET is_active = true WHERE deprecation_date IS NOT NULL")
    )
