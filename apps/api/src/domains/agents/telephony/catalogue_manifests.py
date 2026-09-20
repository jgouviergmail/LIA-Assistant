"""Catalogue manifests for the Telephony agent (agentic outbound calls).

Per-user feature: gated by ``TELEPHONY_ENABLED``. Registration is performed by
``catalogue_loader.initialize_catalogue`` behind the feature flag.
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

# =============================================================================
# Agent Manifest: telephony_agent
# =============================================================================

TELEPHONY_AGENT_MANIFEST = AgentManifest(
    name="telephony_agent",
    description=(
        "Agent specialized in phone calls. Two mandates: place_phone_call_tool phones a "
        "THIRD PARTY on the user's behalf to pursue a goal (e.g. check availability) — "
        "confirmed by the user (HITL draft) before dialing, read-only during the call, "
        "free/busy shared but never meeting details — and returns an asynchronous "
        "summary; call_me_tool phones the USER THEMSELVES on their verified number, "
        "NOW and with no confirmation, to talk things over — what they ask for reaches "
        "their chat, during the call or relayed as their own message once it ends, as "
        "they chose in the settings. A call asked for later or on a schedule is a "
        "reminder or a routine whose instruction is 'call me'."
    ),
    tools=[
        "place_phone_call_tool",
        "call_me_tool",
    ],
    max_parallel_runs=1,
    default_timeout_ms=settings.default_tool_timeout_ms,
    prompt_version="v1",
    owner_team="Team AI",
    version="1.0.0",
    updated_at=datetime.now(UTC),
    display=DisplayMetadata(
        emoji="📞",
        i18n_key="telephony_agent",
        visible=True,
        category="agent",
    ),
)


# =============================================================================
# Tool Manifest: place_phone_call_tool
# =============================================================================

place_phone_call_catalogue_manifest = ToolManifest(
    name="place_phone_call_tool",
    mutation_policy="draft",
    agent="telephony_agent",
    description=(
        "Places an outbound phone call on the user's behalf to pursue a stated objective "
        "(e.g. 'ask if Marie is free for dinner Tuesday'). Resolves the callee to a phone "
        "number ITSELF (contact name or raw number — no separate contact-search step is "
        "needed) and returns a draft that the user MUST confirm before LIA dials. The "
        "summary of the call comes back asynchronously."
    ),
    parameters=[
        ParameterSchema(
            name="contact",
            type="string",
            required=True,
            semantic_type="person_name",
            description=(
                "Who to call: a contact name or a raw phone number. Pass the name "
                "EXACTLY as known in the address book ('Marie Dupont') — never append "
                "annotations or relationship notes ('(my wife)'), they break the "
                "contact lookup."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
            ],
        ),
        ParameterSchema(
            name="objective",
            type="string",
            required=True,
            description=(
                "What LIA must accomplish on the call, in the user's words "
                "(e.g. 'ask if she is free for dinner on Tuesday evening'). "
                "Express every date ABSOLUTELY (weekday + date: 'Saturday July 18'), "
                "never relatively ('tomorrow') — the voice agent speaks this to the "
                "callee and a relative date is ambiguous on the phone."
            ),
            constraints=[
                ParameterConstraint(kind="min_length", value=1),
                ParameterConstraint(kind="max_length", value=500),
            ],
        ),
        ParameterSchema(
            name="date_window",
            type="string",
            required=False,
            description=(
                "Optional free-text availability window to pre-fetch the user's free/busy "
                "for (e.g. 'this week', 'Tuesday afternoon')."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the draft was created (call not yet placed).",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Confirmation / clarification message for the user.",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=60,
        est_tokens_out=80,
        est_cost_usd=0.0001,
        est_latency_ms=300,
    ),
    permissions=PermissionProfile(
        required_scopes=[],  # Per-user connector (ElevenLabs API key), not OAuth scopes
        data_classification="SENSITIVE",
        # Draft-based: place_phone_call_tool returns requires_confirmation=True
        # (phone_call draft) → draft_critique, like create_event/cancel_reminder.
        # hitl_required stays False (see test_hitl_required_consistency.py): the flag
        # only drives ReAct's pre-execution interrupt, redundant AND unrendered for a
        # draft tool (silent hang).
        hitl_required=False,
    ),
    semantic_keywords=[
        "call someone on the phone on my behalf",
        "phone a contact to ask a question for me",
        "give someone a call and get back to me",
        "ring my contact to check their availability",
        "make a phone call to ask if they are free",
    ],
    reference_examples=[
        "success",
        "message",
    ],
    display=DisplayMetadata(
        emoji="📞",
        i18n_key="place_phone_call",
        visible=True,
        category="tool",
    ),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


# =============================================================================
# Tool Manifest: call_me_tool (phone-as-a-channel, lot 3)
# =============================================================================

call_me_catalogue_manifest = ToolManifest(
    name="call_me_tool",
    # No confirmation card, by construction: the person who would confirm is
    # the person who picks up, and the number was verified by a call they
    # answered and a code they typed (lots 1-2). ``reversible`` is also what
    # lets a routine (« call me every morning ») run it unattended (ADR-276).
    mutation_policy="reversible",
    mutation_policy_reason=(
        "The callee is the account holder themselves, on a number they declared and "
        "verified by answering a call and typing the spoken code: the person who would "
        "confirm is the person who picks up, and hanging up undoes it."
    ),
    agent="telephony_agent",
    description=(
        "Phones the USER on their own verified number NOW so LIA and the user can talk "
        "something over by voice — a catch-up, a plan, a list to take down. Use it when "
        "the user asks to be CALLED at once ('call me', 'phone me', 'ring me'), never to "
        "reach a third party (that is place_phone_call_tool), and never for a call asked "
        "for LATER or on a SCHEDULE ('call me in an hour', 'every morning at eight'): "
        "that is a reminder or a routine whose instruction is 'call me'. Needs no "
        "confirmation. What the user asks for on the call reaches their chat: during the "
        "call (Live) or relayed as their own message once it ends (Live direct), as they "
        "chose in the settings — never decided here."
    ),
    parameters=[
        ParameterSchema(
            name="objective",
            type="string",
            required=False,
            description=(
                "What the call is about, in the user's words (e.g. 'go over tomorrow's "
                "meetings', 'take my shopping list'). Express every date ABSOLUTELY "
                "(weekday + date), never relatively. Empty means a catch-up call."
            ),
            constraints=[
                ParameterConstraint(kind="max_length", value=500),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="success",
            type="boolean",
            description="Whether the call is ringing.",
        ),
        OutputFieldSchema(
            path="message",
            type="string",
            description="Status message for the user (ringing, or why not).",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=60,
        est_tokens_out=60,
        est_cost_usd=0.0001,
        est_latency_ms=800,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="SENSITIVE",
        hitl_required=False,
    ),
    semantic_keywords=[
        "call me on my phone",
        "phone me so we can talk",
        "ring me to go over my day",
        "give me a call to take my list",
        "call me every morning",
    ],
    reference_examples=[
        "success",
        "message",
    ],
    display=DisplayMetadata(
        emoji="📲",
        i18n_key="call_me",
        visible=True,
        category="tool",
    ),
    tool_category="create",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)


__all__ = [
    "TELEPHONY_AGENT_MANIFEST",
    "call_me_catalogue_manifest",
    "place_phone_call_catalogue_manifest",
]
