"""JEV's durable statistics: judgements, outcomes, observer agreement (ADR-374).

Revision ID: c2b92b47d7f5
Revises: 77a44a46135f
Create Date: 2026-11-08 04:00:00.000000

Three instance-wide counters, one row per natural key and UTC day, written only by
the sorted UPSERT of ``jev_statistics_repository.upsert_statistics``. They start
empty: nothing before this revision was counted durably (Prometheus kept a week). The
downgrade drops them — the counts are lost, and so is nothing else.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c2b92b47d7f5"
down_revision: str | None = "77a44a46135f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: Mirrored EXACTLY by the models' ``comment=`` (the replay check compares them).
_USAGE = "The JEV usage (JevUsage value) the row counts for."
_DAY = "The UTC day the counted events happened on."
_COUNT = "How many events this key counted that day, summed across workers."
_GATE = "The gate key within its usage (jev_gates.py)."
_BUCKET = (
    "jev_gates.judgement_bucket: floor(score x 100) for a confidence, "
    "ceil(min(p, 1 - p) x 100) for a margin."
)
_OUTCOME = "The outcome code the consumer counted (jev_decisions_total's label)."
_VERDICT = "The observer's answer: useful, empty or uncertain."
_PROPOSED = "Whether the extractor itself proposed anything (its own parse)."
_AGREEMENT_BUCKET = "floor(confidence x 100) of the observer's verdict."


def _base_columns() -> list[sa.Column[object]]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    """Create the three counters, empty."""
    op.create_table(
        "jev_judgement_daily",
        *_base_columns(),
        sa.Column("day", sa.Date(), nullable=False, comment=_DAY),
        sa.Column("usage", sa.String(length=50), nullable=False, comment=_USAGE),
        sa.Column("gate_key", sa.String(length=40), nullable=False, comment=_GATE),
        sa.Column("bucket", sa.SmallInteger(), nullable=False, comment=_BUCKET),
        sa.Column("count", sa.Integer(), nullable=False, comment=_COUNT),
        sa.CheckConstraint("bucket BETWEEN 0 AND 100", name="ck_jev_judgement_daily_bucket"),
        sa.CheckConstraint("count > 0", name="ck_jev_judgement_daily_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day", "usage", "gate_key", "bucket", name="uq_jev_judgement_daily_key"
        ),
    )
    op.create_table(
        "jev_outcome_daily",
        *_base_columns(),
        sa.Column("day", sa.Date(), nullable=False, comment=_DAY),
        sa.Column("usage", sa.String(length=50), nullable=False, comment=_USAGE),
        sa.Column("outcome", sa.String(length=32), nullable=False, comment=_OUTCOME),
        sa.Column("count", sa.Integer(), nullable=False, comment=_COUNT),
        sa.CheckConstraint("count > 0", name="ck_jev_outcome_daily_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "usage", "outcome", name="uq_jev_outcome_daily_key"),
    )
    op.create_table(
        "jev_observer_agreement_daily",
        *_base_columns(),
        sa.Column("day", sa.Date(), nullable=False, comment=_DAY),
        sa.Column("usage", sa.String(length=50), nullable=False, comment=_USAGE),
        sa.Column("verdict", sa.String(length=16), nullable=False, comment=_VERDICT),
        sa.Column("bucket", sa.SmallInteger(), nullable=False, comment=_AGREEMENT_BUCKET),
        sa.Column("proposed", sa.Boolean(), nullable=False, comment=_PROPOSED),
        sa.Column("count", sa.Integer(), nullable=False, comment=_COUNT),
        sa.CheckConstraint(
            "bucket BETWEEN 0 AND 100", name="ck_jev_observer_agreement_daily_bucket"
        ),
        sa.CheckConstraint("count > 0", name="ck_jev_observer_agreement_daily_count"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day",
            "usage",
            "verdict",
            "bucket",
            "proposed",
            name="uq_jev_observer_agreement_daily_key",
        ),
    )


def downgrade() -> None:
    """Drop the three counters."""
    op.drop_table("jev_observer_agreement_daily")
    op.drop_table("jev_outcome_daily")
    op.drop_table("jev_judgement_daily")
