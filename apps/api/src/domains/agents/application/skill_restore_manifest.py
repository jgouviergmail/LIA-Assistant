"""Putting back the previous version of one of the person's own skills, as the settings do."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.skill_restore_schemas import SkillRestoreInput
from src.domains.agents.application.skill_restore_spec import SKILL_RESTORE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SKILL_RESTORE_MANIFEST = ToolManifest(
    name=SKILL_RESTORE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to put back the PREVIOUS version of ONE of the person's own skills: the version its last replacement put aside. Select skill_id from get_lia_skills_tool, where previous_version_at says a previous version exists. Only a skill the person wrote themselves keeps one; a system, library, plugin or imported skill has none. The proposal names the skill and when that version was put aside; the version's words are never shown and are compared again at confirmation, so a skill replaced meanwhile needs a new proposal. The current version becomes the previous one, so the restoration can itself be undone the same way. No skill execution, model, network or other account.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned skill id whose previous version is put back",
            schema=SkillRestoreInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_skills",
    tool_category="update",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "restore the previous version of my skill",
        "undo the last change to my skill",
        "go back to the old version of this skill",
    ],
    display=DisplayMetadata(
        emoji="🧩", i18n_key="restore_lia_skill_previous_version", category="tool"
    ),
)
