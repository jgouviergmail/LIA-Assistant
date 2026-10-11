"""The editor never receives private psyche/personality facts or authority fields."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.psyche_summary_schemas import (
    PsycheSummaryPatch,
    PsycheSummaryRequest,
    PsycheSummaryScope,
)
from src.domains.agents.application.psyche_summary_spec import PSYCHE_SUMMARY_OPERATION

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("field", ["actor_id", "digest", "settings", "language", "state_present"])
def test_request_refuses_server_owned_fields(field):
    with pytest.raises(ValidationError):
        PsycheSummaryRequest.model_validate({"scope": "current_account", field: "injected"})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_confirmation_discloses_generation_and_editor_sees_only_public_request(language):
    scope = PsycheSummaryScope(
        digest="a" * 64,
        input_digest="b" * 64,
        state_present=False,
        settings={"psyche_enabled": False},
        language=language,
    )
    public = scope.public_scope()
    draft = build_action_content(
        uuid4(),
        PSYCHE_SUMMARY_OPERATION,
        PsycheSummaryPatch(psyche_summary=scope),
        {"psyche_summary": public},
        {"psyche_summary": {**public, "requested": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_psyche_summary_note"] in preview
    assert scope.digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh proposal")
    assert json.loads(prompt[1]["content"])["intent"] == {"scope": "current_account"}
    assert "digest" not in str(prompt) and "psyche_enabled" not in str(prompt)
