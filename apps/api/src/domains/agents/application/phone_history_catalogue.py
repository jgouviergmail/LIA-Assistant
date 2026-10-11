"""Retained call history and observed usage form one read-only binding."""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.telephony.history_schemas import PhoneHistoryRead

PHONE_HISTORY_READ_MANIFEST = ToolManifest(
    name="get_lia_phone_calls_tool",
    agent="setting_agent",
    description="Read retained owned call history and public UI details with bounded pages. Usage is observed recorded platform runs: it may omit delegated runs after message associations are purged, and is not a vendor invoice. Missing usage is unavailable, not zero. Never expose encrypted callee numbers, raw transcripts, webhook payloads or credentials, call a vendor, dial, regenerate a recap or delete records. Continue with next_cursor after the last shown call.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Bounded call history page",
            schema=PhoneHistoryRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="calls", type="array", description="Public retained owned call rows"
        ),
        OutputFieldSchema(path="total", type="integer", description="Owned retained call count"),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Last shown UUID; null at end",
        ),
        OutputFieldSchema(path="usage_scope", type="string", description="recorded_platform_runs"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_phone_history",
    semantic_keywords=["my recent calls", "my call history", "recorded call consumption"],
    display=DisplayMetadata(emoji="☎️", i18n_key="get_lia_phone_calls", category="tool"),
)
