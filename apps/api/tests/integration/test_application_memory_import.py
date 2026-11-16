"""Importing an export attached in the chat, on real PostgreSQL and a real stored file (R5).

The model names the file as the conversation shows it, or nothing: the server finds it among the
files the person attached in THIS discussion and seals its id. The proposal counts it exactly; the
confirmation imports through the same door as the settings (``import_memories``): what is new is
created, what the account holds is left, all or nothing. A file of another discussion or of another
person, a file changed after the proposal, or an expired proposal imports nothing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.conversation_target import ConversationKind
from src.domains.agents.application import memory_import
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.memory_import import (
    execute_memory_import,
    prepare_memory_import,
)
from src.domains.agents.application.memory_import_schemas import MemoryImportInput
from src.domains.attachments.models import (
    Attachment,
    AttachmentOrigin,
    AttachmentStatus,
    ConversationAttachmentUsage,
)
from src.domains.conversations.models import Conversation
from src.domains.memories import creation_embeddings
from src.domains.memories.models import Memory
from src.domains.memories.schemas import MemoryCreate
from src.domains.memories.service import MemoryService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration

_VECTOR = [0.5] * 1536
EXPORT = json.dumps(
    {
        "memories": [
            {"content": "Prefers trains to planes", "category": "preference"},
            {"content": "Has a dog named Pixel", "category": "personal"},
            {"content": "Has a dog named Pixel", "category": "personal"},
            {"content": "Allergic to peanuts", "category": "personal"},
        ]
    }
).encode("utf-8")


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "attachments_storage_path", str(tmp_path))
    monkeypatch.setattr(
        creation_embeddings,
        "generate_document_embeddings",
        AsyncMock(side_effect=lambda texts: [_VECTOR for _ in texts]),
    )
    monkeypatch.setattr(creation_embeddings, "enforce_usage_limit", AsyncMock())
    return tmp_path


async def _discussion(
    db: AsyncSession, owner: UUID, kind: ConversationKind = ConversationKind.MAIN
) -> Conversation:
    """A discussion of the person: their one main discussion, or an annex."""
    row = Conversation(user_id=owner, title="Import under test", kind=kind)
    db.add(row)
    await db.flush()
    return row


async def _attached(
    db: AsyncSession,
    owner: UUID,
    root: Path,
    content: bytes,
    *,
    discussion: Conversation | None,
    name: str = "memories.json",
) -> Attachment:
    relative = f"{uuid4()}/{name}"
    stored = root / relative
    stored.parent.mkdir(parents=True)
    stored.write_bytes(content)
    row = Attachment(
        user_id=owner,
        original_filename=name,
        stored_filename=name,
        mime_type="application/json",
        file_size=len(content),
        file_path=relative,
        content_type="document",
        origin=AttachmentOrigin.UPLOAD.value,
        status=AttachmentStatus.READY,
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(row)
    await db.flush()
    if discussion is not None:
        db.add(
            ConversationAttachmentUsage(
                attachment_id=row.id,
                conversation_id=discussion.id,
                conversation_revision=discussion.revision or 0,
            )
        )
    await db.commit()
    return row


def _in_discussion(monkeypatch: pytest.MonkeyPatch, owner: UUID, discussion: Conversation) -> None:
    """The run the tool is called in: its person and its discussion, as LangGraph hands them."""
    context = SimpleNamespace(user_id=owner, conversation_id=str(discussion.id))
    monkeypatch.setattr(memory_import, "runtime_context_if_running", lambda: context)


async def _contents(db: AsyncSession, owner: UUID) -> set[str]:
    rows = await db.scalars(
        select(Memory.content)
        .where(Memory.user_id == owner, Memory.invalidated_at.is_(None))
        .execution_options(populate_existing=True)
    )
    return set(rows)


async def test_the_confirmed_proposal_imports_what_is_new_and_leaves_the_rest(
    async_session: AsyncSession, test_user: User, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    service = MemoryService(async_session, embedder=AsyncMock(return_value=(None, None)))
    await service.create_from_management(
        test_user.id, MemoryCreate(content="Allergic to peanuts", category="personal")
    )
    discussion = await _discussion(async_session, test_user.id)
    # Another discussion's export is never the one read.
    elsewhere = await _discussion(async_session, test_user.id, ConversationKind.SECONDARY)
    await _attached(async_session, test_user.id, store, b'{"memories": []}', discussion=elsewhere)
    attached = await _attached(async_session, test_user.id, store, EXPORT, discussion=discussion)
    _in_discussion(monkeypatch, test_user.id, discussion)

    draft = await prepare_memory_import(async_session, test_user.id, MemoryImportInput())
    shown = draft.before["memories_import"]
    assert (shown["total"], shown["new"], shown["already_present"], shown["duplicates"]) == (
        4,
        2,
        1,
        1,
    )
    assert draft.intent["memories_import"]["attachment_id"] == str(attached.id)
    assert "Pixel" not in draft.model_dump_json(), "no memory's words enter the proposal"
    receipt = PreferenceWriteReceipt()
    await execute_memory_import(async_session, test_user.id, draft, receipt)

    assert receipt.committed
    assert receipt.values == {
        "memories_import": {
            "total": 4,
            "imported": 2,
            "already_present": 1,
            "duplicates": 1,
            "invalid": 0,
        }
    }
    assert await _contents(async_session, test_user.id) == {
        "Prefers trains to planes",
        "Has a dog named Pixel",
        "Allergic to peanuts",
    }


async def test_a_file_named_is_the_one_read_and_an_unknown_name_is_refused(
    async_session: AsyncSession, test_user: User, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    discussion = await _discussion(async_session, test_user.id)
    named = await _attached(
        async_session, test_user.id, store, EXPORT, discussion=discussion, name="old.json"
    )
    await _attached(async_session, test_user.id, store, b'{"memories": []}', discussion=discussion)
    _in_discussion(monkeypatch, test_user.id, discussion)

    draft = await prepare_memory_import(
        async_session, test_user.id, MemoryImportInput(file_name="old.json")
    )
    assert draft.intent["memories_import"]["attachment_id"] == str(named.id)

    with pytest.raises(CommandRejected) as refused:
        await prepare_memory_import(
            async_session, test_user.id, MemoryImportInput(file_name="never-attached.json")
        )
    assert refused.value.code == "NOT_FOUND_OR_UNAUTHORIZED"


async def test_a_file_never_attached_in_this_discussion_is_never_read(
    async_session: AsyncSession, test_user: User, store: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    discussion = await _discussion(async_session, test_user.id)
    await _attached(async_session, test_user.id, store, EXPORT, discussion=None)
    _in_discussion(monkeypatch, test_user.id, discussion)

    with pytest.raises(CommandRejected) as refused:
        await prepare_memory_import(async_session, test_user.id, MemoryImportInput())

    assert refused.value.code == "NOT_FOUND_OR_UNAUTHORIZED"


async def test_outside_a_run_nothing_is_read(
    async_session: AsyncSession, test_user: User, store: Path
) -> None:
    with pytest.raises(CommandRejected) as refused:
        await prepare_memory_import(async_session, test_user.id, MemoryImportInput())

    assert refused.value.code == "NOT_FOUND_OR_UNAUTHORIZED"


@pytest.mark.parametrize("scenario", ["file_changed", "expired"])
async def test_a_proposal_that_no_longer_holds_imports_nothing(
    async_session: AsyncSession,
    test_user: User,
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    discussion = await _discussion(async_session, test_user.id)
    attached = await _attached(async_session, test_user.id, store, EXPORT, discussion=discussion)
    _in_discussion(monkeypatch, test_user.id, discussion)
    draft = await prepare_memory_import(async_session, test_user.id, MemoryImportInput())
    if scenario == "file_changed":
        (store / attached.file_path).write_bytes(EXPORT.replace(b"trains", b"boats"))
    else:
        draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    receipt = PreferenceWriteReceipt()

    with pytest.raises(CommandRejected):
        await execute_memory_import(async_session, test_user.id, draft, receipt)

    assert not receipt.committed
    assert await _contents(async_session, test_user.id) == set()
