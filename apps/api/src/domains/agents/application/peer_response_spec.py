"""Incoming accept/refuse decisions reuse source state and mandatory exact approval."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_response_schemas import (
    PeerResponseInput,
    PeerResponsePatch,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_RESPONSE_OPERATION = ApplicationOperationSpec(
    operation_id="peer_connection.respond",
    tool_name="respond_lia_peer_request_tool",
    sections=("peers",),
    input_model=PeerResponsePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_RESPONSE_MANIFEST = ToolManifest(
    name=PEER_RESPONSE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact human confirmation to accept or decline an explicitly selected INCOMING pending connection request on the current account. Use get_lia_peer_settings_tool requests to read the actual source card and disambiguate. Only its addressee may respond; an outgoing request cannot be accepted or declined by its sender. The preview pins requester name/masked hint, incoming literal note and accept/decline outcome, with private complete pair-state comparison. Preparation writes nothing and sends no notice. Execution rechecks native/account/Peers/deadline authority, current participation and incoming pending direction, then uses the source conditional response and verifies the actual pair status before acknowledged commit. A changed note or pair needs renewed approval. Source lifecycle notices follow acknowledged commit, best effort; unknown completion never retries automatically. Accepting grants a connection, not calendar/task sharing, and sends no relay message. No administrative account activation or paid synthesis.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Incoming connection ID and explicit accept boolean",
            schema=PeerResponseInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact incoming response confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="update",
    initiative_eligible=False,
    semantic_keywords=["accept incoming connection", "decline a peer invitation"],
    display=DisplayMetadata(emoji="🤝", i18n_key="respond_lia_peer_request", category="tool"),
)
