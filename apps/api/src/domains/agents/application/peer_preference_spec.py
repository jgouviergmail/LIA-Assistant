"""Peer discovery and address visibility are distinct confirmed consents."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_preference_schemas import PeerPreferencePatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_PREFERENCE_OPERATION = ApplicationOperationSpec(
    operation_id="peer_preferences.update",
    tool_name="update_lia_peer_settings_tool",
    sections=("peers",),
    input_model=PeerPreferencePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_PREFERENCE_MANIFEST = ToolManifest(
    name=PEER_PREFERENCE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory exact confirmation to change only explicitly selected Connections settings consents on the current account. discovery_enabled permits exact discovery searches to find the account; email_visible permits accepted connections to see its real email address. These are independent consents, neither implies the other. Read existing preferences through get_lia_peer_settings_tool and preserve omitted fields. No invitations, acceptance, messages, shares, blocks or notifications. Preparation writes nothing. Execution rechecks fresh account/native/Peers/deadline authority, locks the source account row and compares exactly the human-approved selected values; stale state requires a new proposal. Source setters are reused and commit acknowledgement is explicit; unknown completion never promises success. New source consent fields require reviewed mapping.",
    parameters=[
        ParameterSchema(
            name="patch",
            type="object",
            required=True,
            description="Sparse explicit discovery_enabled and/or email_visible booleans",
            schema=PeerPreferencePatch.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact consent confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_peers",
    initiative_eligible=False,
    semantic_keywords=["change discoverability", "show my email to accepted connections"],
    display=DisplayMetadata(emoji="🤝", i18n_key="update_lia_peer_settings", category="tool"),
)
