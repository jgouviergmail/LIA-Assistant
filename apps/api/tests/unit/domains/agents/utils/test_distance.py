"""
Unit tests for distance calculation utilities.

Tests for distance calculations using Haversine formula,
distance formatting, viewport utilities, and the extensible calculator architecture.
"""

from unittest.mock import patch

import pytest

from src.domains.agents.utils.distance import (
    EARTH_RADIUS_KM,
    KM_PER_DEGREE_LAT,
    DistanceCalculator,
    DistanceMode,
    DistanceResult,
    HaversineCalculator,
    Viewport,
    _format_distance,
    _haversine_distance,
    calculate_distance,
    calculate_distance_sync,
    circle_to_viewport,
    get_calculator,
    set_calculator,
)

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


# ============================================================================
# Tests for DistanceMode enum
# ============================================================================


class TestDistanceMode:
    """Tests for DistanceMode enum."""

    def test_straight_line_mode_exists(self):
        """Test that STRAIGHT_LINE mode exists."""
        assert DistanceMode.STRAIGHT_LINE.value == "straight_line"

    def test_walking_mode_exists(self):
        """Test that WALKING mode exists."""
        assert DistanceMode.WALKING.value == "walking"

    def test_driving_mode_exists(self):
        """Test that DRIVING mode exists."""
        assert DistanceMode.DRIVING.value == "driving"

    def test_transit_mode_exists(self):
        """Test that TRANSIT mode exists."""
        assert DistanceMode.TRANSIT.value == "transit"

    def test_distance_mode_is_str_enum(self):
        """Test that DistanceMode is a string enum."""
        assert isinstance(DistanceMode.STRAIGHT_LINE, str)
        # value property returns the string value
        assert DistanceMode.STRAIGHT_LINE.value == "straight_line"
        # Can be used in string comparisons via .value
        assert DistanceMode.STRAIGHT_LINE == "straight_line"

    def test_all_modes_present(self):
        """Test that all expected modes are present."""
        modes = [m.value for m in DistanceMode]
        assert "straight_line" in modes
        assert "walking" in modes
        assert "driving" in modes
        assert "transit" in modes


# ============================================================================
# Tests for DistanceResult dataclass
# ============================================================================


class TestDistanceResult:
    """Tests for DistanceResult dataclass."""

    def test_create_minimal_result(self):
        """Test creating result with required fields only."""
        result = DistanceResult(
            km=2.5,
            formatted="2.5 km",
            mode=DistanceMode.STRAIGHT_LINE,
        )

        assert result.km == 2.5
        assert result.formatted == "2.5 km"
        assert result.mode == DistanceMode.STRAIGHT_LINE
        assert result.reference is None
        assert result.duration_minutes is None

    def test_create_full_result(self):
        """Test creating result with all fields."""
        result = DistanceResult(
            km=5.2,
            formatted="5.2 km",
            mode=DistanceMode.DRIVING,
            reference="depuis votre position",
            duration_minutes=15,
        )

        assert result.km == 5.2
        assert result.formatted == "5.2 km"
        assert result.mode == DistanceMode.DRIVING
        assert result.reference == "depuis votre position"
        assert result.duration_minutes == 15

    def test_result_is_frozen(self):
        """Test that DistanceResult is immutable."""
        result = DistanceResult(
            km=1.0,
            formatted="1.0 km",
            mode=DistanceMode.STRAIGHT_LINE,
        )

        with pytest.raises(AttributeError):
            result.km = 2.0  # type: ignore

    def test_to_dict_minimal(self):
        """Test to_dict with minimal fields."""
        result = DistanceResult(
            km=3.14,
            formatted="3.1 km",
            mode=DistanceMode.STRAIGHT_LINE,
        )

        data = result.to_dict()

        assert data["distance_km"] == 3.14
        assert data["distance"] == "3.1 km"
        assert data["distance_mode"] == "straight_line"
        assert "distance_reference" not in data
        assert "duration_minutes" not in data

    def test_to_dict_with_reference(self):
        """Test to_dict includes reference when present."""
        result = DistanceResult(
            km=1.5,
            formatted="1.5 km",
            mode=DistanceMode.STRAIGHT_LINE,
            reference="depuis votre domicile",
        )

        data = result.to_dict()

        assert data["distance_reference"] == "depuis votre domicile"

    def test_to_dict_with_duration(self):
        """Test to_dict includes duration when present."""
        result = DistanceResult(
            km=10.0,
            formatted="10 km",
            mode=DistanceMode.DRIVING,
            duration_minutes=20,
        )

        data = result.to_dict()

        assert data["duration_minutes"] == 20

    def test_to_dict_with_all_fields(self):
        """Test to_dict includes all fields when present."""
        result = DistanceResult(
            km=7.89,
            formatted="7.9 km",
            mode=DistanceMode.TRANSIT,
            reference="from your location",
            duration_minutes=25,
        )

        data = result.to_dict()

        assert data == {
            "distance_km": 7.89,
            "distance": "7.9 km",
            "distance_mode": "transit",
            "distance_reference": "from your location",
            "duration_minutes": 25,
        }


