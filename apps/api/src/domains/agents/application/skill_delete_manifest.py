"""Removing one personal skill excludes system skills, plugins and other accounts."""

from src.domains.agents.application.skill_delete_schemas import SkillDeleteInput
from src.domains.agents.application.skill_delete_spec import SKILL_DELETE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SKILL_DELETE_MANIFEST = ToolManifest(
    name=SKILL_DELETE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to remove ONE owned personal skill and its complete directory. Select skill_id from get_lia_skills_tool. Available system skills and plugin components cannot be deleted individually; uninstall the owning plugin instead. Public current identity/provenance/state and private complete archive/directory witnesses are freshly compared. Changed metadata/files/state/scope require new approval. Rows commit before disk cleanup; unknown commit acknowledgement retains bytes and never automatically replays. Cleanup refuses new registrations or replaced/changed directories, with explicit file/cache pending status on partial failure. Shared account locks serialize imports with cleanup; already-missing directories can settle. No skill execution, model, network import or change to other accounts.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact owned removable skill id",
            schema=SkillDeleteInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_skills",
    tool_category="delete",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["delete my skill", "remove this personal skill"],
    display=DisplayMetadata(emoji="🧩", i18n_key="delete_lia_skill", category="tool"),
)
