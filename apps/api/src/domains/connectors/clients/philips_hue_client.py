"""
Philips Hue Bridge API client with dual-mode support (local + remote).

Provides smart lighting control via the Hue CLIP v2 API:
- Light management (list, control on/off, brightness, color)
- Room management (list, control grouped lights)
- Scene management (list, activate)
- Bridge discovery and press-link pairing

Local mode: Direct HTTPS to bridge IP with hue-application-key header.
Remote mode: HTTPS to api.meethue.com with Bearer token (OAuth2).

Follows the same instantiation pattern as Apple iCloud clients:
    client = PhilipsHueClient(user_id, credentials, connector_service)

Infrastructure reused from existing codebase:
- RedisRateLimiter for distributed rate limiting
- CircuitBreaker for fault tolerance
- httpx.AsyncClient for HTTP connection pooling

Created: 2026-03-20
Reference: docs/connectors/CONNECTOR_PHILIPS_HUE.md
"""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import httpx
import structlog

from src.core.config import settings
from src.core.constants import (
    HTTP_TIMEOUT_HUE_API,
    HUE_API_PREFIX,
    HUE_AUTH_HEADER_NAME,
    HUE_DISCOVERY_URL,
    HUE_PAIRING_DEVICE_TYPE,
    HUE_PAIRING_TIMEOUT_SECONDS,
    HUE_REMOTE_API_BASE_URL,
    HUE_REMOTE_TOKEN_ENDPOINT,
)
from src.core.security import encrypt_data
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import HueBridgeCredentials, HueConnectionMode
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.rate_limiting import RedisRateLimiter
from src.infrastructure.resilience import CircuitBreaker, CircuitBreakerError, get_circuit_breaker

logger = structlog.get_logger(__name__)

# CIE xy color mapping for natural language color names (multilingual)
HUE_COLOR_MAP: dict[str, tuple[float, float]] = {
    # English
    "red": (0.675, 0.322),
    "blue": (0.167, 0.04),
    "green": (0.4091, 0.518),
    "yellow": (0.4317, 0.5007),
    "orange": (0.5567, 0.4091),
    "purple": (0.2651, 0.1291),
    "pink": (0.3944, 0.3093),
    "warm_white": (0.4448, 0.4066),
    "cool_white": (0.3174, 0.3207),
    "white": (0.3127, 0.3290),
    # French
    "rouge": (0.675, 0.322),
    "bleu": (0.167, 0.04),
    "vert": (0.4091, 0.518),
    "jaune": (0.4317, 0.5007),
    "violet": (0.2651, 0.1291),
    "rose": (0.3944, 0.3093),
    "blanc_chaud": (0.4448, 0.4066),
    "blanc_froid": (0.3174, 0.3207),
    "blanc": (0.3127, 0.3290),
    # German
    "rot": (0.675, 0.322),
    "blau": (0.167, 0.04),
    "grün": (0.4091, 0.518),
    "gelb": (0.4317, 0.5007),
    "lila": (0.2651, 0.1291),
    "weiß": (0.3127, 0.3290),
    # Spanish
    "rojo": (0.675, 0.322),
    "azul": (0.167, 0.04),
    "verde": (0.4091, 0.518),
    "amarillo": (0.4317, 0.5007),
    "morado": (0.2651, 0.1291),
    "blanco": (0.3127, 0.3290),
}


def resolve_color(color_input: str) -> tuple[float, float] | None:
    """
    Resolve color name or 'x,y' string to CIE xy coordinates.

    Args:
        color_input: Color name (e.g., 'red', 'rouge') or 'x,y' string.

    Returns:
        Tuple of (x, y) CIE coordinates, or None if unrecognized.
    """
    normalized = color_input.strip().lower().replace(" ", "_")

    # Check named colors
    if normalized in HUE_COLOR_MAP:
        return HUE_COLOR_MAP[normalized]

    # Try parsing as 'x,y' coordinates
    try:
        parts = normalized.split(",")
        if len(parts) == 2:
            x, y = float(parts[0].strip()), float(parts[1].strip())
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                return (x, y)
    except ValueError:
        pass  # Expected: input is not x,y coordinates, fall through to return None

    return None


def _extract_grouped_light_id(room_data: dict[str, Any]) -> str:
    """
    Extract grouped_light service ID from room data.

    Args:
        room_data: Room resource data from CLIP v2 API.

    Returns:
        The grouped_light resource ID.

    Raises:
        ValueError: If no grouped_light service found in room.
    """
    for service in room_data.get("services", []):
        if service.get("rtype") == "grouped_light":
            return str(service["rid"])
    raise ValueError(f"No grouped_light found for room {room_data.get('id')}")