# ============================================================================
# Tests for _haversine_distance function
# ============================================================================


class TestHaversineDistance:
    """Tests for _haversine_distance function."""

    def test_zero_distance_same_point(self):
        """Test that same point returns zero distance."""
        distance = _haversine_distance(SAME_LAT, SAME_LON, SAME_LAT, SAME_LON)
        assert distance == 0.0

    def test_paris_to_eiffel_tower(self):
        """Test distance from Paris center to Eiffel Tower (~2km)."""
        distance = _haversine_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Expected ~2 km
        assert 1.5 < distance < 3.0

    def test_paris_to_arc_de_triomphe(self):
        """Test distance from Paris center to Arc de Triomphe (~2km)."""
        distance = _haversine_distance(PARIS_LAT, PARIS_LON, ARC_LAT, ARC_LON)

        # Expected ~2 km
        assert 1.5 < distance < 3.0

    def test_paris_to_lyon(self):
        """Test distance from Paris to Lyon (~400km)."""
        distance = _haversine_distance(PARIS_LAT, PARIS_LON, LYON_LAT, LYON_LON)

        # Expected ~400 km
        assert 350 < distance < 500

    def test_paris_to_new_york(self):
        """Test transatlantic distance Paris to New York (~5800km)."""
        distance = _haversine_distance(PARIS_LAT, PARIS_LON, NY_LAT, NY_LON)

        # Expected ~5800 km
        assert 5500 < distance < 6200

    def test_symmetry(self):
        """Test that distance is symmetric (A to B == B to A)."""
        dist_ab = _haversine_distance(PARIS_LAT, PARIS_LON, LYON_LAT, LYON_LON)
        dist_ba = _haversine_distance(LYON_LAT, LYON_LON, PARIS_LAT, PARIS_LON)

        assert dist_ab == pytest.approx(dist_ba)

    def test_equator_90_degrees(self):
        """Test distance along equator for 90 degrees longitude."""
        # At equator, 90 degrees = ~10,000 km (quarter circumference)
        distance = _haversine_distance(0, 0, 0, 90)

        # Expected ~10,000 km
        assert 9500 < distance < 10500

    def test_pole_to_pole(self):
        """Test distance from north pole to south pole."""
        # Half circumference ~20,000 km
        distance = _haversine_distance(90, 0, -90, 0)

        # Expected ~20,000 km
        assert 19500 < distance < 20500

    def test_small_distance_meters(self):
        """Test very small distance (few hundred meters)."""
        # Two points ~500m apart
        lat1, lon1 = 48.8566, 2.3522
        lat2, lon2 = 48.8610, 2.3522  # ~490m north

        distance = _haversine_distance(lat1, lon1, lat2, lon2)

        assert 0.4 < distance < 0.6  # ~500m = 0.5km


