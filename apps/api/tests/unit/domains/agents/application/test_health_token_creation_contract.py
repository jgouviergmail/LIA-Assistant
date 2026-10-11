"""Creation shares source label bounds and never accepts caller secrets or identity."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.health_token_creation_schemas import (
    HealthTokenCreatePatch,
    HealthTokenCreateRequest,
)
from src.domains.agents.application.health_token_creation_spec import HEALTH_TOKEN_CREATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.health_metrics.schemas import HealthMetricTokenCreateRequest

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [{"label": "x" * 65}, {"token": "private"}, {"user_id": str(uuid4())}, {"id": str(uuid4())}],
)
def test_secret_and_authority_are_not_accepted(payload):
    with pytest.raises(ValidationError):
        HealthTokenCreateRequest.model_validate(payload)


def test_label_bounds_remain_owned_by_source_schema():
    assert (
        HealthTokenCreateRequest.model_json_schema()["properties"]["label"]
        == HealthMetricTokenCreateRequest.model_json_schema()["properties"]["label"]
    )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_preview_discloses_browser_only_delivery_in_every_language(language):
    patch = HealthTokenCreatePatch(
        health_token_to_create=HealthTokenCreateRequest(label="My watch")
    )
    draft = build_action_content(
        uuid4(),
        HEALTH_TOKEN_CREATE_OPERATION,
        patch,
        {"health_token_to_create": None},
        patch.model_dump(mode="json"),
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_health_token_creation_note"] in preview and "My watch" in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Another label")
    assert json.loads(prompt[1]["content"])["intent"] == {"label": "My watch"}
    assert "user_id" not in str(prompt) and "token_hash" not in str(prompt)
