"""Explicit human confirmation of phone context and mode preferences."""

from src.domains.agents.application.phone_preference_schemas import PhonePreferenceRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PHONE_PREFERENCES_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_phone_preferences_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation of phone context consent, disabled read domains or saved call_mode (direct/delegated). Read get_lia_phone_identity first to see available domains and effective mode. Preserve other settings and number/verification; never dial, verify a number, accept an OTP or credentials, or reconnect a running call. Mode and context consent apply to future owner calls. Domain refusals are checked on each next phone/direct-browser lookup, including running sessions; browser setup declarations refresh at start/wake. Empty disabled_domains enables every offered domain; additions offered later follow the source default-enabled policy. No write before confirmation; changed number, verification or settings requires a new preview.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="One or more explicit non-null phone context/domain/mode values",
            schema=PhonePreferenceRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_phone_identity",
    semantic_keywords=[
        "change my phone context consent",
        "disable phone read domains",
        "change owner call mode",
    ],
    display=DisplayMetadata(emoji="☎️", i18n_key="update_lia_phone_preferences", category="tool"),
)
