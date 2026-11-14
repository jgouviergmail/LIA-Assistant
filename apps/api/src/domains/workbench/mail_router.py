"""Routes of the « Tools » mail screen (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
Every id travels in the query string or the body, bounded and checked
(``ids``); a read, a single write, an act on a selection and a download are
counted in their own windows (``rate_limits``). An attachment is served as a
DOWNLOAD the browser never renders: sandboxed, kept by no cache, its name and
its type made safe — both are the sender's.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from src.core.session_dependencies import get_current_active_session_for_stream
from src.core.time_utils import resolve_user_timezone
from src.domains.users.models import User
from src.domains.workbench import (
    mail_acts,
    mail_attachments,
    mail_folders,
    mail_leaving,
    mail_reading,
)
from src.domains.workbench.downloads import download_response
from src.domains.workbench.ids import ProviderId
from src.domains.workbench.previews import preview_response
from src.domains.workbench.rate_limits import (
    charge_selection,
    rate_limit_bulk,
    rate_limit_download,
    rate_limit_read,
    rate_limit_write,
)
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.card_queries import MailAttachmentQuery
from src.domains.workbench.schemas.mail import (
    AttachmentRequest,
    InlineImagesQuery,
    LabelApplication,
    LabelChange,
    MailConversation,
    MailCounts,
    MailFolder,
    MailFolders,
    MailHtml,
    MailInlineImages,
    MailListing,
    MailMessage,
    MailPage,
    MailReplyMarks,
    MailUnsubscribe,
    MessageSelection,
    MoveOutcome,
    MoveRequest,
    NewLabel,
    ReadStateChange,
    ReplyMarksRequest,
    StarChange,
    TrashEmptied,
    UnsubscribeRequest,
)

router = APIRouter(prefix="/mail")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.get(
    "/folders",
    response_model=MailFolders,
    summary="The folder pane: the system places, then the person's own folders",
    dependencies=[Depends(rate_limit_read)],
)
async def get_folders(user: _Account) -> MailFolders:
    """Read the folder pane of the signed-in account's mailbox."""
    return await mail_folders.read_folders(user.id)


@router.get(
    "/counts",
    response_model=MailCounts,
    dependencies=[Depends(rate_limit_read)],
    summary="What the mailbox leaves unread, each figure keyed as the pane names its folder",
)
async def get_counts(user: _Account) -> MailCounts:
    """The pane's and the rail's figures, read apart from the folders."""
    return await mail_folders.read_counts(user.id)


@router.get(
    "/messages",
    response_model=MailPage,
    summary="One page of a folder, narrowed by the person's words and the chips",
    dependencies=[Depends(rate_limit_read)],
)
async def get_messages(listing: Annotated[MailListing, Query()], user: _Account) -> MailPage:
    """List the messages of a folder."""
    return await mail_reading.list_messages(user.id, resolve_user_timezone(user), listing)


@router.get(
    "/message",
    response_model=MailMessage,
    summary="One message, whole (reading it marks nothing read)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_message(
    message_id: Annotated[ProviderId, Query(alias="id", description="The message.")],
    user: _Account,
) -> MailMessage:
    """Read one message."""
    return await mail_reading.read_message(user.id, message_id)


@router.get(
    "/conversation",
    response_model=MailConversation,
    summary="What was said around a message: its conversation, oldest first, headers alone",
    dependencies=[Depends(rate_limit_read)],
)
async def get_conversation(
    message_id: Annotated[ProviderId, Query(alias="id", description="Any message of it.")],
    user: _Account,
) -> MailConversation:
    """Read a message's conversation."""
    return await mail_reading.read_conversation(user.id, message_id)


@router.post(
    "/reply-marks",
    response_model=MailReplyMarks,
    summary="Where the rows of a page stand in their conversations: answered, drafted, replied to",
    dependencies=[Depends(rate_limit_read)],
)
async def post_reply_marks(request: ReplyMarksRequest, user: _Account) -> MailReplyMarks:
    """Read the reply marks of a page: a read, posted because a page of ids fits no address."""
    return await mail_reading.read_reply_marks(user.id, resolve_user_timezone(user), request)


@router.get(
    "/message/html",
    response_model=MailHtml,
    summary="One message's HTML, for the sandboxed frame (cut at the published ceiling)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_message_html(
    message_id: Annotated[ProviderId, Query(alias="id", description="The message.")],
    user: _Account,
) -> MailHtml:
    """Read one message's HTML body."""
    return await mail_reading.read_message_html(user.id, message_id)


@router.get(
    "/message/images",
    response_model=MailInlineImages,
    summary="The images a message's HTML names, for its frame, under a published budget",
    dependencies=[Depends(rate_limit_read)],
)
async def get_inline_images(
    query: Annotated[InlineImagesQuery, Query()], user: _Account
) -> MailInlineImages:
    """Read the images a message carries inside itself."""
    return await mail_reading.read_inline_images(user.id, query)


