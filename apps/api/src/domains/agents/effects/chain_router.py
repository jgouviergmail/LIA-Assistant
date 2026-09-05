"""Proving the two registers were not altered (ADR-263, lot 5).

A register nobody can verify is a register you are asked to believe. These two
endpoints are what turns the chain from an internal mechanism into a claim a
person can check — one for the account holder, one for an administrator.

Three rules the shape enforces:

- **A STATUS is not a VERDICT, and they are two endpoints.** Opening a page
  states what is sealed, for the price of three indexed queries; claiming the
  journal is intact requires actually walking it, which is an explicit act.
  Running a deep walk on every page view would be both expensive and a claim
  nobody asked for.
- **The user's own verification is DEEP.** A shallow pass proves the chain
  verifies itself, not that the rows are intact; answering « your journal is
  intact » on that basis would be exactly the reassurance-without-evidence the
  chain exists to replace.
- **The answer never hides the window.** Notarising is asynchronous, so recent
  rows are not sealed yet. The response says how many, rather than letting
  « verified » imply « all of it ».
- **Read-only.** Nothing here repairs, re-notarises or re-seals: a chain that
  can be repaired through an endpoint is a chain an attacker can repair too.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.constants import RATE_LIMIT_EFFECTS_READ_PER_MINUTE
from src.core.dependencies import get_db
from src.core.session_dependencies import (
    get_current_active_session,
    get_current_superuser_session,
)
from src.domains.agents.effects.chain_repository import ChainRepository
from src.domains.agents.effects.chain_verify import ChainAudit, verify_chain
from src.domains.auth.dependencies import create_user_rate_limiter
from src.domains.users.models import User

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/effects/chain", tags=["Effects"])
admin_router = APIRouter(prefix="/admin/effects/chain", tags=["Admin", "Effects"])

rate_limit_chain = create_user_rate_limiter(
    action="chain_verify",
    max_calls=RATE_LIMIT_EFFECTS_READ_PER_MINUTE,
)

#: Accounts one administrator sweep may verify. A ceiling rather than "all of
#: them": an instance-wide deep walk is a batch job, not an HTTP request. It
#: applies to a NAMED list as much as to a sweep — an unbounded list of ids is
#: the same unbounded work wearing a different hat — and the response STATES it
#: (ADR-185: a cap is stated, never applied in silence).
MAX_ADMIN_ACCOUNTS = 50


class ChainSeal(BaseModel):
    """What is sealed, said without walking anything.

    Deliberately carries no ``ok``: this endpoint checks nothing, so it must
    not look like it did. It answers « how much of my history is sealed, and
    until when », which is what a page can state on opening.
    """

    sealing_enabled: bool = Field(
        ...,
        description="Whether this instance seals at all — « nothing sealed » is "
        "otherwise ambiguous between switched off and not yet run",
    )
    entries: int = Field(..., description="Links the chain holds")
    sealed_until: datetime | None = Field(
        default=None, description="Moment of the last link — nothing after it is sealed"
    )
    pending: int = Field(..., description="Register rows not sealed yet")


class ChainStatus(BaseModel):
    """What the chain proves about one account, and what it does not yet."""

    ok: bool = Field(..., description="Whether everything checked held")
    entries: int = Field(..., description="Links walked")
    sealed_until: datetime | None = Field(
        default=None, description="Moment of the last link — nothing after it is sealed"
    )
    pending: int = Field(
        ..., description="Register rows not sealed yet; a rewrite there would leave no trace"
    )
    payloads_checked: int = Field(..., description="Register rows re-digested")
    payloads_skipped: int = Field(
        ..., description="Links written under a superseded encoding, not judged"
    )
    head_hash: str | None = Field(
        default=None,
        description="The chain's last hash — note it down to detect a later rewrite",
    )
    broken_at_seq: int | None = Field(default=None, description="Where it stopped, if it did")
    reason: str | None = Field(
        default=None, description="sequence | prev_hash | entry_hash | payload"
    )


class AdminChainStatus(ChainStatus):
    """The same verdict, said of a named account."""

    user_id: str = Field(..., description="Account verified")


class AdminChainSweep(BaseModel):
    """What a sweep verified, and what it did not reach.

    An operator asking « are the registers intact » must never read a list of
    fifty green rows as an answer about five hundred accounts. The two counts
    make the difference explicit rather than leaving it to be inferred from the
    list's length (ADR-185).
    """

    rows: list[AdminChainStatus] = Field(
        default_factory=list, description="Verdicts, broken chains first"
    )
    accounts_checked: int = Field(..., description="Accounts this sweep verified")
    accounts_with_chain: int = Field(
        ..., description="Accounts holding a chain at all — EXACT, from an aggregate"
    )
    limit: int = Field(..., description="Ceiling applied to this sweep")


def _status(audit: ChainAudit, *, pending: int, sealed_until: datetime | None) -> ChainStatus:
    """Shape one audit for a reader.

    Args:
        audit: The verdict.
        pending: Rows not sealed yet on that account.
        sealed_until: Moment of the chain's last link.

    Returns:
        The payload.
    """
    return ChainStatus(
        ok=audit.ok,
        entries=audit.entries,
        sealed_until=sealed_until,
        pending=pending,
        payloads_checked=audit.payloads_checked,
        payloads_skipped=audit.payloads_skipped,
        head_hash=audit.head_hash,
        broken_at_seq=audit.broken_at_seq,
        reason=audit.reason.value if audit.reason else None,
    )


async def _verify_one(db: AsyncSession, user_id: UUID, *, deep: bool) -> ChainStatus:
    """Verify one account and describe what the answer covers.

    Args:
        db: Session.
        user_id: Whose chain.
        deep: Whether to re-digest the covered rows.

    Returns:
        The status.
    """
    repository = ChainRepository(db)
    audit = await verify_chain(db, user_id, deep=deep)
    head = await repository.head(user_id)
    _, pending = await repository.counts(user_id)
    return _status(audit, pending=pending, sealed_until=head.occurred_at)


@router.get(
    "/status",
    response_model=ChainSeal,
    dependencies=[Depends(rate_limit_chain)],
    summary="How much of your journals is sealed",
)
async def own_chain_seal(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> ChainSeal:
    """State what is sealed, without checking it.

    Three indexed queries and no walk: a page opening must not run an audit
    nobody asked for, and must not imply one either — hence no verdict here.

    Args:
        db: Session.
        user: The authenticated caller.

    Returns:
        The seal, and whether this instance seals at all.
    """
    repository = ChainRepository(db)
    head = await repository.head(user.id)
    _, pending = await repository.counts(user.id)
    return ChainSeal(
        sealing_enabled=bool(getattr(settings, "ledger_chain_enabled", False)),
        entries=head.seq,
        sealed_until=head.occurred_at,
        pending=pending,
    )


@router.get(
    "/verify",
    response_model=ChainStatus,
    dependencies=[Depends(rate_limit_chain)],
    summary="Check that your registers have not been altered",
)
async def verify_own_chain(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_active_session),
) -> ChainStatus:
    """Walk this account's chain and re-digest every row it covers.

    Deep, always. A shallow answer would say the chain agrees with itself while
    a register row had been rewritten underneath it — a reassurance with no
    evidence behind it, which is the thing this whole mechanism replaces.

    Args:
        db: Session.
        user: The authenticated caller; no account can verify another's.

    Returns:
        The verdict, with what it does NOT cover stated beside it.
    """
    return await _verify_one(db, user.id, deep=True)


@admin_router.get(
    "/verify",
    response_model=AdminChainSweep,
    summary="Verify one, several or every account's chain",
)
async def verify_chains(
    user_ids: list[UUID] | None = Query(
        None, description="One or several accounts; omit for a sweep of every chain"
    ),
    deep: bool = Query(True, description="Also re-digest the covered register rows"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_current_superuser_session),
) -> AdminChainSweep:
    """Verify the chains an administrator names, or every chain there is.

    No audit-log entry and no unmasking switch, unlike the readable export: a
    verdict says whether rows were altered, never what any of them says. There
    is nothing here to withhold and nothing to reveal.

    Args:
        user_ids: The accounts, or None for a sweep bounded by
            :data:`MAX_ADMIN_ACCOUNTS`.
        deep: Re-digest the covered rows; the only depth that answers the
            question the chain exists for.
        db: Session.
        admin: The authenticated superuser.

    Returns:
        The sweep, broken chains first — an operator opening this must not have
        to scroll to find the one that matters — with what it covered stated
        beside it rather than left to the list's length.
    """
    repository = ChainRepository(db)
    targets = (user_ids or await repository.accounts_with_chain(limit=MAX_ADMIN_ACCOUNTS))[
        :MAX_ADMIN_ACCOUNTS
    ]
    results = [
        AdminChainStatus(
            user_id=str(target), **(await _verify_one(db, target, deep=deep)).model_dump()
        )
        for target in targets
    ]
    broken = [row for row in results if not row.ok]
    if broken:
        logger.error(
            "ledger_chain_admin_verify_found_breaks",
            admin_id=str(admin.id),
            broken=len(broken),
            checked=len(results),
        )
    return AdminChainSweep(
        rows=broken + [row for row in results if row.ok],
        accounts_checked=len(results),
        accounts_with_chain=await repository.count_accounts_with_chain(),
        limit=MAX_ADMIN_ACCOUNTS,
    )


__all__ = ["AdminChainSweep", "ChainSeal", "ChainStatus", "admin_router", "router"]
