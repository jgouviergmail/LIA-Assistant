"""Routes of the « Tools » mail screen — a mailbox's settings (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
The vacation responder read and set in the account's own days, the filters
listed, created (once per submission) and deleted. Gmail and Outlook carry them;
the service refuses them unsent elsewhere.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import mail_settings
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.mail_settings import (
    MailFilter,
    MailFilters,
    MailSenders,
    MailSignature,
    NewFilter,
    SignatureChange,
    Vacation,
    VacationChange,
)

router = APIRouter(prefix="/mail")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.get(
    "/send-as",
    response_model=MailSenders,
    summary="The addresses a message may leave from",
    dependencies=[Depends(rate_limit_read)],
)
async def get_send_as(user: _Account) -> MailSenders:
    """Read the mailbox's addresses."""
    return await mail_settings.read_send_as(user.id)


@router.get(
    "/signature",
    response_model=MailSignature,
    summary="What the active mailbox signs with",
    dependencies=[Depends(rate_limit_read)],
)
async def get_signature(user: _Account) -> MailSignature:
    """Read the signature."""
    return await mail_settings.read_signature(user.id)


@router.put(
    "/signature",
    response_model=MailSignature,
    summary="Keep what the active mailbox signs with",
    dependencies=[Depends(rate_limit_write)],
)
async def put_signature(change: SignatureChange, user: _Account) -> MailSignature:
    """Keep the signature; an empty text clears it."""
    return await mail_settings.save_signature(user.id, change)


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
    summary="Create a filter, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_filter(request: NewFilter, user: _Account) -> MailFilter:
    """Create a filter."""
    return await mail_settings.create_filter(user.id, request)


@router.delete(
    "/filters",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a filter; the mail it already sorted stays where it is",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_filter(
    user: _Account, filter_id: Annotated[ProviderId, Query(description="The filter.")]
) -> None:
    """Delete a filter."""
    await mail_settings.delete_filter(user.id, filter_id)
