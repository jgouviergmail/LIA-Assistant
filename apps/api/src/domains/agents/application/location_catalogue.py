"""Saved location contracts separate paid address resolution from confirmed writes."""

from src.domains.agents.application.location_schemas import LocationChangeRequest, LocationRead
from src.domains.agents.places.catalogue_manifests import get_places_catalogue_manifest
from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

_READ = LocationRead.model_json_schema()
LOCATIONS_READ_MANIFEST = ToolManifest(
    name="get_lia_locations_tool",
    agent="setting_agent",
    description="Read the current user's saved home address and saved last-known position with its timestamp. These are server-saved values, not the current browser position. A failed or corrupted read is unavailable, not empty.",
    parameters=[
        ParameterSchema(
            name="fields",
            type="array",
            required=False,
            description="Distinct saved location selectors",
            schema={**_READ["properties"]["fields"], "$defs": _READ.get("$defs", {})},
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="preferences", type="object", description="Current saved account locations"
        ),
        OutputFieldSchema(path="total", type="integer", description="Exact returned field count"),
    ],
    cost=CostProfile(),
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="read",
    tool_category="readonly",
    binding_unit="lia_locations",
    semantic_keywords=[
        "what home address is saved",
        "what position is remembered",
        "saved location settings",
    ],
    reference_examples=["preferences.values.home_location"],
    display=DisplayMetadata(emoji="📍", i18n_key="get_lia_locations", category="tool"),
)
HOME_LOCATION_UPDATE_MANIFEST = ToolManifest(
    name="update_lia_home_location_tool",
    agent="setting_agent",
    description="Prepare human confirmation to set or clear the current user's home address. Use only an address supplied by the person, never invent coordinates. Set resolves that address through the existing paid Google Places path under current quotas and enabled connector, then freezes the result for confirmation; it never geocodes again on approval. Clear also removes the saved last-known position and needs no connector. Concurrent location changes require a new preview.",
    parameters=[
        ParameterSchema(
            name="change",
            type="object",
            required=True,
            description="Set with address or clear with no address",
            schema=LocationChangeRequest.model_json_schema(),
        )
    ],
    outputs=[
        OutputFieldSchema(
            path="draft", type="object", description="Pending exact location confirmation"
        )
    ],
    cost=get_places_catalogue_manifest.cost,
    permissions=PermissionProfile(data_classification="CONFIDENTIAL"),
    mutation_policy="draft",
    tool_category="update",
    binding_unit="lia_locations",
    semantic_keywords=["change my home address", "clear my saved location", "set where I live"],
    display=DisplayMetadata(emoji="📍", i18n_key="update_lia_home_location", category="tool"),
)
