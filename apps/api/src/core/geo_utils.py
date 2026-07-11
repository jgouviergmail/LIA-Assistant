"""Geographic utility functions shared across domains.

Pure-math helpers with no domain knowledge. Promoted from
``src.domains.agents.utils.distance`` so that non-agent domains (user
location cascade, briefing, heartbeat) can compute distances without
importing the agents domain (coupling reduction, see ADR-126).
"""

import math

# Earth's radius in kilometers (mean radius)
EARTH_RADIUS_KM = 6371.0


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
