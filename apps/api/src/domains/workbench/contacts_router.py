"""Routes of the « Tools » contacts screen (ADR-369, D4).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id and cursor travels in the query string or the body, bounded and
checked (``ids``); reads and writes are counted in two windows. Groups and
« other contacts » answer where the provider has them, and refuse elsewhere.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status
from pydantic import StringConstraints

from src.core.constants import (
    WORKBENCH_CONTACT_PHOTO_MAX_BYTES,
    WORKBENCH_CONTACTS_IMPORT_MAX_BYTES,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import (
    contacts_groups,
    contacts_history,
    contacts_photos,
    contacts_service,
    contacts_transfer,
)
from src.domains.workbench.downloads import DOWNLOAD_POLICY, download_response, one_transfer
from src.domains.workbench.errors import TOO_LARGE, refuse
from src.domains.workbench.ids import OptionalProviderId, ProviderId
from src.domains.workbench.rate_limits import (
    rate_limit_download,
    rate_limit_read,
    rate_limit_write,
)
from src.domains.workbench.schemas.contacts import (
    Contact,
    ContactChange,
    ContactGroup,
    ContactGroups,
    ContactHistory,
    ContactHistoryQuery,
    ContactsImported,
    ContactsPage,
    ContactsQuery,
    GroupJoin,
    GroupLeave,
    GroupRename,
    NewContact,
    OtherContactSave,
)

router = APIRouter(prefix="/contacts")

_VCARD_TYPE: Final = "text/vcard"
_VCARD_NAME: Final = "contacts.vcf"

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
    "/export",
    response_class=Response,
    summary="One contact, or the address book up to its bound, as a vCard file",
    dependencies=[Depends(rate_limit_download)],
)
async def get_export(
    user: _Account,
    contact_id: Annotated[OptionalProviderId, Query(alias="id", description="The contact.")] = None,
) -> Response:
    """Export contacts: the file's name says when the bound cut them."""
    exported = await contacts_transfer.export_contacts(user.id, contact_id)
    return download_response(exported.data, exported.filename, _VCARD_TYPE, _VCARD_NAME)


@router.post(
    "/import",
    response_model=ContactsImported,
    summary="Make a contact of each card of a vCard file, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_import(
    file: UploadFile,
    idempotency_key: Annotated[UUID, Form(description="One key per submission.")],
    user: _Account,
) -> ContactsImported:
    """Import a file: read here, under the account's one transfer."""
    if file.size is None or file.size > WORKBENCH_CONTACTS_IMPORT_MAX_BYTES:
        refuse(TOO_LARGE, max_bytes=WORKBENCH_CONTACTS_IMPORT_MAX_BYTES)
    async with one_transfer(user.id):
        return await contacts_transfer.import_contacts(user.id, await file.read(), idempotency_key)


@router.get(
    "/photo",
    summary="A contact's photo: an image, kept by no cache and never run",
    dependencies=[Depends(rate_limit_read)],
)
async def get_photo(contact_id: _ContactId, user: _Account) -> Response:
    """Read a contact's photo."""
    photo = await contacts_photos.read_photo(user.id, contact_id)
    return Response(
        content=photo.data,
        media_type=photo.mime_type,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": DOWNLOAD_POLICY,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.put(
    "/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Replace a contact's photo with what the person picked, redrawn",
    dependencies=[Depends(rate_limit_write)],
)
async def put_photo(
    file: UploadFile,
    contact_id: Annotated[ProviderId, Form(alias="id", description="The contact.")],
    user: _Account,
) -> Response:
    """Change a contact's photo: read here, under the account's one transfer."""
    if file.size is None or file.size > WORKBENCH_CONTACT_PHOTO_MAX_BYTES:
        refuse(TOO_LARGE, max_bytes=WORKBENCH_CONTACT_PHOTO_MAX_BYTES)
    async with one_transfer(user.id):
        await contacts_photos.write_photo(user.id, contact_id, await file.read())
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/photo",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Take a contact's photo off",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_photo(contact_id: _ContactId, user: _Account) -> Response:
    """Remove a contact's photo."""
    await contacts_photos.remove_photo(user.id, contact_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/history",
    response_model=ContactHistory,
    summary="The latest mail, meetings, calls and texts with a contact",
    dependencies=[Depends(rate_limit_read)],
)
async def get_history(
    query: Annotated[ContactHistoryQuery, Query()], user: _Account, response: Response
) -> ContactHistory:
    """Read what a contact and the person exchanged; texts make the answer private."""
    response.headers["Cache-Control"] = "no-store"
    zone = resolve_user_timezone(user.timezone)
    return await contacts_history.contact_history(user.id, zone, query, datetime.now(UTC))


@router.get(
    "/member-of",
    response_model=ContactGroups,
    summary="The person's own groups a contact is in",
    dependencies=[Depends(rate_limit_read)],
)
async def get_member_of(contact_id: _ContactId, user: _Account) -> ContactGroups:
    """List a contact's groups."""
    return await contacts_groups.groups_of(user.id, contact_id)


@router.post(
    "/groups/join",
    response_model=ContactGroup,
    summary="Put a contact in the group of that name, made if nobody holds it",
    dependencies=[Depends(rate_limit_write)],
)
async def post_join(request: GroupJoin, user: _Account) -> ContactGroup:
    """Add a contact to a group."""
    return await contacts_groups.join_group(user.id, request)


@router.post(
    "/groups/leave",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Take a contact out of a group",
    dependencies=[Depends(rate_limit_write)],
)
async def post_leave(request: GroupLeave, user: _Account) -> Response:
    """Take a contact out of a group."""
    await contacts_groups.leave_group(user.id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/groups",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Rename one of the person's groups",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_group(request: GroupRename, user: _Account) -> Response:
    """Rename a group."""
    await contacts_groups.rename_group(user.id, request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/groups",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    summary="Delete one of the person's groups: its contacts stay",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_group(group_id: _ContactId, user: _Account) -> Response:
    """Delete a group."""
    await contacts_groups.delete_group(user.id, group_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/groups",
    response_model=ContactGroups,
    summary="The account's contact groups",
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
    "/other/save",
    response_model=Contact,
    status_code=status.HTTP_201_CREATED,
    summary="Keep a contact met in mail among the person's own (Google)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_other_save(request: OtherContactSave, user: _Account) -> Contact:
    """Save an other contact."""
    return await contacts_service.save_other_contact(user.id, request)


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
