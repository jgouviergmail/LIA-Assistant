"""Feedback authority is a closed source verdict and exactly one owned identity."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_feedback import feedback_after
from src.domains.agents.application.interest_feedback_schemas import (
    InterestFeedbackPatch,
    InterestFeedbackSelection,
    InterestFeedbackValues,
)
from src.domains.agents.application.interest_spec import INTEREST_FEEDBACK_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {"feedback": "thumbs_up"},
        {"interest_id": str(uuid4()), "notification_id": str(uuid4()), "feedback": "thumbs_up"},
        {"interest_id": str(uuid4()), "feedback": True},
        {"interest_id": str(uuid4()), "feedback": "up"},
        {"interest_id": str(uuid4()), "feedback": "thumbs_up", "run_id": "private"},
        {"interest_id": str(uuid4()), "feedback": "thumbs_up", "actor_id": str(uuid4())},
        {"interest_id": str(uuid4()), "feedback": "thumbs_up", "positive_signals": 999},
    ],
)
def test_feedback_request_refuses_ambiguous_or_injected_authority(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        InterestFeedbackSelection.model_validate(payload)


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_feedback_preview_and_editor_expose_only_source_verdict_authority(language: str) -> None:
    before = InterestFeedbackPatch(
        interest_feedback=InterestFeedbackValues.model_validate(
            {
                "expected": {"id": uuid4(), "status": "active", "subject": None},
                "configuration": {
                    "topic": "Source topic",
                    "category": "science",
                    "positive_signals": 3,
                    "negative_signals": 0,
                },
                "feedback": "thumbs_down",
                "notification": None,
                "card_scope": "all_interest_cards",
            }
        )
    )
    after = InterestFeedbackPatch(interest_feedback=feedback_after(before.interest_feedback))
    draft = build_action_content(
        uuid4(),
        INTEREST_FEEDBACK_OPERATION,
        after,
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_interest_feedback_note"] in preview
    assert (
        "Source topic" in preview and "thumbs_down" in preview and "all_interest_cards" in preview
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another verdict")
    assert json.loads(prompt[1]["content"])["intent"] == {
        "interest_id": str(before.interest_feedback.expected.id),
        "feedback": "thumbs_down",
    }
    assert "positive_signals" not in json.dumps(prompt) and "source_digest" not in json.dumps(
        prompt
    )
    assert changed_resources(draft) == ["interests"]
