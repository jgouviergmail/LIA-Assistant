"""The model can request only a source reset level, never private scope evidence."""

from src.domains.agents.application.psyche_reset_schemas import PsycheResetIntent
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PSYCHE_RESET_MANIFEST = ToolManifest(
    name="reset_lia_psyche_tool",
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation for the current account's psyche reset. soft resets mood to the current source personality baseline, clears active emotions and last appraisal, and resets curiosity/engagement drives. full also resets relationship metrics, self-efficacy and narrative, retaining the stored Big Five traits. purge deletes the whole owned psyche state and all history, including records beyond display limits. soft/full add one source reset snapshot only when a stored state exists; absent state is a verified no-op. Personal preferences and conversations are retained. New interactions or an analysis already started may rebuild state/history; this is not a lasting stop of the engine. The preview binds complete source facts and source-derived public changes, with owner-first locks and fresh expiry/native/source authority before commit. Never accept an actor, digest, baseline or invented count. No model call or summary.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit source reset level",
            schema=PsycheResetIntent.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact source reset confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_psyche",
    initiative_eligible=False,
    semantic_keywords=[
        "reset assistant mood",
        "reset our assistant relationship",
        "erase psyche history",
    ],
    display=DisplayMetadata(emoji="🎭", i18n_key="reset_lia_psyche", category="tool"),
)