class TestHaversineDistanceEdgeCases:
    """Tests for edge cases in Haversine distance calculation."""

    def test_negative_coordinates(self):
        """Test with negative coordinates (southern/western hemisphere)."""
        # Sydney, Australia
        sydney_lat, sydney_lon = -33.8688, 151.2093
        # Cape Town, South Africa
        capetown_lat, capetown_lon = -33.9249, 18.4241

        distance = _haversine_distance(sydney_lat, sydney_lon, capetown_lat, capetown_lon)

        # Expected ~11,000 km
        assert 10500 < distance < 12000

    def test_date_line_crossing(self):
        """Test distance crossing the international date line."""
        # Point east of date line
        lat1, lon1 = 40.0, 179.0
        # Point west of date line
        lat2, lon2 = 40.0, -179.0

        distance = _haversine_distance(lat1, lon1, lat2, lon2)

        # Should be ~2 degrees longitude at 40°N ≈ ~170 km
        assert 150 < distance < 200

    def test_near_poles(self):
        """Test distance calculation near the poles."""
        # Two points near north pole
        lat1, lon1 = 89.0, 0.0
        lat2, lon2 = 89.0, 180.0

        distance = _haversine_distance(lat1, lon1, lat2, lon2)

        # Should be ~220 km (almost across the pole)
        assert 200 < distance < 250


# ============================================================================
# Tests for _format_distance function
# ============================================================================


class TestFormatDistance:
    """Tests for _format_distance function."""

    def test_format_meters_100m(self):
        """Test formatting 100 meters."""
        result = _format_distance(0.1)
        assert result == "100 m"

    def test_format_meters_350m(self):
        """Test formatting 350 meters."""
        result = _format_distance(0.35)
        assert result == "350 m"

    def test_format_meters_999m(self):
        """Test formatting 999 meters (just under 1km)."""
        result = _format_distance(0.999)
        assert result == "999 m"

    def test_format_1km(self):
        """Test formatting exactly 1 km."""
        result = _format_distance(1.0)
        assert result == "1.0 km"

    def test_format_medium_distance(self):
        """Test formatting medium distance (1-10km) with decimal."""
        result = _format_distance(5.7)
        assert result == "5.7 km"

    def test_format_9_9km(self):
        """Test formatting 9.9 km (just under threshold)."""
        result = _format_distance(9.9)
        assert result == "9.9 km"

    def test_format_10km(self):
        """Test formatting exactly 10 km."""
        result = _format_distance(10.0)
        assert result == "10 km"

    def test_format_large_distance(self):
        """Test formatting large distance as integer."""
        result = _format_distance(456.789)
        assert result == "456 km"

    def test_format_very_small(self):
        """Test formatting very small distance."""
        result = _format_distance(0.01)
        assert result == "10 m"

    def test_format_zero(self):
        """Test formatting zero distance."""
        result = _format_distance(0.0)
        assert result == "0 m"


# ============================================================================
# Tests for HaversineCalculator class
# ============================================================================


