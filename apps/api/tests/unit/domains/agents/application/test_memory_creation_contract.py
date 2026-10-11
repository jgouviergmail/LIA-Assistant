"""Memory creation inherits source fields and constraints behind a strict tool boundary."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_create_schemas import (
    MemoryCreateConfiguration,
    MemoryCreatePatch,
    MemoryCreationValues,
)
from src.domains.agents.application.memory_spec import MEMORY_CREATE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.memories.schemas import MemoryCreate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("extra", ["user_id", "id", "embedding", "context_biometric", "pinned"])
def test_creation_refuses_actor_identity_and_private_fields(extra: str) -> None:
    with pytest.raises(ValidationError):
        MemoryCreateConfiguration.model_validate(
            {"content": "Owned fact", "category": "personal", extra: "injected"}
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("importance", True),
        ("importance", "0.7"),
        ("emotional_weight", True),
        ("emotional_weight", "1"),
    ],
)
def test_creation_refuses_scalar_coercion(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        MemoryCreateConfiguration.model_validate(
            {"content": "Owned fact", "category": "personal", field: value}
        )


def test_every_source_field_and_its_constraint_reaches_the_native_schema() -> None:
    assert set(MemoryCreateConfiguration.model_fields) == set(MemoryCreate.model_fields)
    source = MemoryCreate.model_json_schema()["properties"]
    native = MemoryCreateConfiguration.model_json_schema()["properties"]
    assert native == source
    zero = MemoryCreateConfiguration(content="Owned fact", category="personal", importance=0.0)
    assert zero.importance == 0.0


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_creation_preview_shows_full_configuration_but_editor_has_no_minted_identity(
    language: str,
) -> None:
    identity = uuid4()
    configuration = MemoryCreateConfiguration(
        content="Exact new fact",
        category="procedural",
        importance=0.0,
        trigger_topic="topic",
        usage_nuance="Specific nuance",
    )
    # Production preparation expands source defaults before freezing the full creation.
    configuration = MemoryCreateConfiguration.model_validate(configuration.model_dump())
    patch = MemoryCreatePatch(
        memory_to_create=MemoryCreationValues(id=identity, configuration=configuration, pinned=True)
    )
    draft = build_action_content(
        uuid4(),
        MEMORY_CREATE_OPERATION,
        patch,
        {"memory_to_create": None},
        patch.model_dump(mode="json"),
        command_id=identity,
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    assert len(lines) == 3
    for value in (
        configuration.content,
        configuration.trigger_topic,
        configuration.usage_nuance,
        str(identity),
    ):
        assert value in str(lines)
    prompt = build_application_edit_prompt(draft.model_dump(mode="json"), "Revise my fact")
    assert str(identity) not in str(prompt) and str(draft.actor_id) not in str(prompt)
    assert configuration.content in str(prompt)
