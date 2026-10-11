"""Source generated-image sharing is a mandatory confirmed native action."""

from src.domains.agents.application.operation_spec import ApplicationOperationSpec, OperationKind
from src.domains.agents.application.outcomes import ApplicationExecutionOutcome
from src.domains.agents.application.peer_image_schemas import PeerImageInput, PeerImagePatch
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)
from src.domains.feature_switches.registry import PlatformCapability

PEER_IMAGE_OPERATION = ApplicationOperationSpec(
    operation_id="peer_image.share",
    tool_name="share_lia_peer_image_tool",
    sections=("peers",),
    input_model=PeerImagePatch,
    output_model=ApplicationExecutionOutcome,
    kind=OperationKind.ACTION,
    required_capabilities=(PlatformCapability.PEERS,),
)
PEER_IMAGE_MANIFEST = ToolManifest(
    name=PEER_IMAGE_OPERATION.tool_name,
    agent="setting_agent",
    description="Prepare mandatory human confirmation to share one of MY live generated images with one accepted connection. Use actual opaque connection and owned attachment IDs; no guessing, uploaded files, external URLs or arbitrary account lookup. Preview names the exact recipient, image title and literal optional comment. A copy is saved in their gallery with its own expiry; delivery to chat is attempted after saving and can fail without undoing the copy. Existing source daily sender/pair quotas apply and no model is called by sharing. Preparation creates no copy. Changed recipient/pair/image metadata or file bytes require renewed approval. Fresh native/Peers/account/expiry checks precede acknowledged commit. One durable command executes once; unknown commit completion is never automatically retried. No administrator action.",
    parameters=[
        ParameterSchema(
            name="request",
            type="object",
            required=True,
            description="Accepted connection, owned generated image and optional literal comment",
            schema=PeerImageInput.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact image-share confirmation"
        )
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    binding_unit="lia_peers",
    tool_category="create",
    initiative_eligible=False,
    semantic_keywords=["share my generated image", "send image to my connection"],
    display=DisplayMetadata(emoji="🖼️", i18n_key="share_lia_peer_image", category="tool"),
)