@router.get(
    "/message/unsubscribe",
    response_model=MailUnsubscribe,
    summary="The ways out of a mailing list a message names",
    dependencies=[Depends(rate_limit_read)],
)
async def get_unsubscribe(
    message_id: Annotated[ProviderId, Query(alias="id", description="The message.")],
    user: _Account,
) -> MailUnsubscribe:
    """Read how a message says it can be left."""
    return await mail_leaving.read_ways(user.id, message_id)


@router.post(
    "/unsubscribe",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Post the one-click unsubscribe a message promises (RFC 8058)",
    dependencies=[Depends(rate_limit_write)],
)
async def post_unsubscribe(request: UnsubscribeRequest, user: _Account) -> None:
    """Leave a mailing list from one of its messages."""
    await mail_leaving.leave(user.id, request.message_id)


@router.post(
    "/labels",
    response_model=MailFolder,
    status_code=status.HTTP_201_CREATED,
    summary="Create a Gmail label",
    dependencies=[Depends(rate_limit_write)],
)
async def post_label(request: NewLabel, user: _Account) -> MailFolder:
    """Create a label."""
    return await mail_folders.create_label(user.id, request)


@router.patch(
    "/labels",
    response_model=MailFolder,
    summary="Rename a Gmail label",
    dependencies=[Depends(rate_limit_write)],
)
async def patch_label(request: LabelChange, user: _Account) -> MailFolder:
    """Rename a label."""
    return await mail_folders.rename_label(user.id, request)


@router.delete(
    "/labels",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a Gmail label (its messages stay)",
    dependencies=[Depends(rate_limit_write)],
)
async def delete_label(
    label_id: Annotated[ProviderId, Query(description="The label.")], user: _Account
) -> None:
    """Delete a label."""
    await mail_folders.delete_label(user.id, label_id)


@router.post(
    "/labels/apply",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Add and remove Gmail labels on a selection, in one act",
)
async def post_label_application(request: LabelApplication, user: _Account) -> None:
    """Apply labels to messages."""
    await charge_selection(user, len(request.message_ids))
    await mail_folders.apply_labels(user.id, request)


@router.post(
    "/read-state",
    response_model=ActOutcome,
    summary="Mark a selection read or unread; each message answered",
)
async def post_read_state(change: ReadStateChange, user: _Account) -> ActOutcome:
    """Mark messages read or unread."""
    await charge_selection(user, len(change.message_ids))
    return await mail_acts.set_read_state(user.id, change)


@router.post(
    "/star",
    response_model=ActOutcome,
    summary="Star a selection or take its star off; each message answered",
)
async def post_star(change: StarChange, user: _Account) -> ActOutcome:
    """Star messages or take their star off."""
    await charge_selection(user, len(change.message_ids))
    return await mail_acts.set_star(user.id, change)


@router.post(
    "/move",
    response_model=MoveOutcome,
    summary="Send a selection to a place; each message answered with its id from now on",
)
async def post_move(request: MoveRequest, user: _Account) -> MoveOutcome:
    """Send messages to the trash, the archive, the spam, the inbox or a folder."""
    await charge_selection(user, len(request.message_ids))
    return await mail_acts.move_messages(user.id, request)


@router.post(
    "/delete-forever",
    response_model=ActOutcome,
    summary="Delete messages of the trash for good; each message answered",
)
async def post_delete_forever(selection: MessageSelection, user: _Account) -> ActOutcome:
    """Delete messages of the trash for good."""
    await charge_selection(user, len(selection.message_ids))
    return await mail_acts.delete_forever(user.id, selection)


@router.post(
    "/empty-trash",
    response_model=TrashEmptied,
    summary="Delete for good what the trash holds, within a bound",
)
async def post_empty_trash(user: _Account) -> TrashEmptied:
    """Empty the trash: charged as an act on many, whatever it finds."""
    await rate_limit_bulk(user)
    return await mail_acts.empty_trash(user.id)


@router.get(
    "/attachment/preview",
    response_class=Response,
    summary="What can be read of one attachment (kept by no cache, never run)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_attachment_preview(
    request: Annotated[AttachmentRequest, Query()], user: _Account
) -> Response:
    """A bounded image, text or table of one attachment of a message."""
    return preview_response(await mail_attachments.preview_attachment(user.id, request))


@router.get(
    "/attachment",
    response_class=Response,
    summary="Download one attachment (served as a file, never rendered)",
    dependencies=[Depends(rate_limit_download)],
    responses={200: {"content": {"application/octet-stream": {}}}},
)
async def get_attachment(
    request: Annotated[MailAttachmentQuery, Query()], user: _Account
) -> Response:
    """Download one attachment of a message."""
    content = await mail_attachments.download_attachment(user.id, request.provider_query())
    return download_response(
        content.data, content.filename or request.filename or "", content.mime_type, "attachment"
    )
