"""Complete exports have small schemas; content never enters the LLM result."""

from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

INTEREST_EXPORT_MANIFEST = ToolManifest(
    name="export_lia_interests_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to export all owned saved interests in CSV or JSON, including active, blocked and dormant topics beyond displayed pages. The preview seals complete count, observation time and a private source comparison. No file, source content in chat, provider call or settings change before approval. The original authenticated browser starts a single-use bounded download after approval; changed source, expired approval, withdrawn capability and other sessions refuse it. The exported weight is observed at the preview time. CSV text is spreadsheet-safe; JSON preserves text. Starting a request never proves that the file was saved. Never replay an uncertain transfer.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="CSV or JSON export format",
            schema=ManagementExportRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Complete-scope export confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_interests",
    initiative_eligible=False,
    semantic_keywords=["export my interests", "download all saved interest topics"],
    display=DisplayMetadata(emoji="💡", i18n_key="export_lia_interests", category="tool"),
)

MEMORY_EXPORT_MANIFEST = ToolManifest(
    name="export_lia_memories_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to export all current owned memories in CSV or JSON beyond management pages. Superseded historical rows are excluded exactly as in the memory UI; use the full account export for its different scope. JSON reuses the source display projection including retention risk observed at the displayed time; CSV uses the source twelve export columns. Private embeddings and biometric snapshots never enter this export. Importance zero, pinning and usage values are preserved. No file, memory text in chat, retrieval count update, provider call or memory-setting change before approval. Original-session, single-use bounded download follows approval; changed/new/invalidated memories or withdrawn capability refuse. A requested transfer never proves that the file was saved; never automatically replay an uncertain request.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Source CSV or JSON format",
            schema=ManagementExportRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Complete current-memory export confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_memories",
    initiative_eligible=False,
    semantic_keywords=["export my memories", "download my current saved memories"],
    display=DisplayMetadata(emoji="🧠", i18n_key="export_lia_memories", category="tool"),
)

JOURNAL_EXPORT_MANIFEST = ToolManifest(
    name="export_lia_journals_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to export every owned active and archived journal entry beyond displayed pages in CSV or JSON. JSON also preserves the STORED full and brief portrait and its stored provenance, even when stale or personal learning is disabled; this is portability, not the current authorized portrait read. Public entry fields only: no embeddings or private evidence/session traces. The preview contains count, format and observation time; no journal content, portrait, file or provider call before approval. One bounded original-session download follows approval. Changed entries or changed exported portrait, expired approval or withdrawn native/journal capability refuse it. CSV cells are spreadsheet-safe; JSON preserves source text. A requested download never proves the file was saved; never replay an uncertain transfer.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="CSV (default) or JSON including stored portrait",
            schema=ManagementExportRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Complete journal export confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="system",
    binding_unit="lia_journals",
    initiative_eligible=False,
    semantic_keywords=["export my journal", "download all journal entries and stored portrait"],
    display=DisplayMetadata(emoji="📓", i18n_key="export_lia_journals", category="tool"),
)
