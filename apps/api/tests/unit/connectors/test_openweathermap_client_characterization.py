"""
Characterization tests for OpenWeatherMapClient (public contract).

Pin the externally observable behavior BEFORE the migration to
BaseAPIKeyClient (F3), so the migration can be proven behavior-preserving.
Unlike Brave, this client RAISES on errors — callers rely on it:
- 401 raises (invalid API key), message mentions the API key.
- 429 is retried with backoff, then the retry result is returned.
- Persistent network errors raise after retries.
- ``_build_weather_params`` raises ValueError when neither lat/lon nor city.
- geocode()/reverse_geocode() return LISTS (geo/1.0 endpoints).
- ``appid``, ``units``, ``lang`` travel as query params.

Consumers pinned by these tests: weather tools (via APIKeyConnectorTool),
briefing fetch_weather (catches TimeoutError/httpx.HTTPError), heartbeat
context_aggregator (gather with return_exceptions), geocoding (broad except).
"""

from uuid import uuid4

import httpx
import pytest

from src.domains.connectors.clients.openweathermap_client import OpenWeatherMapClient
from tests.unit.connectors.characterization_harness import transport_patches

API_KEY = "owm-test-key-1234567890"


@pytest.fixture(autouse=True)
def _fresh_circuit_breaker():
    """Isolate the process-global circuit-breaker registry between tests."""
    from src.infrastructure.resilience.circuit_breaker import CircuitBreakerRegistry

    CircuitBreakerRegistry.clear()
    yield
    CircuitBreakerRegistry.clear()


@pytest.fixture
def client():
    """OWM client with a high rate limit (no throttling in tests)."""
    return OpenWeatherMapClient(api_key=API_KEY, user_id=uuid4(), rate_limit_per_second=1000)


class TestCurrentWeather:
    async def test_lat_lon_request_params_and_parsing(self, client):
        """lat/lon request hits /data/2.5/weather with appid/units/lang."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"name": "Paris", "main": {"temp": 21.5}})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.get_current_weather(lat=48.85, lon=2.35, units="metric")
            await client.close()

        assert result["main"]["temp"] == 21.5
        req = captured[0]
        assert req.url.path == "/data/2.5/weather"
        params = dict(req.url.params)
        assert params["appid"] == API_KEY
        assert params["lat"] == "48.85"
        assert params["lon"] == "2.35"
        assert params["units"] == "metric"
        assert params["lang"] == "en"  # default

    async def test_city_country_becomes_q_param(self, client):
        """city+country request uses q=city,country."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"name": "Paris"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            await client.get_current_weather(city="Paris", country="FR", lang="fr")
            await client.close()

        params = dict(captured[0].url.params)
        assert params["q"] == "Paris,FR"
        assert params["lang"] == "fr"

    async def test_missing_location_raises_value_error(self, client):
        """Neither lat/lon nor city → ValueError (no HTTP call)."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(ValueError, match="lat/lon or city"):
                await client.get_current_weather()
            await client.close()

        assert captured == []


class TestForecast:
    async def test_forecast_path_and_cnt_cap(self, client):
        """Forecast hits /data/2.5/forecast; cnt is capped at 40."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"city": {"name": "Paris"}, "list": []})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            await client.get_forecast(lat=1.0, lon=2.0, cnt=99)
            await client.close()

        assert captured[0].url.path == "/data/2.5/forecast"
        assert dict(captured[0].url.params)["cnt"] == "40"

    async def test_daily_forecast_aggregates_by_user_timezone(self, client):
        """3-hour entries are grouped per local date with min/max temps."""
        # Two entries: 2026-01-01 23:00 UTC and 2026-01-02 01:00 UTC.
        # In Europe/Paris (UTC+1) both fall on 2026-01-02.
        entries = [
            {
                "dt": 1767308400,  # 2026-01-01T23:00:00Z
                "main": {"temp": 5.0, "humidity": 80},
                "weather": [{"description": "cloudy"}],
                "wind": {"speed": 3.0},
            },
            {
                "dt": 1767315600,  # 2026-01-02T01:00:00Z
                "main": {"temp": 7.0, "humidity": 70},
                "weather": [{"description": "cloudy"}],
                "wind": {"speed": 4.0},
            },
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"city": {"name": "Paris"}, "list": entries})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.get_daily_forecast(lat=1.0, lon=2.0, user_timezone="Europe/Paris")
            await client.close()

        assert len(result["daily"]) == 1
        day = result["daily"][0]
        assert day["date"] == "2026-01-02"
        assert day["temp_min"] == 5.0
        assert day["temp_max"] == 7.0
        assert result["city"] == {"name": "Paris"}


