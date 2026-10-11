"""Exact retention previews disclose quota/TTL and hide all private witnesses."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.asset_retention_manifest import ASSET_RETENTION_MANIFEST
from src.domains.agents.application.asset_retention_schemas import (
    AssetRetentionInput,
    AssetRetentionPatch,
    AssetRetentionSelection,
)
from src.domains.agents.application.asset_retention_spec import ASSET_RETENTION_OPERATION
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_gallery_tools import (
    update_lia_generated_asset_retention_tool,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"user_id": str(uuid4())},
        {"force": True},
        {"kept": 1},
        {"kept": None},
        {"max_files": 99999},
        {"ids": []},
        {"ids": [uuid4() for _ in range(101)]},
    ],
)
def test_retention_request_cannot_widen_scope_quotas_or_bypass_confirmation(extra):
    with pytest.raises(ValidationError):
        AssetRetentionInput.model_validate({"ids": [uuid4()], "kept": True, **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_retention_preview_editor_registry_and_roundtrip_are_exact(language):
    identity = uuid4()
    selected = AssetRetentionSelection(
        request=AssetRetentionInput(ids=(identity,), kept=False),
        items=(
            {
                "id": identity,
                "title": "<script>Literal</script>",
                "original_filename": "File",
                "mime_type": "image/png",
                "file_size": 3,
                "origin": "generated_image",
                "created_at": datetime.now(UTC),
                "expires_at": None,
            },
        ),
        usage={"kept_files": 1, "kept_bytes": 3, "max_files": 100, "max_bytes": 1000},
        ttl_hours=48,
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        ASSET_RETENTION_OPERATION,
        AssetRetentionPatch(asset_retention=selected),
        {"asset_retention": selected.public_scope()},
        {"asset_retention": selected.public_scope(after=True)},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_asset_retention_note"] and labels["application_field_asset_retention"]
    )
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "f" * 64 not in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Change retention"))
    assert "state_digest" not in prompt and "f" * 64 not in prompt
    assert draft.after["asset_retention"]["usage"]["kept_files"] == 0
    assert draft.after["asset_retention"]["release_ttl_hours"] == 48
    assert changed_resources(draft) == ["generated_assets"]
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "File retention", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == ASSET_RETENTION_OPERATION.operation_id
    assert set(
        update_lia_generated_asset_retention_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
    assert (
        ASSET_RETENTION_MANIFEST.mutation_policy == "draft"
        and not ASSET_RETENTION_MANIFEST.permissions.hitl_required
    )
    assert not ASSET_RETENTION_MANIFEST.initiative_eligible
