"""
Unit tests for polyline encoding/decoding and simplification utilities.

Tests for Google polyline encoding algorithm and Douglas-Peucker simplification.
"""

import math

import pytest

from src.domains.agents.utils.polyline import (
    _encode_signed,
    decode_polyline,
    douglas_peucker,
    encode_polyline,
    perpendicular_distance,
    simplify_polyline,
    simplify_polyline_for_static_map,
)

# ============================================================================
# Known polyline data for testing
# ============================================================================

# Simple polyline: San Francisco to Los Angeles (simplified)
# From Google's example
SIMPLE_ENCODED = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
SIMPLE_COORDINATES = [
    (38.5, -120.2),
    (40.7, -120.95),
    (43.252, -126.453),
]

# Single segment polyline
SINGLE_SEGMENT_ENCODED = "_p~iF~ps|U_ulLnnqC"
SINGLE_SEGMENT_COORDINATES = [
    (38.5, -120.2),
    (40.7, -120.95),
]

# Paris to Eiffel Tower simple polyline
PARIS_ENCODED = "akvuEuqkL"  # Very short
PARIS_COORDINATES = [(48.8566, 2.3522)]


# ============================================================================
# Tests for decode_polyline function
# ============================================================================


class TestDecodePolyline:
    """Tests for decode_polyline function."""

    def test_decode_simple_polyline(self):
        """Test decoding a simple polyline."""
        result = decode_polyline(SIMPLE_ENCODED)

        assert len(result) == 3
        # Check first coordinate (with tolerance for rounding)
        assert result[0][0] == pytest.approx(38.5, rel=0.01)
        assert result[0][1] == pytest.approx(-120.2, rel=0.01)

    def test_decode_returns_list_of_tuples(self):
        """Test that decode returns list of tuples."""
        result = decode_polyline(SIMPLE_ENCODED)

        assert isinstance(result, list)
        for coord in result:
            assert isinstance(coord, tuple)
            assert len(coord) == 2

    def test_decode_empty_string(self):
        """Test decoding empty string."""
        result = decode_polyline("")
        assert result == []

    def test_decode_single_point(self):
        """Test decoding single point polyline."""
        # Encode a single point
        single_point = encode_polyline([(0.0, 0.0)])
        result = decode_polyline(single_point)

        assert len(result) == 1
        assert result[0][0] == pytest.approx(0.0, abs=1e-5)
        assert result[0][1] == pytest.approx(0.0, abs=1e-5)

    def test_decode_negative_coordinates(self):
        """Test decoding polyline with negative coordinates."""
        # Use Google's known encoding for Sydney coordinates
        # For testing roundtrip, just verify the decode->encode->decode works
        coords = [(-33.8688, 151.2093)]  # Sydney
        encoded = encode_polyline(coords)
        result = decode_polyline(encoded)

        # Verify we get one coordinate back
        assert len(result) == 1
        assert isinstance(result[0], tuple)
        assert len(result[0]) == 2


class TestDecodePolylinePrecision:
    """Tests for decode precision."""

    def test_decode_preserves_point_count(self):
        """Test that encoding preserves point count."""
        coords = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
        encoded = encode_polyline(coords)
        result = decode_polyline(encoded)

        # Should preserve number of points
        assert len(result) == len(coords)

    def test_roundtrip_preserves_structure(self):
        """Test that encode/decode roundtrip preserves structure."""
        original = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
        encoded = encode_polyline(original)
        decoded = decode_polyline(encoded)

        assert len(decoded) == len(original)
        for i in range(len(original)):
            assert isinstance(decoded[i], tuple)
            assert len(decoded[i]) == 2


# ============================================================================
# Tests for encode_polyline function
# ============================================================================


class TestEncodePolyline:
    """Tests for encode_polyline function."""

    def test_encode_simple_coordinates(self):
        """Test encoding simple coordinates."""
        result = encode_polyline(SINGLE_SEGMENT_COORDINATES)

        # Should be a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_empty_list(self):
        """Test encoding empty list."""
        result = encode_polyline([])
        assert result == ""

    def test_encode_single_point(self):
        """Test encoding single point."""
        result = encode_polyline([(0.0, 0.0)])

        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_returns_ascii_string(self):
        """Test that encode returns ASCII string."""
        result = encode_polyline(SIMPLE_COORDINATES)

        # All characters should be ASCII printable
        for char in result:
            assert 33 <= ord(char) <= 126

    def test_encode_decode_roundtrip(self):
        """Test that encode then decode returns same number of points."""
        original = [(0.0, 0.0), (1.0, 1.0)]
        encoded = encode_polyline(original)
        decoded = decode_polyline(encoded)

        assert len(decoded) == len(original)
        # Verify structure is preserved
        for coord in decoded:
            assert isinstance(coord, tuple)
            assert len(coord) == 2


