"""Changing personal skill activation never changes system administration or executes a skill."""

from src.domains.agents.application.skill_update_schemas import SkillUpdateInput
from src.domains.agents.application.skill_update_spec import SKILL_UPDATE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SKILL_UPDATE_MANIFEST = ToolManifest(
    name=SKILL_UPDATE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to enable or disable ONE skill for the current account. Select the visible skill_id through get_lia_skills_tool. The explicit enabled boolean changes only the personal state, including an available system skill; global system visibility, administrators and other accounts are unchanged. Hidden/shadowed/system-disabled/foreign skills refuse. Full public identity/provenance/current state are compared under fresh skill/account/state locks; metadata or state changes require fresh approval. Same desired value is a confirmed no-op. No execution of the skill, provider, instructions or filesystem changes. Repeated or ambiguous commands cannot invert or replay the switch.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact visible skill id and explicit desired personal enabled state",
            schema=SkillUpdateInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_skills",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["enable my skill", "disable this skill", "personal skill switch"],
    display=DisplayMetadata(emoji="🧩", i18n_key="update_lia_skill_settings", category="tool"),
)