class TestHaversineCalculator:
    """Tests for HaversineCalculator class."""

    @pytest.fixture
    def calculator(self):
        """Create calculator instance."""
        return HaversineCalculator()

    def test_mode_property(self, calculator):
        """Test that mode property returns STRAIGHT_LINE."""
        assert calculator.mode == DistanceMode.STRAIGHT_LINE

    @pytest.mark.asyncio
    async def test_calculate_returns_distance_result(self, calculator):
        """Test that calculate returns DistanceResult."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert isinstance(result, DistanceResult)

    @pytest.mark.asyncio
    async def test_calculate_distance_value(self, calculator):
        """Test that calculate returns correct distance."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Expected ~2 km
        assert 1.5 < result.km < 3.0

    @pytest.mark.asyncio
    async def test_calculate_mode_is_straight_line(self, calculator):
        """Test that result mode is STRAIGHT_LINE."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.mode == DistanceMode.STRAIGHT_LINE

    @pytest.mark.asyncio
    async def test_calculate_formatted_output(self, calculator):
        """Test that formatted output is correct format."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Should be in km format (1-10km range)
        assert "km" in result.formatted or "m" in result.formatted

    @pytest.mark.asyncio
    async def test_calculate_no_reference(self, calculator):
        """Test that calculator doesn't add reference."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.reference is None

    @pytest.mark.asyncio
    async def test_calculate_no_duration(self, calculator):
        """Test that calculator doesn't add duration."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.duration_minutes is None

    @pytest.mark.asyncio
    async def test_calculate_km_rounded_to_2_decimals(self, calculator):
        """Test that km is rounded to 2 decimal places."""
        result = await calculator.calculate(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Check rounding (multiply by 100 should be integer)
        assert result.km == round(result.km, 2)


class TestHaversineCalculatorProtocol:
    """Tests for DistanceCalculator protocol compliance."""

    def test_haversine_calculator_implements_protocol(self):
        """Test that HaversineCalculator implements DistanceCalculator protocol."""
        calculator = HaversineCalculator()

        # Should be instance of protocol (runtime_checkable)
        assert isinstance(calculator, DistanceCalculator)

    def test_protocol_has_mode_property(self):
        """Test that protocol requires mode property."""
        calculator = HaversineCalculator()

        assert hasattr(calculator, "mode")
        assert isinstance(calculator.mode, DistanceMode)

    def test_protocol_has_calculate_method(self):
        """Test that protocol requires calculate method."""
        calculator = HaversineCalculator()

        assert hasattr(calculator, "calculate")
        assert callable(calculator.calculate)


# ============================================================================
# Tests for calculate_distance function
# ============================================================================


class TestCalculateDistance:
    """Tests for calculate_distance async function."""

    @pytest.mark.asyncio
    async def test_basic_calculation(self):
        """Test basic distance calculation."""
        result = await calculate_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert isinstance(result, DistanceResult)
        assert 1.5 < result.km < 3.0

    @pytest.mark.asyncio
    async def test_default_has_no_reference(self):
        """Test that default call has no reference."""
        result = await calculate_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.reference is None

    @pytest.mark.asyncio
    @patch("src.domains.agents.utils.distance.get_distance_reference")
    async def test_with_browser_source(self, mock_get_ref):
        """Test with browser source adds reference."""
        mock_get_ref.return_value = "depuis votre position"

        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            language="fr",
        )

        assert result.reference == "depuis votre position"
        mock_get_ref.assert_called_once_with("browser", "fr")

    @pytest.mark.asyncio
    @patch("src.domains.agents.utils.distance.get_distance_reference")
    async def test_with_home_source(self, mock_get_ref):
        """Test with home source adds reference."""
        mock_get_ref.return_value = "depuis votre domicile"

        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="home",
            language="fr",
        )

        assert result.reference == "depuis votre domicile"
        mock_get_ref.assert_called_once_with("home", "fr")

    @pytest.mark.asyncio
    @patch("src.domains.agents.utils.distance.get_distance_reference")
    async def test_with_english_language(self, mock_get_ref):
        """Test with English language."""
        mock_get_ref.return_value = "from your location"

        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            language="en",
        )

        assert result.reference == "from your location"
        mock_get_ref.assert_called_once_with("browser", "en")

    @pytest.mark.asyncio
    async def test_uses_default_calculator(self):
        """Test that default calculator is used when none provided."""
        result = await calculate_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Default is HaversineCalculator which returns STRAIGHT_LINE mode
        assert result.mode == DistanceMode.STRAIGHT_LINE

    @pytest.mark.asyncio
    async def test_custom_calculator(self):
        """Test with custom calculator."""

        class CustomCalculator:
            @property
            def mode(self) -> DistanceMode:
                return DistanceMode.DRIVING

            async def calculate(
                self, origin_lat: float, origin_lon: float, dest_lat: float, dest_lon: float
            ) -> DistanceResult:
                return DistanceResult(
                    km=99.99,
                    formatted="100 km",
                    mode=self.mode,
                    duration_minutes=60,
                )

        custom = CustomCalculator()
        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            calculator=custom,
        )

        assert result.km == 99.99
        assert result.mode == DistanceMode.DRIVING
        assert result.duration_minutes == 60

    @pytest.mark.asyncio
    @patch("src.domains.agents.utils.distance.get_distance_reference")
    async def test_preserves_duration_from_calculator(self, mock_get_ref):
        """Test that duration from calculator is preserved when adding reference."""
        mock_get_ref.return_value = "test reference"

        class MockCalculator:
            @property
            def mode(self) -> DistanceMode:
                return DistanceMode.DRIVING

            async def calculate(self, *args, **kwargs) -> DistanceResult:
                return DistanceResult(
                    km=5.0,
                    formatted="5.0 km",
                    mode=self.mode,
                    duration_minutes=10,
                )

        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            calculator=MockCalculator(),
        )

        assert result.duration_minutes == 10
        assert result.reference == "test reference"


