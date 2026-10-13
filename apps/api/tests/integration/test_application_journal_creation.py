"""Approved manual entries use source limits, paid-work boundaries and lifecycle."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_create_schemas import JournalCreateConfiguration
from src.domains.agents.application.journal_creation import (
    execute_journal_creation,
    prepare_journal_creation,
)
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from src.domains.users.preference_cas import PreferenceWriteReceipt

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["create", "expired", "provider_off", "lost_ack", "committed_lost_ack"]
)
async def test_journal_creation_has_no_provider_work_before_exact_approval(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, scenario: str
) -> None:
    from src.domains.journals import manual_embeddings

    monkeypatch.setattr(settings, "journals_enabled", True)
    owner_id = test_user.id
    test_user.journal_portrait_full = "Previous portrait"
    await async_session.commit()
    previous_revision = test_user.journal_revision
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
    configuration = JournalCreateConfiguration(
        theme="learnings", title="Owned", content="a" * 1200, search_hints=["owner vocabulary"]
    )
    draft = await prepare_journal_creation(async_session, owner_id, configuration)
    assert calls == []
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario.endswith("lost_ack"):
        original_commit = async_session.commit

        async def lose_ack():
            if scenario == "committed_lost_ack":
                await original_commit()
            raise OperationalError("commit", {}, RuntimeError("ack unavailable"))

        monkeypatch.setattr(async_session, "commit", lose_ack)
    receipt = PreferenceWriteReceipt()
    if scenario != "create":
        with pytest.raises(AuthorizationError if scenario == "provider_off" else CommandRejected):
            await execute_journal_creation(async_session, owner_id, draft, receipt)
        assert not receipt.committed
        await async_session.rollback()
    else:
        await execute_journal_creation(async_session, owner_id, draft, receipt)
        assert receipt.committed
    assert len(calls) == (0 if scenario == "expired" else 1 if scenario == "provider_off" else 2)
    saved = await async_session.scalar(select(JournalEntry).where(JournalEntry.user_id == owner_id))
    committed = scenario in {"create", "committed_lost_ack"}
    assert (saved is not None) is committed
    if saved is not None:
        assert saved.id == draft.command_id and saved.char_count == 1200
        assert saved.source == "manual" and saved.confidence == "medium" and saved.revision == 1
    actor = await async_session.scalar(
        select(User).where(User.id == owner_id).execution_options(populate_existing=True)
    )
    assert actor is not None and actor.journal_revision == previous_revision + int(committed)
    # ADR-343: a journal change never wipes the portrait — the moved revision
    # reads it as STALE until the next consolidation replaces it.
    assert actor.journal_portrait_full == "Previous portrait"
