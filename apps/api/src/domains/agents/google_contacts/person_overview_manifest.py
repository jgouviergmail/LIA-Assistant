"""Catalogue manifest for the person-360 tool (P3, ADR-141).

Registered through ``registry/program_manifests.py`` (frozen-loader budget).
Attached to contact_agent — person-centric home, cross-domain by construction.
"""

from datetime import UTC, datetime

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

get_person_overview_catalogue_manifest = ToolManifest(
    name="get_person_overview_tool",
    agent="contact_agent",
    description=(
        "Cross-domain 360° overview of ONE person: contact card, recent "
        "email exchanges, upcoming shared events, and relevant long-term "
        "memories — in a single call. Use for meeting/call preparation "
        "('prépare mon call avec Marie') or 'tell me everything about X'. "
        "Read-only; the overview is partial when a connector is unavailable."
    ),
    parameters=[
        ParameterSchema(
            name="person_name",
            type="string",
            required=True,
            description="Person name as the user says it (pre-resolved if aliased)",
            constraints=[
                ParameterConstraint(kind="min_length", value=2),
                ParameterConstraint(kind="max_length", value=120),
            ],
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="contact",
            type="object",
            description="Contact card: name, emails, phones, organizations",
        ),
        OutputFieldSchema(
            path="recent_emails",
            type="array",
            description="Last exchanges: subject, from, date, snippet",
        ),
        OutputFieldSchema(
            path="upcoming_events",
            type="array",
            description="Upcoming events mentioning the person",
        ),
        OutputFieldSchema(
            path="memories",
            type="array",
            description="Relevant long-term memories about the person",
        ),
        OutputFieldSchema(
            path="partial_failures",
            type="array",
            description="Sub-blocks that failed (overview is honest about gaps)",
        ),
    ],
    cost=CostProfile(
        est_tokens_in=80,
        est_tokens_out=500,
        est_cost_usd=0.0003,
        est_latency_ms=1500,
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        data_classification="SENSITIVE",
        hitl_required=False,
    ),
    semantic_keywords=[
        "prepare my meeting or call with a person",
        "everything you know about this contact",
        "person overview across emails events memories",
        "who is this person and our recent exchanges",
        "brief me before I talk to someone",
    ],
    reference_examples=[],
    display=DisplayMetadata(
        emoji="👤",
        i18n_key="get_person_overview",
        visible=True,
        category="tool",
    ),
    tool_category="search",
    version="1.0.0",
    updated_at=datetime.now(UTC),
)
