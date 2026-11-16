"""Putting a skill's previous version back from the chat: an exact, confirmed proposal (R5).

The settings could restore the version a person's own skill replaced (lot 14); the assistant could
not. Its proposal names the skill and when the version coming back was put aside, renders the
skill's words literally, never lets an edit retarget another skill, and changes the « skills »
resource once committed.
"""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.core.i18n_drafts import get_draft_preview_labels
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.draft_rendering import render_application_preview
from src.domains.agents.application.prompts import build_application_edit_prompt
from src.domains.agents.application.skill_read_schemas import SkillReadItem
from src.domains.agents.application.skill_restore import restore_draft
from src.domains.agents.application.skill_restore_manifest import SKILL_RESTORE_MANIFEST
from src.domains.agents.application.skill_restore_schemas import (
    SkillRestoreInput,
    SkillRestoreSnapshot,
    canonical_skill_restore,
)
from src.domains.agents.application.state_changes import changed_resources
from src.domains.agents.drafts.card_html import to_html_card
from src.domains.agents.drafts.card_spec import CardSpec
from src.domains.agents.tools.application_skill_tools import (
    restore_lia_skill_previous_version_tool,
)

pytestmark = pytest.mark.unit

REPLACED_AT = datetime(2026, 11, 13, 21, 4, tzinfo=UTC)


def _snapshot(name: str = "notes") -> SkillRestoreSnapshot:
    request = SkillRestoreInput(skill_id=uuid4())
    return SkillRestoreSnapshot(
        request=request,
        skill=SkillReadItem(
            name=name,
            description="Second words",
            descriptions=None,
            scope="user",
            category=None,
            priority=50,
            always_loaded=False,
            has_scripts=False,
            has_plan_template=False,
            enabled_for_user=True,
            admin_enabled=True,
            dialogue=False,
            outputs=None,
            skill_id=request.skill_id,
            provenance="authored",
        ),
        previous_version_at=REPLACED_AT,
        state_digest="e" * 64,
    )


@pytest.mark.parametrize(
    "extra",
    [{"name": "other"}, {"version": "older"}, {"user_id": uuid4()}, {"path": "../x"}],
)
def test_the_request_names_one_skill_by_id_and_nothing_else(extra: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        SkillRestoreInput.model_validate({"skill_id": uuid4(), **extra})


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_the_proposal_is_literal_canonical_and_hides_its_witness(language: str) -> None:
    selected = _snapshot("<script>literal</script>")
    draft = restore_draft(uuid4(), selected)

    assert ApplicationActionDraftContent.model_validate(draft.model_dump(mode="json")) == draft
    assert canonical_skill_restore(draft)
    labels = get_draft_preview_labels(language)
    assert labels["application_skill_restore_note"]
    assert labels["application_field_skill_to_restore"]
    rows = render_application_preview(
        draft.model_dump(mode="json"), labels, lambda value: value or ""
    )
    html = to_html_card(CardSpec(emoji="", title="", separator=": ", lines=tuple(rows)))
    assert "<script>" not in html and "&lt;script&gt;" in html
    prompt = str(build_application_edit_prompt(draft.model_dump(mode="json"), "Same skill"))
    assert "e" * 64 not in prompt and "e" * 64 not in html
    assert changed_resources(draft) == ["skills"]


def test_a_draft_that_says_another_after_is_not_canonical() -> None:
    draft = restore_draft(uuid4(), _snapshot())
    tampered = draft.model_copy(update={"after": {"skill_to_restore": None}})

    assert not canonical_skill_restore(tampered)


def test_the_model_reads_the_request_schema_it_is_held_to() -> None:
    assert SKILL_RESTORE_MANIFEST.parameters[0].schema == SkillRestoreInput.model_json_schema()
    assert SKILL_RESTORE_MANIFEST.mutation_policy == "draft"
    schema = restore_lia_skill_previous_version_tool.tool_call_schema.model_json_schema()
    assert set(schema["properties"]) == {"request"}
