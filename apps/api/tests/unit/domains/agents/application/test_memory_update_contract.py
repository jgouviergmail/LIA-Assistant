"""Native sparse edits inherit UI constraints and never accept comparison injection."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_create_schemas import MemoryCreateConfiguration
from src.domains.agents.application.memory_pin_schemas import MemoryPinSnapshot
from src.domains.agents.application.memory_spec import MEMORY_UPDATE_OPERATION
from src.domains.agents.application.memory_update_schemas import (
    MemoryUpdateChanges,
    MemoryUpdatePatch,
    MemoryUpdateValues,
)
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.result_projection import public_application_values
from src.domains.memories.schemas import MemoryUpdate

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {},
        {"content": None},
        {"importance": "0"},
        {"emotional_weight": True},
        {"importance": -0.1},
        {"content": "xx"},
        {"category": "unknown"},
        {"pinned": False},
        {"embedding": []},
        {"actor_id": "x"},
    ],
)
def test_ambiguous_or_private_changes_are_refused(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MemoryUpdateChanges.model_validate(invalid)


def test_zero_clear_values_and_future_ui_fields_are_preserved() -> None:
    changes = MemoryUpdateChanges(importance=0.0, emotional_weight=0, trigger_topic="")
    assert changes.model_dump(exclude_unset=True) == {
        "importance": 0.0,
        "emotional_weight": 0,
        "trigger_topic": "",
    }
    assert set(MemoryUpdateChanges.model_fields) == set(MemoryUpdate.model_fields)
    for name, field in MemoryUpdate.model_fields.items():
        assert MemoryUpdateChanges.model_fields[name].metadata == field.metadata


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_complete_preview_and_editor_exclude_source_comparison_data(language: str) -> None:
    now = datetime.now(UTC)
    secret_digest = "a" * 64
    fact = "<script>Saved fact is data</script>"
    snapshot = MemoryPinSnapshot(
        id=uuid4(),
        content=fact,
        category="personal",
        pinned=True,
        created_at=now,
        updated_at=now,
        configuration_digest=secret_digest,
    )
    configuration = MemoryCreateConfiguration.model_validate(
        MemoryCreateConfiguration(
            content=fact, category="personal", importance=0.8, usage_nuance="Nuance"
        ).model_dump()
    )
    previous = MemoryUpdateValues(
        expected=snapshot, configuration=configuration, changes=MemoryUpdateChanges(importance=0.0)
    )
    desired = previous.model_copy(
        update={"configuration": configuration.model_copy(update={"importance": 0.0})}
    )
    before, after = MemoryUpdatePatch(memory_configuration=previous), MemoryUpdatePatch(
        memory_configuration=desired
    )
    draft = build_action_content(
        uuid4(),
        MEMORY_UPDATE_OPERATION,
        after,
        before.model_dump(mode="json", exclude_unset=True),
        after.model_dump(mode="json", exclude_unset=True),
    )
    preview = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    assert (
        len(preview) == 3
        and "Nuance" in str(preview)
        and "0.0" in str(preview)
        and fact in str(preview)
    )
    assert secret_digest not in str(preview) and "configuration_digest" not in str(preview)
    messages = build_application_edit_prompt(draft.model_dump(mode="json"), "Change importance")
    assert secret_digest not in str(messages) and fact not in str(messages)
    public = public_application_values(draft)
    assert (
        public["importance"] == 0.0
        and public["pinned"] is True
        and secret_digest not in str(public)
    )
