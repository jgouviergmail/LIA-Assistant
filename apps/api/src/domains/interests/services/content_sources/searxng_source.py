"""The instance's web search as an interest source (lot 18).

A person with no Brave key of their own had their interests searched by Perplexity
(their key too) or not at all. When the operator runs a SearXNG, it searches the
recent web for them — and only for them: a person who configured Brave is searched
with it, their choice wins (ADR-307), so this source does not apply to them.

A search that failed RAISES: the generator files it failed and moves on, it is
never « nothing found » (ADR-303).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from src.core.constants import BRAVE_SEARCH_DEFAULT_COUNT, INTEREST_SOURCE_CONTENT_MAX_LENGTH
from src.core.i18n import resolve_language
from src.domains.agents.display.components.base import html_to_text
from src.domains.connectors.instance_search import (
    INSTANCE_SEARCH_SOURCE,
    WebLink,
    instance_search_available,
    search_instance,
)
from src.domains.connectors.models import ConnectorType
from src.domains.interests.helpers import (
    WEB_SEARCH_QUERY_TEMPLATES,
    build_localized_search_query,
    get_connector_api_key,
)
from src.domains.interests.services.content_sources.base import ContentResult
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: How far back an interest is searched: the week Brave's interest source reads.
_RECENCY: Final = "week"


def _format(links: list[WebLink]) -> str:
    """The links as the presentation step reads them: a numbered title, then its excerpt."""
    parts: list[str] = []
    for index, link in enumerate(links, 1):
        title = html_to_text(link.title).strip()
        if not title:
            continue
        excerpt = html_to_text(link.excerpt).strip()
        parts.append(f"{index}. {title}\n   {excerpt}" if excerpt else f"{index}. {title}")
    content = "\n\n".join(parts)
    if len(content) > INTEREST_SOURCE_CONTENT_MAX_LENGTH:
        content = content[:INTEREST_SOURCE_CONTENT_MAX_LENGTH] + "..."
    return content


class SearXNGContentSource:
    """The instance's SearXNG, searched for a person with no Brave key of their own."""

    source_name: str = INSTANCE_SEARCH_SOURCE

    async def applies(self, user_id: str | None) -> bool:
        """Whether the instance's search would be asked for this person.

        Args:
            user_id: Whose interest.

        Returns:
            True when the person has no Brave key and the instance runs a search.
        """
        if not user_id:
            return False
        if await get_connector_api_key(user_id, ConnectorType.BRAVE_SEARCH):
            return False
        return await instance_search_available()

    async def generate(
        self,
        topic: str,
        user_language: str,
        existing_embeddings: list[list[float]] | None = None,
        user_id: str | None = None,
    ) -> ContentResult | None:
        """Search the recent web for a topic.

        Args:
            topic: The interest.
            user_language: The person's language.
            existing_embeddings: Not used (dedup is the generator's).
            user_id: Whose interest (logging, read budget).

        Returns:
            The links as content with their citations, or None when nothing was found.

        Raises:
            Exception: The search failed — filed failed by the generator.
        """
        language = resolve_language(user_language)
        query = build_localized_search_query(topic, user_language, WEB_SEARCH_QUERY_TEMPLATES)
        links = await search_instance(
            query,
            user_id=UUID(user_id) if user_id else None,
            language=language,
            count=BRAVE_SEARCH_DEFAULT_COUNT,
            recency=_RECENCY,
        )
        content = _format(links)
        if not content:
            return None
        logger.info(
            "searxng_source_content_generated",
            topic_length=len(topic),
            results_count=len(links),
            content_length=len(content),
        )
        return ContentResult(
            content=content,
            source=self.source_name,
            raw_content=content,
            citations=[link.url for link in links if link.url],
            metadata={"query": query, "results_count": len(links), "language": language},
        )
