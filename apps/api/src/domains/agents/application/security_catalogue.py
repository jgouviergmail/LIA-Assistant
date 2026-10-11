"""Security state reads expose reviewed UI metadata, never authentication material."""

from src.domains.agents.application.security_schemas import SecurityRead
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SECURITY_READ_MANIFEST = ToolManifest(
    name="get_lia_security_settings_tool",
    agent="setting_agent",
    description="Read account authentication features, password sign-in enabled state, TOTP active/confirmation state and remaining recovery-code COUNT, and owned passkey metadata. Overview also lists available reauthentication methods; step_up_freshness is unknown without a trusted current session, never an approval proof. Overview, totp or bounded passkeys; use next_cursor as cursor after the last shown item. MFA_DISABLED means MFA state is unavailable, not inactive; password/OAuth methods remain available. No secrets, code values, credential ids, passwords, current-device session identification or secure ceremony. Changes require separate exact confirmation and applicable reauthentication.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Security section or bounded passkey page",
            schema=SecurityRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="step_up_freshness",
            type="string",
            description="Observed fresh/stale session state, unknown without authenticated transport; never permission to execute",
        ),
        OutputFieldSchema(
            path="step_up_valid_until",
            type="string",
            nullable=True,
            description="Observed reauthentication horizon, rechecked when a sensitive action executes",
        ),
        OutputFieldSchema(
            path="features", type="object", description="Effective authentication features"
        ),
        OutputFieldSchema(
            path="password_set",
            type="boolean",
            description="Password sign-in enabled, never the password",
        ),
        OutputFieldSchema(
            path="available_methods",
            type="array",
            nullable=True,
            description="Account methods, independent of current session freshness",
        ),
        OutputFieldSchema(
            path="totp", type="object", nullable=True, description="Non-secret TOTP state"
        ),
        OutputFieldSchema(
            path="passkeys", type="array", nullable=True, description="Owned passkey metadata"
        ),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Continue as cursor; null at end",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_security",
    semantic_keywords=[
        "my security settings",
        "is my two factor authentication enabled",
        "my passkeys",
    ],
    display=DisplayMetadata(emoji="🔐", i18n_key="get_lia_security_settings", category="tool"),
)
