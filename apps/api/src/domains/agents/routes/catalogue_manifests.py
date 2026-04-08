"""
Catalogue manifests for Google Routes tools.

Provides directions, travel times, and route optimization capabilities.
Uses global API key (GOOGLE_API_KEY) - no per-user OAuth required.

Features:
- Route computation with traffic awareness
- Multiple travel modes (car, walk, bike, transit, motorcycle)
- Route modifiers (avoid tolls, highways, ferries)
- Route matrix for multi-point optimization
- Auto-resolution of origin from browser geolocation or home address
- HITL conditional triggering for significant routes (>20km)
"""

from src.domains.agents.registry.catalogue import (
    CostProfile,
    DisplayMetadata,
    OutputFieldSchema,
    ParameterConstraint,
    ParameterSchema,
    PermissionProfile,
    ToolManifest,
)

# ============================================================================
# 1. GET ROUTE (Directions)
# ============================================================================
_get_route_desc = (
    "**Tool: get_route_tool** - Get directions and travel time between two locations.\n"
    "\n"
    "**MODES**:\n"
    "- DRIVE - Default, traffic-aware, car\n"
    "- WALK - Walking directions, feet, foot\n"
    "- BICYCLE - Cycling directions\n"
    "- TRANSIT - Public transportation, subway\n"
    "- TWO_WHEELER - Motorcycle directions, scooter\n"
    "\n"
    "**ORIGIN AUTO-RESOLUTION**:\n"
    "If origin is not specified or 'auto', resolved from:\n"
    "1. Browser geolocation (current position)\n"
    "2. User's home address (if configured)\n"
    "\n"
    "**ROUTE MODIFIERS**:\n"
    "- avoid_tolls: Skip toll roads\n"
    "- avoid_highways: Skip highways\n"
    "- avoid_ferries: Skip ferries\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'How to get to Lyon?' → get_route_tool(destination='Lyon')\n"
    "- 'Paris to Marseille by train' → get_route_tool(origin='Paris', destination='Marseille', travel_mode='TRANSIT')\n"
    "- 'Go to work avoiding tolls' → get_route_tool(destination='work', avoid_tolls=True)\n"
    "- 'Travel time to Nice' → get_route_tool(destination='Nice')\n"
    "\n"
    "**RETURNS**: Distance, duration, traffic conditions, turn-by-turn steps, polyline for map, Google Maps link."
)