class TestGeocoding:
    async def test_geocode_direct_returns_list(self, client):
        """geocode() hits /geo/1.0/direct and returns the list body."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=[{"name": "Paris", "lat": 48.85, "lon": 2.35}])

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.geocode("Paris", country="FR")
            await client.close()

        assert captured[0].url.path == "/geo/1.0/direct"
        params = dict(captured[0].url.params)
        assert params["q"] == "Paris,FR"
        assert params["appid"] == API_KEY
        assert isinstance(result, list)
        assert result[0]["name"] == "Paris"

    async def test_reverse_geocode_returns_list(self, client):
        """reverse_geocode() hits /geo/1.0/reverse with lat/lon/limit."""
        captured: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json=[{"name": "Paris"}])

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.reverse_geocode(lat=48.85, lon=2.35, limit=1)
            await client.close()

        assert captured[0].url.path == "/geo/1.0/reverse"
        params = dict(captured[0].url.params)
        assert params["limit"] == "1"
        assert result == [{"name": "Paris"}]

    async def test_geocode_404_means_no_results(self, client):
        """OWM answers HTTP 404 {"cod":"404","message":"not found"} on geo/1.0
        for a query it cannot match (measured in prod, 2026-08-19). That is
        "no results", not a failure: geocode() returns [] so the Google
        fallback and the tools' location_not_found path stay reachable —
        raising here surfaced a raw traceback to the LLM instead."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"cod": "404", "message": "not found"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.geocode("Prawira, North Lombok")
            await client.close()

        assert result == []

    async def test_reverse_geocode_404_means_no_results(self, client):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"cod": "404", "message": "not found"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.reverse_geocode(lat=0.0, lon=0.0)
            await client.close()

        assert result == []

    async def test_geocode_other_client_errors_still_raise(self, client):
        """Only 404 is a no-results verdict; a 400 stays an error (contract)."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"cod": "400", "message": "bad query"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(httpx.HTTPStatusError):
                await client.geocode("Paris")
            await client.close()


class TestErrorContract:
    """OWM raises on errors (callers absorb: gather(return_exceptions),
    broad except in geocoding, httpx.HTTPError catch in briefing)."""

    async def test_invalid_api_key_raises_mentioning_api_key(self, client):
        """401 raises an exception whose message mentions the API key."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(401, json={"message": "unauthorized"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception, match="API key"):
                await client.get_current_weather(lat=1.0, lon=2.0)
            await client.close()

    async def test_rate_limited_then_success_retries(self, client):
        """A 429 is retried and the retry result is returned."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(429, headers={"Retry-After": "0"})
            return httpx.Response(200, json={"name": "Paris"})

        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await client.get_current_weather(lat=1.0, lon=2.0)
            await client.close()

        assert result == {"name": "Paris"}
        assert calls["n"] == 2

    async def test_persistent_network_error_raises(self, client):
        """Persistent transport errors raise after retries (never None)."""
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ConnectError("boom", request=request)

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception):
                await client.get_current_weather(lat=1.0, lon=2.0)
            await client.close()

        assert calls["n"] >= 3

    async def test_server_error_raises(self, client):
        """5xx ends up raising (after internal retries), never None."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="unavailable")

        p1, p2 = transport_patches(handler)
        with p1, p2:
            with pytest.raises(Exception):
                await client.get_current_weather(lat=1.0, lon=2.0)
            await client.close()


class TestLifecycle:
    async def test_close_is_idempotent(self, client):
        await client.close()
        await client.close()

    async def test_user_id_none_is_supported(self):
        """Keyless-caller mode (heartbeat geocoding) works without user_id."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[{"name": "Paris"}])

        anonymous = OpenWeatherMapClient(api_key=API_KEY, rate_limit_per_second=1000)
        p1, p2 = transport_patches(handler)
        with p1, p2:
            result = await anonymous.reverse_geocode(lat=1.0, lon=2.0)
            await anonymous.close()

        assert result == [{"name": "Paris"}]

    async def test_weather_icon_url_static_helper(self):
        url = OpenWeatherMapClient.get_weather_icon_url("01d", size="2x")
        assert "01d" in url and url.startswith("http")
