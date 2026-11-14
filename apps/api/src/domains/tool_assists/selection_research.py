"""A selected passage becomes one bounded query and one attributed Internet search.

The platform pays for query preparation through the assist accountant. Search clients
use the person's existing connector key, else the instance's keyless search (its
SearXNG, lot 18), else its keyless Wikipedia capability.
No database session survives a model or network wait. No page URL is fetched here.
"""

import asyncio
from typing import Literal, Self, get_args
from urllib.parse import quote
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, Field, ValidationError, model_validator

from src.core.config import settings
from src.core.constants import (
    BRAVE_SEARCH_MAX_QUERY_CHARS,
    BRAVE_SEARCH_MAX_QUERY_WORDS,
    LLM_RUN_BOUND_MARGIN_SECONDS,
    TOOL_ASSIST_SEARCH_RESULTS_MAX,
    TOOL_ASSIST_SEARCH_SOURCES_MAX,
)
from src.core.external_content import wrap_external_content
from src.core.i18n import get_language_name
from src.domains.agents.prompts import load_prompt
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.clients.normalizers.html_text import html_to_text
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.clients.wikipedia_client import WikipediaClient, wikipedia_edition
from src.domains.connectors.instance_search import search_instance
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.service import ConnectorService
from src.domains.feature_switches import guard
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.tool_assists.door import AssistRun
from src.domains.tool_assists.llm import ask_slot
from src.domains.workbench.errors import NOT_CONNECTED, refuse
from src.infrastructure.database.session import get_db_context

ResearchProvider = Literal["brave", "perplexity", "searxng", "wikipedia"]
#: In order of preference: the person's own keys, then the instance's keyless search,
#: then its keyless Wikipedia (ADR-307: the person's choice wins).
SEARCH_CONNECTORS: dict[ResearchProvider, ConnectorType] = {
    "brave": ConnectorType.BRAVE_SEARCH,
    "perplexity": ConnectorType.PERPLEXITY,
    "searxng": ConnectorType.SEARXNG,
    "wikipedia": ConnectorType.WIKIPEDIA,
}


def assert_research_providers_complete() -> None:
    """Every offered provider names its real connector, including keyless Wikipedia."""
    assert set(SEARCH_CONNECTORS) == set(get_args(ResearchProvider))


class SearchQuery(BaseModel):
    """A query inferred from the whole selection, never a fragment cut by the client."""

    query: str = Field(
        min_length=1,
        max_length=BRAVE_SEARCH_MAX_QUERY_CHARS,
        description="Concise search keywords faithful to the selected passage.",
    )

    @model_validator(mode="after")
    def bounded_words(self) -> Self:
        """Refuse an empty or overlong query before the provider can silently clamp it."""
        self.query = self.query.strip()
        if not self.query or len(self.query.split()) > BRAVE_SEARCH_MAX_QUERY_WORDS:
            raise ValueError("Search query is empty or exceeds its word bound")
        return self


class ResearchSource(BaseModel):
    """An attributed provider result; source text is plain, never active markup."""

    title: str = Field(
        min_length=1,
        max_length=settings.tool_assist_text_max_chars,
        description="The source's own title.",
    )
    url: AnyHttpUrl = Field(description="The provider's HTTP(S) source URL, not a model invention.")
    excerpt: str = Field(
        default="",
        max_length=settings.tool_assist_text_max_chars,
        description="The source excerpt returned by the search service.",
    )

    @model_validator(mode="after")
    def no_url_credentials(self) -> Self:
        """A source link must not embed credentials in browser navigation."""
        if self.url.username or self.url.password:
            raise ValueError("Source URLs cannot contain credentials")
        self.title = html_to_text(self.title).strip()
        self.excerpt = html_to_text(self.excerpt).strip()
        if not self.title:
            raise ValueError("Source title has no text")
        return self


class ResearchProposal(BaseModel):
    """Results displayed locally; an empty successful search is explicitly empty."""

    kind: Literal["research"] = Field(default="research", description="An Internet search result.")
    query: str = Field(description="The query actually sent to the provider.")
    provider: ResearchProvider = Field(description="The service actually consulted.")
    summary: str | None = Field(
        default=None,
        max_length=settings.tool_assist_text_max_chars,
        description="A provider synthesis only when sources accompany it.",
    )
    sources: list[ResearchSource] = Field(
        max_length=TOOL_ASSIST_SEARCH_SOURCES_MAX,
        description="The provider's sources in their original citation order.",
    )


async def preferred_provider(user_id: UUID) -> ResearchProvider | None:
    """Read connection metadata only; never open a search merely to offer its menu."""
    if not await guard.is_capability_enabled(PlatformCapability.WEB_SEARCH):
        return None
    async with get_db_context() as db:
        service = ConnectorService(db)
        for provider, connector in SEARCH_CONNECTORS.items():
            if await service.is_connector_active(user_id, connector):
                return provider
    return None


async def _credentials(user_id: UUID, provider: ResearchProvider) -> str | None:
    """Recheck the chosen capability and detach its key before any network wait."""
    async with get_db_context() as db:
        service = ConnectorService(db)
        connector = SEARCH_CONNECTORS[provider]
        if not await service.is_connector_active(user_id, connector):
            refuse(NOT_CONNECTED)
        if connector.is_keyless:
            return None
        credentials = await service.get_api_key_credentials(user_id, connector)
        if credentials is None:
            refuse(NOT_CONNECTED)
        return credentials.api_key


def search_timeout_seconds() -> float:
    """Bound the network phase using the clients' configured time, including closing room."""
    return (
        max(
            settings.http_timeout_brave_search,
            settings.http_timeout_perplexity,
            settings.http_timeout_searxng,
            settings.http_timeout_wikipedia,
        )
        + LLM_RUN_BOUND_MARGIN_SECONDS
    )


