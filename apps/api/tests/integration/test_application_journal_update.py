"""Edited journal content must retain source evidence and preview semantics."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_update import (
    execute_journal_update,
    prepare_journal_update,
)
from src.domains.agents.application.journal_update_schemas import JournalUpdateRequest
from src.domains.journals import manual_embeddings
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "content",
        "title",
        "confidence",
        "noop",
        "stale",
        "foreign",
        "expired",
        "provider_off",
        "bookkeeping",
        "contradictions",
        "lost_ack",
        "committed_lost_ack",
    ],
)
async def test_journal_update_uses_source_transition_and_exact_semantic_scope(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    test_user.journal_portrait_full = "Stored portrait"
    row = JournalEntry(
        user_id=owner_id,
        theme="learnings",
        title="Old title",
        content="Old content",
        char_count=11,
        confidence="medium",
        evidence_count=5,
        contradiction_count=2 if scenario == "contradictions" else 0,
        revision=3,
    )
    async_session.add(row)
    await async_session.commit()
    entry_id = row.id
    calls: list[str] = []

    async def embed(text: str):
        calls.append(text)
        if scenario == "provider_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        return None

    async def allowed(actor_id, *, layer):
        assert actor_id == owner_id and layer == "journal_management"

    monkeypatch.setattr(manual_embeddings, "_generate_document_embedding", embed)
    monkeypatch.setattr(manual_embeddings, "enforce_usage_limit", allowed)
    changes = (
        {"title": "New title"}
        if scenario == "title"
        else (
            {"confidence": "high"}
            if scenario in {"confidence", "contradictions"}
            else {
                "content": "Old content" if scenario == "noop" else "Full new content",
                "confidence": "high",
            }
        )
    )
    request = JournalUpdateRequest.model_validate(
        {"entry_id": str(uuid4() if scenario == "foreign" else entry_id), "changes": changes}
    )
    if scenario == "foreign":
        with pytest.raises(ResourceNotFoundError):
            await prepare_journal_update(async_session, owner_id, request)
        return
    draft = await prepare_journal_update(async_session, owner_id, request)
    assert calls == []
    assert draft.after["journal_entry"]["confidence"] == (
        "low" if scenario == "contradictions" else "medium"
    )
    if scenario == "stale":
        await async_session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == entry_id)
            .values(content="Concurrent words")
        )
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "bookkeeping":
        from src.domains.journals.repository import JournalEntryRepository

        await JournalEntryRepository(async_session).increment_injection_counts([entry_id])
        await async_session.commit()
    elif scenario.endswith("lost_ack"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original_commit()
            raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    errors = {
        "stale": ResourceConflictError,
        "expired": CommandRejected,
        "provider_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_journal_update(async_session, owner_id, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_journal_update(async_session, owner_id, draft, receipt)
        assert receipt.committed and receipt.no_op is (scenario in {"noop", "confidence"})
    saved = await async_session.scalar(
        select(JournalEntry)
        .where(JournalEntry.id == entry_id)
        .execution_options(populate_existing=True)
    )
    assert saved is not None
    replaced = scenario in {"content", "bookkeeping", "committed_lost_ack"}
    assert saved.revision == (4 if replaced else 3)
    assert saved.evidence_count == (0 if replaced else 5) and saved.contradiction_count == (
        2 if scenario == "contradictions" else 0
    )
    assert len(calls) == (
        1
        if scenario
        in {"content", "title", "provider_off", "bookkeeping", "lost_ack", "committed_lost_ack"}
        else 0
    )
