"""Source removal consent is exact, localized and cannot reveal private witnesses."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.source_unlink_schemas import (
    SourceUnlinkInput,
    SourceUnlinkPatch,
    SourceUnlinkSelection,
)
from src.domains.agents.application.source_unlink_spec import (
    SOURCE_UNLINK_MANIFEST,
    SOURCE_UNLINK_OPERATION,
)
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_source_unlink_tools import (
    unlink_lia_knowledge_source_tool,
)

pytestmark = pytest.mark.unit


def test_unlink_tool_requests_only_exact_source_identity_and_mandatory_native_approval():
    actual = unlink_lia_knowledge_source_tool.tool_call_schema.model_json_schema()
    assert set(actual["properties"]) == {"request"}
    assert set(actual["$defs"]["SourceUnlinkInput"]["properties"]) == {
        "space_id",
        "source_id",
        "kind",
    }
    assert SOURCE_UNLINK_MANIFEST.mutation_policy == "draft"
    assert not SOURCE_UNLINK_MANIFEST.permissions.hitl_required
    assert not SOURCE_UNLINK_MANIFEST.initiative_eligible
    with pytest.raises(ValidationError):
        SourceUnlinkInput(space_id=uuid4(), source_id=uuid4(), kind="drive", delete_documents=True)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_source_unlink_preview_hides_proofs_and_names_the_registered_action(language):
    identity = uuid4()
    selected = SourceUnlinkSelection(
        request=SourceUnlinkInput(space_id=identity, source_id=uuid4(), kind="drive"),
        space={
            "id": identity,
            "name": "Owned space",
            "description": None,
            "is_active": False,
            "kind": None,
        },
        source_name="<script>Literal source</script>",
        sync_status="idle",
        documents=2,
        documents_digest="e" * 64,
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        SOURCE_UNLINK_OPERATION,
        SourceUnlinkPatch(source_to_unlink=selected),
        {"source_to_unlink": selected.public_scope()},
        {"source_to_unlink": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_source_unlink_note"] and labels["application_field_source_to_unlink"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change source"))
    for proof in ("documents_digest", "state_digest", "e" * 64, "f" * 64):
        assert proof not in html and proof not in prompt
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Source removal", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == "knowledge_source.unlink"