get_route_catalogue_manifest = ToolManifest(
    name="get_route_tool",
    agent="route_agent",
    description=_get_route_desc,
    # Discriminant phrases - Route and direction queries
    semantic_keywords=[
        # Direction requests (English)
        "provide the route to address",
        "search the route",
        "search the itinerary",
        "search the direction",
        "provide the itinerary",
        "directions to destination address",
        "how to get from here to there",
        "route to location by car",
        "direction to location by subway",
        "travel time and distance to place",
        "navigate to address with GPS",
        # Transport modes
        "driving directions by car automobile",
        "walking route on foot pedestrian",
        "cycling path bicycle bike",
        "public transit bus metro train subway",
        # Route preferences
        "avoid toll roads no tolls",
        "avoid highways no motorway",
        "fastest route quickest path",
        "shortest distance route",
        # Traffic awareness
        "traffic conditions on route",
        "travel time with current traffic",
        "best time to leave depart",
    ],
    parameters=[
        ParameterSchema(
            name="destination",
            type="string",
            required=True,
            description="Physical address, place name, or coordinates. MUST be an address, NOT a person's name. For directions to a person, first get their address from contacts.",
            semantic_type="physical_address",  # Tells LLM: needs address, not person name
        ),
        ParameterSchema(
            name="origin",
            type="string",
            required=False,
            description="Starting point (physical address or coordinates). If empty or 'auto', uses current location or home. Default: auto.",
            semantic_type="physical_address",
        ),
        ParameterSchema(
            name="travel_mode",
            type="string",
            required=False,
            description="Travel mode: DRIVE, WALK, BICYCLE, TRANSIT, TWO_WHEELER. Default: DRIVE.",
        ),
        ParameterSchema(
            name="avoid_tolls",
            type="boolean",
            required=False,
            description="Avoid toll roads. Default: False.",
        ),
        ParameterSchema(
            name="avoid_highways",
            type="boolean",
            required=False,
            description="Avoid highways. Default: False.",
        ),
        ParameterSchema(
            name="avoid_ferries",
            type="boolean",
            required=False,
            description="Avoid ferries. Default: False.",
        ),
        ParameterSchema(
            name="departure_time",
            type="string",
            required=False,
            description=(
                "Departure time in ISO 8601 format for traffic prediction. "
                "Example: '2025-01-15T08:00:00Z'. Mutually exclusive with arrival_time."
            ),
        ),
        ParameterSchema(
            name="arrival_time",
            type="string",
            required=False,
            description=(
                "Target arrival time in ISO 8601 format (when you need to BE THERE). "
                "For routes to CALENDAR EVENTS, use the event's start_datetime. "
                "The system calculates suggested departure time. "
                "Mutually exclusive with departure_time."
            ),
            semantic_type="event_start_datetime",
        ),
        ParameterSchema(
            name="waypoints",
            type="array",
            required=False,
            description="Intermediate stops (max 25). Example: ['Dijon', 'Mâcon'].",
            constraints=[ParameterConstraint(kind="maximum", value=25)],
        ),
        ParameterSchema(
            name="optimize_waypoints",
            type="boolean",
            required=False,
            description="Reorder waypoints for optimal route. Default: False.",
        ),
    ],
    outputs=[
        OutputFieldSchema(path="route", type="object", description="Route information"),
        OutputFieldSchema(path="route.origin", type="string", description="Origin address"),
        OutputFieldSchema(
            path="route.destination", type="string", description="Destination address"
        ),
        OutputFieldSchema(path="route.travel_mode", type="string", description="Travel mode used"),
        OutputFieldSchema(
            path="route.distance_km", type="number", description="Distance in kilometers"
        ),
        OutputFieldSchema(
            path="route.duration_minutes", type="integer", description="Duration in minutes"
        ),
        OutputFieldSchema(
            path="route.duration_formatted",
            type="string",
            description="Human-readable duration (e.g., '2h 30min')",
        ),
        OutputFieldSchema(
            path="route.duration_in_traffic_minutes",
            type="integer",
            nullable=True,
            description="Duration with traffic",
        ),
        OutputFieldSchema(
            path="route.traffic_conditions",
            type="string",
            nullable=True,
            description="Traffic level: NORMAL, LIGHT, MODERATE, HEAVY",
        ),
        OutputFieldSchema(
            path="route.polyline", type="string", description="Encoded polyline for map display"
        ),
        OutputFieldSchema(
            path="route.steps", type="array", description="Turn-by-turn navigation steps"
        ),
        OutputFieldSchema(
            path="route.maps_url", type="string", description="Google Maps URL for directions"
        ),
        OutputFieldSchema(
            path="route.is_arrival_based",
            type="boolean",
            description="True if route was calculated based on arrival_time",
        ),
        OutputFieldSchema(
            path="route.target_arrival_time",
            type="string",
            nullable=True,
            description="Target arrival time (ISO 8601) when is_arrival_based=true",
        ),
        OutputFieldSchema(
            path="route.target_arrival_formatted",
            type="string",
            nullable=True,
            description="Human-readable target arrival time",
        ),
        OutputFieldSchema(
            path="route.suggested_departure_time",
            type="string",
            nullable=True,
            description="Suggested departure time (ISO 8601) to arrive on time",
        ),
        OutputFieldSchema(
            path="route.suggested_departure_formatted",
            type="string",
            nullable=True,
            description="Human-readable suggested departure time",
        ),
        OutputFieldSchema(
            path="alternatives_count", type="integer", description="Number of alternative routes"
        ),
    ],
    cost=CostProfile(est_tokens_in=150, est_tokens_out=600, est_cost_usd=0.007, est_latency_ms=800),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,  # HITL conditionally triggered based on distance
        data_classification="PUBLIC",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="routes",
    reference_examples=[
        "route.distance_km",
        "route.duration_formatted",
        "route.traffic_conditions",
        "route.maps_url",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="🗺️", i18n_key="get_route", visible=True, category="tool"),
)


