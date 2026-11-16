"""Original durable approval precedes importing exactly the memories export attached in the chat.

The model names the file as the conversation shows it (or nothing, for the latest): the server
finds it among the files the person attached in this discussion (their own upload, ready, not
expired, a text export) and seals its id. The proposal counts what the file holds as the import
will (``memories.import_file``) and seals a digest of its bytes; nothing of its words enters the
proposal. The confirmation reads the file again, and an
unchanged file goes through the settings' own door (``memories.import_commands.import_memories``):
what the account holds is left alone, the rest is created all at once or not at all, its vectors
paid by the account under both ceilings, no transaction open while the provider answers.
"""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.attachment_lifecycle import AttachmentStatus
from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.authorization import load_actor
from src.domains.agents.application.availability import require_application_tools
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.memory_import_schemas import (
    MemoryImportInput,
    MemoryImportPatch,
    MemoryImportSnapshot,
    canonical_memory_import,
)
from src.domains.agents.application.memory_import_spec import MEMORY_IMPORT_OPERATION
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.attachments.models import (
    Attachment,
    AttachmentOrigin,
    ConversationAttachmentUsage,
)
from src.domains.attachments.repository import AttachmentRepository
from src.domains.memories.import_commands import held_contents, import_memories
from src.domains.memories.import_file import (
    MemoryImportFileError,
    ParsedMemoryImport,
    parse_memory_import,
)
from src.domains.users.preference_cas import PreferenceWriteReceipt
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _stored_file(file_path: str) -> Path | None:
    """The attachment's file inside the attachments store; None for a path that leaves it."""
    root = Path(settings.attachments_storage_path).resolve()
    stored = (root / file_path).resolve()
    return stored if stored.is_relative_to(root) else None


def _read_export(path: Path, limit: int) -> bytes | None:
    """The file's bytes, read no further than one past ``limit`` (blocking); None when gone."""
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        return handle.read(limit + 1)


#: What a memories export reads as once attached: the JSON or the CSV of the export.
_EXPORT_TYPES: Final = frozenset({"application/json", "text/csv", "text/plain"})


async def _attached_export(db: AsyncSession, actor_id: UUID, request: MemoryImportInput) -> UUID:
    """The export the person attached in this discussion, by its name, else the latest.

    Raises:
        CommandRejected: No discussion to read from, or no such file in it.
    """
    context = runtime_context_if_running()
    if context is None or context.user_id != actor_id or not context.conversation_id:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    query = (
        select(Attachment.id)
        .join(
            ConversationAttachmentUsage,
            ConversationAttachmentUsage.attachment_id == Attachment.id,
        )
        .where(
            ConversationAttachmentUsage.conversation_id == UUID(context.conversation_id),
            Attachment.user_id == actor_id,
            Attachment.origin == AttachmentOrigin.UPLOAD.value,
            Attachment.status == AttachmentStatus.READY,
            Attachment.mime_type.in_(_EXPORT_TYPES),
        )
        .order_by(Attachment.created_at.desc(), Attachment.id)
        .limit(1)
    )
    if request.file_name is not None:
        query = query.where(Attachment.original_filename == request.file_name)
    found = await db.scalar(query)
    if found is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    return found


async def _export(db: AsyncSession, actor_id: UUID, attachment_id: UUID) -> tuple[str, bytes]:
    """The name and bytes of the person's own attached export, or one refusal for every other
    case: another person's file, one not ready, expired or gone answer the same."""
    row = await AttachmentRepository(db).get_by_id(attachment_id)
    now = datetime.now(UTC)
    path = _stored_file(row.file_path) if row is not None else None
    if (
        row is None
        or path is None
        or row.user_id != actor_id
        or row.status != AttachmentStatus.READY
        or (row.expires_at is not None and row.expires_at <= now)
    ):
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    limit = settings.memory_import_max_file_kb * 1024
    content = await asyncio.to_thread(_read_export, path, limit)
    if content is None:
        raise CommandRejected("NOT_FOUND_OR_UNAUTHORIZED")
    if len(content) > limit:
        raise CommandRejected("CONSTRAINT_VIOLATION")
    return row.title or row.original_filename, content


