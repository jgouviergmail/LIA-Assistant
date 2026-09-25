"""What LIA did and read for one person over a period — the activity tool's read (ADR-318).

The two registers answer « what has been done for me » and « what was
consulted » row by row, each on its own tab (ADR-263, ADR-270). The activity
tool asks both at once, for a period, and must answer with the registers' own
honesty:

- **every count is EXACT** — an aggregate over the whole filtered set, never the
  length of the page it lists (ADR-185): the page is the newest actions, and the
  total beside it says what the page left out;
- **the authorship filter is the tabs' own** (``origin_sources``), so the tool
  and the screen cannot disagree about what belongs to the person;
- **consultations read as their DOMAIN** (``treatment_domain``), the register's
  vocabulary, and are COUNTED per domain rather than listed: a turn consults far
  more than it acts, and a list of reads is noise where a count is an answer.

One session, four statements, no network call between them (ADR-304).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import AgentEffect, AgentTreatment, EffectStatus
from src.domains.agents.effects.origin import RegisterOrigin, origin_sources
from src.domains.agents.effects.period import period_conditions
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.treatment_labels import treatment_domain

__all__ = ["ActivityReport", "read_activity"]


@dataclass(frozen=True)
class ActivityReport:
    """One period of one account's registers.

    Attributes:
        actions: The newest actions, newest first — at most the page asked for.
        actions_total: EXACT count of the actions the filters match.
        actions_by_status: EXACT count per outcome over the period and
            authorship — the status filter narrows the list, never this.
        consultations_by_domain: EXACT count per domain over the period and
            authorship, largest first.
    """

    actions: list[AgentEffect]
    actions_total: int
    actions_by_status: dict[str, int]
    consultations_by_domain: dict[str, int]

    @property
    def consultations_total(self) -> int:
        """Every consultation of the period, whatever its domain."""
        return sum(self.consultations_by_domain.values())


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _scope(
    user_column: Any,
    source_column: Any,
    time_column: Any,
    user_id: uuid.UUID,
    since: datetime | None,
    until: datetime | None,
    origin: RegisterOrigin,
) -> list[Any]:
    """The account, the period and the authorship — the conditions both registers share."""
    conditions: list[Any] = [user_column == user_id, *period_conditions(time_column, since, until)]
    sources = origin_sources(origin)
    if sources is not None:
        conditions.append(source_column.in_(sources))
    return conditions


async def read_activity(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    since: datetime | None,
    until: datetime | None,
    origin: RegisterOrigin,
    status: EffectStatus | None,
    limit: int,
) -> ActivityReport:
    """Read one period of an account's two registers.

    Args:
        db: A session serving these four statements only.
        user_id: Whose registers.
        since: Inclusive lower bound.
        until: Exclusive upper bound.
        origin: Which authorships to keep (the tabs' vocabulary).
        status: One outcome for the listed actions, or every outcome.
        limit: How many actions to list.

    Returns:
        The report — the listed page and the exact figures behind it.
    """
    actions, actions_total = await EffectLedgerRepository(db).list_for_user(
        user_id, limit=limit, offset=0, status=status, since=since, until=until, origin=origin
    )

    effect_scope = _scope(
        AgentEffect.user_id,
        AgentEffect.source,
        AgentEffect.claimed_at,
        user_id,
        since,
        until,
        origin,
    )
    status_rows = await db.execute(
        select(AgentEffect.status, func.count()).where(*effect_scope).group_by(AgentEffect.status)
    )
    by_status = {_enum_value(value): int(count) for value, count in status_rows.all()}

    treatment_scope = _scope(
        AgentTreatment.user_id,
        AgentTreatment.source,
        AgentTreatment.occurred_at,
        user_id,
        since,
        until,
        origin,
    )
    tool_rows = await db.execute(
        select(AgentTreatment.tool_name, func.count())
        .where(*treatment_scope)
        .group_by(AgentTreatment.tool_name)
    )
    by_domain: dict[str, int] = {}
    for tool_name, count in tool_rows.all():
        # Several capabilities read as one domain: their counts add up.
        domain = treatment_domain(str(tool_name))
        by_domain[domain] = by_domain.get(domain, 0) + int(count)

    return ActivityReport(
        actions=actions,
        actions_total=actions_total,
        actions_by_status=by_status,
        consultations_by_domain=dict(
            sorted(by_domain.items(), key=lambda item: (-item[1], item[0]))
        ),
    )
