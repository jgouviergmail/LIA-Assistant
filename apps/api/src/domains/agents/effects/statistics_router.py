"""Reading the registers as figures (ADR-263).

Two endpoints over ONE computation, because the question is the same and only
the scope differs: a reader asks about themselves, an operator about one,
several or every account. A second implementation would be a second place for a
count to be right on one screen and wrong on the other.

The reader's route has **no account parameter at all** — the scope is their
session, so there is nothing to pass and therefore nothing to forget. The
operator's takes the same ``user_ids`` the exports take, and an omitted list
means the instance, deliberately.

Nothing here reads a row: every figure is a grouped aggregate over indexed
columns, so opening a chart never moves the content the registers exist to keep
in one place.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RATE_LIMIT_EFFECTS_READ_PER_MINUTE
from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.agents.effects.statistics import (
    RegisterStatistics,
    SeriesKind,
    register_statistics,
)
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects/statistics", tags=["Effects"])
admin_router = APIRouter(prefix="/admin/effects/statistics", tags=["Admin", "Effects"])

rate_limit_statistics = create_user_rate_limiter(
    action="effects_statistics",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)


class SlicePayload(BaseModel):
    """One bar of one chart."""

    label: str = Field(..., description="A BOUNDED value — never free text")
    count: int = Field(..., description="Exact number of rows")
    secondary: int = Field(default=0, description="A second measure on the same bar")


class SeriesPayload(BaseModel):
    """One chart, with its exact figure beside it and what that figure means."""

    slices: list[SlicePayload] = Field(default_factory=list, description="Bars, largest first")
    total: int = Field(
        ...,
        description="EXACT figure for the whole filtered set, including whatever the "
        "top-N folded into « other » — so a reader can check it against the bars "
        "(ADR-185). A sum for « count » and « stacked », a weighted mean for "
        "« average »",
    )
    kind: SeriesKind = Field(
        default=SeriesKind.COUNT,
        description="What the bars draw: « count » (one measure), « stacked » (two "
        "measures on one bar) or « average » (means, which never sum)",
    )


class StatisticsPayload(BaseModel):
    """Every figure the surfaces draw."""

    calls_by_model: SeriesPayload
    calls_by_node: SeriesPayload
    tokens_by_model: SeriesPayload
    consultations_by_domain: SeriesPayload
    consultation_latency_by_tool: SeriesPayload
    actions_by_status: SeriesPayload
    turns_by_outcome: SeriesPayload
    turns_by_mode: SeriesPayload
    integrity_by_kind: SeriesPayload
    activity_by_day: SeriesPayload


def _payload(statistics: RegisterStatistics) -> StatisticsPayload:
    """Shape the computed figures for a client.

    Args:
        statistics: What the aggregation produced.

    Returns:
        The payload. One conversion, so the reader's screen and the operator's
        can never disagree about what a series means.
    """
    return StatisticsPayload(
        **{
            name: SeriesPayload(
                slices=[
                    SlicePayload(label=one.label, count=one.count, secondary=one.secondary)
                    for one in series.slices
                ],
                total=series.total,
                kind=series.kind,
            )
            for name, series in vars(statistics).items()
        }
    )


@router.get(
    "",
    response_model=StatisticsPayload,
    dependencies=[Depends(rate_limit_statistics)],
    summary="Your own registers, as figures",
)
async def own_statistics(
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> StatisticsPayload:
    """The caller's own five records, aggregated.

    Args:
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound.
        db: Session.
        user: The authenticated caller. The scope is their session; there is no
            account parameter, so there is no way to ask for someone else's.

    Returns:
        The figures.
    """
    return _payload(await register_statistics(db, user_ids=[user.id], since=since, until=until))


@admin_router.get(
    "",
    response_model=StatisticsPayload,
    summary="One, several or every account's registers, as figures",
)
async def admin_statistics(
    user_ids: list[UUID] | None = Query(
        None, description="One, several, or (omitted) every account"
    ),
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser_session),
) -> StatisticsPayload:
    """The same figures, over the accounts an operator names.

    No masking switch and no audit entry, unlike the readable export: every
    label here is a BOUNDED value — a model, a graph node, a domain, a status —
    and none of them names a person or quotes anything. There is nothing to
    withhold and nothing to reveal.

    Args:
        user_ids: The accounts, or omitted for the whole instance.
        since: Inclusive lower bound on the period.
        until: Exclusive upper bound.
        db: Session.
        admin: The authenticated superuser.

    Returns:
        The figures.
    """
    logger.info(
        "register_statistics_served",
        admin_id=str(admin.id),
        accounts=len(user_ids) if user_ids else 0,
    )
    return _payload(await register_statistics(db, user_ids=user_ids, since=since, until=until))


__all__ = ["admin_router", "router"]
