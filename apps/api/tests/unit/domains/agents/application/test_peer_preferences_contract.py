"""Only explicit sparse strict consents can be offered for approval."""

import json
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.peer_preference_schemas import PeerPreferencePatch
from src.domains.agents.application.peer_preference_spec import PEER_PREFERENCE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"email_visible": None},
        {"email_visible": "true"},
        {"discovery_enabled": 1},
        {"peer_email_visible": True},
        {"email_visible": True, "user_id": "other"},
    ],
)
def test_peer_preferences_refuse_coercion_or_other_account(payload):
    with pytest.raises(ValidationError):
        PeerPreferencePatch.model_validate(payload)
    assert not Draft202012Validator(PeerPreferencePatch.model_json_schema()).is_valid(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_peer_consent_preview_and_editor_have_only_selected_fields(language):
    patch = PeerPreferencePatch(email_visible=True)
    draft = build_action_content(
        uuid4(), PEER_PREFERENCE_OPERATION, patch, {"email_visible": False}, {"email_visible": True}
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda v: v or "")
    )
    assert labels["application_peer_preferences_note"] in preview
    assert labels["application_field_email_visible"] in preview
    assert labels["application_field_discovery_enabled"] not in preview
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Disable instead")
    assert json.loads(editor[1]["content"])["intent"] == {"email_visible": True}
