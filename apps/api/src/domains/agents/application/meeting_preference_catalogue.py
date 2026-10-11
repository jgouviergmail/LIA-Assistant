"""Future recording defaults are separate from starting, processing or emailing a meeting."""

from src.domains.agents.application.meeting_preference_schemas import MeetingPreferenceInput
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

MEETING_PREFERENCE_READ_MANIFEST = ToolManifest(
    name="get_lia_meeting_preferences_tool",
    agent="setting_agent",
    description="Read the current account's meeting settings: preferred transcription engine (auto/remote/local), transcription language hint, automatic email to the account owner, audio retention and default minutes template reference, plus the enforced retention ceiling. These are future defaults, not a running recording's resolved engine, price or language. No microphone, meeting creation, provider/model, processing, template edit or email call. The retention ceiling is readonly; use the separate confirmed preference update for writes.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="keep_audio_hours_max",
            type="integer",
            description="Enforced readonly retention ceiling",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="read",
    display=DisplayMetadata(emoji="🎙️", i18n_key="get_lia_meeting_preferences", category="tool"),
)
MEETING_PREFERENCE_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_meeting_preferences_tool",
    agent="setting_agent",
    description="Prepare mandatory exact HITL confirmation for the current owner's future meeting defaults. Include only requested fields: transcription engine preference, transcription language hint (auto or ISO-639-1; not application/minutes language), automatic email to the owner, audio retention, or exact owned/builtin default template reference (null restores automatic selection). Read current defaults first. The displayed complete after-state preserves unrequested fields and explicitly reflects original retention clamping to the enforced ceiling. Fresh owner, current capability/ceiling and exact preference CAS apply under the original shared UI transaction. Changed values require fresh consent; unknown commits cannot replay. No recording, transcription, model/provider, past-meeting change or email occurs. No administrator ceiling may be changed.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Only the requested future meeting defaults",
            schema=MeetingPreferenceInput.model_json_schema(),
        )
    ],
    outputs=[],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    binding_unit="lia_meetings",
    tool_category="system",
    mutation_policy="draft",
    initiative_eligible=False,
    display=DisplayMetadata(emoji="🎙️", i18n_key="update_lia_meeting_preferences", category="tool"),
)
