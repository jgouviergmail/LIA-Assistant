"""Daily JEV statistics: judgements by bucket, outcomes, observer agreement (ADR-374).

Three counters, one row per natural key and UTC day, written only through the sorted
UPSERT of ``jev_statistics_repository.upsert_statistics``. They hold the registry's own
vocabulary (a usage, a gate key, an outcome code, a verdict) and counts, never user
content and never a user id: an instance-wide aggregate, like ``instance_daily_budget``.
Each natural key opens with ``day``, so the unique index also serves the window reads.
"""

from datetime import date

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models import BaseModel

#: Mirrored EXACTLY by the migration's ``comment=`` (the replay check compares them).
USAGE_COMMENT = "The JEV usage (JevUsage value) the row counts for."
DAY_COMMENT = "The UTC day the counted events happened on."
COUNT_COMMENT = "How many events this key counted that day, summed across workers."
GATE_COMMENT = "The gate key within its usage (jev_gates.py)."
BUCKET_COMMENT = (
    "jev_gates.judgement_bucket: floor(score x 100) for a confidence, "
    "ceil(min(p, 1 - p) x 100) for a margin."
)
OUTCOME_COMMENT = "The outcome code the consumer counted (jev_decisions_total's label)."
VERDICT_COMMENT = "The observer's answer: useful, empty or uncertain."
PROPOSED_COMMENT = "Whether the extractor itself proposed anything (its own parse)."
AGREEMENT_BUCKET_COMMENT = "floor(confidence x 100) of the observer's verdict."


class JevJudgementDaily(BaseModel):
    """How many judgements of one gate landed in one bucket on one day."""

    __tablename__ = "jev_judgement_daily"

    day: Mapped[date] = mapped_column(Date, nullable=False, comment=DAY_COMMENT)
    usage: Mapped[str] = mapped_column(String(50), nullable=False, comment=USAGE_COMMENT)
    gate_key: Mapped[str] = mapped_column(String(40), nullable=False, comment=GATE_COMMENT)
    bucket: Mapped[int] = mapped_column(SmallInteger, nullable=False, comment=BUCKET_COMMENT)
    count: Mapped[int] = mapped_column(Integer, nullable=False, comment=COUNT_COMMENT)

    __table_args__ = (
        UniqueConstraint("day", "usage", "gate_key", "bucket", name="uq_jev_judgement_daily_key"),
        CheckConstraint("bucket BETWEEN 0 AND 100", name="ck_jev_judgement_daily_bucket"),
        CheckConstraint("count > 0", name="ck_jev_judgement_daily_count"),
    )


class JevOutcomeDaily(BaseModel):
    """How many operations of one usage ended with one outcome on one day."""

    __tablename__ = "jev_outcome_daily"

    day: Mapped[date] = mapped_column(Date, nullable=False, comment=DAY_COMMENT)
    usage: Mapped[str] = mapped_column(String(50), nullable=False, comment=USAGE_COMMENT)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, comment=OUTCOME_COMMENT)
    count: Mapped[int] = mapped_column(Integer, nullable=False, comment=COUNT_COMMENT)

    __table_args__ = (
        UniqueConstraint("day", "usage", "outcome", name="uq_jev_outcome_daily_key"),
        CheckConstraint("count > 0", name="ck_jev_outcome_daily_count"),
    )


class JevObserverAgreementDaily(BaseModel):
    """An observer's verdict beside what the extractor proposed, by confidence bucket."""

    __tablename__ = "jev_observer_agreement_daily"

    day: Mapped[date] = mapped_column(Date, nullable=False, comment=DAY_COMMENT)
    usage: Mapped[str] = mapped_column(String(50), nullable=False, comment=USAGE_COMMENT)
    verdict: Mapped[str] = mapped_column(String(16), nullable=False, comment=VERDICT_COMMENT)
    bucket: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, comment=AGREEMENT_BUCKET_COMMENT
    )
    proposed: Mapped[bool] = mapped_column(Boolean, nullable=False, comment=PROPOSED_COMMENT)
    count: Mapped[int] = mapped_column(Integer, nullable=False, comment=COUNT_COMMENT)

    __table_args__ = (
        UniqueConstraint(
            "day",
            "usage",
            "verdict",
            "bucket",
            "proposed",
            name="uq_jev_observer_agreement_daily_key",
        ),
        CheckConstraint("bucket BETWEEN 0 AND 100", name="ck_jev_observer_agreement_daily_bucket"),
        CheckConstraint("count > 0", name="ck_jev_observer_agreement_daily_count"),
    )
