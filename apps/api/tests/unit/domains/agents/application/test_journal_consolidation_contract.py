"""Approval shows costs/settings while editor and model cannot inject private scope."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_consolidation_schemas import (
    JournalConsolidationPatch,
    JournalConsolidationRequest,
    JournalConsolidationScope,
)
from src.domains.agents.application.journal_consolidation_spec import JOURNAL_CONSOLIDATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("field", ["actor_id", "source_digest", "configuration", "corpus"])
def test_request_cannot_replace_server_authority(field: str) -> None:
    with pytest.raises(ValidationError):
        JournalConsolidationRequest.model_validate({"scope": "current_account", field: "injected"})


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
    public = scope.public_scope()
    draft = build_action_content(
        uuid4(),
        JOURNAL_CONSOLIDATE_OPERATION,
        JournalConsolidationPatch(journal_consolidation=scope),
        {"journal_consolidation": public},
        {"journal_consolidation": {**public, "requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_journal_consolidation_note"] in preview and "203" in preview
    assert scope.corpus.digest not in preview and scope.source_digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this proposal")
    assert json.loads(prompt[1]["content"])["intent"] == {"scope": "current_account"}
    assert (
        "digest" not in str(prompt)
        and "configuration" not in str(prompt)
        and "203" not in str(prompt)
    )
