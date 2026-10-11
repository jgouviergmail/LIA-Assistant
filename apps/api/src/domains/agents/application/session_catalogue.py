"""Bounded session listing remains independent of MFA enrollment availability."""

from src.domains.agents.application.session_revocation_schemas import DeviceSessionRevokeRequest
from src.domains.agents.application.session_schemas import DeviceSessionsRead
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

SESSIONS_READ_MANIFEST = ToolManifest(
    name="get_lia_device_sessions_tool",
    agent="setting_agent",
    description="Read this account's live device sessions: opaque display ids, device names, coarse browser/OS/IP, sign-in methods and times. Bounded pages with next_cursor; never expose session cookies, FCM attestation ids or step-up proof. Without trusted origin session context current is null and current_session_known false; never identify the current device by guessing. No revocation. Independent of the MFA flag.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Bounded session page, continuing from the last shown cursor",
            schema=DeviceSessionsRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="sessions", type="array", description="Owner session metadata"),
        OutputFieldSchema(
            path="total", type="integer", description="Observed live owned session count"
        ),
        OutputFieldSchema(
            path="next_cursor",
            type="string",
            nullable=True,
            description="Last shown display id; null at end",
        ),
        OutputFieldSchema(
            path="current_session_known",
            type="boolean",
            description="Trusted current-session identity availability",
        ),
        OutputFieldSchema(
            path="incomplete",
            type="boolean",
            description="Invalid or mismatched indexed metadata was omitted; total counts only observed valid owned rows",
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_device_sessions",
    semantic_keywords=["my connected devices", "my active sessions", "where am I signed in"],
    display=DisplayMetadata(emoji="📱", i18n_key="get_lia_device_sessions", category="tool"),
)

SESSION_REVOKE_MANIFEST = ToolManifest(
    name="revoke_lia_device_session_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to sign out one owned active session, selected by the opaque display id returned by get_lia_device_sessions_tool. Requires the live originating authenticated browser, which must remain the same at confirmation. No revocation during preparation and no cookie or authentication proof in arguments or results. Revoking the current session can interrupt the reply; detached jobs continue. A changed session identity requires a new preview; an expired target is an acknowledged no-op. This action signs out a session and does not remove its notification-device registration.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="One owned displayed session identity",
            schema=DeviceSessionRevokeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_device_sessions",
    semantic_keywords=["sign out a connected device", "revoke one of my active sessions"],
    display=DisplayMetadata(emoji="📱", i18n_key="revoke_lia_device_session", category="tool"),
)

OTHER_SESSIONS_REVOKE_MANIFEST = ToolManifest(
    name="revoke_lia_other_device_sessions_tool",
    agent="setting_agent",
    description="Prepare exact human confirmation to sign out all other owned sessions observed now. Requires a live originating authenticated browser, kept as the current session. Never accept credentials or authentication proof in chat. No revocation during preparation. After HITL the action waits for secure browser reauthentication and executes only the frozen selection; sessions opened later survive and expired targets are acknowledged no-ops. Incomplete or oversized indexes are refused. Lost completion acknowledgement must be observed, never automatically retried. Detached jobs and device notification registrations remain.",
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending exact confirmation and secure browser handoff",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_device_sessions",
    initiative_eligible=False,
    semantic_keywords=["sign out all other devices", "close all my other sessions"],
    display=DisplayMetadata(
        emoji="📱", i18n_key="revoke_lia_other_device_sessions", category="tool"
    ),
)
