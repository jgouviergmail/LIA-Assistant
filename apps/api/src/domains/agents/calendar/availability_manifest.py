"""Catalogue manifest for the find-availability tool (lot B, 2026-08).

Split from calendar/catalogue_manifests.py (file-size ratchet): one cohesive
manifest module, re-exported by the family module for the loader.
"""

from src.core.constants import (
    AVAILABILITY_DURATION_MAX_MINUTES,
    AVAILABILITY_DURATION_MIN_MINUTES,
    GOOGLE_CALENDAR_SCOPES,
)
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

find_availability_catalogue_manifest = ToolManifest(
    name="find_availability_tool",
    mutation_policy="read",
    # ADR-256: computes free slots, writes nothing.
    tool_category="readonly",
    agent="event_agent",
    description=(
        "**Tool: find_availability_tool** - Find FREE calendar slots in a time "
        "window ('find me a 30-min slot Thursday', 'when am I free next week?'). "
        "Reads busy ranges only (never event details) via the calendar freeBusy "
        "endpoint (Google) or a minimized start/end projection (other providers). "
        "Returns free gaps of at least `duration_minutes`, clamped to working "
        "hours unless `working_hours_only=false` (evenings/weekends requests). "
        "Use get_events_tool instead when the user wants to SEE their events."
    ),
    semantic_keywords=[
        "find a free slot in my calendar",
        "when am I available this week",
        "find time for a meeting of thirty minutes",
        "am I free thursday afternoon",
        "next available time slot in agenda",
        "propose meeting times when I am free",
    ],
    parameters=[
        ParameterSchema(
            name="start_datetime",
            type="string",
            required=True,
            description=(
                "Window start in LOCAL time (user timezone), ISO WITHOUT offset "
                "e.g. '2026-08-27T00:00:00'"
            ),
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="end_datetime",
            type="string",
            required=True,
            description=(
                "Window end in LOCAL time (user timezone), ISO WITHOUT offset "
                "e.g. '2026-08-28T00:00:00'"
            ),
            semantic_type="datetime",
        ),
        ParameterSchema(
            name="duration_minutes",
            type="integer",
            required=False,
            description="Minimum slot duration in minutes (default 30)",
            constraints=[
                ParameterConstraint(kind="minimum", value=AVAILABILITY_DURATION_MIN_MINUTES),
                ParameterConstraint(kind="maximum", value=AVAILABILITY_DURATION_MAX_MINUTES),
            ],
        ),
        ParameterSchema(
            name="working_hours_only",
            type="boolean",
            required=False,
            description=(
                "Keep only working-hours slots (default true). Set false for "
                "explicitly off-hours requests (evenings, weekends)."
            ),
        ),
    ],
    outputs=[
        OutputFieldSchema(path="slots", type="array", description="Free slots"),
        OutputFieldSchema(
            path="slots[].start",
            type="string",
            description="Slot start (ISO)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            path="slots[].end",
            type="string",
            description="Slot end (ISO)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(path="total", type="integer", description="Exact slot count"),
        OutputFieldSchema(path="busy_count", type="integer", description="Busy blocks considered"),
    ],
    cost=CostProfile(est_tokens_in=120, est_tokens_out=250, est_cost_usd=0.003, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="events",
    reference_examples=["slots[0].start", "slots[0].end", "total"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🕐", i18n_key="find_availability", visible=True, category="tool"
    ),
)
