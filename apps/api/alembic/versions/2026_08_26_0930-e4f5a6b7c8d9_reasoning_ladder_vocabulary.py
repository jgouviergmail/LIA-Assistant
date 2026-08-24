"""Make the catalogue's declared ladders speak the intent vocabulary (ADR-245).

``llm_models.reasoning_enum_values`` is the ONE catalogue value the reasoning
resolution still reads: it NARROWS the family's ladder. So it has to be written
in that ladder's vocabulary, and four rows were not -- they declared ``off``,
the pre-ADR-245 sentinel:

    claude-opus-4-6, claude-sonnet-4-6   ["off", "low", "medium", "high", "max"]
    deepseek-v4-flash, deepseek-v4-pro   ["off", "high", "max"]

Nothing was visibly broken, and that is the interesting part. The narrowing is
an intersection, so ``("none","high","max")`` narrowed by ``{"off","high",
"max"}`` gave ``("high","max")`` -- a ladder with no off switch -- and the only
reason an operator could still turn reasoning off is that ``can_disable``, not
ladder membership, governs that (the rule this lot exists to establish). The row
was nevertheless declaring a level that does not exist, the admin catalogue
displayed it, and the next reader of that column would have inherited the trap.

Mapped with ``intent_from_legacy`` -- the same function the stored values, the
reference seeds and the golden proof go through, so the catalogue cannot end up
disagreeing with them about what ``off`` meant.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-26 09:30:00.000000
"""

import json
import logging
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4f5a6b7c8d9"
down_revision: str | None = "d3e4f5a6b7c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# print() raises UnicodeEncodeError under a CP1252 Windows console (audit F047).
logger = logging.getLogger("alembic.runtime.migration")


def _canonical(ladder: list[str]) -> list[str]:
    """Map a declared ladder onto the intent vocabulary, order and dupes handled."""
    from src.core.reasoning_intent import intent_from_legacy

    mapped: list[str] = []
    for level in ladder:
        canonical = intent_from_legacy({"effort": level}).level
        if canonical not in mapped:
            mapped.append(canonical)
    return mapped


def upgrade() -> None:
    """Rewrite every declared ladder that does not already speak the vocabulary."""
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, model_name, reasoning_enum_values FROM llm_models "
            "WHERE reasoning_enum_values IS NOT NULL"
        )
    ).fetchall()

    rewritten = 0
    for row_id, model_name, declared in rows:
        if not isinstance(declared, list):
            continue
        canonical = _canonical([str(level) for level in declared])
        if canonical == declared:
            continue
        bind.execute(
            sa.text(
                "UPDATE llm_models SET reasoning_enum_values = CAST(:value AS jsonb) "
                "WHERE id = :row_id"
            ),
            {"value": json.dumps(canonical), "row_id": row_id},
        )
        logger.info("reasoning ladder normalised: %s %s -> %s", model_name, declared, canonical)
        rewritten += 1

    logger.info("reasoning ladder vocabulary: rewritten=%d rows=%d", rewritten, len(rows))


def downgrade() -> None:
    """Nothing to undo: the mapping is not injective.

    ``off`` and ``none`` both mean "no reasoning", so restoring ``off`` would
    guess which rows used to spell it that way. The canonical value is accepted
    by the pre-ADR-245 code as well -- ``none`` was already a legal enum member
    on the OpenAI rows -- so leaving it in place is both safe and honest.
    """