class _SearchItem(BaseModel):
    """The typed subset a search provider supplies."""

    title: str = Field(description="Provider title.")
    url: AnyHttpUrl = Field(description="Provider URL.")
    description: str = Field(default="", description="Provider excerpt.")


class _BraveWeb(BaseModel):
    results: list[_SearchItem] = Field(default_factory=list, description="The web results page.")


class _BraveAnswer(BaseModel):
    web: _BraveWeb | None = Field(default=None, description="No web section when none were found.")


class _PerplexityAnswer(BaseModel):
    answer: str = Field(description="The service's synthesis.")
    citations: list[AnyHttpUrl] = Field(
        max_length=TOOL_ASSIST_SEARCH_SOURCES_MAX,
        description="The service's cited sources, in their original numbered order.",
    )
    search_results: list[_SearchItem] = Field(
        default_factory=list, description="Described sources."
    )


class _WikiItem(BaseModel):
    title: str = Field(description="The exact article title.")
    snippet: str = Field(default="", description="The returned search excerpt.")


async def _brave(run: AssistRun, query: str, key: str) -> ResearchProposal:
    """Use the raising client door so outages are not reported as empty searches."""
    client = BraveSearchClient(api_key=key, user_id=run.user_id, language=run.language)
    try:
        raw = await client.search_or_raise(query, count=TOOL_ASSIST_SEARCH_RESULTS_MAX)
        answer = _BraveAnswer.model_validate(raw)
        items = answer.web.results if answer.web else []
        return ResearchProposal(
            query=query,
            provider="brave",
            sources=[
                ResearchSource(title=item.title, url=item.url, excerpt=item.description)
                for item in items[:TOOL_ASSIST_SEARCH_RESULTS_MAX]
            ],
        )
    finally:
        await client.close()


async def _perplexity(run: AssistRun, query: str, key: str) -> ResearchProposal:
    """Keep only the citations the native client returned, never URLs from model prose."""
    client = PerplexityClient(
        api_key=key, user_id=run.user_id, model=settings.perplexity_search_model
    )
    try:
        answer = _PerplexityAnswer.model_validate(await client.search(query, return_citations=True))
        described = {str(item.url): item for item in answer.search_results}
        sources = []
        for url in answer.citations:
            item = described.get(str(url))
            sources.append(
                ResearchSource(
                    title=item.title if item else (url.host or str(url)),
                    url=url,
                    excerpt=item.description if item else "",
                )
            )
        return ResearchProposal(
            query=query,
            provider="perplexity",
            sources=sources,
            summary=answer.answer.strip() or None if sources else None,
        )
    finally:
        await client.close()


async def _searxng(run: AssistRun, query: str) -> ResearchProposal:
    """The instance's search: a failure raises (the door files it), never an empty page.

    A link the engines returned without a title or with an address no browser
    may open is left out: one malformed entry never discards the others.
    """
    links = await search_instance(
        query,
        user_id=run.user_id,
        language=run.language,
        count=TOOL_ASSIST_SEARCH_RESULTS_MAX,
    )
    sources: list[ResearchSource] = []
    for link in links:
        try:
            sources.append(
                ResearchSource.model_validate(
                    {"title": link.title, "url": link.url, "excerpt": link.excerpt}
                )
            )
        except ValidationError:
            continue
    return ResearchProposal(query=query, provider="searxng", sources=sources)


async def _wikipedia(run: AssistRun, query: str) -> ResearchProposal:
    """Use the instance's keyless capability and the client's canonical language edition."""
    client = WikipediaClient(language=run.language, user_id=run.user_id)
    try:
        raw = await client.search(query, limit=TOOL_ASSIST_SEARCH_RESULTS_MAX)
        items = [_WikiItem.model_validate(item) for item in raw[:TOOL_ASSIST_SEARCH_RESULTS_MAX]]
        edition = wikipedia_edition(run.language)
        return ResearchProposal(
            query=query,
            provider="wikipedia",
            sources=[
                ResearchSource.model_validate(
                    {
                        "title": item.title,
                        "excerpt": item.snippet,
                        "url": f"https://{edition}.wikipedia.org/wiki/{quote(item.title.replace(' ', '_'), safe='')}",
                    }
                )
                for item in items
            ],
        )
    finally:
        await client.close()


async def research_selection(run: AssistRun, source: str) -> ResearchProposal:
    """Prepare one query, search once, and file that provider's real success or failure."""
    await guard.require_capability(PlatformCapability.WEB_SEARCH)()
    provider = await preferred_provider(run.user_id)
    if provider is None:
        refuse(NOT_CONNECTED)
    prompt = load_prompt("tool_assist_research_prompt").format(
        language=get_language_name(run.language),
        max_query_chars=BRAVE_SEARCH_MAX_QUERY_CHARS,
        max_query_words=BRAVE_SEARCH_MAX_QUERY_WORDS,
        source=wrap_external_content(source, source_url="selection:page", source_type="selection"),
    )
    query = await ask_slot(run, prompt, SearchQuery)
    await guard.require_capability(PlatformCapability.WEB_SEARCH)()
    key = await _credentials(run.user_id, provider)
    async with run.reading(provider):
        async with asyncio.timeout(search_timeout_seconds()):
            if provider == "wikipedia":
                result = await _wikipedia(run, query.query)
            elif provider == "searxng":
                result = await _searxng(run, query.query)
            elif provider == "brave" and key is not None:
                result = await _brave(run, query.query, key)
            elif provider == "perplexity" and key is not None:
                result = await _perplexity(run, query.query, key)
            else:
                refuse(NOT_CONNECTED)
    run.served = True
    return result