# ============================================================================
# Tests for calculate_distance_sync function
# ============================================================================


class TestCalculateDistanceSync:
    """Tests for calculate_distance_sync function."""

    def test_basic_calculation(self):
        """Test basic synchronous distance calculation."""
        result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert isinstance(result, DistanceResult)
        assert 1.5 < result.km < 3.0

    def test_mode_is_straight_line(self):
        """Test that sync version always uses straight line mode."""
        result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.mode == DistanceMode.STRAIGHT_LINE

    def test_default_has_no_reference(self):
        """Test that default call has no reference."""
        result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.reference is None

    @patch("src.domains.agents.utils.distance.get_distance_reference")
    def test_with_source_adds_reference(self, mock_get_ref):
        """Test with source parameter adds reference."""
        mock_get_ref.return_value = "depuis votre position"

        result = calculate_distance_sync(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            language="fr",
        )

        assert result.reference == "depuis votre position"

    @patch("src.domains.agents.utils.distance.get_distance_reference")
    def test_with_different_language(self, mock_get_ref):
        """Test with different language."""
        mock_get_ref.return_value = "von Ihrem Standort"

        result = calculate_distance_sync(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            language="de",
        )

        assert result.reference == "von Ihrem Standort"
        mock_get_ref.assert_called_once_with("browser", "de")

    def test_km_rounded_to_2_decimals(self):
        """Test that km is rounded to 2 decimal places."""
        result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.km == round(result.km, 2)

    def test_no_duration(self):
        """Test that sync version has no duration (Haversine only)."""
        result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        assert result.duration_minutes is None


# ============================================================================
# Tests for get_calculator and set_calculator functions
# ============================================================================


class TestCalculatorManagement:
    """Tests for calculator management functions."""

    def setup_method(self):
        """Reset to default calculator before each test."""
        set_calculator(HaversineCalculator())

    def teardown_method(self):
        """Reset to default calculator after each test."""
        set_calculator(HaversineCalculator())

    def test_get_calculator_returns_calculator(self):
        """Test that get_calculator returns a calculator."""
        calculator = get_calculator()

        assert isinstance(calculator, DistanceCalculator)

    def test_default_calculator_is_haversine(self):
        """Test that default calculator is HaversineCalculator."""
        calculator = get_calculator()

        assert isinstance(calculator, HaversineCalculator)

    def test_set_calculator_changes_default(self):
        """Test that set_calculator changes the default calculator."""

        class MockCalculator:
            @property
            def mode(self) -> DistanceMode:
                return DistanceMode.DRIVING

            async def calculate(self, *args, **kwargs) -> DistanceResult:
                return DistanceResult(
                    km=123.0,
                    formatted="123 km",
                    mode=self.mode,
                )

        mock = MockCalculator()
        set_calculator(mock)

        assert get_calculator() is mock

    @pytest.mark.asyncio
    async def test_calculate_distance_uses_set_calculator(self):
        """Test that calculate_distance uses the set calculator."""

        class MockCalculator:
            @property
            def mode(self) -> DistanceMode:
                return DistanceMode.WALKING

            async def calculate(self, *args, **kwargs) -> DistanceResult:
                return DistanceResult(
                    km=42.0,
                    formatted="42 km",
                    mode=self.mode,
                )

        set_calculator(MockCalculator())

        result = await calculate_distance(0, 0, 1, 1)

        assert result.km == 42.0
        assert result.mode == DistanceMode.WALKING


# ============================================================================
# Tests for Viewport dataclass
# ============================================================================