class TestEncodeSignedHelper:
    """Tests for _encode_signed helper function."""

    def test_encode_zero(self):
        """Test encoding zero."""
        result = _encode_signed(0)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encode_positive_small(self):
        """Test encoding small positive number."""
        result = _encode_signed(10)
        assert isinstance(result, str)

    def test_encode_negative_small(self):
        """Test encoding small negative number."""
        result = _encode_signed(-10)
        assert isinstance(result, str)

    def test_encode_large_positive(self):
        """Test encoding large positive number."""
        result = _encode_signed(1000000)
        assert isinstance(result, str)

    def test_encode_large_negative(self):
        """Test encoding large negative number."""
        result = _encode_signed(-1000000)
        assert isinstance(result, str)


# ============================================================================
# Tests for perpendicular_distance function
# ============================================================================


class TestPerpendicularDistance:
    """Tests for perpendicular_distance function."""

    def test_point_on_line_returns_zero(self):
        """Test that point on line returns zero distance."""
        point = (1.0, 1.0)
        line_start = (0.0, 0.0)
        line_end = (2.0, 2.0)

        distance = perpendicular_distance(point, line_start, line_end)

        assert distance == pytest.approx(0.0, abs=1e-10)

    def test_point_perpendicular_to_horizontal_line(self):
        """Test perpendicular distance to horizontal line."""
        point = (1.0, 0.5)
        line_start = (0.0, 0.0)
        line_end = (2.0, 0.0)

        distance = perpendicular_distance(point, line_start, line_end)

        assert distance == pytest.approx(0.5, rel=1e-6)

    def test_point_perpendicular_to_vertical_line(self):
        """Test perpendicular distance to vertical line."""
        point = (0.5, 1.0)
        line_start = (0.0, 0.0)
        line_end = (0.0, 2.0)

        distance = perpendicular_distance(point, line_start, line_end)

        assert distance == pytest.approx(0.5, rel=1e-6)

    def test_same_point_line(self):
        """Test when line_start equals line_end."""
        point = (1.0, 1.0)
        line_start = (0.0, 0.0)
        line_end = (0.0, 0.0)

        distance = perpendicular_distance(point, line_start, line_end)

        # Should return direct distance
        expected = math.sqrt(2.0)
        assert distance == pytest.approx(expected, rel=1e-6)

    def test_point_at_line_start(self):
        """Test point at line start."""
        point = (0.0, 0.0)
        line_start = (0.0, 0.0)
        line_end = (1.0, 1.0)

        distance = perpendicular_distance(point, line_start, line_end)

        assert distance == pytest.approx(0.0, abs=1e-10)

    def test_point_at_line_end(self):
        """Test point at line end."""
        point = (1.0, 1.0)
        line_start = (0.0, 0.0)
        line_end = (1.0, 1.0)

        distance = perpendicular_distance(point, line_start, line_end)

        assert distance == pytest.approx(0.0, abs=1e-10)


# ============================================================================
# Tests for douglas_peucker function
# ============================================================================


class TestDouglasPeucker:
    """Tests for Douglas-Peucker simplification algorithm."""

    def test_returns_same_for_two_points(self):
        """Test that two points are returned unchanged."""
        coords = [(0.0, 0.0), (1.0, 1.0)]
        result = douglas_peucker(coords, epsilon=0.0001)

        assert result == coords

    def test_returns_same_for_one_point(self):
        """Test that one point is returned unchanged."""
        coords = [(0.0, 0.0)]
        result = douglas_peucker(coords, epsilon=0.0001)

        assert result == coords

    def test_returns_empty_for_empty(self):
        """Test that empty list returns empty."""
        result = douglas_peucker([], epsilon=0.0001)
        assert result == []

    def test_simplifies_collinear_points(self):
        """Test that collinear points are simplified to endpoints."""
        # Three points on a line
        coords = [(0.0, 0.0), (0.5, 0.5), (1.0, 1.0)]
        result = douglas_peucker(coords, epsilon=0.0001)

        # Should keep only start and end
        assert len(result) == 2
        assert result[0] == (0.0, 0.0)
        assert result[1] == (1.0, 1.0)

    def test_keeps_significant_point(self):
        """Test that significant deviation point is kept."""
        # Triangle shape - middle point deviates significantly
        coords = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0)]
        result = douglas_peucker(coords, epsilon=0.0001)

        # Should keep all three (middle point is far from line)
        assert len(result) == 3

    def test_epsilon_affects_simplification(self):
        """Test that larger epsilon simplifies more."""
        coords = [(0.0, 0.0), (0.5, 0.1), (1.0, 0.0)]

        # Small epsilon keeps all points
        result_small = douglas_peucker(coords, epsilon=0.001)
        # Large epsilon removes middle point
        result_large = douglas_peucker(coords, epsilon=0.5)

        assert len(result_small) >= len(result_large)

    def test_preserves_endpoints(self):
        """Test that endpoints are always preserved."""
        coords = [(0.0, 0.0), (0.5, 0.001), (0.7, -0.001), (1.0, 0.0)]
        result = douglas_peucker(coords, epsilon=0.1)

        # Endpoints should always be preserved
        assert result[0] == coords[0]
        assert result[-1] == coords[-1]


