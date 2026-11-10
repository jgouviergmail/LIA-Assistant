"""What the administration screen reads of JEV's durable statistics (ADR-374).

One window of whole UTC days, ending today. Volume, cost and the median latency come
from ONE aggregate over ``token_usage_logs`` grouped by slot (each usage has its own,
``jev_registry``); each counter table is read by ONE ``GROUP BY``: five statements,
whatever the number of usages, and no loop issues a query.
"""

from datetime import UTC, date, datetime, time, timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import now_utc
from src.domains.chat.models import TokenUsageLog
from src.domains.llm_config.jev_gates import JEV_GATES, JUDGEMENT_BUCKETS, OBSERVER_USAGES, GateKind
from src.domains.llm_config.jev_registry import JEV_USAGES, JevUsage
from src.domains.llm_config.jev_settings import read_routing, resolve_thresholds
from src.domains.llm_config.jev_statistics_models import (
    JevJudgementDaily,
    JevObserverAgreementDaily,
    JevOutcomeDaily,
)


class JevGateStatistics(BaseModel):
    """Every judgement of one gate over the window, by bucket."""

    key: str = Field(description="Gate key within its usage.")
    kind: GateKind = Field(description="What the score is; decides how a bucket concludes.")
    threshold: float = Field(description="The threshold the next operation decides with.")
    buckets: list[int] = Field(
        description="Judgements per bucket, index 0..100 (jev_gates.judgement_bucket): a "
        "confidence concludes from bucket threshold × 100 up, a margin up to it."
    )


class JevAgreementRow(BaseModel):
    """An observer's verdicts beside what its extractor proposed, for one bucket."""

    verdict: str = Field(description="The observer's answer: useful, empty or uncertain.")
    bucket: int = Field(description="floor(confidence × 100) of the verdict.")
    proposed: bool = Field(description="Whether the extractor itself proposed anything.")
    count: int = Field(description="How many observations over the window.")


class JevUsageStatistics(BaseModel):
    """One usage's window: what it cost, how it ended, how its gates judged."""

    usage: JevUsage = Field(description="Registered integration point.")
    calls: int = Field(description="Billed calls over the window.")
    cost_eur: float = Field(description="What those calls cost, in euros.")
    latency_p50_ms: int | None = Field(description="Median call latency; None without calls.")
    outcomes: dict[str, int] = Field(description="Operations per outcome code.")
    gates: list[JevGateStatistics] = Field(description="One entry per declared gate.")
    agreement: list[JevAgreementRow] | None = Field(
        description="An observer's verdicts beside its extractor; None for a deciding usage."
    )


class JevStatisticsResponse(BaseModel):
    """The window read, every shipped usage listed, rows or not."""

    days: int = Field(description="Whole UTC days covered, today included.")
    since: date = Field(description="The first UTC day of the window.")
    usages: list[JevUsageStatistics] = Field(description="Every shipped usage, in order.")


async def read_jev_statistics(db: AsyncSession, *, days: int) -> JevStatisticsResponse:
    """Read the last ``days`` UTC days of JEV's statistics.

    Args:
        db: A session; nothing is written.
        days: Whole UTC days, today included (the route bounds it).

    Returns:
        Every shipped usage with its calls, cost, median latency, outcomes, the
        bucketed judgements of each gate and, for an observer, its agreement.
    """
    since = now_utc().date() - timedelta(days=days - 1)
    since_instant = datetime.combine(since, time.min, tzinfo=UTC)
    routing = await read_routing(db)

    judgements = await db.execute(
        select(
            JevJudgementDaily.usage,
            JevJudgementDaily.gate_key,
            JevJudgementDaily.bucket,
            func.sum(JevJudgementDaily.count),
        )
        .where(JevJudgementDaily.day >= since)
        .group_by(JevJudgementDaily.usage, JevJudgementDaily.gate_key, JevJudgementDaily.bucket)
    )
    buckets: dict[tuple[str, str], list[int]] = {}
    for usage, gate_key, bucket, count in judgements.all():
        if 0 <= bucket < JUDGEMENT_BUCKETS:
            buckets.setdefault((usage, gate_key), [0] * JUDGEMENT_BUCKETS)[bucket] += int(count)

    outcome_rows = await db.execute(
        select(JevOutcomeDaily.usage, JevOutcomeDaily.outcome, func.sum(JevOutcomeDaily.count))
        .where(JevOutcomeDaily.day >= since)
        .group_by(JevOutcomeDaily.usage, JevOutcomeDaily.outcome)
    )
    outcomes: dict[str, dict[str, int]] = {}
    for usage, outcome, count in outcome_rows.all():
        outcomes.setdefault(usage, {})[outcome] = int(count)

    agreement_rows = await db.execute(
        select(
            JevObserverAgreementDaily.usage,
            JevObserverAgreementDaily.verdict,
            JevObserverAgreementDaily.bucket,
            JevObserverAgreementDaily.proposed,
            func.sum(JevObserverAgreementDaily.count),
        )
        .where(JevObserverAgreementDaily.day >= since)
        .group_by(
            JevObserverAgreementDaily.usage,
            JevObserverAgreementDaily.verdict,
            JevObserverAgreementDaily.bucket,
            JevObserverAgreementDaily.proposed,
        )
        .order_by(
            JevObserverAgreementDaily.usage,
            JevObserverAgreementDaily.verdict,
            JevObserverAgreementDaily.bucket,
            JevObserverAgreementDaily.proposed,
        )
    )
    agreement: dict[str, list[JevAgreementRow]] = {}
    for usage, verdict, bucket, proposed, count in agreement_rows.all():
        agreement.setdefault(usage, []).append(
            JevAgreementRow(verdict=verdict, bucket=bucket, proposed=proposed, count=int(count))
        )

    slots = {spec.llm_type: usage for usage, spec in JEV_USAGES.items()}
    spend_rows = await db.execute(
        select(
            TokenUsageLog.llm_type,
            func.count(),
            func.coalesce(func.sum(TokenUsageLog.cost_eur), 0),
            func.percentile_cont(0.5).within_group(TokenUsageLog.latency_ms.asc()),
        )
        .where(TokenUsageLog.llm_type.in_(list(slots)), TokenUsageLog.created_at >= since_instant)
        .group_by(TokenUsageLog.llm_type)
    )
    spend = {slots[slot]: (int(n), float(cost), p50) for slot, n, cost, p50 in spend_rows.all()}

    usages: list[JevUsageStatistics] = []
    for usage in JEV_USAGES:
        calls, cost, p50 = spend.get(usage, (0, 0.0, None))
        resolved = resolve_thresholds(usage, routing.thresholds.get(usage.value))
        usages.append(
            JevUsageStatistics(
                usage=usage,
                calls=calls,
                cost_eur=cost,
                latency_p50_ms=round(p50) if p50 is not None else None,
                outcomes=outcomes.get(usage.value, {}),
                gates=[
                    JevGateStatistics(
                        key=gate.key,
                        kind=gate.kind,
                        threshold=float(resolved[gate.key]),
                        buckets=buckets.get((usage.value, gate.key), [0] * JUDGEMENT_BUCKETS),
                    )
                    for gate in JEV_GATES.get(usage, ())
                ],
                agreement=agreement.get(usage.value, []) if usage in OBSERVER_USAGES else None,
            )
        )
    return JevStatisticsResponse(days=days, since=since, usages=usages)
