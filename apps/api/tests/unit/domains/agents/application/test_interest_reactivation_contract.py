"""Reactivation selects one owned identity without exposing reset-policy authority."""

import ast
import inspect
import json
import textwrap
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_reactivation_schemas import (
    InterestReactivateRequest,
    InterestReactivationPatch,
    InterestReactivationResult,
    InterestReactivationValues,
    reactivation_result,
)
from src.domains.agents.application.interest_spec import INTEREST_REACTIVATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.interests.repository import InterestRepository

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "injection",
    [
        {"status": "active"},
        {"positive_signals": 999},
        {"user_id": str(uuid4())},
        {"last_mentioned_at": "2099-01-01"},
        {"embedding": []},
    ],
)
def test_reactivation_identity_cannot_override_source_policy(injection: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterestReactivateRequest.model_validate({"interest_id": str(uuid4()), **injection})


def test_new_source_reset_fields_require_complete_native_confirmation_coverage() -> None:
    tree = ast.parse(textwrap.dedent(inspect.getsource(InterestRepository.reactivate)))
    fields = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.ctx, ast.Store)
        and isinstance(node.value, ast.Name)
        and node.value.id == "interest"
    }
    assert fields == set(InterestReactivationResult.model_fields)


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_complete_reset_preview_and_identity_only_editor(language: str) -> None:
    now = datetime.now(UTC)
    values = InterestReactivationValues.model_validate(
        {
            "expected": {
                "id": uuid4(),
                "configuration": {
                    "topic": "Source topic",
                    "category": "science",
                    "positive_signals": 9,
                    "negative_signals": 7,
                },
                "status": "dormant",
                "subject": "Source subject",
                "last_mentioned_at": now,
                "last_notified_at": now,
                "dormant_since": now,
            },
            "result": reactivation_result().model_dump(),
        }
    )
    draft = build_action_content(
        uuid4(),
        INTEREST_REACTIVATE_OPERATION,
        InterestReactivationPatch(interest_to_reactivate=values),
        {"interest_to_reactivate": values.expected.model_dump(mode="json")},
        {"interest_to_reactivate": values.result.model_dump(mode="json")},
    )
    labels = get_draft_preview_labels(language)
    preview = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    assert labels["application_interest_reactivation_note"] in preview
    assert "Source topic" in preview and "Source subject" in preview and "dormant_since" in preview
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Reactivate this topic")
    assert json.loads(prompt[1]["content"])["intent"] == {"interest_id": str(values.expected.id)}
    assert "negative_signals" not in json.dumps(prompt)
