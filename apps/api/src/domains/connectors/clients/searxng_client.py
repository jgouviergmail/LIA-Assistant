"""The instance's own web search: a SearXNG the operator runs (lot 18).

SearXNG is a metasearch engine: it asks public search engines (Google's
programmable search, DuckDuckGo, Bing News, Brave's site…) on the server's own
address and merges what they return. Measured before LIA relied on it
(``scripts/connectors/measure_searxng.py``): 58 useful searches out of 60 in the
six languages of the site, a median wait of 0.7 s, and engines suspending or
challenging the address within minutes — which its redundancy absorbs.

It is not an API-key client: nothing is authenticated, and its address is the
operator's internal service, never a host a sandboxed run may be handed a key
for (ADR-298 derives those from the API-key clients). Five facts, each pinned by
a test:

- **no credential travels**: the service sits on the internal network only;
- **unfiltered**: every request says ``safesearch=0``, as Brave's says ``off`` (the
  owner's decision, ADR-382), whatever the instance's ``settings.yml`` holds;
- **one shaper for the whole instance**: every account's search leaves from the
  same address and the engines throttle an address, so the burst is smoothed on
  one Redis key (``wait_for_slot``, ADR-254) — a shaper, never a gate: a search
  that waited its share goes ahead, and a Redis outage shapes nothing;
- **one circuit breaker**: a SearXNG that keeps failing is refused at once for a
  while instead of making every turn wait for it;
- **a failure RAISES**: a refused, unreachable or unreadable search is said by the
  caller, never read as « nothing found » (ADR-303) — and it is asked once,
  because SearXNG already waited for its own slow engines.
"""

from __future__ import annotations

from typing import Any, Final, Literal
from uuid import UUID

import httpx
import structlog
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.config import settings
from src.core.constants import (
    SEARXNG_QUERY_MAX_CHARS,
    SEARXNG_SAFESEARCH_OFF,
    SEARXNG_SLOT_WAIT_SECONDS,
)
from src.core.exceptions import ExternalServiceError
from src.core.i18n import resolve_language
from src.core.read_budget import source_http_hooks
from src.domains.connectors.models import ConnectorType
from src.infrastructure.rate_limiting.slot_waiter import wait_for_slot
from src.infrastructure.resilience import CircuitBreakerError, get_circuit_breaker

logger = structlog.get_logger(__name__)

#: LIA's recency vocabulary, which is SearXNG's ``time_range`` word for word.
SearXNGRecency = Literal["day", "week", "month", "year"]
_SERVICE: Final = ConnectorType.SEARXNG.value
#: The shaper's window: a short one smooths a burst without spreading a day's quota.
_SLOT_WINDOW_SECONDS: Final = 10


class SearXNGResult(BaseModel):
    """One link SearXNG returned, read typed: what is not here was never asked for."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    url: str = Field(description="The page's address, as the engine returned it.")
    title: str = Field(default="", description="The page's title.")
    content: str = Field(default="", description="The excerpt the engine showed.")
    engines: list[str] = Field(default_factory=list, description="The engines that found it.")
    published: str | None = Field(
        default=None,
        alias="publishedDate",
        description="The publication date when an engine gave one (news rarely does).",
    )
    metadata: str = Field(
        default="",
        description="An engine's own line, e.g. a news item's age and outlet.",
    )

    @field_validator("title", "content", "metadata", mode="before")
    @classmethod
    def _none_is_empty(cls, value: object) -> object:
        return "" if value is None else value


class SearXNGAnswer(BaseModel):
    """A search's answer: its links, and the engines that could not answer it."""

    model_config = ConfigDict(extra="ignore")

    results: list[SearXNGResult] = Field(
        default_factory=list, description="The merged links, best first."
    )
    unresponsive_engines: list[tuple[str, str]] = Field(
        default_factory=list,
        description="``(engine, reason)`` for each engine that failed: a CAPTCHA, a timeout…",
    )

    @field_validator("results", mode="before")
    @classmethod
    def _links_only(cls, value: object) -> object:
        """A result without an address is no link (an engine's answer box, an infobox)."""
        if not isinstance(value, list):
            return value
        return [item for item in value if isinstance(item, dict) and item.get("url")]


