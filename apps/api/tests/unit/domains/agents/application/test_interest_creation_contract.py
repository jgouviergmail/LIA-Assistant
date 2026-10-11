"""Source creation fields reach all confirmation surfaces without exposing minted authority."""

import ast
import inspect
import json
import textwrap
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.interest_create_schemas import (
    InterestCreateConfiguration,
    InterestCreatePatch,
    InterestCreationValues,
)
from src.domains.agents.application.interest_spec import INTEREST_CREATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.interests.management_commands import create_managed_interest
from src.domains.interests.schemas import InterestCreate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra", ["user_id", "id", "embedding", "status", "subject", "positive_signals"]
)
def test_creation_refuses_private_identity_and_non_ui_configuration(extra: str) -> None:
    with pytest.raises(ValidationError):
        InterestCreateConfiguration.model_validate({"topic": "Owned topic", extra: "injected"})


@pytest.mark.parametrize(
    "invalid",
    [
        {"topic": True},
        {"topic": 3},
        {"topic": b"topic"},
        {"topic": "x"},
        {"topic": "x" * 201},
        {"topic": "topic", "category": "invalid"},
    ],
)
def test_source_limits_and_strict_values_are_enforced(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        InterestCreateConfiguration.model_validate(invalid)


def test_new_source_fields_require_complete_shared_mapping() -> None:
    assert set(InterestCreateConfiguration.model_fields) == set(InterestCreate.model_fields)
    tree = ast.parse(textwrap.dedent(inspect.getsource(create_managed_interest)))
    mapped = {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "configuration"
    }
    assert set(InterestCreate.model_fields) <= mapped
    assert (
        InterestCreateConfiguration.model_json_schema()["properties"]
        == InterestCreate.model_json_schema()["properties"]
    )


@pytest.mark.parametrize("language", ["en", "fr", "de", "es", "it", "zh-CN"])
def test_localized_creation_is_complete_and_editor_cannot_mint_authority(language: str) -> None:
    identity = uuid4()
    configuration = InterestCreateConfiguration(topic="<untrusted topic>", category="science")
    configuration = InterestCreateConfiguration.model_validate(configuration.model_dump())
    patch = InterestCreatePatch(
        interest_to_create=InterestCreationValues(id=identity, configuration=configuration)
    )
    draft = build_action_content(
        uuid4(),
        INTEREST_CREATE_OPERATION,
        patch,
        {"interest_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )
    labels = get_draft_preview_labels(language)
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert labels["application_interest_creation_note"] in str(preview)
    assert "<untrusted topic>" in str(preview) and "science" in str(preview)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Change the topic")
    user = json.loads(prompt[1]["content"])
    assert user["intent"] == configuration.model_dump(mode="json")
    assert (
        str(identity) not in json.dumps(prompt) and "interest_to_create" not in prompt[0]["content"]
    )
