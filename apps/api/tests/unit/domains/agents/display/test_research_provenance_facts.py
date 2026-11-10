"""Research cards retain the received context that explains their relevance."""

from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.data_registry.card_payload import card_payload
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.display.components.article_card import ArticleCard
from src.domains.agents.display.components.base import RenderContext
from src.domains.agents.display.components.search_result_card import SearchResultCard
from src.domains.agents.tools import wikipedia_tools
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.tools.perplexity_tools import PerplexityAskTool
from src.domains.connectors.clients.wikipedia_client import WikipediaClient

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_related_article_keeps_its_origin_after_real_tool_and_registry_round_trip() -> None:
    """The related page's title alone cannot explain which article linked to it."""
    origin = "Original <article> & source"
    client = WikipediaClient(language="en")
    response = {"query": {"pages": {"42": {"links": [{"title": "Related page"}]}}}}
    with (
        patch.object(client, "_make_request", new=AsyncMock(return_value=response)),
        patch.object(wikipedia_tools, "_get_wikipedia_client", return_value=client),
    ):
        output = await wikipedia_tools.get_wikipedia_related_tool.coroutine(
            title=origin, language="en", max_results=1
        )
    assert isinstance(output, UnifiedToolOutput)
    original = next(iter(output.registry_updates.values()))
    payload = card_payload(RegistryItem.model_validate_json(original.model_dump_json()))
    assert payload is not None
    soup = BeautifulSoup(ArticleCard().render(payload, RenderContext(language="en")), "html.parser")
    assert origin in soup.get_text()
    assert "Related page" in soup.get_text()
    assert soup.find("article") is None
    assert soup.find("a", href="https://en.wikipedia.org/wiki/Related_page") is not None


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_perplexity_ask_context_survives_the_producer_without_loading_its_markup(
    language: str,
) -> None:
    """Expert framing is useful evidence; execution-model metadata is not a source."""
    context = "Only compare accessible options.\n" * 40 + "FINAL_CONTEXT <img src=bad>"
    output = PerplexityAskTool(
        tool_name="perplexity_ask", operation="ask"
    ).format_registry_response(
        {
            "success": True,
            "data": {
                "question": "Which option?",
                "answer": "Received answer [1].",
                "context": context,
                "model": "EXECUTION_MODEL_NOT_A_SOURCE",
                "citations": ["https://source.example.test/evidence"],
            },
        }
    )
    original = next(iter(output.registry_updates.values()))
    payload = card_payload(RegistryItem.model_validate_json(original.model_dump_json()))
    assert payload is not None
    soup = BeautifulSoup(
        SearchResultCard().render(payload, RenderContext(language=language)), "html.parser"
    )
    context_block = soup.find(string=lambda value: bool(value and "FINAL_CONTEXT" in value))
    assert context_block is not None
    disclosure = context_block.find_parent("details")
    assert disclosure is not None and not disclosure.has_attr("open")
    assert disclosure.find("summary").get_text().strip()
    assert context in disclosure.get_text()
    assert soup.find("img") is None
    assert "EXECUTION_MODEL_NOT_A_SOURCE" not in soup.get_text()
    assert soup.select_one('.lia-citation[href="https://source.example.test/evidence"]')


@pytest.mark.parametrize("value", [None, "", [], {}, False])
def test_absent_or_malformed_research_context_creates_no_empty_disclosure(value: object) -> None:
    soup = BeautifulSoup(
        SearchResultCard().render(
            {"question": "Question", "answer": "Answer", "context": value},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert soup.find("details") is None
