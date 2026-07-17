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
        "Agent specialized in placing outbound phone calls on the user's behalf. "
        "Calls a person to pursue a goal (e.g. check availability), then returns an "
        "asynchronous summary. Every call is confirmed by the user (HITL draft) before "
        "dialing. Read-only during the call: it may share free/busy availability only, "
        "never meeting details."
    ),
    tools=[
        "place_phone_call_tool",
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


__all__ = [
    "TELEPHONY_AGENT_MANIFEST",
    "place_phone_call_catalogue_manifest",
]
