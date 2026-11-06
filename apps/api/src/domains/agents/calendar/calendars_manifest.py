"""Catalogue manifest of the tool listing calendars, out of ``catalogue_manifests.py``.

Beside it, at its size cap (ADR-369, lot 10).
"""

from src.core.constants import GOOGLE_CALENDAR_SCOPES
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_list_cal_desc = "**Tool: list_calendars_tool** - List available calendars to find 'calendar_id'."

list_calendars_catalogue_manifest = ToolManifest(
    name="list_calendars_tool",
    agent="event_agent",
    description=_list_cal_desc,
    # Discriminant phrases - Calendar list operations
    semantic_keywords=[
        # List available calendars
        "show all my available calendars",
        "list calendars I have access to",
        "which calendars are in my account",
        "display calendar names and IDs",
        # Calendar selection
        "find calendar ID for specific name",
        "show shared calendars I can view",
    ],
    parameters=[
        ParameterSchema(
            name="show_hidden", type="boolean", required=False, description="Include hidden"
        ),
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description="Max (def 100)",
            constraints=[ParameterConstraint(kind="maximum", value=250)],
        ),
    ],
    outputs=[
        OutputFieldSchema(path="calendars", type="array", description="List"),
        OutputFieldSchema(
            path="calendars[].id",
            type="string",
            description="Calendar ID",
            semantic_type="calendar_id",
        ),
        OutputFieldSchema(
            path="calendars[].summary", type="string", description="Name", semantic_type="Text"
        ),
        OutputFieldSchema(
            path="calendars[].accessRole",
            type="string",
            description="Access",
            semantic_type="access_role",
        ),
        OutputFieldSchema(path="calendars[].primary", type="boolean", description="Is primary"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=300, est_cost_usd=0.001, est_latency_ms=300),
    permissions=PermissionProfile(
        required_scopes=GOOGLE_CALENDAR_SCOPES,
        hitl_required=False,
        data_classification="CONFIDENTIAL",
    ),
    max_iterations=1,
    supports_dry_run=False,
    reference_fields=["id", "summary", "primary"],
    reference_examples=["calendars[0].id", "calendars[*].summary"],
    version="1.1.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📚", i18n_key="list_calendars", visible=True, category="tool"),
    initiative_eligible=False,  # Structural tool, not useful for proactive enrichment
)
