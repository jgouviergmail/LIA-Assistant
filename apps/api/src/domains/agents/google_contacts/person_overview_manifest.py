"""Catalogue manifest for the person-360 tool (P3, ADR-141).

The tool was rebuilt on the Relations services (2026-08-01): it reads the CRM
half as well as the connectors, queries mail/calendar by ADDRESS, and applies
the scope the user selected on the relationship card.

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
        "Cross-domain 360° overview of ONE person, in a single call: open "
        "commitments, recent calls, messages relayed through LIA, long-term "
        "memories, contact card, mail exchanged and meetings shared. Use for "
        "meeting/call preparation ('prépare mon call avec Marie', 'point 360° "
        "sur X') or 'tell me everything about X'. SELF-CONTAINED: never add a "
        "contacts, email or calendar lookup alongside it — this tool already "
        "queries them, by ADDRESS rather than by name. The user's own scope "
        "selection (which sections, which directions, how many items) is read "
        "server-side and applied; it is not a parameter to guess. Read-only; "
        "the overview states what it could not read."
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
            path="is_peer",
            type="boolean",
            description="Whether this person is a CONNECTED user of this LIA instance.",
        ),
        OutputFieldSchema(
            path="peer_connection",
            type="object",
            description=(
                "The LIA connection behind this relationship, when there is "
                "one: `connected_since` and what each side shares "
                "(`shared_by_me`, `shared_with_me`, as `domain:level`). Absent "
                "when the two are not connected."
            ),
        ),
        OutputFieldSchema(
            path="contact",
            type="object",
            description=(
                "Address-book entry, in full: name, nickname, organization, "
                "occupation, birthday, biography, emails, phones, postal "
                "addresses, family/professional relations, links, important "
                "dates, messaging handles. A block the address book does not "
                "hold is ABSENT from the object — never report it as empty."
            ),
        ),
        OutputFieldSchema(
            path="open_commitments",
            type="array",
            description=(
                "Open loops with this person: subject, direction, days open, "
                "and `due_hint` (the deadline) when one was captured — absent "
                "means none was, never assume a date. A PAGE: "
                "`open_commitments_total` holds the exact number that exist, "
                "so never count the rows to answer 'how many'."
            ),
        ),
        OutputFieldSchema(
            path="open_commitments_total",
            type="integer",
            description="Exact number of open commitments (database aggregate).",
        ),
        OutputFieldSchema(
            path="recent_calls",
            type="array",
            description=(
                "Past calls: objective, outcome, summary and the instant "
                "they happened. A page — see the total."
            ),
        ),
        OutputFieldSchema(
            path="recent_calls_total",
            type="integer",
            description="Exact number of calls with this person (database aggregate).",
        ),
        OutputFieldSchema(
            path="relayed_messages",
            type="array",
            description="Messages relayed through LIA: direction, text, instant",
        ),
        OutputFieldSchema(
            path="relayed_messages_total",
            type="integer",
            description=(
                "Exact number of relayed messages — present ONLY when both "
                "directions were kept. Absent means the list was narrowed and "
                "no exact count describes it: do not state one."
            ),
        ),
        OutputFieldSchema(
            path="emails",
            type="array",
            description="Mail exchanged, by address: direction, subject, instant",
        ),
        OutputFieldSchema(
            path="events",
            type="array",
            description="Shared meetings: summary, role, start and end instants",
        ),
        OutputFieldSchema(
            path="memories",
            type="array",
            description="Relevant long-term memories about the person",
        ),
        OutputFieldSchema(
            path="unavailable",
            type="array",
            description=(
                "Sections the user asked for that could NOT be read (no "
                "connector, no address, provider error, recall unavailable). "
                "Those sections carry NO key at all in the payload: a missing "
                "block means 'not looked at', an empty list means 'looked and "
                "found nothing'. Say which one it was."
            ),
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
    # Reachable from `peer` too (ADR-191). The analyzer prompt sends every
    # question about a CONNECTED USER to the `peer` domain — "their data is
    # reachable ONLY through the peer domain" — while this tool lives in
    # `contact`. Catalogue filtering drops out-of-domain manifests before
    # reading any score, so without this the 360° on a peer was structurally
    # impossible: measured absent from the planner catalogue at score 0.853,
    # the highest of the whole catalogue.
    serves_domains=["peer"],
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
