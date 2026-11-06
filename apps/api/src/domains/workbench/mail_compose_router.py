"""Routes of the « Tools » mail screen — writing (ADR-369).

Mounted under ``/workbench`` (the capability guard is the parent router's).
« Send » is the confirmation (ADR-316's doctrine): every send carries the
page's key for its submission, and leaves once under the send window. A draft
is saved under the write window — created once per key, changed against the
revision the editor holds.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, UploadFile, status

from src.core.config import settings
from src.core.constants import (
    EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS,
    WORKBENCH_MAIL_QUERY_MAX_CHARS,
)
from src.core.content_disposition import OPAQUE_MEDIA_TYPE
from src.core.session_dependencies import get_current_active_session_for_stream
from src.domains.email_share import recipients as share_recipients
from src.domains.email_share.schemas import (
    RecipientSuggestionItem,
    RecipientSuggestionsResponse,
)
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.users.models import User
from src.domains.workbench import mail_compose, mail_drafts, mail_files, mail_reading
from src.domains.workbench.downloads import one_transfer
from src.domains.workbench.errors import TOO_LARGE, refuse
from src.domains.workbench.ids import OptionalPageToken, ProviderId
from src.domains.workbench.rate_limits import (
    charge_selection,
    rate_limit_read,
    rate_limit_send,
    rate_limit_write,
)
from src.domains.workbench.schemas.acts import ActOutcome
from src.domains.workbench.schemas.mail_compose import (
    AttachableFile,
    AttachablePage,
    DraftSave,
    DraftSelection,
    DraftSend,
    DraftsPage,
    Forward,
    MailDraft,
    NewMessage,
    Reply,
    ReplyRecipients,
    SentMessage,
)

router = APIRouter(prefix="/mail")

_Account = Annotated[User, Depends(get_current_active_session_for_stream)]


@router.post(
    "/send",
    response_model=SentMessage,
    summary="Send a new message, once per submission",
    dependencies=[Depends(rate_limit_send)],
)
async def post_send(message: NewMessage, user: _Account) -> SentMessage:
    """Send a new message."""
    return await mail_compose.send_message(user.id, message)


@router.post(
    "/reply",
    response_model=SentMessage,
    summary="Reply to a message (and to all, when asked), once per submission",
    dependencies=[Depends(rate_limit_send)],
)
async def post_reply(answer: Reply, user: _Account) -> SentMessage:
    """Reply to a message."""
    return await mail_compose.reply(user.id, answer)


@router.get(
    "/reply-recipients",
    response_model=ReplyRecipients,
    summary="Who a reply to a message would reach, for the person to change",
    dependencies=[Depends(rate_limit_read)],
)
async def get_reply_recipients(
    message_id: Annotated[ProviderId, Query(description="The message answered.")],
    user: _Account,
    reply_all: Annotated[bool, Query(description="Answer every recipient too.")] = False,
) -> ReplyRecipients:
    """Read who a reply would reach."""
    return await mail_reading.read_reply_recipients(user.id, message_id, reply_all=reply_all)


@router.post(
    "/forward",
    response_model=SentMessage,
    summary="Forward a message with its files, once per submission",
    dependencies=[Depends(rate_limit_send)],
)
async def post_forward(forwarded: Forward, user: _Account) -> SentMessage:
    """Forward a message."""
    return await mail_compose.forward(user.id, forwarded)


@router.get(
    "/drafts",
    response_model=DraftsPage,
    summary="One page of the drafts, newest first",
    dependencies=[Depends(rate_limit_read)],
)
async def get_drafts(
    user: _Account,
    page_token: Annotated[OptionalPageToken, Query(description="The next page's token.")] = None,
) -> DraftsPage:
    """List the drafts."""
    return await mail_drafts.list_drafts(user.id, page_token=page_token)


@router.get(
    "/draft",
    response_model=MailDraft,
    summary="One draft, whole, with its revision",
    dependencies=[Depends(rate_limit_read)],
)
async def get_draft(
    draft_id: Annotated[ProviderId, Query(alias="id", description="The draft.")],
    user: _Account,
) -> MailDraft:
    """Read one draft."""
    return await mail_drafts.read_draft(user.id, draft_id)


@router.post(
    "/drafts",
    response_model=MailDraft,
    summary="Create a draft once per key, or change one against its revision",
    dependencies=[Depends(rate_limit_write)],
)
async def post_draft(request: DraftSave, user: _Account) -> MailDraft:
    """Save a draft."""
    return await mail_drafts.save_draft(user.id, request)


@router.post(
    "/drafts/send",
    response_model=SentMessage,
    summary="Send a draft as it was last seen, once per submission",
    dependencies=[Depends(rate_limit_send)],
)
async def post_draft_send(request: DraftSend, user: _Account) -> SentMessage:
    """Send a draft."""
    return await mail_drafts.send_draft(user.id, request)


@router.post(
    "/drafts/trash",
    response_model=ActOutcome,
    summary="Move drafts to the trash; each draft answered",
)
async def post_drafts_trash(selection: DraftSelection, user: _Account) -> ActOutcome:
    """Move drafts to the trash."""
    await charge_selection(user, len(selection.draft_ids))
    return await mail_drafts.trash_drafts(user.id, selection)


@router.get(
    "/recipients",
    response_model=RecipientSuggestionsResponse,
    summary="The contacts matching one recipient being typed (never filed: the person types)",
    dependencies=[Depends(rate_limit_read)],
)
async def get_recipients(
    user: _Account,
    q: Annotated[
        str,
        Query(max_length=EMAIL_SHARE_RECIPIENT_QUERY_MAX_CHARS, description="What is typed."),
    ],
) -> RecipientSuggestionsResponse:
    """Suggest recipients from the account's contacts (the e-mail share's matcher)."""
    found = await share_recipients.suggest_recipients(user.id, q, recorded=False)
    return RecipientSuggestionsResponse(
        query=found.query,
        suggestions=[
            RecipientSuggestionItem(name=item.name, email=item.email) for item in found.suggestions
        ],
        truncated=found.truncated,
    )


@router.post(
    "/files",
    response_model=AttachableFile,
    status_code=status.HTTP_201_CREATED,
    summary="Keep a file of the device for the message being written",
    dependencies=[
        Depends(rate_limit_write),
        *capability_dependencies(PlatformCapability.ATTACHMENTS),
    ],
)
async def post_file(file: UploadFile, user: _Account) -> AttachableFile:
    """Keep a file of the device: read here, under the account's one transfer."""
    ceiling = settings.workbench_upload_max_bytes
    if file.size is None or file.size > ceiling:
        refuse(TOO_LARGE, max_bytes=ceiling)
    async with one_transfer(user.id):
        kept = mail_files.DeviceFile(
            filename=file.filename or "",
            declared_type=file.content_type or OPAQUE_MEDIA_TYPE,
            data=await file.read(),
        )
        return await mail_files.keep_device_file(user.id, kept)


@router.get(
    "/attachable",
    response_model=AttachablePage,
    summary="The person's own live files a new message may carry, with their exact total",
    dependencies=[Depends(rate_limit_read)],
)
async def get_attachable(
    user: _Account,
    q: Annotated[
        str | None,
        Query(max_length=WORKBENCH_MAIL_QUERY_MAX_CHARS, description="A part of a file's name."),
    ] = None,
    offset: Annotated[int, Query(ge=0, le=100_000, description="Where the page starts.")] = 0,
) -> AttachablePage:
    """List the files a message may carry."""
    return await mail_files.list_attachable(user.id, query=q, offset=offset)
