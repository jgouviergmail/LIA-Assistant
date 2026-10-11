"""Private URL/file witnesses are excluded from all consent and edit prompts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_url_import_manifest import SKILL_URL_IMPORT_MANIFEST
from src.domains.agents.application.skill_url_import_schemas import (
    SkillUrlImportInput,
    SkillUrlImportPatch,
    SkillUrlImportSnapshot,
)
from src.domains.agents.application.skill_url_import_spec import SKILL_URL_IMPORT_OPERATION
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.tools.application_skill_tools import import_lia_skill_url_tool
from src.domains.skills.ui_projection import parsed_skill_metadata
from src.domains.skills.upload_preview import SkillPackageFile, SkillPackagePreview

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "url",
    [
        "http://public.example/file",
        "https://user:secret@public.example/file",
        "https:///missing",
        "https://user@public.example/file",
    ],
)
def test_url_input_refuses_credentials_and_non_https(url):
    with pytest.raises(ValidationError):
        SkillUrlImportInput(url=url)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_exact_url_consent_and_checkpoint_keep_private_witnesses_private(language):
    request = SkillUrlImportInput(url="https://public.example/file.zip")
    package = SkillPackagePreview(
        **parsed_skill_metadata(
            {"name": "card", "description": "Literal public description"}, "user"
        ),
        files=(SkillPackageFile(path="SKILL.md", size=100),),
    )
    snapshot = SkillUrlImportSnapshot(
        request=request,
        package=package,
        previous=None,
        filename="file.zip",
        size_bytes=200,
        package_digest="a" * 64,
        state_digest="b" * 64,
    )
    draft = build_action_content(
        uuid4(),
        SKILL_URL_IMPORT_OPERATION,
        SkillUrlImportPatch(skill_url_import=snapshot),
        {"skill_url_import": None},
        {"skill_url_import": snapshot.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_skill_url_import_note"] and labels["application_field_skill_url_import"]
    )
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Refresh this same URL")
    )
    for private in ("state_digest", "package_digest", "a" * 64, "b" * 64):
        assert private not in rendered and private not in prompt
    assert changed_resources(draft) == ["skills"]
    assert SKILL_URL_IMPORT_MANIFEST.parameters[0].schema == SkillUrlImportInput.model_json_schema()
    assert set(import_lia_skill_url_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
