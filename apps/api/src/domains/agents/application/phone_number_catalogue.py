"""Number declaration is separate from a paid verification call and secure proof."""

from src.domains.agents.application.phone_number_schemas import PhoneNumberRequest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PHONE_NUMBER_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_phone_number_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to set or clear the current account's declared phone number. Use the existing phone-settings normalization; the preview shows the resolved international number before any write. Re-entering the same number preserves verification; a changed or cleared number loses it. Never verify ownership, ask for an OTP, place a call or change a running call. Changes affect future owner calls. A changed saved number or verification requires a new preview; no write before confirmation.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Set with the explicitly declared number, or clear without a number",
            schema=PhoneNumberRequest.model_json_schema(),
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
    semantic_keywords=["change my phone number", "clear my declared phone number"],
    display=DisplayMetadata(emoji="☎️", i18n_key="update_lia_phone_number", category="tool"),
)
