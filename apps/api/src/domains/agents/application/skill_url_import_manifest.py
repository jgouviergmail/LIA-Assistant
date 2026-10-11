"""URL package source, exact optional replacement and original security bounds are public."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.skill_url_import_schemas import SkillUrlImportInput
from src.domains.agents.application.skill_url_import_spec import SKILL_URL_IMPORT_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SKILL_URL_IMPORT_MANIFEST = ToolManifest(
    name=SKILL_URL_IMPORT_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to import ONE personal skill from a public HTTPS URL supplying SKILL.md or ZIP. Existing pinned-IP SSRF/no-redirect/transfer-deadline/size/package-integrity/quota and shared per-account URL rate limit apply; URL imports must also be enabled on the instance. Embedded URL credentials are forbidden. Complete original public package/file metadata is shown, never instructions or file contents. Remote bytes are privately hashed and fetched again after consent; any remote change requires new approval. A replacement requires exact replace_skill_id from get_lia_skills_tool and seals all old metadata/files; only original compatible URL provenance may replace, never system/plugin/library or another account. Fresh authority/expiry and exact old state are checked under the shared owner/skill locks before swap and before commit. Unknown commit acknowledgement cannot retry; known import with cache failure reports pending refresh. Imported scripts retain third-party sandbox isolation. No LLM/provider or automatic execution of imported scripts.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Public HTTPS package source and exact optional compatible owned replacement",
            schema=SkillUrlImportInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_skills",
    tool_category="create",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=["import skill URL", "install skill ZIP URL"],
    display=DisplayMetadata(emoji="🧩", i18n_key="import_lia_skill_url", category="tool"),
)
