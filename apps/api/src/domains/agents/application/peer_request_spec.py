"""Crossing invitations accept the pair, an outcome stated before approval."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_request_schemas import PeerRequestInput, PeerRequestPatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_REQUEST_OPERATION = ApplicationOperationSpec(
    operation_id="peer_connection.request",
    tool_name="request_lia_peer_connection_tool",
    sections=("peers",),
    input_model=PeerRequestPatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_REQUEST_MANIFEST = ToolManifest(
    name=PEER_REQUEST_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to request a connection with an explicitly selected discoverable peer_id and optional literal note. Use search_lia_peer_directory_tool to resolve exact candidates and ask the user when ambiguous. Source active/discovery/mutual-block/cooldown guards apply. Preparation performs no request or notification. The preview pins target displayed name, masked address hint and pair state: a crossing incoming request means ACCEPTING the connection; an existing outgoing pending request stays unchanged, including its old note. New/revived pending requests use the approved note. Changed identity, consent, block or pair state requires a new proposal. Execution shares canonical source account locks, conditional claims, exact postconditions and acknowledged commit; unknown completion is never repeated automatically. Source lifecycle notifications run only after acknowledged commit, best effort. No share grant, relay message, administrative activation or paid synthesis.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Selected discoverable peer ID and optional source note",
            schema=PeerRequestInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft",
            type="object",
            description="Pending exact invitation or crossing acceptance confirmation",
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="create",
    initiative_eligible=False,
    semantic_keywords=["invite a connection", "request a peer connection"],
    display=DisplayMetadata(emoji="🤝", i18n_key="request_lia_peer_connection", category="tool"),
)