async def _observe(
    db: AsyncSession, actor_id: UUID, request: MemoryImportInput, attachment_id: UUID
) -> tuple[MemoryImportSnapshot, ParsedMemoryImport]:
    """The attached export as the import would read it now, counted exactly."""
    name, content = await _export(db, actor_id, attachment_id)
    try:
        parsed = await asyncio.to_thread(
            parse_memory_import, content, max_memories=settings.memory_import_max_memories
        )
    except MemoryImportFileError as refusal:
        raise CommandRejected(
            "CONSTRAINT_VIOLATION" if refusal.code == "too_many" else "INVALID_INPUT"
        ) from refusal
    held = await held_contents(db, actor_id)
    new = sum(1 for memory in parsed.memories if memory.data.content not in held)
    snapshot = MemoryImportSnapshot(
        request=request,
        attachment_id=attachment_id,
        file_name=name,
        total=parsed.total,
        new=new,
        already_present=len(parsed.memories) - new,
        duplicates=parsed.duplicates,
        invalid=parsed.invalid,
        file_digest=hashlib.sha256(content).hexdigest(),
    )
    return snapshot, parsed


def import_draft(
    actor_id: UUID, selected: MemoryImportSnapshot, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    """The exact proposal: the file and its counts, then the memories it creates."""
    return build_action_content(
        actor_id,
        MEMORY_IMPORT_OPERATION,
        MemoryImportPatch(memories_import=selected),
        {"memories_import": selected.public_scope()},
        {"memories_import": selected.created_scope()},
        command_id=command_id,
    )


async def prepare_memory_import(
    db: AsyncSession, actor_id: UUID, request: MemoryImportInput, *, command_id: UUID | None = None
) -> ApplicationActionDraftContent:
    desired = MemoryImportInput.model_validate(request.model_dump())
    await require_application_tools(db)
    await load_actor(db, actor_id)
    attachment_id = await _attached_export(db, actor_id, desired)
    selected, _parsed = await _observe(db, actor_id, desired, attachment_id)
    return import_draft(actor_id, selected, command_id=command_id)


async def execute_memory_import(
    db: AsyncSession,
    actor_id: UUID,
    draft: ApplicationActionDraftContent,
    receipt: PreferenceWriteReceipt,
) -> None:
    if draft.actor_id != actor_id or draft.operation_id != MEMORY_IMPORT_OPERATION.operation_id:
        raise CommandRejected("FORBIDDEN")
    if not canonical_memory_import(draft):
        raise CommandRejected("INVALID_INPUT")
    expected = MemoryImportPatch.model_validate(draft.intent).memories_import
    await require_application_tools(db)
    await load_actor(db, actor_id)
    # The sealed file, never a new search: a later attachment never stands in for it.
    current, parsed = await _observe(db, actor_id, expected.request, expected.attachment_id)
    # The file is what was approved; what the account holds may have grown meanwhile, and the
    # import leaves alone whatever it holds by then.
    if current.file_digest != expected.file_digest:
        raise CommandRejected("STALE_STATE")
    if datetime.now(UTC) >= draft.expires_at:
        raise CommandRejected("EXPIRED")
    try:
        outcome = await import_memories(db, actor_id, parsed)
    except BaseAPIException as refused:
        # A ceiling or a refused provider call, before anything was written.
        raise CommandRejected("CONSTRAINT_VIOLATION") from refused
    except (Exception, asyncio.CancelledError) as error:
        # The import commits once at its end: past that point the outcome is not known.
        raise CommandRejected("COMPLETION_UNKNOWN") from error
    receipt.committed = True
    receipt.values = {
        "memories_import": {
            "total": outcome.total,
            "imported": outcome.imported,
            "already_present": outcome.already_present,
            "duplicates": outcome.duplicates,
            "invalid": outcome.invalid,
        }
    }
    logger.info("application_memories_imported", actor_id=str(actor_id), imported=outcome.imported)
