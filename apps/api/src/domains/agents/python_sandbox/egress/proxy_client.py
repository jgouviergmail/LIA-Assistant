"""The proxy's management door: reload the ruleset, ask whether it is alive.

Every failure is one class, :class:`EgressProxyUnavailable`, because every
caller answers it the same way — the network run is REFUSED, never launched
against a proxy whose rules may not hold the run's hosts (fail-closed,
SEC-001's doctrine).
"""

from __future__ import annotations

from pathlib import Path

import httpx
import structlog

logger = structlog.get_logger(__name__)

TOKEN_FILENAME = "management.token"
RELOAD_PATH = "/v1/reload"


class EgressProxyUnavailable(RuntimeError):
    """The proxy could not be reached, refused the reload, or has no token."""


class ProxyManagement:
    """A thin client over iron-proxy's management and health listeners."""

    def __init__(
        self,
        *,
        management_url: str,
        health_url: str,
        token: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """
        Args:
            management_url: Base URL of the management listener.
            health_url: Full URL of the liveness endpoint.
            token: The bearer minted by the proxy's entrypoint.
            timeout_seconds: Budget of one call.
            transport: Test seam (``httpx.MockTransport``); None for the real one.
        """
        self._management_url = management_url.rstrip("/")
        self._health_url = health_url
        self._token = token
        self._timeout = timeout_seconds
        self._transport = transport

    @staticmethod
    def read_token(config_dir: Path) -> str:
        """The management bearer, from the shared config volume.

        Raises:
            EgressProxyUnavailable: When the proxy has not minted it (it is
                not running, or the volume is not the proxy's).
        """
        path = config_dir / TOKEN_FILENAME
        try:
            token = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise EgressProxyUnavailable(f"no {TOKEN_FILENAME} at {path}: {exc}") from exc
        if not token:
            raise EgressProxyUnavailable(f"empty {TOKEN_FILENAME} at {path}")
        return token

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def reload(self) -> None:
        """Ask the proxy to re-read its ruleset and swap it in atomically.

        Raises:
            EgressProxyUnavailable: On any status but 200, or on any transport
                failure — named, so the refusal the person reads says why.
        """
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self._management_url}{RELOAD_PATH}",
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.HTTPError as exc:
            raise EgressProxyUnavailable(f"reload failed: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise EgressProxyUnavailable(f"reload refused: HTTP {response.status_code}")
        logger.debug("sandbox_egress_ruleset_reloaded")

    async def healthy(self) -> bool:
        """Whether the liveness endpoint answers 200."""
        try:
            async with self._client() as client:
                response = await client.get(self._health_url)
        except httpx.HTTPError:
            return False
        return response.status_code == 200


__all__ = ["EgressProxyUnavailable", "ProxyManagement", "RELOAD_PATH", "TOKEN_FILENAME"]
