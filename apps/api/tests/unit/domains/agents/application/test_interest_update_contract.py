"""Strict source edit fields reach schema, comparison, confirmation and editor surfaces."""

import ast
import inspect
import json
import textwrap
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_spec import INTEREST_UPDATE_OPERATION
from src.domains.agents.application.interest_update_schemas import (
    InterestEditSnapshot,
    InterestUpdateChanges,
    InterestUpdatePatch,
    InterestUpdateValues,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources
from src.domains.interests.management_commands import (
    preview_interest_update,
    update_managed_interest,
)
from src.domains.interests.management_schemas import InterestConfiguration
from src.domains.interests.schemas import InterestResponse, InterestUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"topic": None},
        {"topic": 3},
        {"topic": "x"},
        {"topic": "x" * 201},
        {"category": "invalid"},
        {"category": None},
        {"positive_signals": 0},
        {"negative_signals": -1},
        {"positive_signals": True},
        {"negative_signals": "0"},
        {"status": "active"},
        {"user_id": "injected"},
        {"embedding": []},
        {"subject": "injected"},
    ],
)
def test_strict_sparse_source_change_refuses_ambiguous_or_private_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        InterestUpdateChanges.model_validate(payload)
    assert not Draft202012Validator(InterestUpdateChanges.model_json_schema()).is_valid(payload)


def test_source_update_fields_are_complete_in_shared_preview_and_write_mapping() -> None:
    assert set(InterestUpdateChanges.model_fields) == set(InterestUpdate.model_fields)
    assert set(InterestConfiguration.model_fields) == set(InterestUpdate.model_fields)
    assert all(
        field.annotation == InterestResponse.model_fields[name].annotation
        for name, field in InterestConfiguration.model_fields.items()
    )
    for method in (preview_interest_update, update_managed_interest):
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        mapped = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert set(InterestUpdate.model_fields) <= mapped
    assert InterestUpdateChanges(negative_signals=0).model_dump(exclude_unset=True) == {
        "negative_signals": 0
    }


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_update_preview_is_complete_and_editor_excludes_comparison_authority(language: str) -> None:
    identity = uuid4()
    previous = InterestUpdateValues(
        expected=InterestEditSnapshot(id=identity, status="active", subject="Derived topic"),
        configuration=InterestConfiguration(
            topic="Old topic", category="science", positive_signals=3, negative_signals=1
        ),
        changes=InterestUpdateChanges(topic="<untrusted new topic>", negative_signals=0),
    )
    desired = previous.model_copy(
        update={
            "configuration": InterestConfiguration(
                topic="<untrusted new topic>",
                category="science",
                positive_signals=3,
                negative_signals=0,
            )
        }
    )
    before, after = InterestUpdatePatch(interest_configuration=previous), InterestUpdatePatch(
        interest_configuration=desired
    )
    draft = build_action_content(
        uuid4(),
        INTEREST_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
    )
    labels = get_draft_preview_labels(language)
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert labels["application_interest_update_note"] in str(preview)
    assert all(
        value in str(preview)
        for value in (
            "Old topic",
            "<untrusted new topic>",
            "Derived topic",
            "positive_signals",
            "negative_signals",
            str(identity),
        )
    )
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change category")
    user = json.loads(prompt[1]["content"])
    assert user["intent"] == {
        "interest_id": str(identity),
        "changes": {"topic": "<untrusted new topic>", "negative_signals": 0},
    }
    assert "interest_configuration" not in prompt[0]["content"]
    assert "Derived topic" not in json.dumps(prompt)
    assert changed_resources(draft) == ["interests"]
