"""Skill metadata growth fails closed; both execution modes receive the reviewed schema."""

import pytest
from pydantic import ValidationError

from src.domains.agents.application.skill_read_schemas import SkillReadInput, SkillReadItem
from src.domains.agents.application.skill_read_spec import SKILL_READ_MANIFEST
from src.domains.agents.tools.application_skill_tools import get_lia_skills_tool
from src.domains.skills.ui_projection import merge_skill_metadata

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "query",
    [
        {"user_id": "other"},
        {"limit": True},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": False},
    ],
)
def test_scope_and_paging_are_strict(query):
    with pytest.raises(ValidationError):
        SkillReadInput.model_validate(query)


def test_new_ui_metadata_requires_explicit_native_projection_review(monkeypatch):
    from src.domains.skills.cache import SkillsCache

    monkeypatch.setattr(SkillsCache, "get_exact", lambda *args: None)
    current = merge_skill_metadata({"name": "test", "description": "public", "scope": "user"})
    assert set(current) == set(SkillReadItem.model_fields)


def test_actual_bound_schema_matches_manifest_and_disallows_initiatives():
    assert SKILL_READ_MANIFEST.parameters[0].schema == SkillReadInput.model_json_schema()
    assert set(get_lia_skills_tool.tool_call_schema.model_json_schema()["properties"]) == {"query"}
    assert SKILL_READ_MANIFEST.mutation_policy == "read"
    assert not SKILL_READ_MANIFEST.initiative_eligible
