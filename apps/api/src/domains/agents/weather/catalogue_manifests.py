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
    required=False,  # Optional: auto-detection from browser geolocation or home address
    description=(
        "City name (e.g. 'Paris, FR', 'London, UK'). "
        "Leave EMPTY to use user's current location (browser GPS) or home address. "
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
)
_LANG_PARAM = ParameterSchema(
    name="language",
    type="string",
    required=False,
    description="Lang code (e.g. 'fr', 'en'). Def: 'fr'.",
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
    semantic_type="event_start_datetime",
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
    outputs=[
        OutputFieldSchema(path="location", type="string", description="Location"),
        OutputFieldSchema(path="temperature", type="number", description="Temp"),
        OutputFieldSchema(path="feels_like", type="number", description="Feels like"),
        OutputFieldSchema(path="humidity", type="integer", description="Humidity %"),
        OutputFieldSchema(path="description", type="string", description="Condition"),
        OutputFieldSchema(path="wind_speed", type="number", description="Wind"),
        OutputFieldSchema(path="pressure", type="integer", description="Pressure hPa"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=200, est_cost_usd=0.001, est_latency_ms=500),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=["location", "temperature", "description"],
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
    outputs=[
        OutputFieldSchema(path="location", type="string", description="Location"),
        OutputFieldSchema(path="forecast", type="array", description="Points"),
        OutputFieldSchema(path="forecast[].datetime", type="string", description="UTC Time"),
        OutputFieldSchema(path="forecast[].temperature", type="number", description="Temp"),
        OutputFieldSchema(path="forecast[].description", type="string", description="Condition"),
        OutputFieldSchema(
            path="forecast[].precipitation_prob", type="number", description="Rain Prob"
        ),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=800, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=["forecast[0].datetime", "forecast[0].temperature"],
    version="1.0.0",
    maintainer="Team Agents",
    display=DisplayMetadata(
        emoji="📅", i18n_key="get_weather_forecast", visible=True, category="tool"
    ),
)

# ============================================================================
# 3. GET HOURLY FORECAST (48h)
# ============================================================================
_hourly_desc = (
    "**Tool: get_hourly_forecast_tool** - Hourly weather forecast (next 48 hours).\n"
    "High precision, one data point per hour.\n"
    "**Use for**: 'Next few hours', 'Hour by hour', 'Precise short-term forecast'.\n"
    "**Granularity**: 1-hour intervals (max 48h)."
)
get_hourly_forecast_catalogue_manifest = ToolManifest(
    name="get_hourly_forecast_tool",
    agent="weather_agent",
    description=_hourly_desc,
    # Discriminant phrases - Hourly weather forecast
    semantic_keywords=[
        "weather hour by hour for today",
        "hourly forecast for this afternoon",
        "weather tonight hour by hour",
        "next few hours weather conditions",
        "precise weather for coming hours",
    ],
    parameters=[
        _LOC_PARAM,
        _DATE_PARAM,
        ParameterSchema(
            name="hours",
            type="integer",
            required=False,
            description="Hours (1-48, def: 24)",
            constraints=[ParameterConstraint(kind="maximum", value=48)],
        ),
        _UNIT_PARAM,
        _LANG_PARAM,
    ],
    outputs=[
        OutputFieldSchema(path="location", type="string", description="Location"),
        OutputFieldSchema(path="hourly", type="array", description="Data"),
        OutputFieldSchema(path="hourly[].datetime", type="string", description="UTC Time"),
        OutputFieldSchema(path="hourly[].temperature", type="number", description="Temp"),
        OutputFieldSchema(path="hourly[].description", type="string", description="Condition"),
    ],
    cost=CostProfile(est_tokens_in=100, est_tokens_out=600, est_cost_usd=0.002, est_latency_ms=600),
    permissions=PermissionProfile(
        required_scopes=[], hitl_required=False, data_classification="PUBLIC"
    ),
    context_key="weathers",  # Must match CONTEXT_DOMAIN_WEATHER in constants.py
    reference_examples=["hourly[0].datetime", "hourly[0].temperature"],
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
