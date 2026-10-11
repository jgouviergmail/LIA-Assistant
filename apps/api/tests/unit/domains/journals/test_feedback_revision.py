"""Response reception can only reinforce the rule revision archived with it."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.domains.conversations import response_feedback as feedback
from src.domains.journals import feedback_hooks

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture
def hooks(monkeypatch):
    port = SimpleNamespace(apply_verdict=AsyncMock(return_value=1))
    monkeypatch.setattr(feedback, "_journal_hooks", port)
    monkeypatch.setattr(feedback, "_journals_ready", lambda: True)
    return port


async def test_feedback_without_archived_revision_is_never_inferred(hooks):
    entry_id = str(uuid4())
    assert (
        await feedback.apply_verdict_to_journals(
            MagicMock(),
            uuid4(),
            {"injected_journal_ids": [entry_id]},
            "thumbs_up",
            message_id=uuid4(),
            conversation_id=uuid4(),
        )
        == 0
    )
    hooks.apply_verdict.assert_not_awaited()


async def test_feedback_carries_exact_revision_and_stable_message_event(hooks):
    entry_id, message_id, conversation_id = str(uuid4()), uuid4(), uuid4()
    metadata = {"injected_journal_ids": [entry_id], "injected_journal_revisions": {entry_id: 3}}
    assert (
        await feedback.apply_verdict_to_journals(
            MagicMock(),
            uuid4(),
            metadata,
            "thumbs_down",
            message_id=message_id,
            conversation_id=conversation_id,
        )
        == 1
    )
    kwargs = hooks.apply_verdict.await_args.kwargs
    assert kwargs["expected_revisions"] == {entry_id: 3}
    assert kwargs["event_key"] == f"response:{message_id}"
    assert kwargs["evidence_source"] == str(conversation_id)


async def test_archive_keeps_only_versions_for_actual_exposed_ids():
    from src.domains.agents.api import archive_metadata

    first, other = str(uuid4()), str(uuid4())
    base = {"run_id": "turn"}
    result = archive_metadata.with_injected_journal_versions(base, [first], {first: 2, other: 9})
    assert result["injected_journal_ids"] == [first]
    assert result["injected_journal_revisions"] == {first: 2}
    assert base == {"run_id": "turn"}


@pytest.fixture
def verdict_runtime(monkeypatch):
    owner, entry_id = uuid4(), uuid4()
    entry = SimpleNamespace(
        id=entry_id, user_id=owner, revision=2, evidence_count=0, contradiction_count=0
    )
    db = MagicMock()

    @asynccontextmanager
    async def savepoint():
        yield

    db.begin_nested = savepoint
    service = SimpleNamespace(
        get_entry_for_user=AsyncMock(return_value=entry), update_entry=AsyncMock(return_value=entry)
    )
    monkeypatch.setattr("src.domains.journals.service.JournalService", lambda _: service)
    monkeypatch.setattr(
        feedback_hooks, "snapshot_extraction_consent", AsyncMock(return_value=4), raising=False
    )
    monkeypatch.setattr(
        feedback_hooks, "is_capability_enabled", AsyncMock(return_value=True), raising=False
    )
    return SimpleNamespace(owner=owner, entry=entry, service=service, db=db)


async def test_changed_rule_does_not_receive_old_response_verdict(verdict_runtime):
    rt = verdict_runtime
    assert (
        await feedback_hooks.JournalResponseFeedbackHooks().apply_verdict(
            rt.db,
            rt.owner,
            [str(rt.entry.id)],
            "evidence",
            expected_revisions={str(rt.entry.id): 1},
            event_key="response:turn",
            evidence_source=None,
        )
        == 0
    )
    rt.service.update_entry.assert_not_awaited()


async def test_feedback_deduplicates_exposed_ids_and_passes_version(verdict_runtime):
    rt = verdict_runtime

    async def update(entry, **kwargs):
        entry.evidence_count += 1
        return entry

    rt.service.update_entry.side_effect = update
    assert (
        await feedback_hooks.JournalResponseFeedbackHooks().apply_verdict(
            rt.db,
            rt.owner,
            [str(rt.entry.id)] * 2,
            "evidence",
            expected_revisions={str(rt.entry.id): 2},
            event_key="response:turn",
            evidence_source=None,
        )
        == 1
    )
    assert rt.service.update_entry.await_args.kwargs["expected_revision"] == 2
    rt.service.update_entry.assert_awaited_once()


async def test_raw_correction_preserves_late_restriction_above_generated_rule_ceiling(
    verdict_runtime, monkeypatch
):
    from src.core.config import settings
    from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH

    rt = verdict_runtime
    rt.service.create_entry = AsyncMock()
    monkeypatch.setattr(settings, "journal_max_entry_chars", 800)
    tail = "Never retain this restriction as a permanent personality trait."
    comment = "Observation: " + "x" * (1200 - len("Observation: ") - len(tail)) + tail
    await feedback_hooks.JournalResponseFeedbackHooks().record_correction(rt.db, rt.owner, comment)
    kwargs = rt.service.create_entry.await_args.kwargs
    assert kwargs["content"] == comment and kwargs["content"].endswith(tail)
    assert kwargs["max_entry_chars"] == JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH
    assert kwargs["source"] == "user_correction" and kwargs["level"] == "L0"


async def test_raw_correction_over_absolute_ceiling_is_rejected_without_truncation(verdict_runtime):
    from src.core.exceptions import ValidationError
    from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH

    rt = verdict_runtime
    rt.service.create_entry = AsyncMock()
    with pytest.raises(ValidationError):
        await feedback_hooks.JournalResponseFeedbackHooks().record_correction(
            rt.db, rt.owner, "x" * (JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH + 1)
        )
    rt.service.create_entry.assert_not_awaited()
