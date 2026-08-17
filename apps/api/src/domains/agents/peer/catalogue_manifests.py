"""Catalogue manifests for Peers tools (peers program, Lot 6).

User-to-user connections from chat: relay a message assistant-to-assistant
(HITL draft, spec A3), list connections, and read what a connected peer
chose to share (calendar availability, task titles — spec A1). Internal
tools (no OAuth on the caller side — the peer's connectors are resolved
server-side under the execution-time share check).
"""

from datetime import UTC, datetime

from src.core.config import settings
from src.domains.agents.registry.catalogue import (
    AgentManifest,
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

PEER_AGENT_MANIFEST = AgentManifest(
    name="peer_agent",
    description=(
        "Agent specialized in connections with OTHER USERS of this LIA "
        "instance: relay a message to a connected user through their own "
        "assistant ('dis à Marie que…', 'demande à Paul comment il va'), "
        "list who the user is connected to, check a connected user's "
        "availability or shared tasks. Sending requires user confirmation "
        "(draft). NOT for the user's own contacts/emails (use contact/email)."
    ),
    tools=[
        "send_peer_message_tool",
        "list_peer_connections_tool",
        "get_peer_availability_tool",
        "get_peer_tasks_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
    display=DisplayMetadata(
        emoji="🤝",
        i18n_key="peer_agent",
        visible=True,
        category="agent",
    ),
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


send_peer_message_catalogue_manifest = ToolManifest(
    name="send_peer_message_tool",
    agent="peer_agent",
    description=(
        "Relays a message to a CONNECTED user of this instance: their own "
        "assistant will convey it in its own voice and language, naming the "
        "sender. Returns a draft the user must confirm — nothing is sent "
        "before confirmation. Use when the user asks to tell/ask something "
        "to a person they are connected with ('passe un message à…', 'dis "
        "à…', 'demande à…'). ALSO the way to REPLY to a relayed message: "
        "relays are stateless (no message_id/thread) — a reply is simply a "
        "new relayed message. recipient_name matching is accent- and "
        "case-insensitive. Keep `message` in the USER'S OWN LANGUAGE (never "
        "translate) and phrase it as ADDRESSED TO the recipient (direct "
        "address): 'demande à X comment il va' → message='comment vas-tu ?'. "
        "SELF-CONTAINED single step: recipient_name resolves among the "
        "user's CONNECTIONS on this instance — never add a contacts lookup "
        "step before it."
    ),
    parameters=[
        ParameterSchema(
            name="recipient_name",
            type="string",
            required=True,
            description="Full name of the connected user (exact name)",
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=255),
            ],
        ),
        ParameterSchema(
            name="message",
            type="string",
            required=True,
            description=(
                "The message to relay, in the user's own LANGUAGE (never "
                "translate), phrased as addressed TO the recipient (direct "
                "address: 'ask X how he is' → 'how are you?') — the "
                "recipient's assistant conveys its intent, never verbatim."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                # The bound the tool enforces (settings-driven, ADR-184: an
                # enforced bound must be published to whoever produces the
                # value) — never hardcode it here or the planner/validator
                # trust a stale limit after a .env change.
                ParameterConstraint(kind="max_length", value=settings.peers_message_max_chars),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the draft was created",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Draft confirmation message shown to the user",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=60,
        est_tokens_out=50,
        est_cost_usd=0.0001,
        est_latency_ms=150,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        # Draft-based (A3): the PEER_MESSAGE draft IS the confirmation —
        # hitl_required stays False (test_hitl_required_consistency doctrine).
        hitl_required=False,
    ),
    semantic_keywords=[
        "relay a message to a connected user",
        "tell another user something through their assistant",
        "ask a connected person a question for me",
        "send word to my contact on this platform",
        "pass a message along to someone I am connected with",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="💬",
        i18n_key="send_peer_message",
        visible=True,
        category="tool",
    ),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


list_peer_connections_catalogue_manifest = ToolManifest(
    name="list_peer_connections_tool",
    agent="peer_agent",
    description=(
        "Lists the user's accepted connections with other users of this "
        "instance: names, since when, what each side shares (calendar, "
        "tasks). Use to answer 'who am I connected to' and before relaying "
        "a message or reading shared data."
    ),
    parameters=[],
    outputs=[
        OutputFieldSchema(
            path="connections",
            type="array",
            description="Connections: name, since, i_share, they_share",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=30,
        est_tokens_out=100,
        est_cost_usd=0.0001,
        est_latency_ms=100,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "who am I connected with on this platform",
        "list my user connections and what they share",
        "show the people linked to my assistant",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="📇",
        i18n_key="list_peer_connections",
        visible=True,
        category="tool",
    ),
    tool_category="readonly",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


get_peer_availability_catalogue_manifest = ToolManifest(
    name="get_peer_availability_tool",
    agent="peer_agent",
    description=(
        "Reads a CONNECTED user's calendar availability, at the level THEY "
        "chose to share: busy slots only (free/busy), or slots with event "
        "titles. Use for 'est-ce que Marie est dispo demain ?'. Refuses when "
        "the peer does not share their calendar. SELF-CONTAINED single step: "
        "peer_name resolves against the user's connections — never add a "
        "contacts lookup or a calendar/event read alongside this tool."
    ),
    parameters=[
        ParameterSchema(
            name="peer_name",
            type="string",
            required=True,
            description="Full name of the connected user (exact name)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="busy_slots",
            type="array",
            description="Busy slots (start/end, titles only at level details)",
        ),
        OutputFieldSchema(
            path="peer_timezone",
            type="string",
            description=(
                "Peer's IANA timezone. Only for inter-step references — the "
                "returned summary is already in the ASKING user's timezone"
            ),
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40,
        est_tokens_out=150,
        est_cost_usd=0.0001,
        est_latency_ms=800,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "check a connected user's availability",
        "is my contact free tomorrow according to their calendar",
        "when is this connected person busy",
        "look at the shared calendar of a connection",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="🗓",
        i18n_key="get_peer_availability",
        visible=True,
        category="tool",
    ),
    tool_category="readonly",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


get_peer_tasks_catalogue_manifest = ToolManifest(
    name="get_peer_tasks_tool",
    agent="peer_agent",
    description=(
        "Reads a CONNECTED user's pending task titles, if they share their "
        "tasks. Titles only — never details. Refuses when the peer does not "
        "share their tasks. SELF-CONTAINED single step: peer_name resolves "
        "against the user's connections — never add a contacts or task-list "
        "lookup alongside this tool."
    ),
    parameters=[
        ParameterSchema(
            name="peer_name",
            type="string",
            required=True,
            description="Full name of the connected user (exact name)",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="task_titles",
            type="array",
            description="Pending task titles shared by the peer",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=40,
        est_tokens_out=100,
        est_cost_usd=0.0001,
        est_latency_ms=600,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="CONFIDENTIAL",
        hitl_required=False,
    ),
    semantic_keywords=[
        "what tasks does my connected contact have",
        "read the shared todo list of a connection",
        "check a connected user's pending tasks",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="✅",
        i18n_key="get_peer_tasks",
        visible=True,
        category="tool",
    ),
    tool_category="readonly",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
