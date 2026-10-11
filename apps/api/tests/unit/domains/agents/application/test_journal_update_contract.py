"""Model-facing sparse edits match validation and hide private comparison lineage."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_update_schemas import (
    JournalUpdateChanges,
    JournalUpdatePatch,
    JournalUpdateValues,
)
from src.domains.agents.application.journal_update_spec import JOURNAL_UPDATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.journals.removal_snapshot import JournalRemovalSnapshot
from src.domains.journals.schemas import JournalEntryResponse, JournalEntryUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"content": None},
        {"evidence_count": 2},
        {"user_id": str(uuid4())},
        {"search_hints": ["hint"] * 6},
    ],
)
def test_sparse_journal_edits_reject_empty_null_or_fabricated_authority(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalUpdateChanges.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_edit_approval_shows_effective_values_and_editor_only_public_request(language: str) -> None:
    assert set(JournalUpdateChanges.model_fields) == set(JournalEntryUpdate.model_fields)
    schema = JournalUpdateChanges.model_json_schema()
    assert schema["minProperties"] == 1 and all(
        "anyOf" not in item for item in schema["properties"].values()
    )
    when = datetime.now(UTC)
    entry = JournalEntryResponse(
        id=uuid4(),
        theme="learnings",
        title="Title",
        content="Original",
        mood="reflective",
        status="active",
        source="manual",
        personality_code=None,
        char_count=8,
        injection_count=4,
        confidence="medium",
        evidence_count=0,
        contradiction_count=0,
        level="L1",
        created_at=when,
        updated_at=when,
    )
    expected = JournalRemovalSnapshot(
        entry_id=entry.id, entries=1, evidence_events=0, total_chars=8, entry=entry, digest="d" * 64
    )
    previous = entry.model_dump(
        mode="json", exclude={"updated_at", "injection_count", "last_injected_at"}
    )
    after = {**previous, "content": "Effective", "char_count": 9, "revision": 2}
    changes = JournalUpdateChanges(content="Effective", confidence="high")
    patch = JournalUpdatePatch(
        journal_configuration=JournalUpdateValues(
            expected=expected, changes=changes, projected=after, invalidates_portrait=True
        )
    )
    draft = build_action_content(
        uuid4(),
        JOURNAL_UPDATE_OPERATION,
        patch,
        {"journal_entry": previous},
        {"journal_entry": after},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert (
        labels["application_journal_update_note"] in preview
        and "Effective" in preview
        and "medium" in preview
    )
    assert expected.digest not in preview and "digest" not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Edit the title")
    assert json.loads(prompt[1]["content"])["intent"] == {
        "entry_id": str(entry.id),
        "changes": changes.model_dump(mode="json", exclude_unset=True),
    }
    assert expected.digest not in str(prompt)