class TestViewport:
    """Tests for Viewport dataclass."""

    def test_create_viewport(self):
        """Test creating viewport with coordinates."""
        viewport = Viewport(
            sw_lat=48.0,
            sw_lon=2.0,
            ne_lat=49.0,
            ne_lon=3.0,
        )

        assert viewport.sw_lat == 48.0
        assert viewport.sw_lon == 2.0
        assert viewport.ne_lat == 49.0
        assert viewport.ne_lon == 3.0

    def test_viewport_is_frozen(self):
        """Test that Viewport is immutable."""
        viewport = Viewport(
            sw_lat=48.0,
            sw_lon=2.0,
            ne_lat=49.0,
            ne_lon=3.0,
        )

        with pytest.raises(AttributeError):
            viewport.sw_lat = 47.0  # type: ignore

    def test_to_dict_format(self):
        """Test that to_dict returns Google Places API format."""
        viewport = Viewport(
            sw_lat=48.5,
            sw_lon=2.0,
            ne_lat=49.5,
            ne_lon=3.0,
        )

        data = viewport.to_dict()

        assert "rectangle" in data
        assert "low" in data["rectangle"]
        assert "high" in data["rectangle"]
        assert data["rectangle"]["low"]["latitude"] == 48.5
        assert data["rectangle"]["low"]["longitude"] == 2.0
        assert data["rectangle"]["high"]["latitude"] == 49.5
        assert data["rectangle"]["high"]["longitude"] == 3.0

    def test_to_dict_structure(self):
        """Test complete to_dict structure."""
        viewport = Viewport(
            sw_lat=40.0,
            sw_lon=-74.5,
            ne_lat=41.0,
            ne_lon=-73.5,
        )

        expected = {
            "rectangle": {
                "low": {"latitude": 40.0, "longitude": -74.5},
                "high": {"latitude": 41.0, "longitude": -73.5},
            }
        }

        assert viewport.to_dict() == expected


# ============================================================================
# Tests for circle_to_viewport function
# ============================================================================


class TestCircleToViewport:
    """Tests for circle_to_viewport function."""

    def test_returns_viewport(self):
        """Test that function returns Viewport."""
        viewport = circle_to_viewport(PARIS_LAT, PARIS_LON, 1000)

        assert isinstance(viewport, Viewport)

    def test_small_radius_500m(self):
        """Test viewport for 500m radius."""
        viewport = circle_to_viewport(PARIS_LAT, PARIS_LON, 500)

        # SW should be south and west of center
        assert viewport.sw_lat < PARIS_LAT
        assert viewport.sw_lon < PARIS_LON

        # NE should be north and east of center
        assert viewport.ne_lat > PARIS_LAT
        assert viewport.ne_lon > PARIS_LON

    def test_viewport_is_symmetric(self):
        """Test that viewport is symmetric around center."""
        center_lat, center_lon = 48.8566, 2.3522
        radius = 1000  # 1km

        viewport = circle_to_viewport(center_lat, center_lon, radius)

        # Latitude offset should be symmetric
        lat_offset_sw = center_lat - viewport.sw_lat
        lat_offset_ne = viewport.ne_lat - center_lat
        assert lat_offset_sw == pytest.approx(lat_offset_ne, rel=1e-6)

        # Longitude offset should be symmetric
        lon_offset_sw = center_lon - viewport.sw_lon
        lon_offset_ne = viewport.ne_lon - center_lon
        assert lon_offset_sw == pytest.approx(lon_offset_ne, rel=1e-6)

    def test_larger_radius_gives_larger_viewport(self):
        """Test that larger radius gives larger viewport."""
        small = circle_to_viewport(PARIS_LAT, PARIS_LON, 500)
        large = circle_to_viewport(PARIS_LAT, PARIS_LON, 5000)

        # Larger viewport should have more extreme coordinates
        assert large.sw_lat < small.sw_lat
        assert large.sw_lon < small.sw_lon
        assert large.ne_lat > small.ne_lat
        assert large.ne_lon > small.ne_lon

    def test_latitude_offset_uses_constant(self):
        """Test that latitude offset uses KM_PER_DEGREE_LAT."""
        radius_km = 10.0  # 10 km
        radius_m = radius_km * 1000

        viewport = circle_to_viewport(0, 0, radius_m)

        expected_offset = radius_km / KM_PER_DEGREE_LAT
        actual_offset = viewport.ne_lat - 0

        assert actual_offset == pytest.approx(expected_offset, rel=1e-6)

    def test_longitude_offset_depends_on_latitude(self):
        """Test that longitude offset varies with latitude."""
        radius = 10000  # 10km

        # At equator
        equator_vp = circle_to_viewport(0, 0, radius)
        equator_lon_offset = equator_vp.ne_lon - 0

        # At 60 degrees latitude (longitude degrees are ~half as long)
        lat60_vp = circle_to_viewport(60, 0, radius)
        lat60_lon_offset = lat60_vp.ne_lon - 0

        # At higher latitude, longitude offset should be larger
        assert lat60_lon_offset > equator_lon_offset

    def test_near_pole_handles_edge_case(self):
        """Test behavior near poles (where cos(lat) approaches 0)."""
        # Very close to pole
        viewport = circle_to_viewport(89.9, 0, 1000)

        # Should not raise error
        assert isinstance(viewport, Viewport)

    def test_at_equator(self):
        """Test at equator where longitude degrees are longest."""
        radius_m = 1000

        viewport = circle_to_viewport(0, 0, radius_m)

        # At equator, lat and lon offsets should be approximately equal
        lat_offset = viewport.ne_lat - 0
        lon_offset = viewport.ne_lon - 0

        # Both should be ~0.009 degrees (1km / 111km)
        assert lat_offset == pytest.approx(lon_offset, rel=0.01)

    def test_conversion_from_meters_to_km(self):
        """Test that meters are correctly converted to km."""
        radius_m = 5000  # 5km
        viewport = circle_to_viewport(PARIS_LAT, PARIS_LON, radius_m)

        # Latitude offset should be ~5km / 111km = ~0.045 degrees
        lat_offset = viewport.ne_lat - PARIS_LAT
        expected_offset = 5.0 / KM_PER_DEGREE_LAT

        assert lat_offset == pytest.approx(expected_offset, rel=0.01)


