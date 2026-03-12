"""
Polyline encoding/decoding and simplification utilities.

Google polyline encoding algorithm implementation with Douglas-Peucker simplification
for reducing polyline length while preserving route shape.

Used to ensure static map URLs stay within Google's 16384 character limit.
"""

import math

from src.core.constants import (
    POLYLINE_EPSILON_VALUES,
    POLYLINE_MAX_EPSILON,
    STATIC_MAP_BASE_URL_LENGTH,
    STATIC_MAP_MAX_URL_LENGTH,
)


def decode_polyline(encoded: str) -> list[tuple[float, float]]:
    """
    Decode a Google-encoded polyline string into a list of (lat, lng) tuples.

    Google's polyline encoding algorithm compresses coordinates into ASCII characters.

    Args:
        encoded: Google-encoded polyline string

    Returns:
        List of (latitude, longitude) tuples
    """
    coordinates: list[tuple[float, float]] = []
    index = 0
    lat = 0
    lng = 0

    while index < len(encoded):
        # Decode latitude
        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lat += ~(result >> 1) if result & 1 else result >> 1

        # Decode longitude
        shift = 0
        result = 0
        while True:
            byte = ord(encoded[index]) - 63
            index += 1
            result |= (byte & 0x1F) << shift
            shift += 5
            if byte < 0x20:
                break
        lng += ~(result >> 1) if result & 1 else result >> 1

        coordinates.append((lat / 1e5, lng / 1e5))

    return coordinates


def encode_polyline(coordinates: list[tuple[float, float]]) -> str:
    """
    Encode a list of (lat, lng) tuples into a Google-encoded polyline string.

    Args:
        coordinates: List of (latitude, longitude) tuples

    Returns:
        Google-encoded polyline string
    """
    encoded = []
    prev_lat = 0
    prev_lng = 0

    for lat, lng in coordinates:
        # Convert to integer representation (5 decimal places)
        lat_int = round(lat * 1e5)
        lng_int = round(lng * 1e5)

        # Encode differences
        encoded.append(_encode_signed(lat_int - prev_lat))
        encoded.append(_encode_signed(lng_int - prev_lng))

        prev_lat = lat_int
        prev_lng = lng_int

    return "".join(encoded)


def _encode_signed(value: int) -> str:
    """Encode a single signed integer to polyline format."""
    # Left-shift and invert if negative
    value = ~(value << 1) if value < 0 else value << 1

    encoded = []
    while value >= 0x20:
        encoded.append(chr((value & 0x1F) | 0x20 + 63))
        value >>= 5
    encoded.append(chr(value + 63))

    return "".join(encoded)


def perpendicular_distance(
    point: tuple[float, float],
    line_start: tuple[float, float],
    line_end: tuple[float, float],
) -> float:
    """
    Calculate perpendicular distance from a point to a line segment.

    Uses simple Euclidean distance for efficiency (accurate enough for small areas).

    Args:
        point: (lat, lng) point
        line_start: (lat, lng) start of line
        line_end: (lat, lng) end of line

    Returns:
        Perpendicular distance (in coordinate units)
    """
    if line_start == line_end:
        return math.sqrt((point[0] - line_start[0]) ** 2 + (point[1] - line_start[1]) ** 2)

    # Calculate perpendicular distance using cross product
    dx = line_end[0] - line_start[0]
    dy = line_end[1] - line_start[1]

    # Normalize
    line_length = math.sqrt(dx * dx + dy * dy)

    if line_length == 0:
        return math.sqrt((point[0] - line_start[0]) ** 2 + (point[1] - line_start[1]) ** 2)

    # Cross product gives parallelogram area, divide by base for height
    cross = abs((point[0] - line_start[0]) * dy - (point[1] - line_start[1]) * dx)

    return cross / line_length


def douglas_peucker(
    coordinates: list[tuple[float, float]],
    epsilon: float,
) -> list[tuple[float, float]]:
    """
    Douglas-Peucker polyline simplification algorithm.

    Recursively simplifies a polyline by removing points that are within
    epsilon distance from the simplified line.

    Args:
        coordinates: List of (lat, lng) tuples
        epsilon: Maximum distance threshold (in coordinate units, ~0.00001 = ~1m)

    Returns:
        Simplified list of coordinates
    """
    if len(coordinates) <= 2:
        return coordinates

    # Find the point with maximum distance from line between start and end
    max_distance = 0.0
    max_index = 0

    for i in range(1, len(coordinates) - 1):
        distance = perpendicular_distance(coordinates[i], coordinates[0], coordinates[-1])
        if distance > max_distance:
            max_distance = distance
            max_index = i

    # If max distance is greater than epsilon, recursively simplify
    if max_distance > epsilon:
        # Recursive call on two halves
        left = douglas_peucker(coordinates[: max_index + 1], epsilon)
        right = douglas_peucker(coordinates[max_index:], epsilon)

        # Combine results (avoiding duplicate at split point)
        return left[:-1] + right
    else:
        # All points are within epsilon, keep only endpoints
        return [coordinates[0], coordinates[-1]]


