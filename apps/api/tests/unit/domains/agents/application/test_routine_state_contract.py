"""Both orchestration modes offer exact confirmation and a bounded private projection."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

from src.core.i18n_drafts import DRAFT_PREVIEW_LABELS
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.routine_catalogue import ROUTINE_STATE_MANIFEST
from src.domains.agents.application.routine_schemas import (
    RoutineSnapshot,
    RoutineStatePatch,
    RoutineStateValues,
)
from src.domains.agents.application.routine_spec import ROUTINE_STATE_OPERATION
from src.domains.agents.automation.catalogue_manifests import (
    toggle_scheduled_action_catalogue_manifest,
)
from src.domains.agents.tools.application_routine_tools import set_lia_routine_state_tool
from src.domains.feature_switches.registry import CAPABILITY_SPECS, PlatformCapability

pytestmark = pytest.mark.unit


def test_routine_state_publishes_strict_input_and_gates_legacy_discovery() -> None:
    schema = set_lia_routine_state_tool.tool_call_schema.model_json_schema()
    validator = Draft202012Validator(schema)
    request = {"change": {"routine_id": str(uuid4()), "enabled": False}}
    assert validator.is_valid(request)
    assert not validator.is_valid({"change": {**request["change"], "owner_id": "foreign"}})
    assert not validator.is_valid({"change": {**request["change"], "enabled": "false"}})
    assert "runtime" not in set_lia_routine_state_tool.tool_call_schema.model_fields
    assert ROUTINE_STATE_MANIFEST.mutation_policy == "draft"
    assert toggle_scheduled_action_catalogue_manifest.mutation_policy == "draft"
    assert (
        "toggle_scheduled_action_tool"
        in CAPABILITY_SPECS[PlatformCapability.APPLICATION_TOOLS].tools
    )


@pytest.mark.parametrize("language", ["fr", "en", "es", "de", "it", "zh-CN"])
def test_routine_preview_and_editor_hide_the_configuration_digest(language: str) -> None:
    expected = RoutineSnapshot(
        id=uuid4(), title="Routine", enabled=True, configuration_digest="a" * 64
    )
    previous = RoutineStatePatch(routine_state=RoutineStateValues(expected=expected, enabled=True))
    desired = RoutineStatePatch(routine_state=RoutineStateValues(expected=expected, enabled=False))
    draft = build_action_content(
        uuid4(),
        ROUTINE_STATE_OPERATION,
        desired,
        previous.model_dump(mode="json"),
        desired.model_dump(mode="json"),
    )
    content = draft.model_dump(mode="json")
    lines = render_application_preview(
        content,
        DRAFT_PREVIEW_LABELS[language],
        lambda value: value or datetime.now(UTC).isoformat(),
    )
    assert len(lines) == 4
    assert str(expected.id) in str(lines)
    assert "a" * 64 not in str(lines)
    prompt = build_application_edit_prompt(content, "Enable it")
    assert "a" * 64 not in str(prompt)
    assert "configuration_digest" not in str(prompt)
