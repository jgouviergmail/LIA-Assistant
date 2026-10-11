"""Destructive consent names literal files while keeping private file witnesses out of the model."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.asset_download_manifest import ASSET_DOWNLOAD_MANIFEST
from src.domains.agents.application.asset_download_schemas import (
    AssetDownloadInput,
    AssetDownloadPatch,
    AssetDownloadSnapshot,
)
from src.domains.agents.application.asset_download_spec import ASSET_DOWNLOAD_OPERATION
from src.domains.agents.application.asset_file_schemas import AssetFileWitness
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.effects.labels import build_effect_label
from src.domains.agents.tools.application_gallery_tools import (
    download_lia_generated_asset_tool,
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
def test_download_request_cannot_widen_scope_quotas_or_bypass_confirmation(extra):
    with pytest.raises(ValidationError):
        AssetDownloadInput.model_validate({"asset_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_download_preview_editor_registry_and_roundtrip_are_exact(language):
    identity = uuid4()
    selected = AssetDownloadSnapshot(
        request=AssetDownloadInput(asset_id=identity),
        item={
            "id": identity,
            "title": "<script>Literal</script>",
            "original_filename": "File",
            "mime_type": "image/png",
            "file_size": 3,
            "origin": "generated_image",
            "created_at": datetime.now(UTC),
            "expires_at": None,
        },
        file=AssetFileWitness(id=identity, stored_filename="private.png", file_digest="e" * 64),
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        ASSET_DOWNLOAD_OPERATION,
        AssetDownloadPatch(asset_to_download=selected),
        {"asset_to_download": None},
        {"asset_to_download": selected.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_asset_download_note"] and labels["application_field_asset_to_download"]
    )
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "f" * 64 not in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Download the same file")
    )
    assert "state_digest" not in prompt and "f" * 64 not in prompt
    assert draft.after["asset_to_download"]["id"] == str(identity)
    assert "private.png" not in html and "private.png" not in prompt
    assert "e" * 64 not in html and "e" * 64 not in prompt
    label = build_effect_label(
        "draft:application_action",
        {"draft": {"title": "File delete", "operation_id": draft.operation_id}},
    )
    assert label["values"]["operation"] == ASSET_DOWNLOAD_OPERATION.operation_id
    assert set(
        download_lia_generated_asset_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
    assert (
        ASSET_DOWNLOAD_MANIFEST.mutation_policy == "draft"
        and not ASSET_DOWNLOAD_MANIFEST.permissions.hitl_required
    )
    assert not ASSET_DOWNLOAD_MANIFEST.initiative_eligible
