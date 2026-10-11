"""Full manual configuration and bounded provider input are readable before approval."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_create_schemas import (
    JournalCreateConfiguration,
    JournalCreatePatch,
    JournalCreationValues,
)
from src.domains.agents.application.journal_creation_spec import JOURNAL_CREATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.journals.constants import JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH
from src.domains.journals.schemas import JournalEntryCreate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": str(uuid4())},
        {"source": "consolidation"},
        {"level": "L3"},
        {"search_hints": ["x"] * 6},
        {"search_hints": ["x" * 101]},
        {"content": "x" * (JOURNAL_ENTRY_CONTENT_ABSOLUTE_MAX_LENGTH + 1)},
    ],
)
def test_manual_creation_refuses_authority_invention_or_unbounded_provider_input(
    extra: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalCreateConfiguration.model_validate(
            {"theme": "learnings", "title": "Title", "content": "Content", **extra}
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_creation_confirmation_is_complete_and_editor_excludes_identity(language: str) -> None:
    assert set(JournalCreateConfiguration.model_fields) == set(JournalEntryCreate.model_fields)
    selected = JournalCreateConfiguration(
        theme="learnings", title="Unique title", content="Full content", search_hints=["hint"]
    )
    selected = JournalCreateConfiguration.model_validate(selected.model_dump())
    identity = uuid4()
    patch = JournalCreatePatch(
        journal_entry_to_create=JournalCreationValues(id=identity, configuration=selected)
    )
    draft = build_action_content(
        uuid4(),
        JOURNAL_CREATE_OPERATION,
        patch,
        {"journal_entry_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert (
        labels["application_journal_creation_note"] in preview
        and "Full content" in preview
        and "hint" in preview
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the title")
    assert json.loads(prompt[1]["content"])["intent"] == selected.model_dump(mode="json")
    assert str(identity) not in str(prompt)
