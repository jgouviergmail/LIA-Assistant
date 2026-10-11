"""Original share preparation receives exact stored bytes or a full server-rendered answer."""

from dataclasses import replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import EMAIL_SHARE_MARKDOWN_MAX_CHARS
from src.domains.agents.application.asset_download_schemas import AssetDownloadInput
from src.domains.agents.application.asset_download_snapshot import open_asset_snapshot
from src.domains.agents.application.bookmark_keep_scope import bookmark_copy_digest
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.email_share_send_schemas import (
    EmailShareSendInput,
    NativeSharedFile,
    SharedSavedAnswer,
)
from src.domains.agents.effects.digest import payload_digest
from src.domains.bookmarks.export import export_bookmark
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.service import BookmarkService
from src.domains.conversations.models import Conversation
from src.domains.email_share.schemas import EmailShareRequest, SharedMarkdown
from src.domains.email_share.service import InlineFile, PreparedShare, ShareRoute, prepare_share
from src.domains.users.models import User
from src.infrastructure.email.outgoing import OutgoingAttachment


async def prepare_exact_email_source(
    db: AsyncSession,
    actor: User,
    request: EmailShareSendInput,
    route: ShareRoute,
    *,
    freeze: bool = False,
) -> tuple[PreparedShare, str, str | None]:
    source = request.attachment
    if isinstance(source, NativeSharedFile):
        prepared = await prepare_share(
            db, actor, EmailShareRequest.model_validate(request.model_dump()), route
        )
        selected, reader = await open_asset_snapshot(
            db, actor.id, AssetDownloadInput(asset_id=source.attachment_id), lock=freeze
        )
        try:
            if freeze:
                await reader.freeze(max_bytes=selected.item.file_size)
                parts = []
                while chunk := await reader.read_chunk():
                    parts.append(chunk)
                prepared = replace(
                    prepared,
                    source=InlineFile(
                        OutgoingAttachment(
                            selected.item.original_filename,
                            selected.item.mime_type,
                            b"".join(parts),
                        )
                    ),
                )
            return prepared, payload_digest(selected.model_dump(mode="json")), None
        finally:
            await reader.close()
    service = BookmarkService(db)
    if isinstance(source, SharedSavedAnswer):
        if freeze:
            await db.execute(
                select(MessageBookmark.id)
                .where(
                    MessageBookmark.id == source.bookmark_id, MessageBookmark.user_id == actor.id
                )
                .with_for_update()
            )
        row = await service.repository.get_for_user(actor.id, source.bookmark_id)
        if row is None:
            raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    else:
        if freeze:
            unlocked = await service.repository.owned_assistant_message(actor.id, source.message_id)
            if unlocked is None:
                raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
            parent = await db.scalar(
                select(Conversation.id)
                .where(
                    Conversation.id == unlocked.conversation_id, Conversation.user_id == actor.id
                )
                .with_for_update()
            )
            if parent is None:
                raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
            message = await service.repository.owned_assistant_message(
                actor.id, source.message_id, lock=True
            )
            if message is None:
                raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
            await service.repository.preceding_user_message(message, lock=True)
        row = await service.copy_owned_answer(actor.id, source.message_id)
    exported = export_bookmark(row, actor)
    text = exported.text
    if len(text) > EMAIL_SHARE_MARKDOWN_MAX_CHARS:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    # The original inline-export schema accepts a portable ASCII base name.
    inline = SharedMarkdown(
        kind="markdown",
        filename=exported.base_name,
        text=text,
    )
    desired = EmailShareRequest.model_validate(
        {**request.model_dump(), "attachment": inline.model_dump()}
    )
    prepared = await prepare_share(db, actor, desired, route)
    return (
        prepared,
        payload_digest({"copy": bookmark_copy_digest(row), "markdown": text}),
        row.content[:300],
    )
