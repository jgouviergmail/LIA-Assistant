"""Explicit source relation preferences cannot expand defaults or grant authority."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.relation_settings_schemas import RelationSettingsPatch
from src.domains.agents.application.relation_settings_spec import RELATION_SETTINGS_UPDATE_OPERATION

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"relation_debrief_enabled": None},
        {"relation_debrief_enabled": "false"},
        {"user_id": "other"},
        {"relation_overview_scope": {"sections": ["emails"] * 8}},
        {"relation_overview_scope": {"sections": ["emails", "emails"]}},
        {"relation_overview_scope": {"max_items": True}},
        {"relation_overview_scope": {"admin": True}},
    ],
)
def test_relation_settings_reject_authority_null_coercions_and_unbounded_selections(payload):
    with pytest.raises(ValidationError):
        RelationSettingsPatch.model_validate(payload)


def test_sparse_scope_change_preserves_empty_sources_and_source_defaults():
    patch = RelationSettingsPatch.model_validate({"relation_overview_scope": {"sections": []}})
    assert patch.model_fields_set == {"relation_overview_scope"}
    assert patch.relation_overview_scope.sections == []


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_relation_approval_and_editor_preserve_complete_exact_scope(language):
    intent = RelationSettingsPatch.model_validate(
        {"relation_debrief_enabled": False, "relation_overview_scope": {"sections": []}}
    )
    whole = {
        "relation_debrief_enabled": False,
        "relation_overview_scope": intent.relation_overview_scope.model_dump(mode="json"),
    }
    intent = RelationSettingsPatch.model_validate(whole)
    draft = build_action_content(
        uuid4(),
        RELATION_SETTINGS_UPDATE_OPERATION,
        intent,
        {"relation_debrief_enabled": True, "relation_overview_scope": None},
        whole,
    )
    labels = get_draft_preview_labels(language)
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_relation_settings_note"] in rendered
    assert labels["application_field_relation_overview_scope"] in rendered
    assert '"sections": []' in rendered
    messages = build_application_edit_prompt(
        draft.model_dump(mode="json"), "Enable the daily debrief"
    )
    assert json.loads(messages[1]["content"])["intent"] == whole
