"""Local file material belongs to a confirmed original browser, never a model parameter."""

from src.domains.agents.application.skill_file_upload_schemas import SkillFileUploadInput
from src.domains.agents.application.skill_file_upload_spec import SKILL_FILE_UPLOAD_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SKILL_FILE_UPLOAD_MANIFEST = ToolManifest(
    name=SKILL_FILE_UPLOAD_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human approval to import ONE local SKILL.md or ZIP selected and explicitly confirmed afterward in the originating browser. No host path, file bytes, instructions or automatic browser selection are accepted as model arguments. Without replace_skill_id this can only create a new personal skill; an existing compatible own skill replacement requires exact id from get_lia_skills_tool and seals old metadata/files privately. Original file-size/ZIP member/expansion/package-integrity/provenance/name/quota checks apply with published original limits. The original browser session, fresh account/capability and expiry are checked before parsing, before swap and before commit. Changes to the target/files/limits require new approval. Unknown acknowledgement cannot replay; known import with cache failure reports pending refresh. No system, managed library/plugin, other-account mutation or automatic script/model execution.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact optional compatible own skill id; file is chosen by the browser",
            schema=SkillFileUploadInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_skills",
    tool_category="create",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🧩", i18n_key="import_lia_skill_file", category="tool"),
)
