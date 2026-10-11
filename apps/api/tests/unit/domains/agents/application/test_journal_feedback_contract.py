"""Approval shows costs/settings while editor and model cannot inject private scope."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationScope,
)
from src.domains.agents.application.journal_feedback_schemas import (
    JournalFeedbackPatch,
    JournalFeedbackRequest,
    JournalFeedbackValues,
)
from src.domains.agents.application.journal_feedback_spec import JOURNAL_FEEDBACK_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("field", ["actor_id", "source_digest", "configuration", "corpus"])
def test_request_cannot_replace_server_authority(field: str) -> None:
    with pytest.raises(ValidationError):
        JournalFeedbackRequest.model_validate({"comment": "Correction", field: "injected"})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_paid_confirmation_discloses_source_scope_and_editor_hides_comparison(
    language: str,
) -> None:
    scope = JournalConsolidationScope(
        corpus=JournalRemovalSnapshot(
            entry_id=None, entries=203, evidence_events=7, total_chars=800, digest="a" * 64
        ),
        source_digest="b" * 64,
        configuration={"journals_enabled": True, "journal_consolidation_with_history": False},
    )
    from src.domains.agents.application.journal_feedback import feedback_public_scope

    values = JournalFeedbackValues(
        request=JournalFeedbackRequest(
            comment="Complete correction", highlighted_section="Prior portrait"
        ),
        expected=scope,
    )
    public = feedback_public_scope(values)
    draft = build_action_content(
        uuid4(),
        JOURNAL_FEEDBACK_OPERATION,
        JournalFeedbackPatch(journal_feedback=values),
        {"journal_feedback": public},
        {"journal_feedback": {**public, "requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_journal_feedback_note"] in preview and "203" in preview
    assert scope.corpus.digest not in preview and scope.source_digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this proposal")
    assert json.loads(prompt[1]["content"])["intent"] == values.request.model_dump(mode="json")
    assert (
        "digest" not in str(prompt)
        and "configuration" not in str(prompt)
        and "203" not in str(prompt)
    )


def test_feedback_inherits_source_fields_and_reviews_future_additions() -> None:
    from src.domains.journals.schemas import JournalPortraitFeedbackRequest

    assert (
        set(JournalFeedbackRequest.model_fields)
        == set(JournalPortraitFeedbackRequest.model_fields)
        == {"comment", "highlighted_section"}
    )


@pytest.mark.parametrize("committed", [False, True])
async def test_partial_outcome_retains_verified_maintenance_acknowledgement(monkeypatch, committed):
    from src.domains.agents.application import journal_feedback
    from src.domains.agents.application.command_service import CommandRejected
    from src.domains.users.preference_cas import PreferenceWriteReceipt

    scope = JournalConsolidationScope(
        corpus=JournalRemovalSnapshot(
            entry_id=None, entries=1, evidence_events=0, total_chars=10, digest="a" * 64
        ),
        source_digest="b" * 64,
        configuration={},
    )
    values = JournalFeedbackValues(
        request=JournalFeedbackRequest(comment="Correction"), expected=scope
    )
    public = journal_feedback.feedback_public_scope(values)
    draft = build_action_content(
        uuid4(),
        JOURNAL_FEEDBACK_OPERATION,
        JournalFeedbackPatch(journal_feedback=values),
        {"journal_feedback": public},
        {"journal_feedback": {**public, "requested": True}},
    )

    async def maintenance(db, actor_id, derived, receipt):
        assert derived.expires_at == draft.expires_at
        if committed:
            receipt.committed = True
            receipt.values = {"journal_consolidation": {"status": "success", "actions_applied": 2}}
        raise CommandRejected("COMPLETION_UNKNOWN")

    monkeypatch.setattr(journal_feedback, "execute_journal_consolidation", maintenance)
    receipt = PreferenceWriteReceipt(committed=True)
    with pytest.raises(CommandRejected):
        await journal_feedback._run_feedback_maintenance(
            None, draft.actor_id, draft, scope, receipt
        )
    outcome = receipt.values["journal_feedback"]
    assert outcome["feedback_saved"] is True
    assert outcome["maintenance_status"] == ("success" if committed else "completion_unknown")
    if committed:
        assert outcome["actions_applied"] == 2