class PhilipsHueClient:
    """
    Philips Hue Bridge API client supporting local and remote modes.

    Uses composition for rate limiting and circuit breaker,
    following the same pattern as BaseAppleClient.

    Attributes:
        connector_type: The connector type for this client.
        user_id: User UUID for logging and tracking.
        credentials: Decrypted HueBridgeCredentials.
        connector_service: ConnectorService for credential persistence.
    """

    connector_type = ConnectorType.PHILIPS_HUE

    def __init__(
        self,
        user_id: UUID,
        credentials: HueBridgeCredentials,
        connector_service: Any,
    ) -> None:
        """
        Initialize Hue client.

        Args:
            user_id: User ID for logging and tracking.
            credentials: Hue credentials (decrypted HueBridgeCredentials).
            connector_service: ConnectorService for token refresh (remote mode).
        """
        self.user_id = user_id
        self.credentials = credentials
        self.connector_service = connector_service
        self._connection_mode = credentials.connection_mode
        self._http_client: httpx.AsyncClient | None = None
        self._circuit_breaker: CircuitBreaker | None = None
        self._redis_rate_limiter: RedisRateLimiter | None = None

        # Mode-specific setup
        if self._connection_mode == HueConnectionMode.LOCAL:
            self._base_url = f"https://{credentials.bridge_ip}"
            self._verify_ssl = False  # Bridge uses self-signed certificate
        else:
            self._base_url = HUE_REMOTE_API_BASE_URL
            self._verify_ssl = True

        logger.debug(
            "hue_client_initialized",
            user_id=str(user_id),
            connection_mode=self._connection_mode.value,
            bridge_ip=(
                credentials.bridge_ip if self._connection_mode == HueConnectionMode.LOCAL else None
            ),
        )

    # =========================================================================
    # INFRASTRUCTURE (Rate Limiting, Circuit Breaker, HTTP Client)
    # =========================================================================

    async def _get_redis_rate_limiter(self) -> RedisRateLimiter:
        """Get or create Redis rate limiter (lazy init)."""
        if self._redis_rate_limiter is None:
            redis = await get_redis_session()
            self._redis_rate_limiter = RedisRateLimiter(redis)
        return self._redis_rate_limiter

    def _get_rate_limit_key(self) -> str:
        """Get rate limit key for this client."""
        return f"hue_rate_limit:{self.user_id}"

    async def _rate_limit(self) -> None:
        """
        Apply distributed rate limiting using Redis sliding window.

        Follows the same pattern as BaseAppleClient._rate_limit().

        Raises:
            RuntimeError: If rate limit exceeded after retries.
        """
        if not settings.rate_limit_enabled:
            return

        try:
            limiter = await self._get_redis_rate_limiter()
            rate_limit_key = self._get_rate_limit_key()
            max_calls = settings.hue_rate_limit_per_second * 60
            window_seconds = 60

            max_retries = 3
            for attempt in range(max_retries):
                allowed = await limiter.acquire(
                    key=rate_limit_key,
                    max_calls=max_calls,
                    window_seconds=window_seconds,
                )
                if allowed:
                    return

                wait_time = 1.0 * (attempt + 1)
                logger.warning(
                    "hue_rate_limit_exceeded_retrying",
                    user_id=str(self.user_id),
                    attempt=attempt + 1,
                    wait_time_seconds=wait_time,
                )
                await asyncio.sleep(wait_time)

            raise RuntimeError(f"Hue Bridge rate limit exceeded after {max_retries} retries")
        except RuntimeError:
            raise
        except Exception as e:
            logger.warning(
                "hue_rate_limit_fallback",
                user_id=str(self.user_id),
                error=str(e),
            )

    def _get_circuit_breaker(self) -> CircuitBreaker:
        """Get or create circuit breaker for Hue (lazy init)."""
        if self._circuit_breaker is None:
            self._circuit_breaker = get_circuit_breaker("philips_hue")
        return self._circuit_breaker

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with mode-appropriate SSL config."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                verify=self._verify_ssl,
                timeout=settings.hue_bridge_timeout_seconds,
            )
        return self._http_client

    # =========================================================================
    # TOKEN REFRESH (Remote mode only)
    # =========================================================================

    async def _ensure_valid_remote_token(self) -> None:
        """
        Refresh remote token if expired (remote mode only).

        Does NOT use connector_service._refresh_oauth_token() because it
        rewrites plain ConnectorCredentials, overwriting HueBridgeCredentials
        fields (connection_mode, remote_username, bridge_ip, etc.).

        Instead, performs direct POST to Hue token endpoint and persists
        the full HueBridgeCredentials format.
        """
        if self._connection_mode != HueConnectionMode.REMOTE:
            return
        if self.credentials.expires_at and self.credentials.expires_at > datetime.now(UTC):
            return  # Token still valid

        logger.info(
            "hue_remote_token_refresh_started",
            user_id=str(self.user_id),
            expires_at=str(self.credentials.expires_at),
        )

        # 1. Direct token refresh (preserves HueBridgeCredentials format)
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_HUE_API) as client:
            response = await client.post(
                HUE_REMOTE_TOKEN_ENDPOINT,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self.credentials.refresh_token,
                },
                auth=(settings.hue_remote_client_id, settings.hue_remote_client_secret),
            )
            response.raise_for_status()
            token_data = response.json()

        # 2. Update in-memory credentials (HueBridgeCredentials, preserving all fields)
        self.credentials.access_token = token_data["access_token"]
        new_refresh = token_data.get("refresh_token")
        if new_refresh:
            self.credentials.refresh_token = new_refresh
        self.credentials.expires_at = datetime.now(UTC) + timedelta(
            seconds=token_data["expires_in"]
        )

        # 3. Persist updated HueBridgeCredentials (all Hue-specific fields preserved)
        if self.connector_service:
            try:
                connector = await self.connector_service.repository.get_by_user_and_type(
                    self.user_id, ConnectorType.PHILIPS_HUE
                )
                if connector:
                    connector.credentials_encrypted = encrypt_data(
                        self.credentials.model_dump_json()
                    )
                    await self.connector_service.db.commit()
                    logger.info(
                        "hue_remote_token_refresh_success",
                        user_id=str(self.user_id),
                        new_expires_at=str(self.credentials.expires_at),
                    )
            except Exception as e:
                logger.error(
                    "hue_remote_token_persist_failed",
                    user_id=str(self.user_id),
                    error=str(e),
                )

    # =========================================================================
    # HTTP REQUEST (Core method with rate limiting + circuit breaker)
    # =========================================================================

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make authenticated request to Hue Bridge.

        Handles rate limiting, circuit breaker, auth header injection,
        SSL verification, and token refresh (remote mode).

        Args:
            method: HTTP method (GET, PUT, POST, DELETE).
            endpoint: CLIP v2 resource endpoint (e.g., 'light', 'room/123').
            json_data: Optional JSON request body.

        Returns:
            Parsed JSON response dict.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses.
            CircuitBreakerError: If circuit is open.
            RuntimeError: If rate limit exceeded.
        """
        # 1. Rate limiting
        await self._rate_limit()

        # 2. Build URL
        if self._connection_mode == HueConnectionMode.LOCAL:
            url = f"{self._base_url}{HUE_API_PREFIX}/{endpoint}"
        else:
            url = (
                f"{self._base_url}/bridge/{self.credentials.remote_username}"
                f"{HUE_API_PREFIX}/{endpoint}"
            )

        # 3. Build headers
        if self._connection_mode == HueConnectionMode.LOCAL:
            headers = {HUE_AUTH_HEADER_NAME: self.credentials.api_key or ""}
        else:
            await self._ensure_valid_remote_token()
            headers = {"Authorization": f"Bearer {self.credentials.access_token}"}

        # 4. Circuit breaker check
        cb = self._get_circuit_breaker()

        # 5. Execute request
        client = await self._get_client()
        try:
            response = await client.request(method, url, headers=headers, json=json_data)
            response.raise_for_status()
            await cb.record_success()

            result: dict[str, Any] = response.json()
            return result

        except httpx.HTTPStatusError as e:
            await cb.record_failure(str(e))
            logger.error(
                "hue_api_error",
                user_id=str(self.user_id),
                method=method,
                endpoint=endpoint,
                status_code=e.response.status_code,
                connection_mode=self._connection_mode.value,
            )
            raise
        except CircuitBreakerError:
            logger.warning(
                "hue_circuit_breaker_open",
                user_id=str(self.user_id),
                connection_mode=self._connection_mode.value,
            )
            raise
        except Exception as e:
            await cb.record_failure(str(e))
            logger.error(
                "hue_request_failed",
                user_id=str(self.user_id),
                method=method,
                endpoint=endpoint,
                error=str(e),
                connection_mode=self._connection_mode.value,
            )
            raise

    # =========================================================================
    # PUBLIC API: Test Connection
    # =========================================================================

    async def test_connection(self) -> dict[str, Any]:
        """
        Test bridge connectivity.

        Returns:
            Bridge info dict from CLIP v2 API.
        """
        return await self._make_request("GET", "bridge")

    # =========================================================================
    # PUBLIC API: Lights
    # =========================================================================

    async def list_lights(self) -> list[dict[str, Any]]:
        """
        List all lights with their current state.

        Returns:
            List of light resource dicts from CLIP v2 API.
        """
        result = await self._make_request("GET", "light")
        return list(result.get("data", []))

    async def get_light(self, light_id: str) -> dict[str, Any]:
        """
        Get a single light by ID.

        Args:
            light_id: Light resource ID.

        Returns:
            Light resource dict.
        """
        result = await self._make_request("GET", f"light/{light_id}")
        data = result.get("data", [])
        return dict(data[0]) if data else {}

    async def update_light(
        self,
        light_id: str,
        *,
        on: bool | None = None,
        brightness: float | None = None,
        color_xy: tuple[float, float] | None = None,
        color_temperature_mirek: int | None = None,
    ) -> dict[str, Any]:
        """
        Update a light's state.

        Args:
            light_id: Light resource ID.
            on: Turn on (True) or off (False).
            brightness: Brightness percentage (0-100).
            color_xy: CIE xy color coordinates as (x, y) tuple.
            color_temperature_mirek: Color temperature in mirek (153-500).

        Returns:
            API response dict.
        """
        body: dict[str, Any] = {}
        if on is not None:
            body["on"] = {"on": on}
        if brightness is not None:
            body["dimming"] = {"brightness": min(100.0, max(0.0, brightness))}
        if color_xy is not None:
            body["color"] = {"xy": {"x": color_xy[0], "y": color_xy[1]}}
        if color_temperature_mirek is not None:
            body["color_temperature"] = {"mirek": color_temperature_mirek}

        return await self._make_request("PUT", f"light/{light_id}", json_data=body)

    # =========================================================================
    # PUBLIC API: Rooms
    # =========================================================================

    async def list_rooms(self) -> list[dict[str, Any]]:
        """
        List all rooms with their services.

        Returns:
            List of room resource dicts.
        """
        result = await self._make_request("GET", "room")
        return list(result.get("data", []))

    async def control_room(
        self,
        room_id: str,
        *,
        on: bool | None = None,
        brightness: float | None = None,
    ) -> dict[str, Any]:
        """
        Control all lights in a room via its grouped_light.

        Args:
            room_id: Room resource ID.
            on: Turn all lights on (True) or off (False).
            brightness: Brightness percentage (0-100) for all lights.

        Returns:
            API response dict.

        Raises:
            ValueError: If room has no grouped_light service.
        """
        # Resolve room → grouped_light
        room_result = await self._make_request("GET", f"room/{room_id}")
        room_data = room_result.get("data", [{}])[0]
        grouped_light_id = _extract_grouped_light_id(room_data)

        # Control grouped light
        body: dict[str, Any] = {}
        if on is not None:
            body["on"] = {"on": on}
        if brightness is not None:
            body["dimming"] = {"brightness": min(100.0, max(0.0, brightness))}

        return await self._make_request("PUT", f"grouped_light/{grouped_light_id}", json_data=body)

    # =========================================================================
    # PUBLIC API: Scenes
    # =========================================================================

    async def list_scenes(self) -> list[dict[str, Any]]:
        """
        List all available scenes.

        Returns:
            List of scene resource dicts.
        """
        result = await self._make_request("GET", "scene")
        return list(result.get("data", []))

    async def activate_scene(self, scene_id: str) -> dict[str, Any]:
        """
        Activate a scene by ID.

        Args:
            scene_id: Scene resource ID.

        Returns:
            API response dict.
        """
        return await self._make_request(
            "PUT", f"scene/{scene_id}", json_data={"recall": {"action": "active"}}
        )

    # =========================================================================
    # STATIC METHODS: Discovery & Pairing (no instance needed)
    # =========================================================================

    @staticmethod
    async def discover_bridges() -> list[dict[str, Any]]:
        """
        Discover Philips Hue bridges on local network via discovery.meethue.com.

        Returns:
            List of bridge info dicts with 'id', 'internalipaddress', 'port'.
        """
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_HUE_API) as client:
            response = await client.get(HUE_DISCOVERY_URL)
            response.raise_for_status()
            result: list[dict[str, Any]] = response.json()
            return result

    @staticmethod
    async def pair_bridge(bridge_ip: str) -> dict[str, Any]:
        """
        Pair with a Hue Bridge via press-link authentication.

        User must press the physical button on the bridge within 30 seconds
        before calling this method.

        Args:
            bridge_ip: Bridge internal IP address.

        Returns:
            API response: [{"success": {"username": "...", "clientkey": "..."}}]
            or [{"error": {"type": 101, "description": "link button not pressed"}}].
        """
        # Hue bridges use self-signed TLS certificates by design (local network only)
        async with httpx.AsyncClient(verify=False, timeout=HUE_PAIRING_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"https://{bridge_ip}/api",
                json={
                    "devicetype": HUE_PAIRING_DEVICE_TYPE,
                    "generateclientkey": True,
                },
            )
            result: dict[str, Any] = response.json()
            return result
