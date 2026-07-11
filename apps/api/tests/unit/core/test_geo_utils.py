"""
Unit tests for geographic utility functions.

Tests for the Haversine great-circle distance formula and its constants,
promoted to core from the agents distance module (ADR-126).
"""

import pytest

from src.core.geo_utils import EARTH_RADIUS_KM, haversine_distance

# ============================================================================
# Known coordinates for testing
# ============================================================================

# Paris center (Place de la Concorde)
PARIS_LAT, PARIS_LON = 48.8656, 2.3212

# Eiffel Tower
EIFFEL_LAT, EIFFEL_LON = 48.8584, 2.2945

# Arc de Triomphe
ARC_LAT, ARC_LON = 48.8738, 2.2950

# Lyon (far from Paris)
LYON_LAT, LYON_LON = 45.7640, 4.8357

# New York (very far from Paris)
NY_LAT, NY_LON = 40.7128, -74.0060

# Same point (for zero distance test)
SAME_LAT, SAME_LON = 48.8566, 2.3522


class TestHaversineDistance:
    """Tests for haversine_distance function."""

    def test_zero_distance_same_point(self):
        """Test that same point returns zero distance."""
        distance = haversine_distance(SAME_LAT, SAME_LON, SAME_LAT, SAME_LON)
        assert distance == 0.0

    def test_paris_to_eiffel_tower(self):
        """Test distance from Paris center to Eiffel Tower (~2km)."""
        distance = haversine_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Expected ~2 km
        assert 1.5 < distance < 3.0

    def test_paris_to_arc_de_triomphe(self):
        """Test distance from Paris center to Arc de Triomphe (~2km)."""
        distance = haversine_distance(PARIS_LAT, PARIS_LON, ARC_LAT, ARC_LON)

        # Expected ~2 km
        assert 1.5 < distance < 3.0

    def test_paris_to_lyon(self):
        """Test distance from Paris to Lyon (~400km)."""
        distance = haversine_distance(PARIS_LAT, PARIS_LON, LYON_LAT, LYON_LON)

        # Expected ~400 km
        assert 350 < distance < 500

    def test_paris_to_new_york(self):
        """Test transatlantic distance Paris to New York (~5800km)."""
        distance = haversine_distance(PARIS_LAT, PARIS_LON, NY_LAT, NY_LON)

        # Expected ~5800 km
        assert 5500 < distance < 6200

    def test_symmetry(self):
        """Test that distance is symmetric (A to B == B to A)."""
        dist_ab = haversine_distance(PARIS_LAT, PARIS_LON, LYON_LAT, LYON_LON)
        dist_ba = haversine_distance(LYON_LAT, LYON_LON, PARIS_LAT, PARIS_LON)

        assert dist_ab == pytest.approx(dist_ba)

    def test_equator_90_degrees(self):
        """Test distance along equator for 90 degrees longitude."""
        # At equator, 90 degrees = ~10,000 km (quarter circumference)
        distance = haversine_distance(0, 0, 0, 90)

        # Expected ~10,000 km
        assert 9500 < distance < 10500

    def test_pole_to_pole(self):
        """Test distance from north pole to south pole."""
        # Half circumference ~20,000 km
        distance = haversine_distance(90, 0, -90, 0)

        # Expected ~20,000 km
        assert 19500 < distance < 20500

    def test_small_distance_meters(self):
        """Test very small distance (few hundred meters)."""
        # Two points ~500m apart
        lat1, lon1 = 48.8566, 2.3522
        lat2, lon2 = 48.8610, 2.3522  # ~490m north

        distance = haversine_distance(lat1, lon1, lat2, lon2)

        assert 0.4 < distance < 0.6  # ~500m = 0.5km


class TestHaversineDistanceEdgeCases:
    """Tests for edge cases in Haversine distance calculation."""

    def test_negative_coordinates(self):
        """Test with negative coordinates (southern/western hemisphere)."""
        # Sydney, Australia
        sydney_lat, sydney_lon = -33.8688, 151.2093
        # Cape Town, South Africa
        capetown_lat, capetown_lon = -33.9249, 18.4241

        distance = haversine_distance(sydney_lat, sydney_lon, capetown_lat, capetown_lon)

        # Expected ~11,000 km
        assert 10500 < distance < 12000

    def test_date_line_crossing(self):
        """Test distance crossing the international date line."""
        # Point east of date line
        lat1, lon1 = 40.0, 179.0
        # Point west of date line
        lat2, lon2 = 40.0, -179.0

        distance = haversine_distance(lat1, lon1, lat2, lon2)

        # Should be ~2 degrees longitude at 40°N ≈ ~170 km
        assert 150 < distance < 200

    def test_near_poles(self):
        """Test distance calculation near the poles."""
        # Two points near north pole
        lat1, lon1 = 89.0, 0.0
        lat2, lon2 = 89.0, 180.0

        distance = haversine_distance(lat1, lon1, lat2, lon2)

        # Should be ~220 km (almost across the pole)
        assert 200 < distance < 250


class TestConstants:
    """Tests for module constants."""

    def test_earth_radius_km(self):
        """Test EARTH_RADIUS_KM constant."""
        # Earth's mean radius is approximately 6371 km
        assert EARTH_RADIUS_KM == 6371.0
