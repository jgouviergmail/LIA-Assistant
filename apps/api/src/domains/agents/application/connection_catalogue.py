"""Manifests for saved connection cards and exact local unlink confirmation."""

from src.domains.agents.application.connection_schemas import (
    ConnectorConnectionsRead,
    ConnectorUnlinkRequest,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

CONNECTOR_CONNECTIONS_READ_MANIFEST = ToolManifest(
    name="get_lia_connectors_tool",
    agent="setting_agent",
    description="Read this account's saved connection cards: id, service type, saved status, account email and timestamps. Follow next_cursor as after_id for all pages. Saved status is not live provider availability. Credentials, full service-specific settings and authorization are separate secure flows.",
    parameters=[
        ParameterSchema(
            name="query",
            type="object",
            required=False,
            description="Selected owned connection or bounded page",
            schema=ConnectorConnectionsRead.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="connectors", type="array", description="Owned saved connection cards"
        ),
        OutputFieldSchema(path="total", type="integer", description="Matching connection count"),
        OutputFieldSchema(
            path="next_cursor", type="string", description="Next page, null when complete"
        ),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_connections",
    semantic_keywords=[
        "my connected services",
        "my saved connections",
        "which account is connected",
    ],
    display=DisplayMetadata(emoji="🔌", i18n_key="get_lia_connectors", category="tool"),
)
CONNECTOR_UNLINK_MANIFEST = ToolManifest(
    name="disconnect_lia_connector_tool",
    agent="setting_agent",
    description="Prepare human confirmation to unlink one local service connection selected by its current id. No deletion before approval. Other services remain linked and provider-wide consent is retained. A changed connection requires a new preview; reconnect through secure UI to use the service again. This never resets credentials or revokes an external account globally.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Existing owned connection to unlink locally",
            schema=ConnectorUnlinkRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(path="draft", type="object", description="Pending exact confirmation")
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="delete",
    binding_unit="lia_connections",
    semantic_keywords=["disconnect my service", "unlink my connection locally"],
    display=DisplayMetadata(emoji="🔌", i18n_key="disconnect_lia_connector", category="tool"),
)
