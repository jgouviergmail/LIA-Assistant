"""Skill-library schemas, complete consent and request-only edits survive checkpoints."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_library_import_manifest import LIBRARY_INSTALL_MANIFEST
from src.domains.agents.application.skill_library_import_schemas import (
    LibraryImportPatch,
    LibraryImportSnapshot,
    LibraryInstallInput,
)
from src.domains.agents.application.skill_library_import_spec import LIBRARY_INSTALL_OPERATION
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_skill_library_tools import install_lia_library_skill_tool
from src.domains.skill_library.schemas import (
    LibraryChanges,
    LibraryFile,
    LibraryPreviewResponse,
    LibraryUpdatePreviewResponse,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [{"force": True}, {"actor_id": str(uuid4())}, {"is_system": True}, {"instructions": "private"}],
)
def test_install_has_no_admin_or_body_override(extra):
    with pytest.raises(ValidationError):
        LibraryInstallInput.model_validate(
            {"repository": "acme/skills", "commit_sha": "a" * 40, **extra}
        )


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_library_consent_checkpoint_literal_metadata_and_private_witness(language):
    request = LibraryInstallInput(repository="acme/skills", commit_sha="a" * 40)
    preview = LibraryPreviewResponse(
        repository=request.repository,
        ref="HEAD",
        path="",
        commit_sha=request.commit_sha,
        tree_sha="b" * 40,
        name="pdf",
        description="<script>literal</script>",
        files=[
            LibraryFile(path="SKILL.md", size=500),
            LibraryFile(path="scripts/run.py", size=700),
        ],
        has_scripts=True,
        conflict="none",
    )
    snapshot = LibraryImportSnapshot(
        kind="install",
        request=request,
        preview=LibraryUpdatePreviewResponse(
            preview=preview, changes=LibraryChanges(added=[f.path for f in preview.files])
        ),
        state_digest="f" * 64,
    )
    draft = build_action_content(
        uuid4(),
        LIBRARY_INSTALL_OPERATION,
        LibraryImportPatch(skill_library_import=snapshot),
        {"skill_library_import": None},
        {"skill_library_import": snapshot.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_skill_library_import_note"]
        and labels["application_field_skill_library_import"]
    )
    lines = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(lines)))
    assert "<script>" not in html and "&lt;script&gt;" in html and "scripts/run.py" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Use the same exact source")
    )
    assert "state_digest" not in prompt and "f" * 64 not in prompt and "f" * 64 not in html
    assert changed_resources(draft) == ["skills"]
    assert LIBRARY_INSTALL_MANIFEST.parameters[0].schema == LibraryInstallInput.model_json_schema()
    assert set(
        install_lia_library_skill_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