# ============================================================================
# Tests for constants
# ============================================================================


class TestConstants:
    """Tests for module constants."""

    def test_earth_radius_km(self):
        """Test EARTH_RADIUS_KM constant."""
        # Earth's mean radius is approximately 6371 km
        assert EARTH_RADIUS_KM == 6371.0

    def test_km_per_degree_lat(self):
        """Test KM_PER_DEGREE_LAT constant."""
        # Approximately 111 km per degree of latitude
        assert KM_PER_DEGREE_LAT == 111.0


# ============================================================================
# Integration tests
# ============================================================================


class TestDistanceIntegration:
    """Integration tests combining multiple components."""

    @pytest.mark.asyncio
    async def test_full_flow_with_formatting(self):
        """Test complete flow from coordinates to formatted output."""
        result = await calculate_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        # Should have all expected fields
        assert result.km > 0
        assert result.formatted
        assert result.mode == DistanceMode.STRAIGHT_LINE

        # to_dict should work
        data = result.to_dict()
        assert "distance_km" in data
        assert "distance" in data

    @pytest.mark.asyncio
    @patch("src.domains.agents.utils.distance.get_distance_reference")
    async def test_full_flow_with_reference(self, mock_get_ref):
        """Test complete flow with reference text."""
        mock_get_ref.return_value = "depuis votre position"

        result = await calculate_distance(
            PARIS_LAT,
            PARIS_LON,
            EIFFEL_LAT,
            EIFFEL_LON,
            source="browser",
            language="fr",
        )

        data = result.to_dict()
        assert "distance_reference" in data
        assert data["distance_reference"] == "depuis votre position"

    def test_sync_and_async_give_same_distance(self):
        """Test that sync and async versions give same distance."""
        import asyncio

        async def get_async_result():
            return await calculate_distance(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)

        sync_result = calculate_distance_sync(PARIS_LAT, PARIS_LON, EIFFEL_LAT, EIFFEL_LON)
        async_result = asyncio.get_event_loop().run_until_complete(get_async_result())

        assert sync_result.km == async_result.km
        assert sync_result.mode == async_result.mode

    def test_viewport_to_dict_is_api_compatible(self):
        """Test that viewport to_dict is compatible with Google Places API."""
        viewport = circle_to_viewport(PARIS_LAT, PARIS_LON, 1000)
        data = viewport.to_dict()

        # Should have exact structure expected by Google Places
        assert isinstance(data["rectangle"]["low"]["latitude"], float)
        assert isinstance(data["rectangle"]["low"]["longitude"], float)
        assert isinstance(data["rectangle"]["high"]["latitude"], float)
        assert isinstance(data["rectangle"]["high"]["longitude"], float)
