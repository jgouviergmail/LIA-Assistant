"""
Catalogue manifests for Weather tools (OpenWeatherMap API).
Optimized for orchestration efficiency.
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
# Shared Parameters
# ============================================================================
_LOC_PARAM = ParameterSchema(
    name="location",
    type="string",
    required=False,  # Optional: auto-detected (browser > last-known > home, ADR-219)
    description=(
        "City name (e.g. 'Paris, FR', 'London, UK'). "
        "Leave EMPTY to use the user's position (browser GPS, else their "
        "fresh last-known position, else home address). "
        "NEVER ask user for location - use auto-detection if not specified. "
        "For weather at a CALENDAR EVENT, use the event's location field."
    ),
    semantic_type="physical_address",  # Cross-domain: can use events[].location
)
_UNIT_PARAM = ParameterSchema(
    name="units",
    type="string",
    required=False,
    description="'metric' (Celsius, def) or 'imperial' (Fahrenheit).",
    semantic_type="unit_system",
)
_LANG_PARAM = ParameterSchema(
    name="language",
    type="string",
    required=False,
    description="Lang code (e.g. 'fr', 'en'). Def: 'fr'.",
    semantic_type="language_code",
)
_DATE_PARAM = ParameterSchema(
    name="date",
    type="string",
    required=False,
    description=(
        "Target date for forecast. Accepts: temporal reference ('today', 'tomorrow'), "
        "ISO date ('2026-01-22'), or ISO datetime from calendar events. "
        "For weather at a CALENDAR EVENT, use the event's start_datetime."
    ),
    semantic_type="event_start_datetime",  # Cross-domain: weather for a calendar event
)

# ============================================================================
# 1. GET CURRENT WEATHER
# ============================================================================
_current_desc = (
    "**Tool: get_current_weather_tool** - Current weather conditions (right now).\n"
    "Returns temperature, humidity, wind speed, weather description.\n"
    "**Use for**: 'Weather now', 'Temperature in Paris', 'Current conditions'.\n"
    "**Output**: Single snapshot of current state."
)
get_current_weather_catalogue_manifest = ToolManifest(
    name="get_current_weather_tool",
    agent="weather_agent",
    description=_current_desc,
    # Discriminant phrases - Current weather conditions
    semantic_keywords=[
        "what is the current weather right now",
        "temperature outside at this moment",
        "is it raining or sunny now",
        "how cold or hot is it today",
        "current weather conditions in location",
        "check if it's raining outside now",
    ],
    # NOTE: No date parameter - current weather is always "now"
    # Calendar event dates should route to get_weather_forecast_tool via semantic_type
    parameters=[_LOC_PARAM, _UNIT_PARAM, _LANG_PARAM],
    # Registry-backed tool: the payload is grouped under the `weathers` context
    # key, never at the top level. Advertising bare `temperature` made the
    # planner emit `$steps.X.temperature`, which no execution can resolve.
    outputs=[
        OutputFieldSchema(path="weathers", type="array", description="Current weather readings"),
        # The payload carries the resolved location as a RECORD (name / country /
        # lat / lon), not a label — declaring it `string` with a `locality`
        # semantic type invited the planner to chain a dict where a city name
        # was expected.
        OutputFieldSchema(
            path="weathers[].location",
            type="object",
            description="Resolved location (name / country / lat / lon)",
        ),
        OutputFieldSchema(
            path="weathers[].location.name",
            type="string",
            description="City name",
            semantic_type="locality",
        ),
        OutputFieldSchema(
            path="weathers[].temperature",
            type="number",
            description="Temp",
            semantic_type="temperature",
        ),
        OutputFieldSchema(
            path="weathers[].feels_like",
            type="number",
            description="Feels like",
            semantic_type="temperature",
        ),
        OutputFieldSchema(
            path="weathers[].humidity",
            type="integer",
            description="Humidity %",
            semantic_type="humidity",
        ),
        OutputFieldSchema(path="weathers[].description", type="string", description="Condition"),
        OutputFieldSchema(
            path="weathers[].wind_speed",
            type="number",
            description="Wind",
            semantic_type="wind_speed",
        ),
        OutputFieldSchema(path="weathers[].pressure", type="integer", description="Pressure hPa"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=200, est_cost_usd=0.001, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=[
        # The city NAME, not the `location` record: a reference example is what
        # the planner will chain, and chaining a dict into a string parameter
        # fails at execution.
        "weathers[0].location.name",
        "weathers[0].temperature",
        "weathers[0].description",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="🌤️", i18n_key="get_current_weather", visible=True, category="tool"
    ),
)

# ============================================================================
# 2. GET WEATHER FORECAST (5 Days / 3h)
# ============================================================================
_forecast_desc = (
    "**Tool: get_weather_forecast_tool** - Multi-day weather forecast (1 to max days, 3h intervals).\n"
    "Returns ~40 data points with temperature, conditions, precipitation probability.\n"
    "**Use for**: 'Weather this week', 'Forecast for tomorrow', 'Best day for outdoor activity', "
    "'Weather at my calendar event'.\n"
    "**CALENDAR EVENTS**: Use event's start_datetime as 'date' parameter to get weather FOR that day.\n"
    "**Granularity**: 3-hour intervals. Use 'days' parameter (1-5)."
)
get_weather_forecast_catalogue_manifest = ToolManifest(
    name="get_weather_forecast_tool",
    agent="weather_agent",
    description=_forecast_desc,
    # Discriminant phrases - Multi-day weather forecast
    semantic_keywords=[
        "weather forecast for the next few days",
        "what will weather be like tomorrow",
        "will it rain this week forecast",
        "weather prediction for upcoming days",
        "weekend weather forecast in location",
        "best day for outdoor activity weather",
        "weather for my calendar event appointment",
    ],
    parameters=[
        _LOC_PARAM,
        _DATE_PARAM,
        ParameterSchema(
            name="days",
            type="integer",
            required=False,
            description=(
                "Number of days to forecast (1-5, def: 5). "
                "CALCULATE from current datetime to reach target day. "
                "Ex: If today is Monday and user asks for 'Friday', set days=5 to include Friday. "
                "Ex: If today is Wednesday and user asks for 'this weekend', set days=4 to include Sat."
            ),
            constraints=[ParameterConstraint(kind="maximum", value=5)],
        ),
        _UNIT_PARAM,
        _LANG_PARAM,
    ],
    # The daily forecast exposes BOTH a flat `forecasts` list and the
    # registry-backed `weathers` entries. The collection is `forecasts`, not
    # `forecast`, and its temperatures are min/max/avg — there is no single
    # `temperature`, and no `datetime`: the slot is dated by `date`.
    outputs=[
        OutputFieldSchema(
            path="location",
            type="object",
            description="Resolved location (name / country / display)",
        ),
        OutputFieldSchema(
            # The semantic type belongs on the string, not on the object above:
            # `location` is a record, and typing it `locality` would invite the
            # planner to chain a dict where a city name is expected.
            path="location.display",
            type="string",
            description="Location label for display",
            semantic_type="locality",
        ),
        OutputFieldSchema(path="days", type="integer", description="Number of days returned"),
        OutputFieldSchema(path="forecasts", type="array", description="Daily forecast points"),
        OutputFieldSchema(
            path="forecasts[].date",
            type="string",
            description="Day (ISO date)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            path="forecasts[].temp_min",
            type="number",
            description="Min temp",
            semantic_type="temperature",
        ),
        OutputFieldSchema(
            path="forecasts[].temp_max",
            type="number",
            description="Max temp",
            semantic_type="temperature",
        ),
        OutputFieldSchema(
            path="forecasts[].temp_avg",
            type="number",
            description="Average temp",
            semantic_type="temperature",
        ),
        OutputFieldSchema(path="forecasts[].description", type="string", description="Condition"),
        OutputFieldSchema(
            path="forecasts[].humidity",
            type="integer",
            description="Humidity %",
            semantic_type="humidity",
        ),
        OutputFieldSchema(
            path="forecasts[].wind_speed",
            type="number",
            description="Wind",
            semantic_type="wind_speed",
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=800, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=[
        "forecasts[0].date",
        "forecasts[0].temp_min",
        "forecasts[0].temp_max",
        "location.display",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📅", i18n_key="get_weather_forecast", visible=True, category="tool"
    ),
)

# ============================================================================
# 3. GET HOURLY FORECAST (intra-day, 3-hour steps, up to 5 days)
# ============================================================================
_hourly_desc = (
    "**Tool: get_hourly_forecast_tool** - Intra-day weather forecast in 3-hour steps.\n"
    "Backed by the free 5-day / 3-hour forecast: NOT hour-by-hour — a time like 11:15\n"
    "maps to the nearest 3-hour slot.\n"
    "**Use for**: a TIME OF DAY, today or on a future day within 5 days\n"
    "('next few hours', 'this afternoon', 'at 11am', 'for my 11:15 appointment').\n"
    "**Pass `date`** for any day other than today; omit it for a rolling window from now.\n"
    "**Granularity**: 3-hour slots, up to 5 days ahead. For a whole-day summary use\n"
    "get_weather_forecast_tool instead."
)
get_hourly_forecast_catalogue_manifest = ToolManifest(
    name="get_hourly_forecast_tool",
    agent="weather_agent",
    description=_hourly_desc,
    # Discriminant phrases - intra-day forecast at 3-hour granularity
    semantic_keywords=[
        "weather by 3-hour slots for today",
        "forecast for this afternoon",
        "weather tonight by time slot",
        "next few hours weather conditions",
        "weather at a specific time on a future day",
        "weather at the time of my appointment",
    ],
    parameters=[
        _LOC_PARAM,
        _DATE_PARAM,
        ParameterSchema(
            name="hours",
            type="integer",
            required=False,
            description="Rolling window size in hours from now (1-48, def: 24). IGNORED when 'date' is given.",
            constraints=[ParameterConstraint(kind="maximum", value=48)],
        ),
        _UNIT_PARAM,
        _LANG_PARAM,
    ],
    # Registry-backed: the slots hang off the `weathers` entry, they are NOT a
    # top-level `hourly` list. The payload key is `temp` (see
    # weather_formatting._format_hourly_response), not `temperature`.
    outputs=[
        OutputFieldSchema(path="weathers", type="array", description="Hourly forecast entry"),
        OutputFieldSchema(
            path="weathers[].location",
            type="object",
            description="Location",
            semantic_type="locality",
        ),
        OutputFieldSchema(
            path="weathers[].interval", type="string", description="Slot interval (e.g. '3 hours')"
        ),
        OutputFieldSchema(path="weathers[].hourly", type="array", description="3-hour slots"),
        OutputFieldSchema(
            path="weathers[].hourly[].datetime",
            type="string",
            description="UTC epoch (datetime_text is the local wall clock)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            path="weathers[].hourly[].datetime_text",
            type="string",
            description="Local wall-clock time of the slot (YYYY-MM-DD HH:MM:SS, user timezone)",
            semantic_type="datetime",
        ),
        OutputFieldSchema(
            # Measured a float, not a string — the manifest had it wrong before
            # the path prefix was fixed too.
            path="weathers[].hourly[].temp",
            type="number",
            description="Temp",
            semantic_type="temperature",
        ),
        OutputFieldSchema(
            path="weathers[].hourly[].description", type="string", description="Condition"
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=600, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=[
        "weathers[0].hourly[0].datetime_text",
        "weathers[0].hourly[0].temp",
    ],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="⏰", i18n_key="get_hourly_forecast", visible=True, category="tool"
    ),
    initiative_eligible=False,  # Too granular for proactive enrichment; forecast is sufficient
)

__all__ = [
    "get_current_weather_catalogue_manifest",
    "get_weather_forecast_catalogue_manifest",
    "get_hourly_forecast_catalogue_manifest",
]
