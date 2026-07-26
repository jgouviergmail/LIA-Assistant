"""Geographic utility functions shared across domains.

Pure-math helpers with no domain knowledge. Promoted from
``src.domains.agents.utils.distance`` so that non-agent domains (user
location cascade, briefing, heartbeat) can compute distances without
importing the agents domain (coupling reduction, see ADR-126).
"""

import math

# Earth's radius in kilometers (mean radius)
EARTH_RADIUS_KM = 6371.0

# 8-point compass, clockwise from North. These are CODES, not display labels:
# the letters happen to read as English, but every rendering layer resolves them
# through i18n (``V3Messages.get_wind_cardinal`` server-side, the
# ``dashboard.weather.wind_cardinal.*`` keys client-side). Never print one.
WIND_CARDINAL_CODES: tuple[str, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# Each sector spans 45°, centred on its point — N covers [-22.5, 22.5).
_WIND_SECTOR_DEGREES = 360 / len(WIND_CARDINAL_CODES)
_WIND_SECTOR_HALF = _WIND_SECTOR_DEGREES / 2


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate straight-line distance using the Haversine formula.

    This gives the shortest distance over the earth's surface
    (great-circle distance).

    Args:
        lat1: First point latitude (degrees).
        lon1: First point longitude (degrees).
        lat2: Second point latitude (degrees).
        lon2: Second point longitude (degrees).

    Returns:
        Distance in kilometers.
    """
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine formula
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_KM * c


def wind_deg_to_cardinal(deg: float | int | str | None) -> str | None:
    """Convert a wind bearing to its 8-point compass code.

    Single source of truth for the degrees → compass mapping, shared by the
    briefing weather card (which ships the code to the frontend) and the agent
    weather card (which localizes it server-side). Two divergent tables used to
    coexist — one spelling the points in English, one in French — so the same
    bearing read differently depending on which card showed it.

    Args:
        deg: Bearing in degrees, 0 = North, clockwise. Values outside
            [0, 360) are wrapped. Accepts the numeric strings providers send.

    Returns:
        One of :data:`WIND_CARDINAL_CODES`, or ``None`` when *deg* is missing
        or not a number — never a fabricated bearing.

    Example:
        >>> wind_deg_to_cardinal(0)
        'N'
        >>> wind_deg_to_cardinal(225)
        'SW'
        >>> wind_deg_to_cardinal(None) is None
        True
    """
    if deg is None:
        return None
    try:
        bearing = float(deg) % 360
    except (TypeError, ValueError):
        return None
    if math.isnan(bearing):
        return None
    index = int(((bearing + _WIND_SECTOR_HALF) % 360) // _WIND_SECTOR_DEGREES)
    return WIND_CARDINAL_CODES[index]
