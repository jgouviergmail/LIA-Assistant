"""Journal deletion binds complete owned scope and preserves source lifecycle effects."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, ResourceNotFoundError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_removal import (
    execute_journal_removal,
    prepare_journal_removal,
)
from src.domains.agents.application.journal_removal_schemas import JournalDeleteRequest
from src.domains.journals.evidence_models import JournalEvidenceEvent
from src.domains.journals.models import JournalEntry
from src.domains.journals.service import JournalService
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "single",
        "all",
        "foreign",
        "stale",
        "stale_embedding",
        "bookkeeping",
        "new_row",
        "expired",
        "late_off",
        "lost_ack",
        "committed_lost_ack",
        "missing_effect",
    ],
)
async def test_journal_removal_exact_scope_and_complete_bulk(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    test_user.journals_enabled = False
    test_user.journal_portrait_full = "Owned portrait"
    other = User(id=uuid4(), email=f"journal-delete-{uuid4()}@example.test", is_active=True)
    async_session.add(other)
    await async_session.flush()
    foreign = JournalEntry(
        user_id=other.id,
        theme="learnings",
        title="Foreign",
        content="FOREIGN SECRET",
        char_count=14,
    )
    rows = [
        JournalEntry(
            user_id=owner_id, theme="learnings", title=f"Owned {i}", content="Owned", char_count=5
        )
        for i in range(203 if scenario in {"all", "new_row"} else 1)
    ]
    async_session.add_all([foreign, *rows])
    if scenario == "stale_embedding":
        rows[0].embedding = [0.0] * 1536
    await async_session.flush()
    evidence = JournalEvidenceEvent(
        user_id=owner_id,
        journal_entry_id=rows[0].id,
        rule_revision=1,
        event_key="owned-removal-event",
        outcome="evidence",
    )
    async_session.add(evidence)
    await async_session.commit()
    foreign_id = foreign.id
    evidence_id = evidence.id
    revision = test_user.journal_revision
    entry_id = (
        foreign.id
        if scenario == "foreign"
        else None if scenario in {"all", "new_row"} else rows[0].id
    )
    if scenario == "foreign":
        with pytest.raises(ResourceNotFoundError):
            await prepare_journal_removal(
                async_session, owner_id, JournalDeleteRequest(entry_id=entry_id)
            )
        return
    draft = await prepare_journal_removal(
        async_session, owner_id, JournalDeleteRequest(entry_id=entry_id)
    )
    assert "FOREIGN SECRET" not in str(draft.before) and "digest" not in str(draft.before)
    if scenario == "stale":
        await async_session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == rows[0].id)
            .values(content="Changed private source", session_id="changed private trace")
        )
        await async_session.commit()
    elif scenario == "new_row":
        async_session.add(
            JournalEntry(
                user_id=owner_id, theme="learnings", title="New", content="New", char_count=3
            )
        )
        await async_session.commit()
    elif scenario == "bookkeeping":
        from src.domains.journals.repository import JournalEntryRepository

        await JournalEntryRepository(async_session).increment_injection_counts([rows[0].id])
        await async_session.commit()
    elif scenario == "stale_embedding":
        changed_embedding = [0.0] * 1536
        changed_embedding[777] = 0.5
        await async_session.execute(
            update(JournalEntry)
            .where(JournalEntry.id == rows[0].id)
            .values(embedding=changed_embedding, updated_at=rows[0].updated_at)
        )
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "late_off":
        original_flush = async_session.flush

        async def withdraw(*args, **kwargs):
            await original_flush(*args, **kwargs)
            monkeypatch.setattr(settings, "application_tools_enabled", False)

        monkeypatch.setattr(async_session, "flush", withdraw)
    elif scenario.endswith("lost_ack"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original_commit()
            raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    elif scenario == "missing_effect":

        async def broken_delete(service: JournalService, *args, **kwargs):
            return None

        monkeypatch.setattr(JournalService, "delete_entry", broken_delete)
    receipt = PreferenceWriteReceipt()
    errors = {
        "stale": ResourceConflictError,
        "stale_embedding": ResourceConflictError,
        "new_row": ResourceConflictError,
        "expired": CommandRejected,
        "late_off": AuthorizationError,
        "lost_ack": CommandRejected,
        "committed_lost_ack": CommandRejected,
        "missing_effect": ValueError,
    }
    if scenario in errors:
        with pytest.raises(errors[scenario]):
            await execute_journal_removal(async_session, owner_id, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_journal_removal(async_session, owner_id, draft, receipt)
        assert receipt.committed
    remaining = await async_session.scalar(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.user_id == owner_id)
    )
    committed = scenario in {"single", "all", "committed_lost_ack", "bookkeeping"}
    assert remaining == (0 if committed else len(rows) + int(scenario == "new_row"))
    assert (
        await async_session.scalar(
            select(JournalEvidenceEvent.id).where(JournalEvidenceEvent.id == evidence_id)
        )
        is None
    ) is committed
    assert await async_session.get(JournalEntry, foreign_id) is not None
    actor = await async_session.scalar(
        select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    )
    assert actor is not None
    assert actor.journal_revision == revision + int(committed)
    assert actor.journal_portrait_full == (None if committed else "Owned portrait")
