"""Routes of the « Tools » files screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id and cursor travels in the query string or the body, bounded and
checked (``ids``); reads, downloads and acts are counted in their own windows,
a selection of several as a bulk act. A file leaves as a DOWNLOAD the browser
never renders (``downloads``): its name and its type are the Drive owner's.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, Query, Response, UploadFile, status

from src.core.config import settings
from src.core.content_disposition import OPAQUE_MEDIA_TYPE, served_media_type
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.workbench import (
    files_organize,
    files_preview,
    files_service,
    files_sharing,
    files_text,
)
from src.domains.workbench.downloads import download_response, one_transfer
from src.domains.workbench.errors import TOO_LARGE, refuse
from src.domains.workbench.files_organize import DriveUpload
from src.domains.workbench.ids import OptionalProviderId, ProviderId
from src.domains.workbench.previews import preview_response
from src.domains.workbench.rate_limits import (
    charge_selection,
    rate_limit_download,
    rate_limit_read,
    rate_limit_write,
)
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.card_queries import FileDownloadQuery
from src.domains.workbench.schemas.files import (
    DriveItem,
    DriveQuota,
    FileCopied,
    FileCopy,
    FileDetail,
    FileFromMail,
    FileMove,
    FileName,
    FileRef,
    FileRename,
    FileSelection,
    FileShare,
    FileShareRemoval,
    FileSharing,
    FilesPage,
    FilesQuery,
    FileStar,
    FileText,
    FileTextChange,
    NewFolder,
    SharedLink,
)

router = APIRouter(prefix="/files")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.get(
    "",
    response_model=FilesPage,
    summary="One page of a folder (My Drive when none is named), or of a Drive-wide search",
    dependencies=[Depends(rate_limit_read)],
)
async def get_files(query: Annotated[FilesQuery, Query()], user: _Account) -> FilesPage:
    """List a folder or search Drive."""
    return await files_service.list_files(user.id, query)


@router.get(
    "/quota",
    response_model=DriveQuota,
    summary="What the account uses of its drive",
    dependencies=[Depends(rate_limit_read)],
)
async def get_quota(user: _Account) -> DriveQuota:
    """Read the quota."""
    return await files_service.read_quota(user.id)


@router.get(
    "/file",
    response_model=FileDetail,
    summary="One item, and the folders it lives in up to My Drive",
    dependencies=[Depends(rate_limit_read)],
)
async def get_file(
    file_id: Annotated[ProviderId, Query(alias="id", description="The item.")], user: _Account
) -> FileDetail:
    """Read one item and its breadcrumb."""
    return await files_service.read_file(user.id, file_id)


@router.get(
    "/download",
    response_class=Response,
    summary="Download a file — a Google document exported (served as a file, never rendered)",
    dependencies=[Depends(rate_limit_download)],
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def get_download(query: Annotated[FileDownloadQuery, Query()], user: _Account) -> Response:
    """Download one file."""
    got = await files_service.download_file(user.id, query.provider_query())
    return download_response(got.data, got.filename, got.mime_type, "file")


@router.get(
    "/preview",
    summary="What can be shown of a file before it is opened",
    dependencies=[Depends(rate_limit_read)],
)
async def get_preview(id: ProviderId, user: _Account) -> Response:  # noqa: A002 - the query's name
    """A bounded image or excerpt, kept by no cache and never run."""
    return preview_response(await files_preview.preview_file(user.id, id))


@router.get(
    "/text",
    response_model=FileText,
    summary="A text file's words, and the version a change must name",
    dependencies=[Depends(rate_limit_read)],
)
async def get_text(id: ProviderId, user: _Account) -> FileText:  # noqa: A002 - the query's name
    """Read a text file whole."""
    return await files_text.read_text(user.id, id)


@router.put(
    "/text",
    response_model=DriveItem,
    summary="Write a text file's words back, on the version they were read at",
    dependencies=[Depends(rate_limit_write)],
)
async def put_text(request: FileTextChange, user: _Account) -> DriveItem:
    """Write a text file back."""
    return await files_text.write_text(user.id, request)


@router.post(
    "/upload",
    response_model=DriveItem,
    status_code=status.HTTP_201_CREATED,
    summary="Send a file to a folder, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_upload(
    file: UploadFile,
    name: Annotated[FileName, Form(description="Its name on the drive.")],
    idempotency_key: Annotated[UUID, Form(description="One key per submission.")],
    user: _Account,
    folder_id: Annotated[
        OptionalProviderId, Form(description="Its folder; the top if none.")
    ] = None,
) -> DriveItem:
    """Send a file: read here, under the account's one transfer."""
    ceiling = settings.workbench_upload_max_bytes
    if file.size is None or file.size > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)
    async with one_transfer(user.id):
        upload = DriveUpload(
            name=name,
            data=await file.read(),
            mime_type=served_media_type(file.content_type or OPAQUE_MEDIA_TYPE),
            folder_id=folder_id,
            key=idempotency_key,
        )
        return await files_organize.upload_file(user.id, upload)


