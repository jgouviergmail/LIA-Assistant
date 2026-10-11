"""The planner sees exact personal library sources and the original import boundaries."""

from pydantic import BaseModel

from src.domains.agents.application.operation_spec import ApplicationOperationSpec
from src.domains.agents.application.skill_library_import_schemas import (
    LibraryInstallInput,
    LibraryUpdateInput,
)
from src.domains.agents.application.skill_library_import_spec import (
    LIBRARY_INSTALL_OPERATION,
    LIBRARY_UPDATE_OPERATION,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)


def _manifest(
    spec: ApplicationOperationSpec, request: type[BaseModel], description: str
) -> ToolManifest:
    return ToolManifest(
        name=spec.tool_name,
        agent="setting_agent",
        description=description,
        parameters=[
            ParameterSchema(
                name="request",
                type="object",
                required=True,
                description="Exact original immutable commit and owned source",
                schema=request.model_json_schema(),
            )
        ],
        outputs=[],
        cost=CostProfile(),
        permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
        binding_unit="lia_skill_library",
        tool_category="create" if spec is LIBRARY_INSTALL_OPERATION else "update",
        mutation_policy="draft",
        initiative_eligible=False,
        display=DisplayMetadata(
            emoji="🧩", i18n_key=spec.tool_name.removesuffix("_tool"), category="tool"
        ),
    )


LIBRARY_INSTALL_MANIFEST = _manifest(
    LIBRARY_INSTALL_OPERATION,
    LibraryInstallInput,
    "Prepare mandatory human confirmation to install ONE personal skill from the original library at the exact full commit_sha shown by get_lia_skill_library_tool. Use repository/path/ref/portal/registry_id/skill_id from that preview. Complete file, script and audit metadata is displayed; skill instructions never enter the prompt. Source audit/name conflicts/quota/SSRF and shared library rate limits apply through the original service. Branch movement cannot retarget the commit. Fresh account/capability and absent owned identity/file state are checked under the shared owner lock before live swap and again before commit. Unknown commit acknowledgement cannot automatically retry; known install with cache failure reports pending refresh. Third-party skills retain library provenance and existing sandbox isolation. No system, administrator or other-account mutation.",
)
LIBRARY_UPDATE_MANIFEST = _manifest(
    LIBRARY_UPDATE_OPERATION,
    LibraryUpdateInput,
    "Prepare mandatory human confirmation to update ONE owned library skill to the full commit_sha from its original update preview. Select exact skill_id through get_lia_skill_library_tool. Complete changed-file and audit metadata is displayed. The old owned source, public state and complete local archive are sealed privately; changed files/source/state require new approval. Original source/SSRF/audit/name/quota and shared rate limits apply. Fresh authority and expiry are checked under the shared owner lock before replacing files and before commit. Unknown acknowledgement cannot replay; known update with cache failure reports pending refresh. Preserves library provenance and sandbox isolation. No system, plugin-component or other-account update.",
)
