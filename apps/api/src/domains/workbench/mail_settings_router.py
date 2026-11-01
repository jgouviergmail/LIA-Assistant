"""Routes of the « Tools » mail screen — Gmail's mailbox settings (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
The vacation responder read and set in the account's own days, the filters
listed and created (once per submission). Gmail alone carries them; the
service refuses them unsent elsewhere.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import mail_settings
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.mail_settings import (
    MailFilter,
    MailFilters,
    NewFilter,
    Vacation,
    VacationChange,
)

router = APIRouter(prefix="/mail")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.get(
    "/vacation",
    response_model=Vacation,
    summary="The vacation responder, in the account's days",
    dependencies=[Depends(rate_limit_read)],
)
async def get_vacation(user: _Account) -> Vacation:
    """Read the vacation responder."""
    return await mail_settings.read_vacation(user.id, resolve_user_timezone(user))


@router.put(
    "/vacation",
    response_model=Vacation,
    summary="Turn the vacation responder on (its words and days) or off",
    dependencies=[Depends(rate_limit_write)],
)
async def put_vacation(change: VacationChange, user: _Account) -> Vacation:
    """Set the vacation responder."""
    return await mail_settings.set_vacation(user.id, resolve_user_timezone(user), change)


@router.get(
    "/filters",
    response_model=MailFilters,
    summary="The mailbox's filters, each with what it matches and does",
    dependencies=[Depends(rate_limit_read)],
)
async def get_filters(user: _Account) -> MailFilters:
    """List the filters."""
    return await mail_settings.list_filters(user.id)


@router.post(
    "/filters",
    response_model=MailFilter,
    status_code=status.HTTP_201_CREATED,
    summary="Create a filter, once per submission (nothing deletes one here)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_filter(request: NewFilter, user: _Account) -> MailFilter:
    """Create a filter."""
    return await mail_settings.create_filter(user.id, request)