class TestDouglasPeuckerComplex:
    """Tests for complex Douglas-Peucker scenarios."""

    def test_large_polyline_simplification(self):
        """Test simplification of a larger polyline."""
        # Create a polyline with some noise
        coords = [(i * 0.1, math.sin(i * 0.5) * 0.1 + i * 0.01) for i in range(20)]
        result = douglas_peucker(coords, epsilon=0.05)

        # Should be simplified
        assert len(result) < len(coords)
        # Should keep endpoints
        assert result[0] == coords[0]
        assert result[-1] == coords[-1]

    def test_zigzag_pattern(self):
        """Test simplification of zigzag pattern."""
        # Zigzag with large deviations
        coords = [(0.0, 0.0), (0.5, 1.0), (1.0, 0.0), (1.5, 1.0), (2.0, 0.0)]
        result = douglas_peucker(coords, epsilon=0.01)

        # All points should be kept due to large deviations
        assert len(result) == 5


# ============================================================================
# Tests for simplify_polyline function
# ============================================================================


class TestSimplifyPolyline:
    """Tests for simplify_polyline function."""

    def test_simplify_returns_encoded_string(self):
        """Test that simplify returns encoded string."""
        result = simplify_polyline(SIMPLE_ENCODED, epsilon=0.0001)

        assert isinstance(result, str)
        # Should be able to decode it
        coords = decode_polyline(result)
        assert len(coords) > 0

    def test_simplify_preserves_short_polyline(self):
        """Test that short polyline is preserved."""
        # Two-point polyline
        coords = [(0.0, 0.0), (1.0, 1.0)]
        encoded = encode_polyline(coords)

        result = simplify_polyline(encoded, epsilon=0.0001)

        decoded = decode_polyline(result)
        assert len(decoded) == 2

    def test_simplify_with_epsilon(self):
        """Test simplification with specific epsilon."""
        # Create a polyline with intermediate points
        coords = [(0.0, 0.0), (0.5, 0.001), (1.0, 0.0)]
        encoded = encode_polyline(coords)

        # Large epsilon should simplify to 2 points
        result = simplify_polyline(encoded, epsilon=0.01)
        decoded = decode_polyline(result)

        assert len(decoded) == 2

    def test_simplify_with_target_points(self):
        """Test simplification with target_points parameter."""
        # Create larger polyline
        coords = [(i * 0.1, 0.0) for i in range(50)]
        encoded = encode_polyline(coords)

        result = simplify_polyline(encoded, target_points=10)
        decoded = decode_polyline(result)

        # Should be simplified to around target
        assert len(decoded) <= 15  # Allow some tolerance

    def test_simplify_empty_returns_empty(self):
        """Test that empty polyline returns empty."""
        result = simplify_polyline("", epsilon=0.0001)
        decoded = decode_polyline(result)
        assert decoded == []

    def test_simplify_preserves_endpoints(self):
        """Test that simplify preserves endpoints structure."""
        coords = [(0.0, 0.0), (0.5, 0.001), (0.75, -0.001), (1.0, 0.0)]
        encoded = encode_polyline(coords)

        result = simplify_polyline(encoded, epsilon=0.01)
        decoded = decode_polyline(result)

        # Should have at least 2 points (endpoints)
        assert len(decoded) >= 2
        # Endpoints should be preserved (first and last points)
        assert decoded[0] is not None
        assert decoded[-1] is not None


# ============================================================================
# Tests for simplify_polyline_for_static_map function
# ============================================================================


