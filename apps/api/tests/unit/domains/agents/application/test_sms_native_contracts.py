"""SMS actions must be reachable and their approval previews must be canonical."""

import pytest

from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.sms_action_spec import SMS_NATIVE_OPERATIONS
from src.domains.agents.application.state_resources import DEDICATED_RESOURCES

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("spec", SMS_NATIVE_OPERATIONS, ids=lambda spec: spec.operation_id)
def test_sms_operation_is_registered_and_invalidates_sms(spec):
    assert APPLICATION_OPERATIONS.get(spec.operation_id) == spec
    assert DEDICATED_RESOURCES[spec.operation_id] == "sms"


def test_sms_token_approval_hands_off_without_creating_a_secret():
    from uuid import uuid4

    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.secure_handoff import secure_handoff_outcome
    from src.domains.agents.application.sms_action_schemas import (
        SmsTokenCreatePatch,
        SmsTokenCreateRequest,
    )
    from src.domains.agents.application.sms_action_spec import SMS_TOKEN_CREATE_OPERATION

    patch = SmsTokenCreatePatch(ingestion_token_to_create=SmsTokenCreateRequest(label="iPhone"))
    draft = build_action_content(
        uuid4(),
        SMS_TOKEN_CREATE_OPERATION,
        patch,
        {"ingestion_token_to_create": None},
        patch.model_dump(mode="json"),
    )
    result = secure_handoff_outcome(draft)
    assert result.phase == "waiting" and not result.committed
    assert result.interaction.kind == "device" and not result.values


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_sms_preview_and_editor_disclose_no_private_comparison_material(language):
    import json
    from uuid import uuid4

    from src.core.i18n_drafts import get_draft_preview_labels
    from src.domains.agents.application.action_preparation import build_action_content
    from src.domains.agents.application.draft_rendering import render_application_preview
    from src.domains.agents.application.prompts import build_application_edit_prompt
    from src.domains.agents.application.sms_action_schemas import (
        SmsTokenCreatePatch,
        SmsTokenCreateRequest,
    )
    from src.domains.agents.application.sms_action_spec import SMS_TOKEN_CREATE_OPERATION

    patch = SmsTokenCreatePatch(
        ingestion_token_to_create=SmsTokenCreateRequest(label="Owned phone")
    )
    draft = build_action_content(
        uuid4(),
        SMS_TOKEN_CREATE_OPERATION,
        patch,
        {"ingestion_token_to_create": None},
        patch.model_dump(mode="json"),
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_sms_note"] in preview and "Owned phone" in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Another label")
    assert json.loads(prompt[1]["content"])["intent"] == {"label": "Owned phone", "source_id": None}
    assert "actor_id" not in str(prompt) and "token_hash" not in str(prompt)
