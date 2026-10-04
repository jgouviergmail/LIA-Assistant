"""All supplied research facts stay reachable, safely and without another search."""

import pytest
from bs4 import BeautifulSoup

from src.domains.agents.display.components.article_card import ArticleCard
from src.domains.agents.display.components.base import BaseComponent, RenderContext
from src.domains.agents.display.components.search_result_card import SearchResultCard
from src.domains.agents.display.components.web_search_card import WebSearchCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_article_keeps_full_received_content_categories_sections_and_language(language):
    content = "Introduction. " * 100 + "\n\nFINAL_RECEIVED_FACT"
    soup = BeautifulSoup(
        ArticleCard().render(
            {
                "title": "Article",
                "url": "https://fr.wikipedia.org/wiki/Article",
                "content": content,
                "language": "fr",
                "page_id": 0,
                "content_length": len(content),
                "sections": [{"title": "Section finale", "level": 2, "index": "7"}],
                "categories": [f"CATEGORY_{i}" for i in range(7)],
            },
            RenderContext(language=language),
        ),
        "html.parser",
    )
    assert "FINAL_RECEIVED_FACT" in soup.get_text()
    assert "CATEGORY_6" in soup.get_text()
    assert "Section finale" in soup.get_text()
    assert "fr" in soup.get_text()
    assert soup.select("details.lia-collapsible")


@pytest.mark.parametrize("card", [SearchResultCard(), WebSearchCard()])
def test_search_preserves_last_citation_and_related_question(card: BaseComponent):
    citations = [f"https://source{i}.example.test/article{i}" for i in range(9)]
    payload = {
        "query": "Research",
        "citations": citations,
        "related_questions": [f"QUESTION_{i}" for i in range(7)],
    }
    payload["answer" if isinstance(card, SearchResultCard) else "synthesis"] = "Fact [9]."
    soup = BeautifulSoup(card.render(payload, RenderContext(language="en")), "html.parser")
    assert soup.find("a", href=citations[-1])
    assert "QUESTION_6" in soup.get_text()
    assert soup.select_one('.lia-citation[href="https://source8.example.test/article8"]')


def test_unified_search_keeps_every_result_and_its_full_received_snippet():
    soup = BeautifulSoup(
        WebSearchCard().render(
            {
                "query": "Research",
                "results": [
                    {
                        "title": f"Result {i}",
                        "url": f"https://result{i}.example.test",
                        "snippet": "Preview. " * 30 + f" FINAL_SNIPPET_{i}",
                    }
                    for i in range(8)
                ],
                "wikipedia": {
                    "title": "Wikipedia",
                    "summary": "A sentence. " * 50 + "FINAL_WIKI",
                    "url": "https://en.wikipedia.org/wiki/Article",
                },
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "FINAL_SNIPPET_7" in soup.get_text()
    assert "FINAL_WIKI" in soup.get_text()


@pytest.mark.parametrize(
    "card,payload",
    [
        (
            ArticleCard(),
            {
                "title": {"PRIVATE_RAW_TREE": "secret"},
                "url": "javascript:alert(1)",
                "content": [],
                "thumbnail": {"bad": "secret"},
                "categories": [True, {"PRIVATE_RAW_TREE": "secret"}],
            },
        ),
        (
            SearchResultCard(),
            {
                "answer": {"PRIVATE_RAW_TREE": "secret"},
                "citations": ["javascript:alert(1)", {}, None],
                "related_questions": [[], {}],
            },
        ),
        (
            WebSearchCard(),
            {
                "query": {},
                "synthesis": [],
                "citations": "javascript:alert(1)",
                "results": [
                    None,
                    {
                        "title": {},
                        "url": "javascript:alert(1)",
                        "snippet": {"PRIVATE_RAW_TREE": "secret"},
                    },
                ],
                "wikipedia": True,
            },
        ),
    ],
)
def test_malformed_optional_external_fields_do_not_break_or_create_fake_links(
    card: BaseComponent, payload
):
    soup = BeautifulSoup(card.render(payload, RenderContext(language="en")), "html.parser")
    assert "PRIVATE_RAW_TREE" not in soup.get_text()
    assert not soup.select('a[href=""], a[href^="javascript:"], img[src=""]')


def test_standard_search_snippet_is_reachable_after_the_preview():
    soup = BeautifulSoup(
        SearchResultCard().render(
            {
                "title": "Result",
                "url": "https://source.example.test",
                "snippet": "First sentence. " * 50 + "LAST_FACT",
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "LAST_FACT" in soup.get_text()
    assert soup.select_one("details.lia-collapsible")


def test_actual_search_contract_keeps_ask_question_and_brave_age():
    card = SearchResultCard()
    question = BeautifulSoup(
        card.render(
            {"question": "ACTUAL_ASK_QUESTION", "answer": "Answer", "source": "perplexity"},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "ACTUAL_ASK_QUESTION" in question.get_text()
    assert "Perplexity" in question.get_text()
    news = BeautifulSoup(
        card.render(
            {
                "title": "News",
                "url": "https://news.example.test/article",
                "description": "Story",
                "age": "2 hours ago",
                "source": "brave",
                "endpoint": "news",
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "2 hours ago" in news.get_text()
    assert "news.example.test" in news.get_text()
    assert "Brave" in news.get_text()


def test_malformed_preferred_article_text_does_not_hide_a_valid_fallback():
    soup = BeautifulSoup(
        ArticleCard().render(
            {"title": "Article", "summary": {}, "content": "ACTUAL_FALLBACK"},
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    assert "ACTUAL_FALLBACK" in soup.get_text()


def test_rejected_source_never_renumbers_a_later_citation():
    soup = BeautifulSoup(
        SearchResultCard().render(
            {
                "answer": "First [1], second [2].",
                "citations": ["javascript:alert(1)", "https://second.example.test"],
            },
            RenderContext(language="en"),
        ),
        "html.parser",
    )
    source = soup.select_one(".lia-research-list li")
    assert source["value"] == "2"
    assert soup.select_one('.lia-citation[href="https://second.example.test"]').get_text() == "[2]"


@pytest.mark.parametrize(
    "url",
    [
        "/\\external.example.test/private",
        "https:\\external.example.test",
        "https://source.example.test/\\bad",
    ],
)
def test_browser_backslash_destinations_are_inert_for_research_and_shared_links(url):
    from src.domains.agents.display.components.base import safe_url

    assert safe_url(url) == ""
    soup = BeautifulSoup(
        SearchResultCard().render(
            {"title": "Untrusted destination", "url": url}, RenderContext(language="en")
        ),
        "html.parser",
    )
    assert not soup.find("a")