@router.post(
    "/from-mail",
    response_model=DriveItem,
    status_code=status.HTTP_201_CREATED,
    summary="Send a mail's attachment to a folder, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_from_mail(request: FileFromMail, user: _Account) -> DriveItem:
    """Keep a mail's attachment on the drive."""
    return await files_organize.save_mail_attachment(user.id, request)


@router.post(
    "/folders",
    response_model=DriveItem,
    status_code=status.HTTP_201_CREATED,
    summary="Create a folder, once per submission",
    dependencies=[Depends(rate_limit_write)],
)
async def post_folder(request: NewFolder, user: _Account) -> DriveItem:
    """Create a folder."""
    return await files_organize.create_folder(user.id, request)


@router.patch(
    "/file",
    response_model=DriveItem,
    summary="Rename a file or a folder",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_file(request: FileRename, user: _Account) -> DriveItem:
    """Rename an item."""
    return await files_organize.rename_file(user.id, request)


@router.patch(
    "/star",
    response_model=DriveItem,
    summary="Star an item, or take its star back",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_star(request: FileStar, user: _Account) -> DriveItem:
    """Set an item's star."""
    return await files_organize.star_file(user.id, request)


@router.post(
    "/move",
    response_model=ActOutcome,
    summary="Move files to a folder, each answered",
)
async def post_move(request: FileMove, user: _Account) -> ActOutcome:
    """Move a selection."""
    await charge_selection(user, len(request.file_ids))
    return await files_organize.move_files(user.id, request)


@router.post(
    "/copy",
    response_model=FileCopied,
    summary="Copy a file; OneDrive finishes it after answering",
    dependencies=[Depends(rate_limit_write)],
)
async def post_copy(request: FileCopy, user: _Account) -> FileCopied:
    """Copy a file."""
    return await files_organize.copy_file(user.id, request)


@router.get(
    "/sharing",
    response_model=FileSharing,
    summary="Who reaches an item",
    dependencies=[Depends(rate_limit_read)],
)
async def get_sharing(id: ProviderId, user: _Account) -> FileSharing:  # noqa: A002 - the query's
    """Read an item's sharing."""
    return await files_sharing.read_sharing(user.id, id)


@router.post(
    "/sharing",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Give a person access: the drive tells them",
    dependencies=[Depends(rate_limit_write)],
)
async def post_sharing(request: FileShare, user: _Account) -> None:
    """Share an item."""
    await files_sharing.share_file(user.id, request)


@router.post(
    "/sharing/link",
    response_model=SharedLink,
    summary="Let anyone with the link read an item",
    dependencies=[Depends(rate_limit_write)],
)
async def post_sharing_link(request: FileRef, user: _Account) -> SharedLink:
    """Open a link."""
    return await files_sharing.open_link(user.id, request.file_id)


@router.post(
    "/sharing/remove",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Take an access back",
    dependencies=[Depends(rate_limit_write)],
)
async def post_sharing_remove(request: FileShareRemoval, user: _Account) -> None:
    """Take an access back."""
    await files_sharing.remove_share(user.id, request)


@router.post(
    "/restore",
    response_model=ActOutcome,
    summary="Take files out of the trash, each answered",
)
async def post_restore(selection: FileSelection, user: _Account) -> ActOutcome:
    """Restore a selection."""
    await charge_selection(user, len(selection.file_ids))
    return await files_organize.restore_files(user.id, selection)


@router.post(
    "/delete",
    response_model=ActOutcome,
    summary="Delete files for good, each answered: by hand only",
)
async def post_delete(selection: FileSelection, user: _Account) -> ActOutcome:
    """Delete a selection for good."""
    await charge_selection(user, len(selection.file_ids))
    return await files_organize.delete_files(user.id, selection)


@router.post(
    "/trash/empty",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete for good all that the trash holds: by hand only",
    dependencies=[Depends(rate_limit_write)],
)
async def post_empty_trash(user: _Account) -> None:
    """Empty the trash."""
    await files_organize.empty_trash(user.id)


@router.post(
    "/trash",
    response_model=ActOutcome,
    summary="Move files to Drive's trash, each answered",
)
async def post_trash(selection: FileSelection, user: _Account) -> ActOutcome:
    """Move files to the trash."""
    await charge_selection(user, len(selection.file_ids))
    return await files_service.trash_files(user.id, selection)
