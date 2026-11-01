"""Routes of the « Tools » files screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id and cursor travels in the query string or the body, bounded and
checked (``ids``); reads, downloads and acts are counted in their own windows,
a selection of several as a bulk act. A file leaves as a DOWNLOAD the browser
never renders (``downloads``): its name and its type are the Drive owner's.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.users.models import User
from src.domains.workbench import files_service
from src.domains.workbench.downloads import download_response
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.rate_limits import (
    charge_selection,
    rate_limit_download,
    rate_limit_read,
)
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.files import (
    DownloadQuery,
    FileDetail,
    FileSelection,
    FilesPage,
    FilesQuery,
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
async def get_download(query: Annotated[DownloadQuery, Query()], user: _Account) -> Response:
    """Download one file."""
    got = await files_service.download_file(user.id, query)
    return download_response(got.data, got.filename, got.mime_type, "file")


@router.post(
    "/trash",
    response_model=ActOutcome,
    summary="Move files to Drive's trash, each answered",
)
async def post_trash(selection: FileSelection, user: _Account) -> ActOutcome:
    """Move files to the trash."""
    await charge_selection(user, len(selection.file_ids))
    return await files_service.trash_files(user.id, selection)
