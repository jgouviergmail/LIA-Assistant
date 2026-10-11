"""Reset previews and editors expose source levels and public effects, never private fingerprints."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.psyche_reset import psyche_reset_preview
from src.domains.agents.application.psyche_reset_schemas import (
    PsycheResetIntent,
    PsycheResetPatch,
    PsycheResetValues,
)
from src.domains.agents.application.psyche_reset_spec import PSYCHE_RESET_OPERATION
from src.domains.psyche.reset_snapshot import PsycheResetSnapshot

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"level": "unknown"},
        {"level": "purge", "user_id": str(uuid4())},
        {"level": "soft", "baseline": 0.5},
        {"level": "full", "digest": "invented"},
    ],
)
def test_reset_input_never_accepts_invented_authority_or_effects(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        PsycheResetIntent.model_validate(payload)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_reset_preview_and_editor_exclude_private_scope(language: str) -> None:
    scope = PsycheResetSnapshot(
        states=1,
        history=203,
        digest="a" * 64,
        before={"drive_curiosity": 0.9},
        after={"drive_curiosity": 0.5},
    )
    values = PsycheResetValues(request=PsycheResetIntent(level="full"), expected=scope)
    before, after = psyche_reset_preview(values)
    draft = build_action_content(
        uuid4(), PSYCHE_RESET_OPERATION, PsycheResetPatch(psyche_reset=values), before, after
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_psyche_reset_note"] in preview and "203" in preview
    assert scope.digest not in preview and "digest" not in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Use soft reset instead")
    assert json.loads(prompt[1]["content"])["intent"] == {"level": "full"}
    assert scope.digest not in str(prompt)
