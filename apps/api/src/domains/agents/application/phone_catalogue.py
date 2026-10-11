"""Phone identity state is a read, independent of calling and verification actions."""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    PermissionProfile,
    ToolManifest,
)

PHONE_IDENTITY_READ_MANIFEST = ToolManifest(
    name="get_lia_phone_identity_tool",
    agent="setting_agent",
    description="Read your saved phone identity: number, verification, pending verification, rich context consent, allowed/disabled domains, saved and effective call mode, and Live availability. number_status distinguishes unset, available and unreadable saved ciphertext. This consults no vendor and does not dial, verify, clear codes, alter settings or expose credentials. Verification applies to a readable line. Requires active platform application tools and telephony capabilities.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="identity", type="object", description="Reviewed phone identity UI state"
        ),
        OutputFieldSchema(
            path="number_status", type="string", description="unset, available or unreadable"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_phone_identity",
    semantic_keywords=["my phone number", "is my phone verified", "my phone call settings"],
    display=DisplayMetadata(emoji="☎️", i18n_key="get_lia_phone_identity", category="tool"),
)
