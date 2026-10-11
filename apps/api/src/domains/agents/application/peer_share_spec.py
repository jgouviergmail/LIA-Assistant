"""Explicit independent share changes require exact human approval."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_share_schemas import PeerShareInput, PeerSharePatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_SHARE_OPERATION = ApplicationOperationSpec(
    operation_id="peer_share.update",
    tool_name="update_lia_peer_share_tool",
    sections=("peers",),
    input_model=PeerSharePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_SHARE_MANIFEST = ToolManifest(
    name=PEER_SHARE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to change ONE current-account read-only data share on an explicitly selected accepted connection. Use get_lia_peer_settings_tool connections for source identity and both share directions. domain calendar permits availability or details; task permits titles; explicit null revokes that domain. Only MY share changes; the peer's shares and other domains remain independent. Preparation sends no data and writes nothing. Current pair/identity and selected own-domain share are privately compared under source locks; changed selected state requires new approval. Execution uses the source setter, verifies persisted granularity and acknowledged commit. Same level is a no-op. No provider fetch, relay message, notification, connection acceptance or administrative action. A share permits future authorized reads, never provider writes; unknown completion is not automatically retried.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Connection ID, domain and explicit target level or null",
            schema=PeerShareInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact own-share consent"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="update",
    initiative_eligible=False,
    semantic_keywords=["share my calendar availability", "revoke my task sharing"],
    display=DisplayMetadata(emoji="🤝", i18n_key="update_lia_peer_share", category="tool"),
)
