"""One browser-consented source upload; acceptance never claims completed indexing."""

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from uuid import UUID

from fastapi import UploadFile
from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import FormData
from starlette.datastructures import UploadFile as ParsedUploadFile

from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.document_upload import read_document_upload_selection
from src.domains.agents.application.document_upload_schemas import (
    DocumentUploadInput,
    DocumentUploadPatch,
    DocumentUploadSelection,
    canonical_document_upload,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.rag_spaces.document_deletion_cleanup import cleanup_deleted_document_file
from src.domains.rag_spaces.service import RAGSpaceService
from src.domains.rag_spaces.storage_paths import stored_file_path
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.file_transfer import LocalFileRead

Check = Callable[[], Awaitable[None]]
FormParser = Callable[[], AbstractAsyncContextManager[FormData]]


def _require_unexpired(draft: ApplicationActionDraftContent) -> None:
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")


async def _check_destination(
    db: AsyncSession, actor_id: UUID, selected: DocumentUploadSelection
) -> None:
    actual = await read_document_upload_selection(
        db, actor_id, DocumentUploadInput(space_id=selected.space.id)
    )
    if actual != selected:
        raise CommandRejected("STALE_STATE")


def _selected_file(data: FormData) -> UploadFile:
    values = data.multi_items()
    if len(values) != 1 or values[0][0] != "file":
        raise ValueError("Confirm exactly one local file")
    file = values[0][1]
    if not isinstance(file, ParsedUploadFile) or not file.filename:
        raise ValueError("A local file is required")
    return UploadFile(file=file.file, size=file.size, filename=file.filename, headers=file.headers)


async def accept_document_upload(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
    check: Check,
    *,
    file_confirmed: bool,
    parse_form: FormParser,
) -> dict[str, JsonValue]:
    if (
        file_confirmed is not True
        or draft.actor_id != actor_id
        or not canonical_document_upload(draft)
    ):
        raise CommandRejected("INVALID_INPUT")
    _require_unexpired(draft)
    selected = DocumentUploadPatch.model_validate(draft.intent).document_to_upload
    await check()
    await _check_destination(db, actor_id, selected)
    # The durable browser claim is already committed. Release the read
    # transaction before waiting for the network/multipart body.
    await db.commit()
    async with parse_form() as data:
        file = _selected_file(data)
        _require_unexpired(draft)
        return await _store_selected_file(db, actor_id, draft, selected, receipt, check, file)


async def _store_selected_file(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    selected: DocumentUploadSelection,
    receipt: PreferenceWriteReceipt,
    check: Check,
    file: UploadFile,
) -> dict[str, JsonValue]:
    filename: str | None = None
    digest: str | None = None
    committing = False
    try:
        await check()
        service = RAGSpaceService(db)
        await service.get_space(selected.space.id, actor_id, for_update=True)
        await _check_destination(db, actor_id, selected)
        document = await service.upload_document(
            selected.space.id, actor_id, file, commit=False, document_id=draft.command_id
        )
        filename = document.filename
        reader = LocalFileRead.open(stored_file_path(actor_id, selected.space.id, filename))
        try:
            digest = reader.identity_digest
        finally:
            await reader.close()
        await check()
        _require_unexpired(draft)
        committing = True
        try:
            await db.commit()
        except (Exception, asyncio.CancelledError) as error:
            raise ContinuationCompletionUnknown() from error
        receipt.committed = True
    except BaseException:
        if not committing:
            await db.rollback()
            if filename is not None:
                await cleanup_deleted_document_file(actor_id, selected.space.id, filename, digest)
        raise
    return {
        "document_id": str(draft.command_id),
        "space_id": str(selected.space.id),
        "upload_accepted": True,
        "status": "pending",
        "indexing_completed": False,
    }
