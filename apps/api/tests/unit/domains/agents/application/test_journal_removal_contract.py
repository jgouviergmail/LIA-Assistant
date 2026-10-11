"""Removal previews expose exact public effects and never private fingerprints."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_removal_schemas import (
    JournalDeletePatch,
    JournalDeleteRequest,
)
from src.domains.agents.application.journal_removal_spec import JOURNAL_DELETE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [{}, {"entry_id": None, "user_id": str(uuid4())}, {"entry_id": None, "digest": "invented"}],
)
def test_removal_requires_explicit_scope_and_no_model_owned_comparison(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalDeleteRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_complete_removal_preview_and_editor_do_not_expose_private_fingerprints(
    language: str,
) -> None:
    snapshot = JournalRemovalSnapshot(
        entry_id=None, entries=203, evidence_events=4, total_chars=1015, digest="b" * 64
    )
    patch = JournalDeletePatch(journal_entries_to_delete=snapshot)
    draft = build_action_content(
        uuid4(),
        JOURNAL_DELETE_OPERATION,
        patch,
        {"journal_entries_to_delete": snapshot.public_scope()},
        {"journal_entries_to_delete": None},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert "203" in preview and labels["application_journal_removal_note"] in preview
    assert "digest" not in preview and snapshot.digest not in preview
    prompt = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Delete only the selected entry instead"
    )
    assert json.loads(prompt[1]["content"])["intent"] == {"entry_id": None}
    assert snapshot.digest not in str(prompt)
