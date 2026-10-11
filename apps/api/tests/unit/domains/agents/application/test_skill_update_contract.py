"""Personal activation consent survives checkpoints, escapes descriptions and edits request only."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.action_preparation import build_action_content
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.application.skill_update_manifest import SKILL_UPDATE_MANIFEST
from src.domains.agents.application.skill_update_schemas import (
    SkillUpdateInput,
    SkillUpdateObservation,
    SkillUpdatePatch,
)
from src.domains.agents.application.skill_update_spec import SKILL_UPDATE_OPERATION
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_skill_tools import update_lia_skill_settings_tool

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "extra",
    [
        {"enabled": 1},
        {"enabled": "false"},
        {"admin_enabled": False},
        {"user_id": uuid4()},
        {"instructions": "untrusted"},
    ],
)
def test_personal_skill_input_is_strict_and_cannot_change_administration(extra):
    with pytest.raises(ValidationError):
        SkillUpdateInput.model_validate({"skill_id": uuid4(), "enabled": False, **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_skill_metadata_is_literal_in_confirmation_and_never_editable(language):
    request = SkillUpdateInput(skill_id=uuid4(), enabled=False)
    expected = SkillReadItem(
        name="<script>literal</script>",
        description="Untrusted description",
        descriptions=None,
        scope="admin",
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
        provenance="system",
    )
    draft = build_action_content(
        uuid4(),
        SKILL_UPDATE_OPERATION,
        SkillUpdatePatch(
            skill_personal_state=SkillUpdateObservation(request=request, expected=expected)
        ),
        {"skill_personal_state": expected.model_dump(mode="json")},
        {
            "skill_personal_state": expected.model_copy(
                update={"enabled_for_user": False}
            ).model_dump(mode="json")
        },
    )
    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    labels = get_draft_preview_labels(language)
    assert (
        labels["application_skill_update_note"] and labels["application_field_skill_personal_state"]
    )
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(
        build_application_edit_prompt(draft.model_dump(mode="json"), "Enable this same skill")
    )
    assert '"expected"' not in prompt and '"admin_enabled"' not in prompt
    assert changed_resources(draft) == ["skills"]
    assert SKILL_UPDATE_MANIFEST.parameters[0].schema == SkillUpdateInput.model_json_schema()
    assert set(
        update_lia_skill_settings_tool.tool_call_schema.model_json_schema()["properties"]
    ) == {"request"}