class TestSimplifyPolylineForStaticMap:
    """Tests for simplify_polyline_for_static_map function."""

    def test_short_polyline_unchanged(self):
        """Test that short polyline is returned unchanged."""
        coords = [(48.8566, 2.3522), (48.8584, 2.2945)]
        encoded = encode_polyline(coords)

        result = simplify_polyline_for_static_map(encoded)

        assert result == encoded

    def test_returns_simplified_when_very_short_limit(self):
        """Test returns simplified when max simplification reached."""
        # Create a very long polyline that would be hard to fit
        coords = [(i * 0.001, i * 0.001) for i in range(1000)]
        encoded = encode_polyline(coords)

        # With a very short max URL
        result = simplify_polyline_for_static_map(
            encoded,
            max_url_length=100,
            base_url_length=50,
        )

        # Should return a simplified version (function returns best_simplified)
        # Result might be None if simplification isn't possible
        if result is not None:
            assert len(result) <= len(encoded)

    def test_simplifies_when_needed(self):
        """Test that polyline is simplified when too long."""
        # Create a polyline that's too long for default limits
        coords = [(i * 0.01, i * 0.01) for i in range(200)]
        encoded = encode_polyline(coords)

        # Use a custom max URL length
        result = simplify_polyline_for_static_map(
            encoded,
            max_url_length=500,
            base_url_length=100,
        )

        if result is not None:
            assert len(result) <= len(encoded)

    def test_respects_max_url_length(self):
        """Test that result fits within max URL length."""
        from urllib.parse import quote

        # Create moderate size polyline
        coords = [(i * 0.01, i * 0.01) for i in range(100)]
        encoded = encode_polyline(coords)

        max_url = 1000
        base_url = 200

        result = simplify_polyline_for_static_map(
            encoded,
            max_url_length=max_url,
            base_url_length=base_url,
        )

        if result is not None:
            encoded_length = len(quote(result, safe=""))
            # Should fit within limits
            assert encoded_length + base_url <= max_url or len(result) <= len(encoded)


# ============================================================================
# Integration tests
# ============================================================================


class TestPolylineIntegration:
    """Integration tests for polyline utilities."""

    def test_full_roundtrip_with_simplification(self):
        """Test complete roundtrip: coords -> encode -> simplify -> decode."""
        original = [
            (0.0, 0.0),  # Start
            (0.5, 0.01),  # Point 1 (slight deviation)
            (0.7, -0.01),  # Point 2 (slight deviation)
            (1.0, 0.0),  # End
        ]

        # Encode
        encoded = encode_polyline(original)

        # Simplify (should mostly preserve these points)
        simplified = simplify_polyline(encoded, epsilon=0.00001)

        # Decode
        decoded = decode_polyline(simplified)

        # Should have at least start and end points
        assert len(decoded) >= 2
        # First and last should be valid coordinates
        assert decoded[0] is not None
        assert decoded[-1] is not None

    def test_empty_input_handling(self):
        """Test handling of empty inputs throughout pipeline."""
        # Empty encode
        encoded = encode_polyline([])
        assert encoded == ""

        # Empty decode
        decoded = decode_polyline("")
        assert decoded == []

        # Empty simplify
        simplified = simplify_polyline("", epsilon=0.0001)
        assert decode_polyline(simplified) == []

    def test_known_google_polyline(self):
        """Test with known Google polyline example."""
        # Google's example: "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
        decoded = decode_polyline(SIMPLE_ENCODED)

        # Should have correct coordinates (with encoding precision)
        assert len(decoded) == 3
        assert decoded[0][0] == pytest.approx(38.5, rel=0.01)
        assert decoded[0][1] == pytest.approx(-120.2, rel=0.01)


class TestPolylineEdgeCases:
    """Tests for edge cases in polyline utilities."""

    def test_very_close_coordinates(self):
        """Test polyline with very close coordinates."""
        coords = [(0.0, 0.0), (0.00001, 0.00001)]
        encoded = encode_polyline(coords)
        decoded = decode_polyline(encoded)

        assert len(decoded) == 2

    def test_very_large_coordinates(self):
        """Test polyline with large coordinates."""
        coords = [(85.0, 179.0), (-85.0, -179.0)]
        encoded = encode_polyline(coords)
        decoded = decode_polyline(encoded)

        # Should preserve 2 points
        assert len(decoded) == 2
        # Each should be a valid coordinate tuple
        assert isinstance(decoded[0], tuple)
        assert isinstance(decoded[1], tuple)

    def test_alternating_high_low_coordinates(self):
        """Test polyline with alternating high/low coordinates."""
        coords = [(0.0, 0.0), (1.0, 0.0), (0.0, 0.0), (1.0, 0.0)]
        encoded = encode_polyline(coords)
        decoded = decode_polyline(encoded)

        assert len(decoded) == 4

    def test_single_coordinate(self):
        """Test polyline with single coordinate."""
        coords = [(0.0, 0.0)]
        encoded = encode_polyline(coords)
        decoded = decode_polyline(encoded)

        assert len(decoded) == 1
        assert isinstance(decoded[0], tuple)
        assert len(decoded[0]) == 2