def clamp_query(query: str) -> str:
    """The query within ``SEARXNG_QUERY_MAX_CHARS``, cut at a word boundary.

    A planner can write a paragraph; a search URL carries words. A compliant query
    leaves untouched; a single overlong word is hard-cut (no boundary to keep).
    """
    if len(query) <= SEARXNG_QUERY_MAX_CHARS:
        return query
    cut = query[:SEARXNG_QUERY_MAX_CHARS].rstrip()
    boundary = cut.rfind(" ")
    return cut[:boundary].rstrip() if boundary > 0 else cut


class SearXNGClient:
    """Client of the instance's SearXNG (JSON API, ``GET /search``), for ONE search."""

    connector_type = ConnectorType.SEARXNG

    def __init__(
        self,
        *,
        user_id: UUID | None = None,
        rate_limit_per_second: float | None = None,
    ) -> None:
        """Build a client for one search; the caller closes it.

        Args:
            user_id: Whose search (logging and read budget) — never the shaper's key,
                which is the instance's.
            rate_limit_per_second: The instance's rate; the setting when None.
        """
        self.user_id = user_id
        self.base_url = settings.searxng_url.strip().rstrip("/")
        self._rate_per_second = (
            rate_limit_per_second
            if rate_limit_per_second is not None
            else settings.client_rate_limit_searxng_per_second
        )
        self._http: httpx.AsyncClient | None = None

    def _get_http_timeout(self) -> float:
        """The operator's wait for one metasearch."""
        return float(settings.http_timeout_searxng)

    def _get_rate_limit_key(self) -> str:
        """ONE key for the instance: the engines throttle its address, not an account."""
        return f"keyless:instance:{_SERVICE}"

    async def close(self) -> None:
        """Close the connection pool this search opened."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _shape(self) -> None:
        """Smooth the instance's burst; never refuse (ADR-254)."""
        if not settings.rate_limit_enabled:
            return
        await wait_for_slot(
            self._get_rate_limit_key(),
            max(1, int(self._rate_per_second * _SLOT_WINDOW_SECONDS)),
            _SLOT_WINDOW_SECONDS,
            timeout_seconds=SEARXNG_SLOT_WAIT_SECONDS,
        )

    async def search(
        self,
        query: str,
        *,
        language: str | None,
        recency: SearXNGRecency | None = None,
        news: bool = False,
    ) -> SearXNGAnswer:
        """Ask SearXNG once.

        Args:
            query: The words to search.
            language: The person's language, passed verbatim (SearXNG reads the
                backend's ``zh-CN``); the declared language when None (ADR-323).
            recency: Only results from the last day, week, month or year.
            news: Search the news category instead of the web.

        Returns:
            The typed answer; an empty one when no engine found anything.

        Raises:
            ExternalServiceError: The circuit breaker is open.
            httpx.HTTPStatusError: SearXNG answered with an error status.
            httpx.RequestError: It could not be reached in time.
            ValueError: It answered something that is not its JSON.
        """
        breaker = get_circuit_breaker(f"keyless_{_SERVICE}")
        try:
            await breaker.check()
        except CircuitBreakerError as exc:
            raise ExternalServiceError(
                service_name=_SERVICE,
                detail=f"{_SERVICE} temporarily unavailable (circuit open)",
                error_type="circuit_open",
                retry_after=exc.retry_after,
            ) from exc
        await self._shape()

        params: dict[str, Any] = {
            "q": clamp_query(query),
            "format": "json",
            "language": language or resolve_language(),
            "pageno": 1,
            # Unfiltered whatever the instance's settings say (ADR-382).
            "safesearch": SEARXNG_SAFESEARCH_OFF,
        }
        if news:
            params["categories"] = "news"
        if recency is not None:
            params["time_range"] = recency
        if self._http is None:
            self._http = httpx.AsyncClient(
                event_hooks=source_http_hooks(self.user_id),
                timeout=self._get_http_timeout(),
                follow_redirects=False,
            )
        try:
            response = await self._http.get(f"{self.base_url}/search", params=params)
        except httpx.RequestError as exc:
            await breaker.record_failure(RuntimeError(type(exc).__name__))
            raise
        if response.status_code >= 500:
            await breaker.record_failure(RuntimeError(f"HTTP {response.status_code}"))
        else:
            # A refusal is an answer: the service is up.
            await breaker.record_success()
        response.raise_for_status()
        return SearXNGAnswer.model_validate(response.json())


__all__ = ["SearXNGAnswer", "SearXNGClient", "SearXNGRecency", "SearXNGResult", "clamp_query"]
