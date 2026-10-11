"""Source bounds, effect classification and model-facing sparse contracts stay aligned."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.core.i18n_journal_settings import JOURNAL_SETTINGS_COPY
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.journal_catalogue import JOURNAL_SETTINGS_OPERATION
from src.domains.agents.application.journal_settings_schemas import (
    JournalSettingField,
    JournalSettingsPatch,
)
from src.domains.journals.schemas import JournalSettingsUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"journals_enabled": None},
        {"journals_enabled": "false"},
        {"journal_context_max_results": True},
        {"journal_max_total_chars": 4999},
        {"user_id": "other"},
        {"consolidate": True},
    ],
)
def test_journal_settings_rejects_empty_null_coercion_and_invented_actions(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        JournalSettingsPatch.model_validate(payload)


def test_future_source_settings_require_deliberate_confirmation_and_sync_coverage() -> None:
    assert set(JournalSettingsPatch.model_fields) == set(JournalSettingsUpdate.model_fields)
    assert {field.value for field in JournalSettingField} == set(JournalSettingsUpdate.model_fields)
    schema = JournalSettingsPatch.model_json_schema()
    assert schema["minProperties"] == 1 and schema["additionalProperties"] is False
    assert all(
        prop.get("type") != "null" and "anyOf" not in prop for prop in schema["properties"].values()
    )
    assert set(JOURNAL_SETTINGS_COPY) == {"fr", "en", "de", "es", "it", "zh-CN"}
    assert all(len(copy) == 8 and all(copy) for copy in JOURNAL_SETTINGS_COPY.values())


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_journal_approval_renders_every_source_field_and_effect_note(language: str) -> None:
    labels = get_draft_preview_labels(language)
    values = {
        "journals_enabled": False,
        "journal_consolidation_enabled": False,
        "journal_consolidation_with_history": True,
        "journal_max_total_chars": 10000,
        "journal_context_max_chars": 2000,
        "journal_max_entry_chars": 300,
        "journal_context_max_results": 5,
    }
    patch = JournalSettingsPatch.model_validate(values)
    draft = build_action_content(uuid4(), JOURNAL_SETTINGS_OPERATION, patch, values, values)
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_journal_settings_note"] in rendered
    for field in JournalSettingField:
        assert labels[f"application_field_{field.value}"] in rendered