# ============================================================================
# 2. GET ROUTE MATRIX (Distance/Duration Matrix)
# ============================================================================
_get_route_matrix_desc = (
    "**Tool: get_route_matrix_tool** - Compute distance/duration matrix between multiple locations.\n"
    "\n"
    "**USE CASES**:\n"
    "- Find nearest location from multiple options\n"
    "- Optimize delivery routes\n"
    "- Compare travel times from different starting points\n"
    "- Plan multi-stop trips\n"
    "\n"
    "**LIMITS**:\n"
    "- Max 25 origins x 25 destinations = 625 elements\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- 'Which warehouse is closest?' → get_route_matrix_tool(origins=['Warehouse A', 'Warehouse B'], destinations=['Client'])\n"
    "- 'Travel time to 3 clients from Paris' → get_route_matrix_tool(origins=['Paris'], destinations=['Client1', 'Client2', 'Client3'])\n"
    "- 'Optimal order to visit these addresses' → Use response optimal_order field\n"
    "\n"
    "**RETURNS**: Matrix of distances and durations, optimal order (if applicable)."
)

get_route_matrix_catalogue_manifest = ToolManifest(
    name="get_route_matrix_tool",
    agent="route_agent",
    description=_get_route_matrix_desc,
    # Discriminant phrases - Matrix and optimization queries
    semantic_keywords=[
        # Nearest location queries
        "find nearest location closest place",
        "which is closer nearer destination",
        "shortest distance from multiple origins",
        "compare distances to destinations",
        # Route optimization
        "optimize delivery route order",
        "best order to visit locations",
        "optimal sequence for stops",
        "traveling salesman multi-stop",
        # Matrix calculations
        "distance matrix between locations",
        "travel time comparison table",
        "compare routes from different starts",
    ],
    parameters=[
        ParameterSchema(
            name="origins",
            type="array",
            required=True,
            description="List of starting points as physical addresses (max 25). Example: ['Paris', 'Lyon'].",
            constraints=[ParameterConstraint(kind="maximum", value=25)],
            semantic_type="physical_address",  # Array of addresses
        ),
        ParameterSchema(
            name="destinations",
            type="array",
            required=True,
            description="List of destinations as physical addresses (max 25). Example: ['Marseille', 'Nice'].",
            constraints=[ParameterConstraint(kind="maximum", value=25)],
            semantic_type="physical_address",  # Array of addresses
        ),
        ParameterSchema(
            name="travel_mode",
            type="string",
            required=False,
            description="Travel mode: DRIVE, WALK, BICYCLE, TRANSIT. Default: DRIVE.",
        ),
        ParameterSchema(
            name="departure_time",
            type="string",
            required=False,
            description="Departure time in ISO 8601 for traffic prediction.",
        ),
    ],
    outputs=[
        OutputFieldSchema(
            path="matrix",
            type="array",
            description="2D matrix of route data [origin_idx][dest_idx]",
        ),
        OutputFieldSchema(
            path="matrix[][].distance_km", type="number", description="Distance in km"
        ),
        OutputFieldSchema(
            path="matrix[][].duration_minutes", type="integer", description="Duration in minutes"
        ),
        OutputFieldSchema(
            path="matrix[][].duration_formatted",
            type="string",
            description="Human-readable duration",
        ),
        OutputFieldSchema(
            path="matrix[][].condition",
            type="string",
            description="Route condition (OK, ROUTE_NOT_FOUND)",
        ),
        OutputFieldSchema(path="origins", type="array", description="Origin list (for reference)"),
        OutputFieldSchema(
            path="destinations", type="array", description="Destination list (for reference)"
        ),
        OutputFieldSchema(
            path="optimal_order",
            type="array",
            nullable=True,
            description="Optimal destination order (indices) if single origin",
        ),
        OutputFieldSchema(path="travel_mode", type="string", description="Travel mode used"),
    ],
    cost=CostProfile(
        est_tokens_in=200, est_tokens_out=800, est_cost_usd=0.010, est_latency_ms=1200
    ),
    permissions=PermissionProfile(
        required_scopes=[],
        hitl_required=False,
        data_classification="PUBLIC",
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="routes",
    reference_examples=[
        "matrix[0][0].distance_km",
        "matrix[0][0].duration_formatted",
        "optimal_order",
        "origins",
        "destinations",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📊", i18n_key="get_route_matrix", visible=True, category="tool"),
    initiative_eligible=False,  # Complex multi-point tool, not suitable for quick proactive check
)


__all__ = [
    "get_route_catalogue_manifest",
    "get_route_matrix_catalogue_manifest",
]
