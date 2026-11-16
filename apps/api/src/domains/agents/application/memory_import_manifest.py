"""Importing a memories export the person attached in the conversation, as the settings do."""

from src.domains.agents.application.memory_import_schemas import MemoryImportInput
from src.domains.agents.application.memory_import_spec import MEMORY_IMPORT_OPERATION
from src.domains.agents.application.output_contracts import pending_application_output_fields
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

MEMORY_IMPORT_MANIFEST = ToolManifest(
    name=MEMORY_IMPORT_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to import the memories of an export file the person ATTACHED in this conversation: the CSV or JSON of the memories export. Name the file exactly as the attachment line of the person's message shows it, or omit file_name for the export attached most recently in this discussion; never invent an id. The proposal shows the file's name and the exact counts it holds (new, already held, duplicates inside the file, invalid entries); the memories' words are never shown, and the file is compared again at confirmation. A memory the account already holds is left alone; everything new is created at once or nothing is, its vectors paid by the account under its ceilings. A file over the published size or entry limits is refused. Never for a file that is not a memories export, and never to create memories from free text (create_lia_memory_tool does that).",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="The attached export, by the file name this conversation shows",
            schema=MemoryImportInput.model_json_schema(),
        )
    ],
    outputs=pending_application_output_fields(),
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_memories",
    tool_category="create",
    mutation_policy="draft",
    initiative_eligible=False,
    semantic_keywords=[
        "import my memories from this file",
        "restore my memories from the export",
        "load the memories export I attached",
    ],
    display=DisplayMetadata(emoji="🧠", i18n_key="import_lia_memories", category="tool"),
)
