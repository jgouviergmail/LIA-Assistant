"""The instance's web search: ONE door for every surface that searches the web (lot 18).

A person who configured a search key of their own (Brave) is searched with it,
everywhere: their choice wins, as the weather's does (ADR-307). A person with
none was searched by nothing but Wikipedia — so the operator can run a SearXNG,
and every surface that searches the web for that person asks it here:

- whether the instance runs one: the keyless predicate (``connectors/keyless.py``),
  read in a session of its own and closed before anything is searched (ADR-304);
- the search itself, handed back as plain links — the title, the address, the
  excerpt, and the engine's own line (a news item's age and outlet: SearXNG's
  news carry no machine date, measured 0 dated items on 15 news searches);
- a failure RAISES, counted on the connector metrics every client shares; the
  surface says it failed, it never reads « nothing found » (ADR-303).

Readers: the chat's unified web search, the knowledge enrichment of an answer,
the interest sweep and the Tools' research assist. The radio files a story by
its publication date, which SearXNG does not give: it keeps its own-key rule.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Final
from uuid import UUID

import httpx
import structlog

from src.core.exceptions import ExternalServiceError
from src.domains.connectors.clients.searxng_client import SearXNGClient, SearXNGRecency
from src.domains.connectors.keyless import is_keyless_available
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.repository import ConnectorRepository
from src.infrastructure.database import get_db_context
from src.infrastructure.observability.metrics import (
    connector_api_duration_seconds,
    connector_api_errors_total,
    connector_api_requests_total,
)

logger = structlog.get_logger(__name__)

#: The name every surface writes for a link the instance's search found.
INSTANCE_SEARCH_SOURCE: Final = ConnectorType.SEARXNG.value
_OPERATION: Final = "search"


@dataclass(frozen=True)
class WebLink:
    """One link the instance's search found.

    Attributes:
        title: The page's title.
        url: Its address.
        snippet: The excerpt the engine showed ("" when none).
        note: The engine's own line — a news item's age and outlet ("" when none).
    """

    title: str
    url: str
    snippet: str
    note: str

    @property
    def excerpt(self) -> str:
        """What a reader shows of the link: the engine's line first, then the excerpt.

        A news item carries its age and outlet in ``note`` and no machine date, so the
        line travels with the words it dates.
        """
        if self.note and self.snippet:
            return f"[{self.note}] {self.snippet}"
        return self.snippet or self.note


async def instance_search_available() -> bool:
    """Whether the instance runs a web search for every account (ADR-307 predicate).

    Returns:
        True when the operator deployed one and the administrator left it on.
    """
    async with get_db_context() as db:
        return await is_keyless_available(ConnectorRepository(db), ConnectorType.SEARXNG)


def _failure_kind(error: Exception) -> tuple[str, str]:
    """``(status, error_type)`` of a failed search, read from its TYPE, never its words."""
    if isinstance(error, httpx.HTTPStatusError):
        return "error", "refused"
    if isinstance(error, ExternalServiceError):
        return "error", "circuit_open"
    if isinstance(error, httpx.TimeoutException):
        return "timeout", "timeout"
    if isinstance(error, ValueError):
        # It answered, with something that is not its JSON: up, but not speaking it.
        return "error", "malformed"
    return "error", "unreachable"


async def search_instance(
    query: str,
    *,
    user_id: UUID | None,
    language: str | None,
    count: int,
    recency: SearXNGRecency | None = None,
    news: bool = False,
) -> list[WebLink]:
    """Search the web through the instance's SearXNG, once.

    The caller has asked :func:`instance_search_available` first (and found the
    person has no search key of their own).

    Args:
        query: The words to search.
        user_id: Whose search (logging, read budget); never the rate-limit bucket.
        language: The person's language; the declared one when None (ADR-323).
        count: The most links handed back.
        recency: Only results from the last day, week, month or year.
        news: Search the news category instead of the web.

    Returns:
        The links, best first; empty when no engine found anything.

    Raises:
        httpx.HTTPStatusError, httpx.RequestError, ExternalServiceError, ValueError:
            The search failed; the caller says so.
    """
    client = SearXNGClient(user_id=user_id)
    started = perf_counter()
    try:
        answer = await client.search(query, language=language, recency=recency, news=news)
    except Exception as error:
        status, error_type = _failure_kind(error)
        connector_api_requests_total.labels(
            connector_type=INSTANCE_SEARCH_SOURCE, operation=_OPERATION, status=status
        ).inc()
        connector_api_errors_total.labels(
            connector_type=INSTANCE_SEARCH_SOURCE, error_type=error_type
        ).inc()
        # The type, never the message: an error text can quote the query (ADR-317).
        logger.warning(
            "instance_search_failed", error_type=type(error).__name__, failure=error_type
        )
        raise
    finally:
        connector_api_duration_seconds.labels(
            connector_type=INSTANCE_SEARCH_SOURCE, operation=_OPERATION
        ).observe(perf_counter() - started)
        await client.close()

    connector_api_requests_total.labels(
        connector_type=INSTANCE_SEARCH_SOURCE, operation=_OPERATION, status="success"
    ).inc()
    if answer.unresponsive_engines:
        connector_api_errors_total.labels(
            connector_type=INSTANCE_SEARCH_SOURCE, error_type="engine_unresponsive"
        ).inc(len(answer.unresponsive_engines))
        # Engine names and their reasons are facts about the service, never content.
        logger.info(
            "instance_search_engines_unresponsive",
            engines=sorted({engine for engine, _reason in answer.unresponsive_engines}),
        )
    links = [
        WebLink(
            title=result.title,
            url=result.url,
            snippet=result.content,
            note=result.metadata,
        )
        for result in answer.results[:count]
    ]
    logger.info(
        "instance_search_answered",
        results_count=len(links),
        news=news,
        has_recency=recency is not None,
    )
    return links


__all__ = [
    "INSTANCE_SEARCH_SOURCE",
    "WebLink",
    "instance_search_available",
    "search_instance",
]
