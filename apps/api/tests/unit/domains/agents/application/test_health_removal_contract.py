"""Approval exposes source counts while private data comparison stays outside editing."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.health_removal_schemas import (
    HealthRemovalPatch,
    HealthRemovalRequest,
)
from src.domains.agents.application.health_removal_spec import HEALTH_REMOVAL_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.health_metrics.removal_snapshot import HealthRemovalSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"kind": "unknown"},
        {"kind": None, "user_id": "other"},
        {"kind": None, "digest": "injected"},
    ],
)
def test_deletion_requires_explicit_scope_without_client_authority(payload):
    with pytest.raises(ValidationError):
        HealthRemovalRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_every_language_discloses_complete_counts_and_editor_hides_private_comparison(language):
    scope = HealthRemovalSnapshot(
        kind=None, count=203, counts_by_kind={"steps": 203}, digest="a" * 64
    )
    draft = build_action_content(
        uuid4(),
        HEALTH_REMOVAL_OPERATION,
        HealthRemovalPatch(health_samples_to_delete=scope),
        {"health_samples_to_delete": scope.public_scope()},
        {"health_samples_to_delete": None},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert "203" in preview and labels["application_health_removal_note"] in preview
    assert scope.digest not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Delete steps only")
    assert json.loads(prompt[1]["content"])["intent"] == {"kind": None}
    assert "digest" not in str(prompt) and "203" not in str(prompt)
