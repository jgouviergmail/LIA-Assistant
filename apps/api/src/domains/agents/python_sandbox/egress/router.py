"""The person's egress grants — list, change a scope, revoke; and what needs
no question (ADR-298).

Everything here reads the person's own rows: ``user_id`` is a filter of
every statement. No capability guard sits on this router on purpose: the
ACT is the tool's network run, gated at the act; these routes are the
RECORD, which stays readable and revocable when the act is switched off
(ADR-280).
"""

from __future__ import annotations

import uuid
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.constants import (
    PYTHON_SANDBOX_GRANTS_PAGE_DEFAULT_LIMIT,
    PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT,
    PYTHON_SANDBOX_GRANTS_PAGE_MIN_LIMIT,
)
from src.core.dependencies import get_db
from src.core.exceptions import ResourceNotFoundError
from src.core.session_dependencies import get_current_active_session
from src.domains.agents.python_sandbox.egress.connectors import active_connector_hosts
from src.domains.agents.python_sandbox.egress.grants_repository import EgressGrantRepository
from src.domains.agents.python_sandbox.egress.hosts import HostStatus
from src.domains.agents.python_sandbox.egress.offer import merge_reachable
from src.domains.agents.python_sandbox.egress.schemas import (
    EgressGrantListResponse,
    EgressGrantResponse,
    EgressGrantScopeUpdate,
    ReachableHost,
    ReachableHostsResponse,
)
from src.domains.connectors.service import ConnectorService
from src.domains.users.models import User

router = APIRouter(prefix="/sandbox/egress-grants", tags=["Sandbox egress"])


def _raise_grant_not_found(grant_id: uuid.UUID) -> NoReturn:
    """404 for a grant that is not the caller's or does not exist — one answer
    for both, so a caller cannot tell that the row exists (hide_existence)."""
    raise ResourceNotFoundError(resource_type="sandbox_egress_grant", resource_id=grant_id)


@router.get("", response_model=EgressGrantListResponse, summary="List the account's egress grants")
async def list_grants(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
    limit: Annotated[
        int,
        Query(ge=PYTHON_SANDBOX_GRANTS_PAGE_MIN_LIMIT, le=PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT),
    ] = PYTHON_SANDBOX_GRANTS_PAGE_DEFAULT_LIMIT,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EgressGrantListResponse:
    """One page, newest first, and the EXACT total behind it."""
    rows, total = await EgressGrantRepository(db).list_page(user.id, limit=limit, offset=offset)
    return EgressGrantListResponse(
        items=[EgressGrantResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
        max_limit=PYTHON_SANDBOX_GRANTS_PAGE_MAX_LIMIT,
        max_per_user=get_settings().python_sandbox_max_grants_per_user,
    )


@router.get(
    "/reachable",
    response_model=ReachableHostsResponse,
    summary="What this account's scripts may reach without a question",
)
async def reachable_hosts(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> ReachableHostsResponse:
    """The connector hosts (a credential travels) and the operator's list."""
    settings = get_settings()
    # The plain service is the gate here: this request holds its session
    # alone, so the tool's lock-wrapped sibling is not needed.
    connectors = await active_connector_hosts(ConnectorService(db), user.id)
    items = [
        ReachableHost(
            host=reachable.host,
            status=HostStatus.CONNECTOR if reachable.credential else HostStatus.OPERATOR,
            connector=reachable.credential.connector if reachable.credential else None,
        )
        for reachable in merge_reachable(connectors, settings.python_sandbox_egress_hosts)
    ]
    return ReachableHostsResponse(
        items=items, ask_enabled=settings.python_sandbox_egress_ask_enabled
    )


@router.patch(
    "/{grant_id}", response_model=EgressGrantResponse, summary="Change a grant's data scope"
)
async def update_grant_scope(
    grant_id: uuid.UUID,
    payload: EgressGrantScopeUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> EgressGrantResponse:
    """With or without the turn's data — the one thing a person edits here."""
    row = await EgressGrantRepository(db).set_scope(
        user.id, grant_id, share_turn_data=payload.share_turn_data
    )
    if row is None:
        _raise_grant_not_found(grant_id)
    await db.commit()
    return EgressGrantResponse.model_validate(row)


@router.delete("/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke a grant")
async def revoke_grant(
    grant_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    """The next run that declares this host asks again."""
    if not await EgressGrantRepository(db).delete_for_user(user.id, grant_id):
        _raise_grant_not_found(grant_id)
    await db.commit()


__all__ = ["router"]
