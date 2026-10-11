"""A saved correction and its generated portrait have separate truthful outcomes."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from src.core.config import settings
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.journal_feedback import (
    execute_journal_feedback,
    prepare_journal_feedback,
)
from src.domains.agents.application.journal_feedback_schemas import JournalFeedbackRequest
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
    "scenario", ["success", "model_failure", "changed", "expired", "withdrawn"]
)
async def test_feedback_is_saved_only_after_confirmation_and_survives_generation_failure(
    isolated_runtime, monkeypatch, scenario
):
    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    await _entry(db, user)
    actor_id = user.id
    provider = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.domains.journals.manual_embeddings._generate_document_embedding", provider
    )
    draft = await prepare_journal_feedback(
        db,
        actor_id,
        JournalFeedbackRequest(
            comment="That portrait is inaccurate", highlighted_section="Prior portrait"
        ),
    )
    provider.assert_not_called()
    assert "That portrait is inaccurate" in str(draft.after)
    model = _answer(monkeypatch, "{" if scenario == "model_failure" else {"actions": []})
    if scenario == "changed":
        await _entry(db, user, "Concurrent source entry")
    if scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    if scenario == "withdrawn":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    receipt = PreferenceWriteReceipt()
    if scenario == "success":
        await execute_journal_feedback(db, actor_id, draft, receipt)
        assert (
            receipt.committed
            and receipt.values["journal_feedback"]["maintenance_status"] == "no_op"
        )
    else:
        from src.core.exceptions import AuthorizationError, ResourceConflictError

        expected = (
            ResourceConflictError
            if scenario == "changed"
            else AuthorizationError if scenario == "withdrawn" else CommandRejected
        )
        with pytest.raises(expected):
            await execute_journal_feedback(db, actor_id, draft, receipt)
    rows = (
        await db.scalars(
            select(JournalEntry).where(
                JournalEntry.user_id == actor_id, JournalEntry.source == "user_correction"
            )
        )
    ).all()
    if scenario in {"changed", "expired", "withdrawn"}:
        assert rows == [] and not receipt.committed
        provider.assert_not_called()
        model.assert_not_called()
    else:
        assert len(rows) == 1 and rows[0].level == "L0" and rows[0].confidence == "medium"
        assert (
            rows[0].content
            == "User highlighted: «Prior portrait»\nUser feedback: That portrait is inaccurate"
        )
        assert rows[0].id == draft.command_id and receipt.committed
        assert receipt.values["journal_feedback"]["feedback_saved"] is True


async def test_concurrent_change_after_saved_correction_refuses_generation_but_keeps_feedback(
    isolated_runtime, monkeypatch
):
    from src.domains.agents.application import journal_feedback

    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    await _entry(db, user)
    actor_id = user.id
    monkeypatch.setattr(
        "src.domains.journals.manual_embeddings._generate_document_embedding",
        AsyncMock(return_value=None),
    )
    draft = await prepare_journal_feedback(
        db, actor_id, JournalFeedbackRequest(comment="Correction")
    )
    source_create = journal_feedback.create_managed_journal_entry

    async def create_then_concurrent_change(*args, **kwargs):
        created = await source_create(*args, **kwargs)
        await _entry(db, user, "Concurrent maintenance input")
        return created

    monkeypatch.setattr(
        journal_feedback, "create_managed_journal_entry", create_then_concurrent_change
    )
    model = _answer(monkeypatch, {"actions": []})
    receipt = PreferenceWriteReceipt()
    from src.core.exceptions import ResourceConflictError

    with pytest.raises(ResourceConflictError):
        await execute_journal_feedback(db, actor_id, draft, receipt)
    model.assert_not_called()
    assert receipt.committed and receipt.values["journal_feedback"]["feedback_saved"] is True
    assert receipt.values["journal_feedback"]["maintenance_status"] == "failed"
    assert (
        await db.scalar(select(JournalEntry.id).where(JournalEntry.id == draft.command_id))
        == draft.command_id
    )


async def test_original_approval_deadline_survives_the_saved_correction_phase(
    isolated_runtime, monkeypatch
):
    from src.domains.agents.application import journal_feedback

    db = isolated_runtime
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "journals_enabled", True)
    user = await _user(db)
    await _entry(db, user)
    actor_id = user.id
    monkeypatch.setattr(
        "src.domains.journals.manual_embeddings._generate_document_embedding",
        AsyncMock(return_value=None),
    )
    draft = await prepare_journal_feedback(
        db, actor_id, JournalFeedbackRequest(comment="Correction")
    )
    source_create = journal_feedback.create_managed_journal_entry

    async def create_then_expire(*args, **kwargs):
        created = await source_create(*args, **kwargs)
        draft.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        return created

    monkeypatch.setattr(journal_feedback, "create_managed_journal_entry", create_then_expire)
    model = _answer(monkeypatch, {"actions": []})
    receipt = PreferenceWriteReceipt()
    with pytest.raises(CommandRejected) as refused:
        await execute_journal_feedback(db, actor_id, draft, receipt)
    assert refused.value.code == "EXPIRED" and receipt.committed
    assert receipt.values["journal_feedback"]["feedback_saved"] is True
    model.assert_not_called()
