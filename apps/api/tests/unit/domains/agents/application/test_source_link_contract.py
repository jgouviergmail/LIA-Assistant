"""A standing link preview discloses future indexing and keeps private state out of model edits."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.source_link_schemas import (
    SourceLinkInput,
    SourceLinkPatch,
    SourceLinkSelection,
)
from src.domains.agents.application.source_link_spec import (
    SOURCE_LINK_MANIFEST,
    SOURCE_LINK_OPERATION,
)
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_source_link_tools import link_lia_knowledge_source_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"kind": "mail", "provider_id": "INBOX"},
        {"provider_id": "https://example.com/folder"},
        {"user_id": str(uuid4())},
        {"source_name": "Invented name"},
        {"sync_now": True},
    ],
)
def test_native_link_cannot_widen_the_picker_or_override_account_name_and_effect(extra):
    with pytest.raises(ValidationError):
        SourceLinkInput.model_validate(
            {"space_id": uuid4(), "kind": "drive", "provider_id": "real-folder", **extra}
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_source_link_preview_is_canonical_localized_and_registered(language):
    identity = uuid4()
    selected = SourceLinkSelection(
        request=SourceLinkInput(space_id=identity, kind="drive", provider_id="real-folder"),
        space={
            "id": identity,
            "name": "Owned inactive space",
            "description": None,
            "is_active": False,
            "kind": None,
        },
        source_name="<script>Literal folder</script>",
        owned_count=1,
        max_sources=2,
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        SOURCE_LINK_OPERATION,
        SourceLinkPatch(source_to_link=selected),
        {"source_to_link": selected.public_scope()},
        {"source_to_link": selected.public_scope(after=True)},
    )
    labels = get_draft_preview_labels(language)
    assert labels["application_source_link_note"] and labels["application_field_source_to_link"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change source"))
    assert "state_digest" not in prompt and "f" * 64 not in prompt and "f" * 64 not in html
    assert draft.after["source_to_link"]["indexed_now"] is False
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "Source link", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == "knowledge_source.link"
    actual = link_lia_knowledge_source_tool.tool_call_schema.model_json_schema()
    assert set(actual["properties"]) == {"request"}
    assert (
        SOURCE_LINK_MANIFEST.mutation_policy == "draft"
        and not SOURCE_LINK_MANIFEST.permissions.hitl_required
    )
    assert not SOURCE_LINK_MANIFEST.initiative_eligible
