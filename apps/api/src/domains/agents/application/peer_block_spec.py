"""Silent source blocks and non-restoring unblock actions require exact human consent."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_block_schemas import PeerBlockInput, PeerBlockPatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_BLOCK_OPERATION = ApplicationOperationSpec(
    operation_id="peer_block.update",
    tool_name="update_lia_peer_block_tool",
    sections=("peers",),
    input_model=PeerBlockPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_BLOCK_MANIFEST = ToolManifest(
    name=PEER_BLOCK_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to block or unblock a known Connections participant or a user already on MY block list. Use get_lia_peer_settings_tool requests/connections/blocks to select the actual opaque peer ID. No arbitrary account-directory lookup. blocked=true places MY directional block and silently severs any pending/accepted pair plus both share directions; for an accepted pair the existing source Workboard release is attempted best effort. No private ticket data or invented success counts. blocked=false lifts MY block only: it never restores a connection, shares or work assignment, and never lifts the other person's block. The selected pair/shares/own block and public identity are privately compared under locks; changed source state requires renewed approval. Current account/native/Peers/deadline checks surround the source verb and persisted postconditions before acknowledged commit. No notification, relay message, account deletion or administrator action; same state without a live pair to sever is an acknowledged no-op. Unknown completion never automatically retries.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Known peer ID and explicit blocked boolean",
            schema=PeerBlockInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact directional block confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="update",
    initiative_eligible=False,
    semantic_keywords=["block my connection", "unblock this peer"],
    display=DisplayMetadata(emoji="🛡️", i18n_key="update_lia_peer_block", category="tool"),
)
