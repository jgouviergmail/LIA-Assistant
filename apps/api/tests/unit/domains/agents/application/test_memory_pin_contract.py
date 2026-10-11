"""Native pin exposes only an owned id and a strict desired boolean."""

import ast
import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_pin import memory_pin_snapshot
from src.domains.agents.application.memory_pin_schemas import (
    MemoryPinPatch,
    MemoryPinRequest,
    MemoryPinSnapshot,
    MemoryPinValues,
)
from src.domains.agents.application.memory_spec import MEMORY_PIN_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.result_projection import public_application_values
from src.domains.agents.tools.application_memory_tools import set_lia_memory_pin_tool
from src.domains.memories.schemas import MemoryUpdate

pytestmark = pytest.mark.unit


def test_every_ui_setting_participates_in_the_confirmed_fact_digest() -> None:
    tree = ast.parse(inspect.getsource(memory_pin_snapshot))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "payload_digest"
    ]
    assert len(calls) == 1 and isinstance(calls[0].args[0], ast.Dict)
    keys = {node.value for node in calls[0].args[0].keys if isinstance(node, ast.Constant)}
    assert keys == set(MemoryUpdate.model_fields), "A new UI setting must enter the HITL digest"


@pytest.mark.parametrize("pinned", ["true", 1, 0, None, []])
def test_pin_refuses_coercion(pinned: object) -> None:
    with pytest.raises(ValidationError):
        MemoryPinRequest.model_validate({"memory_id": str(uuid4()), "pinned": pinned})


@pytest.mark.parametrize("injected", ["actor_id", "expected", "configuration_digest", "embedding"])
def test_pin_refuses_identity_and_snapshot_injection(injected: str) -> None:
    with pytest.raises(ValidationError):
        MemoryPinRequest.model_validate({"memory_id": str(uuid4()), "pinned": True, injected: "x"})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_exact_preview_is_localized_and_editor_never_receives_private_snapshot(
    language: str,
) -> None:
    now = datetime.now(UTC)
    private_digest = "a" * 64
    expected = MemoryPinSnapshot(
        id=uuid4(),
        content="<script>untrusted saved fact</script>",
        category="personal",
        pinned=False,
        created_at=now,
        updated_at=now,
        configuration_digest=private_digest,
    )
    before = MemoryPinPatch(memory_pin=MemoryPinValues(expected=expected, pinned=False))
    after = MemoryPinPatch(memory_pin=MemoryPinValues(expected=expected, pinned=True))
    draft = build_action_content(
        uuid4(),
        MEMORY_PIN_OPERATION,
        after,
        before.model_dump(mode="json"),
        after.model_dump(mode="json"),
    )
    preview = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    assert len(preview) == 3 and expected.content in str(preview)
    assert private_digest not in str(preview) and "configuration_digest" not in str(preview)
    messages = build_application_edit_prompt(draft.model_dump(mode="json"), "Unpin instead")
    assert private_digest not in str(messages) and expected.content not in str(messages)
    assert public_application_values(draft) == {"memory_id": str(expected.id), "pinned": True}
    schema = set_lia_memory_pin_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"selection"}
