"""Both modes see the source creation schema and one mandatory native confirmation."""

from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.application.space_create_schemas import SpaceCreateInput
from src.domains.agents.application.space_create_spec import SPACE_CREATE_OPERATION
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SPACE_CREATE_MANIFEST = ToolManifest(
    name=SPACE_CREATE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to create one empty active personal knowledge space. Full current source UI name/description schema; normalized whitespace, account space quota and unique name are verified before preview and again before the acknowledged write. No document, upload, indexing, provider/model call or cost beyond normal assistant prompt costs. Future ready documents of an active space can enrich answers. No space is created before confirmation. Stale quota/configuration requires renewed approval; unknown commit completion is never retried automatically. No system/admin space or arbitrary target account.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Exact source name and optional description",
            schema=SpaceCreateInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_knowledge_spaces",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "create my knowledge space",
        "new document space",
        "create knowledge folder",
    ],
    display=DisplayMetadata(emoji="📚", i18n_key="create_lia_knowledge_space", category="tool"),
)
