"""Reading the consultation register (ADR-263, lot 4).

The companion of ``router.py``, and deliberately a separate module rather than
a second half of it: the two registers answer different questions, the owner
arbitrated that they must stay **two distinct lists**, and a shared router
would have made "one filter, two meanings" an easy mistake to write.

Same three properties as the action journal, for the same reasons: private
(a register is only trustworthy if it is also private), exact (the total is an
aggregate over the FILTERED set, never the page length — ADR-185), and keys
rather than sentences (the client resolves the wording, so a line about a
consultation made in French still reads in German after a language switch).

Nothing here writes: there is nothing to correct in an observation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import RATE_LIMIT_EFFECTS_READ_PER_MINUTE
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects/treatments", tags=["Effects"])

rate_limit_treatments = create_user_rate_limiter(
    action="treatments_read",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)

#: Page size ceiling. A cap is stated, never applied in silence: the response
#: carries the exact total next to the page (ADR-185).
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class TreatmentEntry(BaseModel):
    """One recorded consultation, as a reader sees it.

    Deliberately narrow: which capability, when, how long, with what outcome.
    A consultation records no argument, and this payload acquires none on the
    way out — « searched Marie's emails » would reveal a search nobody asked to
    have recorded.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Register row id")
    domain: str = Field(..., description="Domain key the client resolves to a noun")
    tool_name: str = Field(..., description="Capability that was consulted")
    mutation_policy: str | None = Field(default=None, description="Its declared policy")
    outcome: str = Field(..., description="ok | failed")
    source: str = Field(..., description="user | scheduled | subagent")
    execution_mode: str = Field(..., description="pipeline | react | subagent")
    duration_ms: int = Field(..., description="How long the capability took")
    thread_id: str = Field(..., description="Conversation the consultation belongs to")
    run_id: str = Field(..., description="Turn that consulted")
    occurred_at: datetime = Field(..., description="When the call returned (UTC)")


class TreatmentPage(BaseModel):
    """One page of the consultation journal, with the EXACT total beside it."""

    entries: list[TreatmentEntry] = Field(default_factory=list, description="The page")
    total: int = Field(..., description="Exact number of consultations, not the page length")
    limit: int = Field(..., description="Page size actually applied")
    offset: int = Field(..., description="Page offset")


def _value_of(value: Any) -> str:
    """The stored spelling of an enum column, or the string itself."""
    return str(getattr(value, "value", value))


def _entry(row: Any) -> TreatmentEntry:
    """Shape one register row for a reader.

    Args:
        row: The ``AgentTreatment`` row.

    Returns:
        The entry, carrying the DOMAIN key rather than a sentence — the client
        resolves it, exactly as it does for the action register's label key.
    """
    from src.domains.agents.effects.treatment_labels import treatment_domain

    return TreatmentEntry(
        id=str(row.id),
        domain=treatment_domain(row.tool_name),
        tool_name=row.tool_name,
        mutation_policy=(_value_of(row.mutation_policy) if row.mutation_policy else None),
        outcome=_value_of(row.outcome),
        source=_value_of(row.source),
        execution_mode=row.execution_mode,
        duration_ms=row.duration_ms,
        thread_id=row.thread_id,
        run_id=row.run_id,
        occurred_at=row.occurred_at,
    )


@router.get(
    "/run/{run_id}",
    response_model=list[TreatmentEntry],
    dependencies=[Depends(rate_limit_treatments)],
    summary="Capabilities consulted during one run",
)
async def list_run_treatments(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> list[TreatmentEntry]:
    """Everything the register recorded for one run of this user.

    Args:
        run_id: The run to read.
        db: Session.
        user: The authenticated caller — rows of anybody else are invisible,
            not forbidden: a register must not confirm that someone else's
            turn exists.

    Returns:
        The consultations, oldest first.
    """
    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    rows = await TreatmentRepository(db).list_for_run(run_id)
    return [_entry(row) for row in rows if row.user_id == user.id]


@router.get(
    "/journal",
    response_model=TreatmentPage,
    dependencies=[Depends(rate_limit_treatments)],
    summary="What has been consulted on this account",
)
async def list_treatment_journal(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    tool_name: str | None = Query(None, description="One capability, or every capability"),
    since: datetime | None = Query(None, description="Inclusive lower bound"),
    until: datetime | None = Query(None, description="Exclusive upper bound"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> TreatmentPage:
    """One page of the user's own consultation journal, newest first.

    Args:
        limit: Page size, capped by :data:`MAX_PAGE_SIZE`.
        offset: Page offset.
        tool_name: Restrict to one capability. Filtering SERVER-side is what
            keeps the total exact: a count computed over everything, displayed
            above a filtered list, describes a set the reader cannot see.
        since: Inclusive lower bound on the consultation time.
        until: Exclusive upper bound.
        db: Session.
        user: The authenticated caller.

    Returns:
        The page and the exact total (ADR-185).
    """
    from src.domains.agents.effects.treatment_repository import TreatmentRepository

    rows, total = await TreatmentRepository(db).list_for_user(
        user.id, limit=limit, offset=offset, tool_name=tool_name, since=since, until=until
    )
    return TreatmentPage(
        entries=[_entry(row) for row in rows], total=total, limit=limit, offset=offset
    )
