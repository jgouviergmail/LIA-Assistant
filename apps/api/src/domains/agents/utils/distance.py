"""
Distance calculation utilities with extensible architecture.

Supports:
- Haversine formula (straight-line distance) - default, free, instant
- Future: Google Routes API (real distance with walking/driving modes)

Architecture:
- Uses Protocol pattern for strategy/plugin approach
- DistanceCalculator protocol defines the interface
- HaversineCalculator is the default implementation (fallback)
- Future GoogleRoutesCalculator can be added without modifying existing code

Usage:
    from src.domains.agents.utils.distance import calculate_distance, DistanceResult

    # Basic usage (uses Haversine by default)
    result = await calculate_distance(
        origin_lat=48.8566, origin_lon=2.3522,
        dest_lat=48.8584, dest_lon=2.2945,
    )
    print(result.formatted)  # "2.1 km"
    print(result.mode)       # "straight_line"

    # With source for reference text
    result = await calculate_distance(
        origin_lat=48.8566, origin_lon=2.3522,
        dest_lat=48.8584, dest_lon=2.2945,
        source="browser",
        language="fr",
    )
    print(result.reference)  # "depuis votre position"
"""

import math
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from src.domains.agents.utils.i18n_location import get_distance_reference


class DistanceMode(str, Enum):
    """Distance calculation mode."""

    STRAIGHT_LINE = "straight_line"  # Haversine (vol d'oiseau)
    WALKING = "walking"  # Google Routes API - walking
    DRIVING = "driving"  # Google Routes API - driving
    TRANSIT = "transit"  # Google Routes API - public transit


@dataclass(frozen=True)
class DistanceResult:
    """
    Immutable result of a distance calculation.

    Attributes:
        km: Distance in kilometers (rounded to 2 decimals)
        formatted: Human-readable distance (e.g., "350 m", "2.1 km")
        mode: Calculation mode used
        reference: Optional localized reference text (e.g., "depuis votre position")
        duration_minutes: Optional travel time (only for Routes API)
    """

    km: float
    formatted: str
    mode: DistanceMode
    reference: str | None = None
    duration_minutes: int | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            "distance_km": self.km,
            "distance": self.formatted,
            "distance_mode": self.mode.value,
        }
        if self.reference:
            result["distance_reference"] = self.reference
        if self.duration_minutes is not None:
            result["duration_minutes"] = self.duration_minutes
        return result