def simplify_polyline(
    encoded: str,
    epsilon: float = 0.0001,
    target_points: int | None = None,
) -> str:
    """
    Simplify an encoded polyline using Douglas-Peucker algorithm.

    Args:
        encoded: Google-encoded polyline string
        epsilon: Distance threshold (0.0001 ~= 10m). Lower = more detail.
        target_points: Optional target number of points (auto-adjusts epsilon)

    Returns:
        Simplified encoded polyline string
    """
    # Decode
    coordinates = decode_polyline(encoded)

    if len(coordinates) <= 2:
        return encoded

    # If target_points specified, iteratively find appropriate epsilon
    if target_points and len(coordinates) > target_points:
        # Binary search for appropriate epsilon
        max_eps = 0.01
        current_eps = epsilon

        for _ in range(10):  # Max 10 iterations
            simplified = douglas_peucker(coordinates, current_eps)

            if len(simplified) <= target_points:
                break
            elif len(simplified) > target_points * 1.5:
                # Too many points, increase epsilon
                current_eps = (current_eps + max_eps) / 2
            else:
                # Close enough
                break

        coordinates = simplified
    else:
        coordinates = douglas_peucker(coordinates, epsilon)

    # Re-encode
    return encode_polyline(coordinates)


def simplify_polyline_for_static_map(
    encoded: str,
    max_url_length: int = STATIC_MAP_MAX_URL_LENGTH,
    base_url_length: int = STATIC_MAP_BASE_URL_LENGTH,
) -> str | None:
    """
    Simplify a polyline to fit within Google Static Maps URL limit.

    Google Static Maps API has a URL limit of 16384 characters.
    This function progressively simplifies the polyline until it fits.

    Args:
        encoded: Google-encoded polyline string
        max_url_length: Maximum target URL length (default from STATIC_MAP_MAX_URL_LENGTH)
        base_url_length: Estimated length of URL without polyline (from STATIC_MAP_BASE_URL_LENGTH)

    Returns:
        Simplified polyline string, or None if cannot simplify enough
    """
    from urllib.parse import quote

    import structlog

    logger = structlog.get_logger(__name__)

    # Check if original fits
    test_encoded = quote(encoded, safe="")
    if len(test_encoded) + base_url_length <= max_url_length:
        return encoded

    original_length = len(encoded)

    # Progressive simplification with increasing epsilon
    # Values from POLYLINE_EPSILON_VALUES, capped at POLYLINE_MAX_EPSILON (~300m)
    # to avoid excessive route deformation while preserving accurate endpoints

    best_simplified = None
    best_epsilon = 0.0

    for epsilon in POLYLINE_EPSILON_VALUES:
        simplified = simplify_polyline(encoded, epsilon=epsilon)
        test_encoded = quote(simplified, safe="")
        best_simplified = simplified
        best_epsilon = epsilon

        if len(test_encoded) + base_url_length <= max_url_length:
            logger.info(
                "polyline_simplified",
                original_length=original_length,
                simplified_length=len(simplified),
                epsilon=epsilon,
                reduction_percent=round((1 - len(simplified) / original_length) * 100, 1),
            )
            return simplified

    # If we get here, even max epsilon wasn't enough to fit URL limit
    # Use the best simplified version we have rather than extreme deformation
    # The markers (A/B) will show accurate origin/destination
    if best_simplified:
        logger.warning(
            "polyline_max_simplification_reached",
            original_length=original_length,
            simplified_length=len(best_simplified),
            epsilon=best_epsilon,
            max_epsilon=POLYLINE_MAX_EPSILON,
            message=f"Using max epsilon ({POLYLINE_MAX_EPSILON}) to preserve route shape; markers ensure accuracy",
        )
        return best_simplified

    # Should never reach here, but just in case
    logger.warning(
        "polyline_cannot_simplify",
        original_length=original_length,
    )
    return None
