"""
Catalogue manifests for Google Places tools.
Optimized for orchestration efficiency.

Architecture Simplification (2026-01):
- get_places_tool replaces search_places_tool + get_place_details_tool
- Always returns full place content (hours, phone, reviews)
- Supports query mode (text search) OR ID mode (direct fetch) OR proximity mode
"""

from src.core.constants import (
    PLACES_MIN_RATING_MAX,
    PLACES_MIN_RATING_MIN,
    PLACES_TOOL_DEFAULT_LIMIT,
    PLACES_TOOL_DEFAULT_MAX_RESULTS,
    PLACES_VALID_PRICE_LEVELS,
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

# ============================================================================
# 1. GET PLACES (Unified - replaces search + details)
# ============================================================================
_get_places_desc = (
    "**Tool: get_places_tool** - Get places with full details.\n"
    "\n"
    "**MODES**:\n"
    "- Query mode: get_places_tool(query='Italian restaurants', location='Paris') → search in location\n"
    "- ID mode: get_places_tool(place_id='ChIJ...') → fetch specific place\n"
    "- Batch mode: get_places_tool(place_ids=['ChIJ1', 'ChIJ2']) → fetch multiple places\n"
    "- Proximity mode: get_places_tool(place_type='restaurant') → nearby places (auto-location)\n"
    "\n"
    "**PARAMETER SEPARATION (CRITICAL)**:\n"
    "- `query`: ONLY the type/name of place (e.g., 'monoprix', 'Italian restaurants', 'pharmacy')\n"
    "- `location`: City, postal code, address, or neighborhood (e.g., 'Paris', '75001', 'Le Marais')\n"
    "- If NO location specified: auto-resolved from browser geolocation or home address\n"
    "\n"
    "**RADIUS FILTERING**:\n"
    "- `radius_meters`: Maximum distance from location in meters (places FARTHER are excluded)\n"
    "- Default: 1000m (1 km), Maximum: 50000m (50 km)\n"
    "- Example: 'restaurants within 5km' → radius_meters=5000\n"
    "\n"
    "**DISTANCE EXAMPLES**:\n"
    "- 'within 5 km radius' → radius_meters=5000\n"
    "- 'less than 10 km away' → radius_meters=10000\n"
    "- 'restaurants within 2km of Paris' → location='Paris', radius_meters=2000\n"
    "\n"
    "**RATING FILTERING**:\n"
    "- `min_rating`: Minimum rating (1.0-5.0) - excludes places with rating below this value\n"
    "- Example: 'restaurants with rating above 4' → min_rating=4.0\n"
    "- Example: 'rating > 4.5' or 'well-rated' → min_rating=4.5\n"
    "\n"
    "**PRICE FILTERING**:\n"
    "- `price_levels`: List of price levels to include\n"
    "- Values: PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE, PRICE_LEVEL_EXPENSIVE, PRICE_LEVEL_VERY_EXPENSIVE\n"
    "- Example: 'cheap restaurants' → price_levels=['PRICE_LEVEL_INEXPENSIVE']\n"
    "- Example: 'mid-range to expensive' → price_levels=['PRICE_LEVEL_MODERATE', 'PRICE_LEVEL_EXPENSIVE']\n"
    "\n"
    "**SEARCHABLE FIELDS**:\n"
    "- query (place name/type), location (city/address), place_type, radius_meters\n"
    "- min_rating (rating filter), price_levels (price filter), open_now (availability filter)\n"
    "\n"
    "**COMMON USE CASES**:\n"
    "- '3 monoprix in Paris' → query='monoprix', location='Paris', max_results=3\n"
    "- 'Italian restaurants in Lyon' → query='Italian restaurants', location='Lyon'\n"
    "- 'pharmacies in 75001' → query='pharmacies', location='75001'\n"
    "- 'restaurants near me' → query='restaurants' (NO location → uses geolocation)\n"
    "- 'cafes near my home' → query='cafes' (NO location → uses home address)\n"
    "- 'restaurants with rating > 4.5' → query='restaurants', min_rating=4.5\n"
    "- '2 well-rated restaurants' → query='restaurants', min_rating=4.0, max_results=2\n"
    "- 'cheap restaurants' → query='restaurants', price_levels=['PRICE_LEVEL_INEXPENSIVE']\n"
    "- 'is this place open?' → place_id='ID from context'\n"
    "\n"
    "**RETURNS**: Full place info (name, address, phone, hours, reviews, distance_km, etc.)."
)

get_places_catalogue_manifest = ToolManifest(
    name="get_places_tool",
    agent="place_agent",
    description=_get_places_desc,
    # Discriminant phrases - Local place discovery (CONCEPT-based, not instance-based)
    semantic_keywords=[
        # Location-based search (city/destination - not just nearby)
        "search for places establishments in city or town",
        "find businesses shops in specific location destination",
        "looking for places to eat drink stay in area",
        "discover places of interest in destination location",
        # Proximity-based search (nearby)
        "find places to eat nearby my location",
        "search for shops stores close to me",
        "nearby businesses establishments around here",
        "places to stay in this area or city",
        "restaurants",
        "cafes",
        "bars",
        "hotels",
        "shops",
        "stores",
        "supermarkets",
        "malls",
        "pharmacies",
        "hospitals",
        "clinics",
        "doctors",
        "dentists",
        "banks",
        "ATMs",
        "gas stations",
        "parking",
        "train stations",
        "airports",
        "museums",
        "theaters",
        "cinemas",
        "galleries",
        "libraries",
        "gyms",
        "swimming pools",
        "spas",
        "parks",
        "gardens",
        "playgrounds",
        "beaches",
        "monuments",
        "landmarks",
        "tourist attractions",
        "castles",
        "historic sites",
        "churches",
        "mosques",
        "temples",
        "schools",
        "universities",
        "post offices",
        "police stations",
        "hair salons",
        "bakeries",
        "florists",
        "bookstores",
        "car repair",
        "veterinarians",
        "nightclubs",
        "bowling",
        "zoo",
        "aquarium",
        "stadiums",
        # Place discovery
        "where to eat good food nearby",
        "entertainment nightlife spots around here",
        "best rated places in this neighborhood",
        "find specific business type nearby",
        # Place details
        "opening hours of this business",
        "is this place establishment open now",
        "phone number of nearby place",
        "reviews and ratings of business",
        # Rating and quality filtering
        "well rated restaurants with high rating score",
        "places with good reviews above four stars",
        "highly rated establishments top rated places",
        "restaurants with rating higher than threshold",
        # Price filtering
        "cheap affordable budget places to eat",
        "expensive high end luxury restaurants",
        "moderate mid range price level dining",
        "inexpensive budget friendly options nearby",
    ],
    parameters=[
        # Query mode parameter - ONLY place type/name, NOT location
        ParameterSchema(
            name="query",
            type="string",
            required=False,
            description=(
                "Place type or name to search (e.g., 'monoprix', 'Italian restaurants', 'pharmacy'). "
                "Do NOT include location here - use 'location' parameter instead."
            ),
        ),
        # Location parameter - city, postal code, address, neighborhood
        ParameterSchema(
            name="location",
            type="string",
            required=False,
            description=(
                "City name, postal code, address, or neighborhood (e.g., 'Paris', '75001', 'Le Marais', '10 rue de la Paix'). "
                "Leave EMPTY to use user's current location (browser GPS) or home address. "
                "For places near a person, first get their address from contacts."
            ),
            semantic_type="physical_address",  # Triggers contacts resolution for person references
        ),
        # ID mode parameters
        ParameterSchema(
            name="place_id",
            type="string",
            required=False,
            description="Single place ID for direct fetch.",
        ),
        ParameterSchema(
            name="place_ids",
            type="array",
            required=False,
            description="Multiple place IDs for batch fetch.",
        ),
        # Proximity mode parameter
        ParameterSchema(
            name="place_type",
            type="string",
            required=False,
            description="Type filter: restaurant, cafe, bar, hotel, pharmacy, etc.",
        ),
        # Common options
        ParameterSchema(
            name="max_results",
            type="integer",
            required=False,
            description=f"Max results (def: {PLACES_TOOL_DEFAULT_LIMIT}, max: {PLACES_TOOL_DEFAULT_MAX_RESULTS})",
            constraints=[
                ParameterConstraint(kind="maximum", value=PLACES_TOOL_DEFAULT_MAX_RESULTS)
            ],
        ),
        ParameterSchema(
            name="radius_meters",
            type="integer",
            required=False,
            description=(
                "Maximum distance from location in meters (def: 1000m, max: 50000m). "
                "Example: 'within 5 km' → 5000"
            ),
            constraints=[ParameterConstraint(kind="maximum", value=50000)],
        ),
        ParameterSchema(
            name="open_now",
            type="boolean",
            required=False,
            description="Filter to only open places",
        ),
        ParameterSchema(
            name="min_rating",
            type="number",
            required=False,
            description=(
                f"Minimum rating filter ({PLACES_MIN_RATING_MIN}-{PLACES_MIN_RATING_MAX}). "
                "Only returns places with rating >= this value. "
                "Example: 'rating above 4' → 4.0, 'well-rated' → 4.0"
            ),
            constraints=[
                ParameterConstraint(kind="minimum", value=PLACES_MIN_RATING_MIN),
                ParameterConstraint(kind="maximum", value=PLACES_MIN_RATING_MAX),
            ],
        ),
        ParameterSchema(
            name="price_levels",
            type="array",
            required=False,
            description=(
                "Price level filter list. Valid values: "
                + ", ".join(sorted(PLACES_VALID_PRICE_LEVELS - {"PRICE_LEVEL_FREE"}))
                + ". Example: 'cheap' → ['PRICE_LEVEL_INEXPENSIVE']"
            ),
        ),
    ],
    outputs=[
        # Full place outputs (merged from search + details)
        OutputFieldSchema(
            path="places", type="array", description="List of places with full details"
        ),
        OutputFieldSchema(path="places[].place_id", type="string", description="Place ID"),
        OutputFieldSchema(path="places[].name", type="string", description="Name"),
        OutputFieldSchema(
            path="places[].address",
            type="string",
            description="Address",
            semantic_type="physical_address",  # Cross-domain: can be used as routes.destination
        ),
        OutputFieldSchema(
            path="places[].phone",
            type="string",
            nullable=True,
            description="Phone number",
            semantic_type="phone_number",
        ),
        OutputFieldSchema(
            path="places[].website", type="string", nullable=True, description="Website URL"
        ),
        OutputFieldSchema(
            path="places[].rating", type="number", nullable=True, description="Rating"
        ),
        OutputFieldSchema(
            path="places[].price_level", type="string", nullable=True, description="Price level"
        ),
        OutputFieldSchema(
            path="places[].opening_hours", type="object", nullable=True, description="Opening hours"
        ),
        OutputFieldSchema(
            path="places[].reviews", type="array", nullable=True, description="Reviews"
        ),
        OutputFieldSchema(
            path="places[].distance_km", type="number", nullable=True, description="Distance (km)"
        ),
        OutputFieldSchema(path="total", type="integer", description="Count"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=800, est_cost_usd=0.008, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    max_iterations=1,
    supports_dry_run=True,
    context_key="places",
    reference_examples=[
        "places[0].place_id",
        "places[0].name",
        "places[0].phone",
        "places[0].opening_hours",
        "total",
    ],
    version="2.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(emoji="📍", i18n_key="get_places", visible=True, category="tool"),
)


# ============================================================================
# 2. GET CURRENT LOCATION (Reverse Geocoding)
# ============================================================================
_location_desc = (
    "**Tool: get_current_location_tool** - Get user's current location.\n"
    "Uses browser geolocation + reverse geocoding to answer:\n"
    "- 'Where am I?', 'My location', 'What is my address?'\n"
    "**No parameters needed** - uses browser geolocation automatically.\n"
    "**Requires**: Browser geolocation permission enabled."
)

get_current_location_catalogue_manifest = ToolManifest(
    name="get_current_location_tool",
    agent="place_agent",
    description=_location_desc,
    # Discriminant phrases - Current location identification
    semantic_keywords=[
        "where am I right now geolocation",
        "what is my current address location",
        "identify this place from GPS position",
        "show my coordinates and street address",
    ],
    parameters=[],  # No parameters - uses browser geolocation automatically
    outputs=[
        OutputFieldSchema(
            path="locations",
            type="array",
            description="Array of location results (typically 1 item)",
        ),
        OutputFieldSchema(
            path="locations[].formatted_address",
            type="string",
            description="Full address",
            semantic_type="physical_address",  # Cross-domain: can be used as routes.destination
        ),
        OutputFieldSchema(
            path="locations[].locality", type="string", nullable=True, description="City"
        ),
        OutputFieldSchema(
            path="locations[].country", type="string", nullable=True, description="Country"
        ),
        OutputFieldSchema(
            path="locations[].postal_code",
            type="string",
            nullable=True,
            description="Postal code",
        ),
        OutputFieldSchema(
            path="locations[].latitude",
            type="number",
            description="Latitude",
            semantic_type="coordinate",  # Cross-domain: can be used for geo queries
        ),
        OutputFieldSchema(
            path="locations[].longitude",
            type="number",
            description="Longitude",
            semantic_type="coordinate",  # Cross-domain: can be used for geo queries
        ),
        OutputFieldSchema(path="locations[].source", type="string", description="Location source"),
    ],
    cost=CostProfile(est_tokens_in=50, est_tokens_out=200, est_cost_usd=0.002, est_latency_ms=400),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="CONFIDENTIAL"
    ),
    context_key="locations",  # Must match CONTEXT_DOMAIN_LOCATION in constants.py
    reference_examples=[
        "locations[0].formatted_address",
        "locations[0].locality",
        "locations[0].country",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📍", i18n_key="get_current_location", visible=True, category="tool"
    ),
)


__all__ = [
    # Unified tool (v2.0 - replaces search + details)
    "get_places_catalogue_manifest",
    # Other tools
    "get_current_location_catalogue_manifest",
]
