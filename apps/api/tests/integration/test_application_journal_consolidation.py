"""Native approval fences the existing paid source workflow and observed settlement."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError

from src.core.config import settings
from src.core.exceptions import AuthorizationError, ResourceConflictError, UsageLimitExceededError
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_consolidation import (
    execute_journal_consolidation,
    prepare_journal_consolidation,
)
from src.domains.agents.application.journal_consolidation_schemas import JournalConsolidationRequest
from src.domains.journals.models import JournalEntry
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.journals.test_consolidation_integrity import (
    _answer,
    _entry,
    _user,
)
from tests.integration.domains.journals.test_consolidation_integrity import (
    isolated_runtime as isolated_runtime,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "no_op",
        "changed",
        "expired",
        "withdrawn",
        "quota",
        "busy",
        "lost_ack",
        "committed_lost_ack",
    ],
)
async def test_confirmed_consolidation_preserves_scope_and_uncertain_outcomes(
    isolated_runtime, monkeypatch, scenario
):
    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    entry = await _entry(db, user)
    actor_id, entry_id = user.id, entry.id
    proposal = await prepare_journal_consolidation(
        db, actor_id, JournalConsolidationRequest(scope="current_account")
    )
    assert "WHEN urgent" not in str(proposal.intent) and "digest" not in str(proposal.before)
    assert user.journal_last_attempted_at is None
    await db.commit()
    if scenario == "changed":
        await db.execute(
            update(JournalEntry).where(JournalEntry.id == entry_id).values(content="Changed")
        )
        await db.commit()
    if scenario == "expired":
        proposal = proposal.model_copy(
            update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
        )

    if scenario == "quota":
        monkeypatch.setattr(
            "src.domains.agents.application.journal_consolidation.enforce_usage_limit",
            AsyncMock(side_effect=UsageLimitExceededError(limit_name="daily_budget")),
        )
    if scenario == "busy":
        user.journal_consolidation_held_until = datetime.now(UTC) + timedelta(minutes=1)
        await db.commit()

    async def withdraw():
        if scenario == "withdrawn":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        if scenario in {"lost_ack", "committed_lost_ack"}:
            _lose_settlement_acknowledgement(
                monkeypatch, committed=scenario == "committed_lost_ack"
            )

    model = _answer(
        monkeypatch,
        {
            "actions": (
                [] if scenario == "no_op" else [{"action": "delete", "entry_id": str(entry_id)}]
            )
        },
        on_generation=withdraw,
    )
    receipt = PreferenceWriteReceipt()
    if scenario in {"success", "no_op"}:
        await execute_journal_consolidation(db, actor_id, proposal, receipt)
        assert receipt.committed and receipt.values["journal_consolidation"]["actions_applied"] == (
            0 if scenario == "no_op" else 1
        )
        assert receipt.no_op is False
        remaining = await db.scalar(select(JournalEntry.id).where(JournalEntry.id == entry_id))
        assert (remaining is not None) is (scenario == "no_op")
    else:
        expected_error = (
            UsageLimitExceededError
            if scenario == "quota"
            else (
                ResourceConflictError
                if scenario == "changed"
                else AuthorizationError if scenario == "withdrawn" else CommandRejected
            )
        )
        with pytest.raises(expected_error) as refused:
            await execute_journal_consolidation(db, actor_id, proposal, receipt)
        if scenario in {"lost_ack", "committed_lost_ack"}:
            assert (
                isinstance(refused.value, CommandRejected)
                and refused.value.code == "COMPLETION_UNKNOWN"
            )
        assert not receipt.committed
        if scenario in {"changed", "expired", "quota", "busy"}:
            model.assert_not_called()


async def test_commit_acknowledgement_loss_refuses_replay_even_when_effect_is_visible(
    isolated_runtime, monkeypatch
):
    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    entry = await _entry(db, user)
    actor_id, entry_id = user.id, entry.id
    draft = await prepare_journal_consolidation(
        db, actor_id, JournalConsolidationRequest(scope="current_account")
    )
    await db.commit()
    _lose_settlement_acknowledgement(monkeypatch, committed=True)
    _answer(monkeypatch, {"actions": [{"action": "delete", "entry_id": str(entry_id)}]})

    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected, match="COMPLETION_UNKNOWN"):
        await execute_journal_consolidation(db, actor_id, draft, receipt)
    await db.rollback()
    assert await db.scalar(select(JournalEntry.id).where(JournalEntry.id == entry_id)) is None
    assert receipt.committed is False


def _lose_settlement_acknowledgement(monkeypatch, *, committed):
    from src.domains.journals import consolidation_settlement

    source_settle_commit = consolidation_settlement.commit_consolidation

    async def fail_at_effect_commit(db, count, status):
        original_commit = db.commit

        async def uncertain():
            if committed:
                await original_commit()
            raise OperationalError("COMMIT", {}, RuntimeError("lost acknowledgement"))

        monkeypatch.setattr(db, "commit", uncertain)
        try:
            await source_settle_commit(db, count, status)
        finally:
            monkeypatch.setattr(db, "commit", original_commit)

    monkeypatch.setattr(consolidation_settlement, "commit_consolidation", fail_at_effect_commit)


async def test_withdrawal_between_embeddings_preserves_source_entry_and_spends_no_second_call(
    isolated_runtime, monkeypatch
):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    entry = await _entry(db, user)
    actor_id, entry_id, original_content = user.id, entry.id, entry.content
    draft = await prepare_journal_consolidation(
        db, actor_id, JournalConsolidationRequest(scope="current_account")
    )
    await db.commit()

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr(
        "src.domains.agents.application.journal_consolidation.get_db_context", context
    )

    async def first_embedding(*args):
        monkeypatch.setattr(settings, "application_tools_enabled", False)
        return [None]

    from src.domains.journals import maintenance_actions
    from src.domains.journals.service import prepare_embeddings

    monkeypatch.setattr(maintenance_actions, "prepare_embeddings", prepare_embeddings)
    provider = AsyncMock(side_effect=first_embedding)
    monkeypatch.setattr(
        "src.domains.journals.embedding.get_journal_embeddings",
        lambda: SimpleNamespace(aembed_documents=provider),
    )
    _answer(
        monkeypatch,
        {
            "actions": [
                {
                    "action": "update",
                    "entry_id": str(entry_id),
                    "content": "A complete replacement rule",
                    "search_hints": ["keyword"],
                }
            ]
        },
    )
    receipt = PreferenceWriteReceipt()
    with pytest.raises(AuthorizationError):
        await execute_journal_consolidation(db, actor_id, draft, receipt)
    provider.assert_awaited_once()
    assert receipt.committed is False
    assert (
        await db.scalar(select(JournalEntry.content).where(JournalEntry.id == entry_id))
        == original_content
    )


async def test_source_consolidation_restores_parent_embedding_accounting_context(
    isolated_runtime, monkeypatch
):
    from src.infrastructure.llm.embedding_context import (
        clear_embedding_context,
        get_embedding_context,
        set_embedding_context,
    )

    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    entry = await _entry(db, user)
    draft = await prepare_journal_consolidation(
        db, user.id, JournalConsolidationRequest(scope="current_account")
    )
    _answer(monkeypatch, {"actions": [{"action": "delete", "entry_id": str(entry.id)}]})
    set_embedding_context(str(user.id), "parent-session", run_id="parent-run")
    parent = get_embedding_context()
    try:
        await execute_journal_consolidation(db, user.id, draft, PreferenceWriteReceipt())
        assert get_embedding_context() is parent
    finally:
        clear_embedding_context()
