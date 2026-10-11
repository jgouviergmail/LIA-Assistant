"""Complete-scope confirmations remain bounded and never publish the fact-selection digest."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_bulk_schemas import (
    InterestBulkDeletePatch,
    InterestBulkDeleteRequest,
    InterestBulkSnapshot,
)
from src.domains.agents.application.interest_spec import INTEREST_BULK_DELETE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"scope": "active"},
        {"scope": True},
        {"scope": "all_owned", "category": "science"},
        {"scope": "all_owned", "user_id": "injected"},
    ],
)
def test_global_erasure_requires_explicit_unfiltered_owned_scope(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        InterestBulkDeleteRequest.model_validate(payload)


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_global_preview_contains_complete_counts_without_saved_facts_or_private_digest(
    language: str,
) -> None:
    snapshot = InterestBulkSnapshot(
        selected_count=603,
        by_category={"science": 603},
        by_status={"active": 201, "blocked": 201, "dormant": 201},
        unknown_category_count=0,
        unknown_status_count=0,
        selection_digest="a" * 64,
    )
    patch = InterestBulkDeletePatch(interests_to_delete=snapshot)
    draft = build_action_content(
        uuid4(),
        INTEREST_BULK_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"interests_to_delete": None},
    )
    labels = get_draft_preview_labels(language)
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert labels["application_interest_bulk_note"] in str(preview)
    assert "603" in str(preview) and "blocked" in str(preview) and "dormant" in str(preview)
    assert snapshot.selection_digest not in str(preview)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Confirm this scope")
    assert json.loads(prompt[1]["content"])["intent"] == {"scope": "all_owned"}
    assert snapshot.selection_digest not in json.dumps(prompt)
    assert changed_resources(draft) == ["interests"]


@pytest.mark.parametrize(
    "invalid",
    [
        {"selected_count": True},
        {"selected_count": 2},
        {"by_category": {"private-topic": 1}},
        {"by_status": {"active": -1}},
        {"unknown_category_count": -1},
        {"selection_digest": "bad"},
    ],
)
def test_summary_refuses_unbounded_incomplete_or_malformed_counts(
    invalid: dict[str, object],
) -> None:
    values = {
        "selected_count": 1,
        "by_category": {"science": 1},
        "by_status": {"active": 1},
        "unknown_category_count": 0,
        "unknown_status_count": 0,
        "selection_digest": "a" * 64,
    }
    with pytest.raises(ValidationError):
        InterestBulkSnapshot.model_validate({**values, **invalid})
