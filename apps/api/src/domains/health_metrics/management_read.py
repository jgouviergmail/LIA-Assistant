"""UI windows and native stable pagination share one owned SQL predicate."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ResourceNotFoundError
from src.domains.health_metrics.models import HealthMetricToken, HealthSample
from src.domains.health_metrics.schemas import HealthMetricTokenRow, HealthSampleRow


class HealthSamplePage(BaseModel):
    model_config = ConfigDict(frozen=True)
    rows: list[HealthSampleRow]
    total: int


class HealthTokenPage(BaseModel):
    model_config = ConfigDict(frozen=True)
    rows: list[HealthMetricTokenRow]
    total: int


def health_token_statement(actor_id: UUID) -> Select[tuple[HealthMetricToken]]:
    return select(HealthMetricToken).where(HealthMetricToken.user_id == actor_id)


async def read_health_token_page(
    db: AsyncSession, actor_id: UUID, *, limit: int, after_id: UUID | None, as_of: datetime
) -> HealthTokenPage:
    source = health_token_statement(actor_id).where(HealthMetricToken.created_at <= as_of)
    total = await db.scalar(select(func.count()).select_from(source.subquery()))
    page = source
    if after_id is not None:
        anchor = await db.scalar(
            source.where(HealthMetricToken.id == after_id).execution_options(populate_existing=True)
        )
        if anchor is None:
            raise ResourceNotFoundError("health_token_cursor", after_id)
        page = page.where(
            or_(
                HealthMetricToken.created_at < anchor.created_at,
                (HealthMetricToken.created_at == anchor.created_at)
                & (HealthMetricToken.id < anchor.id),
            )
        )
    rows = (
        await db.scalars(
            page.order_by(HealthMetricToken.created_at.desc(), HealthMetricToken.id.desc())
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    ).all()
    return HealthTokenPage(
        rows=[HealthMetricTokenRow.model_validate(row) for row in rows], total=total or 0
    )


def health_sample_statement(
    actor_id: UUID,
    *,
    kind: str | None = None,
    from_ts: datetime | None = None,
    to_ts: datetime | None = None,
) -> Select[tuple[HealthSample]]:
    statement = select(HealthSample).where(HealthSample.user_id == actor_id)
    if kind is not None:
        statement = statement.where(HealthSample.kind == kind)
    if from_ts is not None:
        statement = statement.where(HealthSample.date_start >= from_ts)
    if to_ts is not None:
        statement = statement.where(HealthSample.date_start < to_ts)
    return statement


async def read_health_sample_page(
    db: AsyncSession,
    actor_id: UUID,
    *,
    kind: str | None,
    from_ts: datetime | None,
    to_ts: datetime | None,
    limit: int,
    after_id: UUID | None,
    as_of: datetime,
) -> HealthSamplePage:
    source = health_sample_statement(actor_id, kind=kind, from_ts=from_ts, to_ts=to_ts).where(
        HealthSample.created_at <= as_of
    )
    total = await db.scalar(select(func.count()).select_from(source.subquery()))
    page = source
    if after_id is not None:
        anchor = await db.scalar(
            source.where(HealthSample.id == after_id).execution_options(populate_existing=True)
        )
        if anchor is None:
            raise ResourceNotFoundError("health_cursor", after_id)
        page = page.where(
            or_(
                HealthSample.date_start < anchor.date_start,
                (HealthSample.date_start == anchor.date_start) & (HealthSample.id < anchor.id),
            )
        )
    rows = (
        await db.scalars(
            page.order_by(HealthSample.date_start.desc(), HealthSample.id.desc())
            .limit(limit + 1)
            .execution_options(populate_existing=True)
        )
    ).all()
    return HealthSamplePage(
        rows=[HealthSampleRow.model_validate(row) for row in rows], total=total or 0
    )
