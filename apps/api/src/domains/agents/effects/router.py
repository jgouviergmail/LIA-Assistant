"""Reading the effect register (ADR-263).

Two questions, one source: *what did this turn do?* (the debug panel and the
message card) and *what has been done for me?* (the action journal). Both are
strictly user-scoped — a register is only trustworthy if it is also private.

The API ships ``label_key`` and ``values``, never a translated sentence: the
frontend resolves the wording in the reader's current language, so a line about
an action taken in French still reads in German after the user switches. The
backend table (``core.i18n_effects``) serves the EXPORT, where there is no
client to resolve anything.

Nothing here writes. Correcting a ledger row is a reviewed database operation,
never an endpoint — an executor that could edit its own record would defeat the
point of keeping one.
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
from src.domains.agents.effects.models import EffectStatus
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects", tags=["Effects"])

rate_limit_effects = create_user_rate_limiter(
    action="effects_read",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)

#: Page size ceiling. A cap is stated, never applied in silence: the response
#: carries the exact total next to the page (ADR-185).
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class EffectEntry(BaseModel):
    """One recorded effect, as a reader sees it."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Ledger row id")
    label_key: str = Field(..., description="i18n key the client resolves")
    values: dict[str, Any] = Field(default_factory=dict, description="Values of the wording")
    tool_name: str = Field(..., description="Capability that acted")
    mutation_policy: str = Field(..., description="Declared policy under which it acted")
    status: str = Field(..., description="succeeded | failed | refused | claimed | abandoned")
    source: str = Field(..., description="user | scheduled | subagent")
    execution_mode: str = Field(..., description="pipeline | react")
    approval_kind: str | None = Field(default=None, description="How the user authorised it")
    error_code: str | None = Field(default=None, description="Why it failed or was refused")
    claimed_at: datetime = Field(..., description="When it was claimed, before happening")
    closed_at: datetime | None = Field(default=None, description="When its outcome was recorded")


class EffectPage(BaseModel):
    """One page of the journal, with the EXACT total beside it."""

    entries: list[EffectEntry] = Field(default_factory=list, description="The page")
    total: int = Field(..., description="Exact number of effects, not the page length")
    limit: int = Field(..., description="Page size actually applied")
    offset: int = Field(..., description="Page offset")


def _entry(row: Any) -> EffectEntry:
    """Shape one ledger row for a reader.

    Args:
        row: The ``AgentEffect`` row.

    Returns:
        The entry, with its label decrypted into key and values.
    """
    from src.domains.agents.effects.labels import readable_label

    label_key, values = readable_label(row)
    return EffectEntry(
        id=str(row.id),
        label_key=label_key,
        values=values,
        tool_name=row.tool_name,
        mutation_policy=_value_of(row.mutation_policy),
        status=_value_of(row.status),
        source=_value_of(row.source),
        execution_mode=row.execution_mode,
        approval_kind=row.approval_kind,
        error_code=row.error_code,
        claimed_at=row.claimed_at,
        closed_at=row.closed_at,
    )


def _given(value: Any) -> Any:
    """The value the caller actually supplied, or None.

    FastAPI's declared defaults are ``Query`` OBJECTS, and those are truthy: a
    handler that reads them with a truthiness test behaves one way through the
    framework and another when called directly (a test, a script).

    Args:
        value: A parameter value, possibly the un-substituted placeholder.

    Returns:
        The value, or None when nothing was supplied.
    """
    from fastapi.params import Param

    return None if isinstance(value, Param) else value


def _value_of(value: Any) -> str:
    """The stored spelling of an enum column, or the string itself."""
    return str(getattr(value, "value", value))


@router.get(
    "/run/{run_id}",
    response_model=list[EffectEntry],
    dependencies=[Depends(rate_limit_effects)],
    summary="Effects recorded during one run",
)
async def list_run_effects(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> list[EffectEntry]:
    """Everything the register recorded for one run of this user.

    Args:
        run_id: The run to read.
        db: Session.
        user: The authenticated caller — rows of anybody else are invisible,
            not forbidden: a register must not confirm that someone else's
            action exists.

    Returns:
        The effects, oldest first.
    """
    from src.domains.agents.effects.repository import EffectLedgerRepository

    rows = await EffectLedgerRepository(db).list_for_run(run_id)
    return [_entry(row) for row in rows if row.user_id == user.id]


@router.get(
    "/journal",
    response_model=EffectPage,
    dependencies=[Depends(rate_limit_effects)],
    summary="What has been done on this account",
)
async def list_journal(
    limit: int = Query(DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    status: EffectStatus | None = Query(None, description="One outcome, or every outcome"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> EffectPage:
    """One page of the user's own action journal, newest first.

    Args:
        limit: Page size, capped by :data:`MAX_PAGE_SIZE`.
        offset: Page offset.
        status: Restrict to one outcome. Filtering SERVER-side is what keeps
            the total exact: a count computed over everything, displayed above
            a filtered list, describes a set the reader cannot see.
        db: Session.
        user: The authenticated caller.

    Returns:
        The page and the exact total — a count shown to a user is exact or it
        does not exist (ADR-185).
    """
    from src.domains.agents.effects.repository import EffectLedgerRepository

    # Typed as the enum, so an unknown value is refused by FastAPI with a 422
    # rather than raising a ValueError the client reads as a server fault.
    rows, total = await EffectLedgerRepository(db).list_for_user(
        user.id, limit=limit, offset=offset, status=_given(status)
    )
    return EffectPage(
        entries=[_entry(row) for row in rows], total=total, limit=limit, offset=offset
    )
