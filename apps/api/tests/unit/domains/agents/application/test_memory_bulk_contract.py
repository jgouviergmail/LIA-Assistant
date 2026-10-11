"""Bulk proposals keep exact scope counts bounded and private selection identities out of prompts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.memory_bulk_schemas import (
    MemoryBulkDeletePatch,
    MemoryBulkDeleteRequest,
    MemoryBulkSnapshot,
)
from src.domains.agents.application.memory_spec import MEMORY_BULK_DELETE_OPERATION
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.result_projection import public_application_values

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "invalid",
    [
        {"preserve_pinned": "true"},
        {"preserve_pinned": 1},
        {"actor_id": str(uuid4())},
        {"selected_count": 0},
        {"selection_digest": "a" * 64},
    ],
)
def test_bulk_selection_refuses_coercion_and_scope_injection(invalid: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MemoryBulkDeleteRequest.model_validate(invalid)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_large_scope_has_a_bounded_localized_exact_count_preview(language: str) -> None:
    digest = "a" * 64
    snapshot = MemoryBulkSnapshot(
        preserve_pinned=True,
        selected_count=100_000,
        preserved_count=10,
        pinned_count=0,
        procedural_count=2,
        invalidated_count=8,
        by_category={"personal": 99_998, "procedural": 2},
        selection_digest=digest,
    )
    patch = MemoryBulkDeletePatch(memories_to_delete=snapshot)
    draft = build_action_content(
        uuid4(),
        MEMORY_BULK_DELETE_OPERATION,
        patch,
        patch.model_dump(mode="json"),
        {"memories_to_delete": None},
    )
    preview = render_application_preview(
        draft.model_dump(mode="json"), get_draft_preview_labels(language), lambda value: value or ""
    )
    assert len(preview) == 3 and "100000" in str(preview)
    assert digest not in str(preview) and "selection_digest" not in str(preview)
    assert len(str(preview)) < 2000
    editor = build_application_edit_prompt(draft.model_dump(mode="json"), "Erase pinned too")
    assert digest not in str(editor) and "100000" not in str(editor)
    assert public_application_values(draft) == {
        "deleted_count": 100_000,
        "preserved_count": 10,
        "preserve_pinned": True,
    }
