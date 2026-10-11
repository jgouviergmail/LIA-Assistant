"""Deletion keeps its full source fact visible while exposing only an owned selector to editing."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_removal_schemas import (
    InterestDeletePatch,
    InterestDeleteRequest,
    InterestDeleteValues,
)
from src.domains.agents.application.interest_spec import INTEREST_DELETE_OPERATION
from src.domains.agents.application.interest_update_schemas import (
    InterestEditSnapshot,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.result_projection import public_application_values
from src.domains.agents.application.state_changes import changed_resources
from src.domains.interests.management_schemas import InterestConfiguration

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("extra", ["user_id", "all", "status", "expected", "embedding"])
def test_deletion_selector_refuses_owner_scope_and_comparison_injection(extra: str) -> None:
    with pytest.raises(ValidationError):
        InterestDeleteRequest.model_validate({"interest_id": str(uuid4()), extra: "injected"})


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_deletion_preview_and_editor_retain_the_source_selection(language: str) -> None:
    identity = uuid4()
    patch = InterestDeletePatch(
        interest_to_delete=InterestDeleteValues(
            expected=InterestEditSnapshot(
                id=identity, status="blocked", subject="Derived grouping"
            ),
            configuration=InterestConfiguration(
                topic="<untrusted topic>",
                category="science",
                positive_signals=3,
                negative_signals=1,
            ),
        )
    )
    draft = build_action_content(
        uuid4(),
        INTEREST_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"interest_to_delete": None},
    )
    labels = get_draft_preview_labels(language)
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert labels["application_interest_removal_note"] in str(preview)
    assert all(
        value in str(preview)
        for value in (
            str(identity),
            "<untrusted topic>",
            "blocked",
            "Derived grouping",
            "positive_signals",
            "negative_signals",
        )
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another interest")
    assert json.loads(prompt[1]["content"])["intent"] == {"interest_id": str(identity)}
    assert "interest_to_delete" not in prompt[0]["content"]
    assert "Derived grouping" not in json.dumps(prompt)
    assert changed_resources(draft) == ["interests"]
    assert public_application_values(draft) == {"interest_id": str(identity), "deleted": True}
