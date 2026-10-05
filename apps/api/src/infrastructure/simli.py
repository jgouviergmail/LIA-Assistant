"""Bounded fixed-origin Simli HTTP shared by connector verification and avatars."""

import json
from typing import Literal

import httpx
from pydantic import BaseModel, Field, TypeAdapter, ValidationError, field_validator

from src.core.config import settings

SIMLI_ORIGIN = "https://api.simli.ai"
SIMLI_RESPONSE_MAX_BYTES = 65_536


class SimliError(Exception):
    """Stable non-sensitive code; never a provider response or request URL."""


class SimliIceServer(BaseModel):
    """Provider ICE credentials; never rendered in diagnostics."""

    urls: str | list[str]
    username: str | None = Field(default=None, max_length=512)
    credential: str | None = Field(default=None, max_length=2048, repr=False)

    @field_validator("urls")
    @classmethod
    def validate_ice_urls(cls, value: str | list[str]) -> str | list[str]:
        urls = [value] if isinstance(value, str) else value
        if not 1 <= len(urls) <= 8 or any(
            len(url) > 2048 or not url.startswith(("stun:", "stuns:", "turn:", "turns:"))
            for url in urls
        ):
            raise ValueError("invalid ICE URLs")
        return value


class SimliHttpClient:
    """Short-lived HTTP resources with no redirects or paid POST retries."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def request(
        self, method: Literal["GET", "POST"], path: str, payload: dict[str, object] | None = None
    ) -> object:
        try:
            async with httpx.AsyncClient(
                base_url=SIMLI_ORIGIN,
                timeout=settings.avatar_http_timeout_seconds,
                follow_redirects=False,
                headers={"x-simli-api-key": self._api_key, "accept-encoding": "identity"},
            ) as client:
                async with client.stream(method, path, json=payload) as response:
                    if response.status_code != 200:
                        raise SimliError("provider_refused")
                    if response.headers.get("content-encoding", "identity") != "identity":
                        raise SimliError("provider_bad_encoding")
                    data = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        data.extend(chunk)
                        if len(data) > SIMLI_RESPONSE_MAX_BYTES:
                            raise SimliError("provider_payload_too_large")
                    return json.loads(data)
        except (httpx.HTTPError, ValueError) as exc:
            raise SimliError(
                "provider_unavailable"
                if isinstance(exc, httpx.HTTPError)
                else "provider_bad_payload"
            ) from None

    async def ice(self) -> list[SimliIceServer]:
        try:
            servers = TypeAdapter(list[SimliIceServer]).validate_python(
                await self.request("GET", "/compose/ice")
            )
            if not servers or len(servers) > 16:
                raise SimliError("provider_bad_ice")
            return servers
        except ValidationError:
            raise SimliError("provider_bad_ice") from None
