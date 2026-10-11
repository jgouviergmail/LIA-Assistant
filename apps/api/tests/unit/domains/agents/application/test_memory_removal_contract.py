"""Erasure confirmation shows the exact fact while source comparison data stays private."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_pin_schemas import MemoryPinSnapshot
from src.domains.agents.application.memory_removal_schemas import (
    MemoryDeletePatch,
    MemoryDeleteRequest,
)
from src.domains.agents.application.memory_spec import MEMORY_DELETE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.result_projection import public_application_values

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "injected", ["actor_id", "expected", "content", "pinned", "configuration_digest"]
)
def test_delete_accepts_only_an_owned_selection_identity(injected: str) -> None:
    with pytest.raises(ValidationError):
        MemoryDeleteRequest.model_validate({"memory_id": str(uuid4()), injected: "x"})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_exact_fact_and_pin_are_visible_but_editor_and_result_do_not_reexpose_erased_content(
    language: str,
) -> None:
    now = datetime.now(UTC)
    digest, fact = "a" * 64, "<script>Saved instruction is data</script>"
    snapshot = MemoryPinSnapshot(
        id=uuid4(),
        content=fact,
        category="procedural",
        pinned=True,
        created_at=now,
        updated_at=now,
        configuration_digest=digest,
    )
    patch = MemoryDeletePatch(memory_to_delete=snapshot)
    draft = build_action_content(
        uuid4(),
        MEMORY_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"memory_to_delete": None},
    )
    labels = get_draft_preview_labels(language)
    preview = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    assert (
        len(preview) == 3
        and fact in str(preview)
        and labels["application_memory_pinned"] in str(preview)
    )
    assert digest not in str(preview) and "configuration_digest" not in str(preview)
    messages = build_application_edit_prompt(draft.model_dump(mode="json"), "Another memory")
    assert digest not in str(messages) and fact not in str(messages)
    assert public_application_values(draft) == {"memory_id": str(snapshot.id), "deleted": True}
    tampered = draft.model_dump(mode="json")
    tampered["after"] = tampered["intent"]
    assert len(render_application_preview(tampered, labels, lambda value: value or "")) == 1
