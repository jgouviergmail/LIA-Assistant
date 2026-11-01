"""Routes of the « Tools » contacts screen (ADR-369, D4).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id and cursor travels in the query string or the body, bounded and
checked (``ids``); reads and writes are counted in two windows. Groups and
« other contacts » answer where the provider has them, and refuse elsewhere.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import StringConstraints

from src.core.constants import WORKBENCH_MAIL_QUERY_MAX_CHARS
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.workbench import contacts_service
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.rate_limits import rate_limit_read, rate_limit_write
from src.domains.workbench.schemas.contacts import (
    Contact,
    ContactChange,
    ContactGroups,
    ContactsPage,
    ContactsQuery,
    NewContact,
)

router = APIRouter(prefix="/contacts")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]
_ContactId = Annotated[ProviderId, Query(alias="id", description="The contact.")]
_Words = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS
    ),
    Query(description="The words searched."),
]


@router.get(
    "",
    response_model=ContactsPage,
    summary="One page of contacts: the account's, a search, or a group (Google)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_contacts(query: Annotated[ContactsQuery, Query()], user: _Account) -> ContactsPage:
    """List contacts."""
    return await contacts_service.list_contacts(user.id, query)


@router.get(
    "/contact",
    response_model=Contact,
    summary="One contact, whole and typed",
    dependencies=[Depends(rate_limit_read)],
)
async def get_contact(contact_id: _ContactId, user: _Account) -> Contact:
    """Read one contact."""
    return await contacts_service.read_contact(user.id, contact_id)


@router.get(
    "/groups",
    response_model=ContactGroups,
    summary="The account's contact groups (Google)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_groups(user: _Account) -> ContactGroups:
    """List the contact groups."""
    return await contacts_service.list_groups(user.id)


@router.get(
    "/other",
    response_model=ContactsPage,
    summary="« Other contacts » — met in mail, never saved (Google)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_other(q: _Words, user: _Account) -> ContactsPage:
    """Search the other contacts."""
    return await contacts_service.search_other(user.id, q)


@router.post(
    "",
    response_model=Contact,
    status_code=status.HTTP_201_CREATED,
    summary="Create a contact, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_contact(request: NewContact, user: _Account) -> Contact:
    """Create a contact."""
    return await contacts_service.create_contact(user.id, request)


@router.patch(
    "",
    response_model=Contact,
    summary="Change a contact (a list sent replaces that list)",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_contact(request: ContactChange, user: _Account) -> Contact:
    """Change a contact."""
    return await contacts_service.update_contact(user.id, request)


@router.delete(
    "",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete a contact",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_contact(contact_id: _ContactId, user: _Account) -> Response:
    """Delete a contact."""
    await contacts_service.delete_contact(user.id, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
