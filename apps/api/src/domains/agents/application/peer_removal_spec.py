"""Severance is an explicit confirmed relationship action with source-owned consequences."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_removal_schemas import PeerRemovalInput, PeerRemovalPatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_REMOVAL_OPERATION = ApplicationOperationSpec(
    operation_id="peer_connection.remove",
    tool_name="remove_lia_peer_connection_tool",
    sections=("peers",),
    input_model=PeerRemovalPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_REMOVAL_MANIFEST = ToolManifest(
    name=PEER_REMOVAL_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to REMOVE one explicitly selected accepted connection on the current account. Read actual identity and both sharing directions through get_lia_peer_settings_tool connections. Preview pins the pair and both directions of shares: removal revokes all of them and attempts the source Workboard return-to-owner policy for work the pair shares at execution. No private ticket content or invented counts. The source release adapter is best effort: severance can succeed if that attempt fails; never promise every ticket returned from an unknown count. Pending requests cannot be cancelled by this operation. Source pair/shares changed since approval require a new proposal. Execution rechecks fresh account/native/Peers/deadline authority, source conditional removal and persisted absence of shares before acknowledged commit. Lifecycle notifications to both sides are attempted after saving. No block, message, account deletion or administrator action. Unknown completion is not automatically retried.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Explicit accepted connection ID to remove",
            schema=PeerRemovalInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact connection-removal confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="delete",
    initiative_eligible=False,
    semantic_keywords=["remove my connection", "disconnect this peer"],
    display=DisplayMetadata(emoji="🤝", i18n_key="remove_lia_peer_connection", category="tool"),
)
