"""Canonical destructive previews disclose scope and never expose private witnesses."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.source_delete_manifest import SOURCE_DELETE_MANIFEST
from src.domains.agents.application.source_delete_schemas import (
    SourceDeleteInput,
    SourceDeletePatch,
    SourceDeleteSelection,
)
from src.domains.agents.application.source_delete_spec import SOURCE_DELETE_OPERATION
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkSelection,
)
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_source_delete_tools import (
    delete_lia_knowledge_source_tool,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": str(uuid4())},
        {"force": True},
        {"delete_all": True},
        {"max_items": 1000000},
        {"worker_id": "other"},
    ],
)
def test_source_delete_request_cannot_widen_account_scope_limits_or_skip_guards(extra):
    with pytest.raises(ValidationError):
        SourceDeleteInput.model_validate(
            {"space_id": uuid4(), "source_id": uuid4(), "kind": "drive", **extra}
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_source_delete_preview_editor_actions_and_serialization_are_canonical(language):
    identity = uuid4()
    source = SourceUnlinkSelection(
        request=SourceUnlinkInput(space_id=identity, source_id=uuid4(), kind="drive"),
        space={
            "id": identity,
            "name": "Owned inactive destination",
            "description": None,
            "is_active": False,
            "kind": None,
        },
        source_name="<script>Literal source</script>",
        sync_status="idle",
        documents=0,
        documents_digest="e" * 64,
        state_digest="f" * 64,
    )
    selected = SourceDeleteSelection(
        source=source,
        batches=(),
    )
    draft = build_action_content(
        uuid4(),
        SOURCE_DELETE_OPERATION,
        SourceDeletePatch(source_to_delete=selected),
        {"source_to_delete": selected.public_scope()},
        {"source_to_delete": selected.public_scope(after=True)},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert labels["application_source_delete_note"] and labels["application_field_source_to_delete"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change source"))
    assert "state_digest" not in prompt and "documents_digest" not in prompt
    assert "f" * 64 not in html and "e" * 64 not in html
    assert draft.after["source_to_delete"]["source_removed"] is True
    assert draft.after["source_to_delete"]["documents_deleted"] == 0
    assert changed_resources(draft) == ["spaces"]
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Source sync", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == "knowledge_source.delete"
    assert set(
        delete_lia_knowledge_source_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
    assert SOURCE_DELETE_MANIFEST.mutation_policy == "draft"
    assert not SOURCE_DELETE_MANIFEST.permissions.hitl_required
    assert not SOURCE_DELETE_MANIFEST.initiative_eligible
