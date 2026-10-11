"""Personal activation consent survives checkpoints, escapes descriptions and edits request only."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_delete_manifest import SKILL_DELETE_MANIFEST
from src.domains.agents.application.skill_delete_schemas import (
    SkillDeleteInput,
    SkillDeletePatch,
    SkillDeleteSnapshot,
)
from src.domains.agents.application.skill_delete_spec import SKILL_DELETE_OPERATION
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_skill_tools import delete_lia_skill_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"force": True},
        {"directory": "untrusted"},
        {"admin_enabled": False},
        {"user_id": uuid4()},
        {"instructions": "untrusted"},
    ],
)
def test_personal_skill_input_is_strict_and_cannot_change_administration(extra):
    with pytest.raises(ValidationError):
        SkillDeleteInput.model_validate({"skill_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_skill_metadata_is_literal_in_confirmation_and_never_editable(language):
    request = SkillDeleteInput(
        skill_id=uuid4(),
    )
    expected = SkillReadItem(
        name="<script>literal</script>",
        description="Untrusted description",
        descriptions=None,
        scope="user",
        category=None,
        priority=50,
        always_loaded=False,
        has_scripts=True,
        has_plan_template=False,
        enabled_for_user=True,
        admin_enabled=True,
        dialogue=False,
        outputs=None,
        skill_id=request.skill_id,
        provenance="authored",
    )
    draft = build_action_content(
        uuid4(),
        SKILL_DELETE_OPERATION,
        SkillDeletePatch(
            skill_to_delete=SkillDeleteSnapshot(
                request=request, skill=expected, files_present=True, state_digest="f" * 64
            )
        ),
        {
            "skill_to_delete": SkillDeleteSnapshot(
                request=request, skill=expected, files_present=True, state_digest="f" * 64
            ).public_scope()
        },
        {"skill_to_delete": None},
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert labels["application_skill_delete_note"] and labels["application_field_skill_to_delete"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Remove this same skill")
    )
    assert "state_digest" not in prompt and "f" * 64 not in prompt and "f" * 64 not in html
    assert changed_resources(draft) == ["skills"]
    assert SKILL_DELETE_MANIFEST.parameters[0].schema == SkillDeleteInput.model_json_schema()
    assert set(delete_lia_skill_tool.tool_call_schema.model_json_schema()["properties"]) == {
        "request"
    }