@runtime_checkable
class DistanceCalculator(Protocol):
    """
    Protocol for distance calculation strategies.

    Implement this protocol to add new distance calculation methods
    (e.g., Google Routes API, GraphHopper, OSRM, etc.)
    """

    async def calculate(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> DistanceResult:
        """
        Calculate distance between two points.

        Args:
            origin_lat, origin_lon: Origin coordinates
            dest_lat, dest_lon: Destination coordinates

        Returns:
            DistanceResult with distance information
        """
        ...

    @property
    def mode(self) -> DistanceMode:
        """Return the calculation mode used by this calculator."""
        ...


# =============================================================================
# HAVERSINE CALCULATOR (Default/Fallback)
# =============================================================================

# Earth's radius in kilometers (mean radius)
EARTH_RADIUS_KM = 6371.0


def _haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate straight-line distance using the Haversine formula.

    This gives the shortest distance over the earth's surface
    (great-circle distance).

    Args:
        lat1, lon1: First point coordinates (degrees)
        lat2, lon2: Second point coordinates (degrees)

    Returns:
        Distance in kilometers
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


def _format_distance(distance_km: float) -> str:
    """
    Format distance for human-readable display.

    Rules:
    - < 1 km: show in meters (e.g., "350 m")
    - 1-10 km: show with 1 decimal (e.g., "2.1 km")
    - >= 10 km: show as integer (e.g., "15 km")
    """
    if distance_km < 1:
        return f"{int(distance_km * 1000)} m"
    elif distance_km < 10:
        return f"{distance_km:.1f} km"
    else:
        return f"{int(distance_km)} km"


class HaversineCalculator:
    """
    Default distance calculator using Haversine formula.

    Provides instant, free straight-line distance calculation.
    Used as fallback when Google Routes API is not available.
    """

    @property
    def mode(self) -> DistanceMode:
        return DistanceMode.STRAIGHT_LINE

    async def calculate(
        self,
        origin_lat: float,
        origin_lon: float,
        dest_lat: float,
        dest_lon: float,
    ) -> DistanceResult:
        """Calculate straight-line distance using Haversine formula."""
        distance_km = _haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
        distance_km_rounded = round(distance_km, 2)

        return DistanceResult(
            km=distance_km_rounded,
            formatted=_format_distance(distance_km),
            mode=self.mode,
        )


# =============================================================================
# PUBLIC API
# =============================================================================

# Default calculator instance (singleton)
_default_calculator: DistanceCalculator = HaversineCalculator()


def get_calculator() -> DistanceCalculator:
    """Get the current distance calculator."""
    return _default_calculator


def set_calculator(calculator: DistanceCalculator) -> None:
    """
    Set a custom distance calculator.

    Use this to switch to Google Routes API when available:
        from src.domains.agents.utils.distance import set_calculator
        set_calculator(GoogleRoutesCalculator(client))
    """
    global _default_calculator
    _default_calculator = calculator


async def calculate_distance(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    source: str | None = None,
    language: str = "fr",
    calculator: DistanceCalculator | None = None,
) -> DistanceResult:
    """
    Calculate distance between two points.

    This is the main entry point for distance calculation.
    Uses the default calculator (Haversine) unless a custom one is provided.

    Args:
        origin_lat, origin_lon: Origin coordinates
        dest_lat, dest_lon: Destination coordinates
        source: Location source for reference text ("browser", "home", or None)
        language: Language for reference text (fr, en, es, de, it, zh-CN)
        calculator: Optional custom calculator (uses default if None)

    Returns:
        DistanceResult with distance information and optional reference

    Example:
        result = await calculate_distance(
            origin_lat=48.8566, origin_lon=2.3522,
            dest_lat=48.8584, dest_lon=2.2945,
            source="browser",
            language="fr",
        )
        print(result.formatted)   # "2.1 km"
        print(result.reference)   # "depuis votre position"
    """
    calc = calculator or _default_calculator
    result = await calc.calculate(origin_lat, origin_lon, dest_lat, dest_lon)

    # Add reference text if source is provided
    if source:
        reference = get_distance_reference(source, language)
        # Create new result with reference (DistanceResult is immutable)
        result = DistanceResult(
            km=result.km,
            formatted=result.formatted,
            mode=result.mode,
            reference=reference,
            duration_minutes=result.duration_minutes,
        )

    return result


# Convenience function for synchronous contexts (wraps async)
def calculate_distance_sync(
    origin_lat: float,
    origin_lon: float,
    dest_lat: float,
    dest_lon: float,
    source: str | None = None,
    language: str = "fr",
) -> DistanceResult:
    """
    Synchronous version of calculate_distance using Haversine only.

    Note: This always uses Haversine (no async API calls).
    For async contexts, prefer calculate_distance().
    """
    distance_km = _haversine_distance(origin_lat, origin_lon, dest_lat, dest_lon)
    distance_km_rounded = round(distance_km, 2)
    reference = get_distance_reference(source, language) if source else None

    return DistanceResult(
        km=distance_km_rounded,
        formatted=_format_distance(distance_km),
        mode=DistanceMode.STRAIGHT_LINE,
        reference=reference,
    )


# =============================================================================
# VIEWPORT UTILITIES (for Google Places locationRestriction)
# =============================================================================


@dataclass(frozen=True)
class Viewport:
    """
    Rectangular viewport defined by southwest and northeast corners.

    Used for Google Places locationRestriction which requires a rectangle,
    not a circle. This is the bounding box of a circle.

    Attributes:
        sw_lat: Southwest corner latitude
        sw_lon: Southwest corner longitude
        ne_lat: Northeast corner latitude
        ne_lon: Northeast corner longitude
    """

    sw_lat: float
    sw_lon: float
    ne_lat: float
    ne_lon: float

    def to_dict(self) -> dict:
        """
        Convert to Google Places API locationRestriction format.

        Returns:
            Dict with 'rectangle' containing 'low' (SW) and 'high' (NE) corners.
        """
        return {
            "rectangle": {
                "low": {"latitude": self.sw_lat, "longitude": self.sw_lon},
                "high": {"latitude": self.ne_lat, "longitude": self.ne_lon},
            }
        }


# Constants for geo calculations
KM_PER_DEGREE_LAT = 111.0  # ~111 km per degree of latitude


def circle_to_viewport(
    center_lat: float,
    center_lon: float,
    radius_meters: float,
) -> Viewport:
    """
    Convert a circle to a bounding box (viewport).

    Used for Google Places Text Search which requires locationRestriction
    as a rectangle, not a circle like locationBias.

    The bounding box is the smallest rectangle that fully contains the circle.

    Args:
        center_lat: Center latitude in degrees
        center_lon: Center longitude in degrees
        radius_meters: Radius in meters

    Returns:
        Viewport with SW and NE corners

    Example:
        >>> vp = circle_to_viewport(48.8566, 2.3522, 500)
        >>> print(vp.to_dict())
        {"rectangle": {"low": {...}, "high": {...}}}
    """
    radius_km = radius_meters / 1000.0

    # Latitude offset: 1 degree ≈ 111 km (constant)
    lat_offset = radius_km / KM_PER_DEGREE_LAT

    # Longitude offset: depends on latitude (shrinks towards poles)
    # 1 degree longitude ≈ 111 km * cos(latitude)
    km_per_degree_lon = KM_PER_DEGREE_LAT * math.cos(math.radians(center_lat))
    if km_per_degree_lon > 0:
        lon_offset = radius_km / km_per_degree_lon
    else:
        lon_offset = 0  # Edge case at poles

    return Viewport(
        sw_lat=center_lat - lat_offset,
        sw_lon=center_lon - lon_offset,
        ne_lat=center_lat + lat_offset,
        ne_lon=center_lon + lon_offset,
    )
