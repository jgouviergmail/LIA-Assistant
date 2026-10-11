"""Token selection and editor projection never expose stored token secrets."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.health_token_schemas import (
    HealthTokenRevokePatch,
    HealthTokenRevokeRequest,
)
from src.domains.agents.application.health_token_spec import HEALTH_TOKEN_REVOKE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.health_metrics.schemas import HealthMetricTokenRow
from src.domains.health_metrics.token_commands import HealthTokenSelection

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"token_id": "bad"},
        {"token_id": str(uuid4()), "user_id": str(uuid4())},
        {"token_id": str(uuid4()), "digest": "invented"},
    ],
)
def test_explicit_token_identity_cannot_supply_authority(payload):
    with pytest.raises(ValidationError):
        HealthTokenRevokeRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_public_preview_and_editor_exclude_private_comparison(language):
    token = HealthMetricTokenRow(
        id=uuid4(),
        label="<script>private label</script>",
        token_prefix="hm_public",
        created_at=datetime.now(UTC),
        last_used_at=None,
        revoked_at=None,
    )
    selected = HealthTokenSelection(token=token, digest="a" * 64)
    scope = selected.public_scope()
    draft = build_action_content(
        uuid4(),
        HEALTH_TOKEN_REVOKE_OPERATION,
        HealthTokenRevokePatch(health_token_to_revoke=selected),
        {"health_token_to_revoke": scope},
        {"health_token_to_revoke": {**scope, "revoked": True}},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_health_token_note"] in preview and "hm_public" in preview
    assert selected.digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Revoke another token")
    assert json.loads(prompt[1]["content"])["intent"] == {"token_id": str(token.id)}
    assert "digest" not in str(prompt) and "private label" not in str(prompt)
