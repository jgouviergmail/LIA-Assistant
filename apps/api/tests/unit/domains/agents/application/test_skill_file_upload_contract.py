"""A browser file handoff carries only exact public metadata and a private local witness."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_file_upload_manifest import SKILL_FILE_UPLOAD_MANIFEST
from src.domains.agents.application.skill_file_upload_schemas import (
    SkillFileUploadInput,
    SkillFileUploadPatch,
    SkillFileUploadSelection,
)
from src.domains.agents.application.skill_file_upload_spec import SKILL_FILE_UPLOAD_OPERATION
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.tools.application_skill_tools import import_lia_skill_file_tool
from src.domains.skills.ui_projection import merge_skill_metadata

pytestmark = pytest.mark.unit


def selection_values():
    return {
        "request": SkillFileUploadInput(),
        "previous": None,
        "state_digest": None,
        "max_file_size_bytes": 102400,
        "max_package_files": 100,
        "max_decompressed_bytes": 1048576,
        "max_personal_skills": 20,
    }


@pytest.mark.parametrize(
    "case", ["target_only", "witness_only", "previous_only", "wrong_target", "missing_witness"]
)
def test_replacement_identity_and_private_witness_are_indivisible(case):
    previous = SkillReadItem.model_validate(
        merge_skill_metadata(
            {
                "name": "owned",
                "description": "public",
                "scope": "user",
                "skill_id": str(uuid4()),
                "provenance": "authored",
            }
        )
    )
    values = selection_values()
    if case in {"target_only", "wrong_target", "missing_witness"}:
        values["request"] = SkillFileUploadInput(
            replace_skill_id=previous.skill_id if case != "wrong_target" else uuid4()
        )
    if case in {"previous_only", "wrong_target", "missing_witness"}:
        values["previous"] = previous
    if case in {"witness_only", "previous_only", "wrong_target"}:
        values["state_digest"] = "a" * 64
    with pytest.raises(ValidationError):
        SkillFileUploadSelection.model_validate(values)


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_checkpoint_consent_and_editing_exclude_file_material(language):
    previous = SkillReadItem.model_validate(
        merge_skill_metadata(
            {
                "name": "owned",
                "description": "public",
                "scope": "user",
                "skill_id": str(uuid4()),
                "provenance": "authored",
            }
        )
    )
    selected = SkillFileUploadSelection.model_validate(
        {
            **selection_values(),
            "request": SkillFileUploadInput(replace_skill_id=previous.skill_id),
            "previous": previous,
            "state_digest": "a" * 64,
        }
    )
    draft = build_action_content(
        uuid4(),
        SKILL_FILE_UPLOAD_OPERATION,
        SkillFileUploadPatch(skill_file_upload=selected),
        {"skill_file_upload": previous.model_dump(mode="json")},
        {"skill_file_upload": selected.public_scope()},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    rendered = str(
        render_application_preview(draft.model_dump(mode="json"), labels, lambda value: value or "")
    )
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Choose another local file")
    )
    assert "state_digest" not in rendered and "state_digest" not in prompt
    assert "a" * 64 not in rendered and "a" * 64 not in prompt
    assert labels["application_skill_file_upload_note"]
    assert changed_resources(draft) == ["skills"]


def test_actual_bound_schema_exposes_no_path_or_file_bytes_to_the_model():
    assert (
        SKILL_FILE_UPLOAD_MANIFEST.parameters[0].schema == SkillFileUploadInput.model_json_schema()
    )
    assert set(import_lia_skill_file_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
    assert set(SkillFileUploadInput.model_fields) == {"replace_skill_id"}
    assert not SKILL_FILE_UPLOAD_MANIFEST.initiative_eligible
