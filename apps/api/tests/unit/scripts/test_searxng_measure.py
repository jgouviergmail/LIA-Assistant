"""The SearXNG bench reads an answer the way it claims (lot 18): its tallies are the proof."""

from __future__ import annotations

import pytest

from scripts.connectors.measure_searxng import (
    CORPUS,
    USEFUL_RESULTS_MIN,
    Outcome,
    outcome_of,
    search_params,
    tally,
)

pytestmark = pytest.mark.unit

NEWS = next(probe for probe in CORPUS if probe.kind == "news")
FACT = next(probe for probe in CORPUS if probe.kind == "fact")


def _result(url: str, *engines: str, published: str | None = None) -> dict[str, object]:
    return {"url": url, "title": "t", "engines": list(engines), "publishedDate": published}


def test_the_corpus_speaks_every_language_of_the_site_with_chinese_as_the_backend_spells_it() -> (
    None
):
    assert {probe.language for probe in CORPUS} == {"en", "fr", "de", "es", "it", "zh-CN"}
    assert len({probe.key for probe in CORPUS}) == len(CORPUS)


def test_a_news_probe_asks_the_news_category_within_its_range() -> None:
    params = search_params(NEWS)

    assert params["categories"] == "news" and params["time_range"] == NEWS.time_range
    assert params["format"] == "json" and params["language"] == NEWS.language
    assert "categories" not in search_params(FACT) and "time_range" not in search_params(FACT)


def test_an_answer_is_read_into_counts_engines_failures_and_hosts() -> None:
    payload = {
        "results": [
            _result("https://a.example/x", "brave", "duckduckgo", published="2026-11-05T08:00:00"),
            _result("https://a.example/y", "brave"),
            _result("https://b.example/z", "google cse"),
        ],
        "unresponsive_engines": [["startpage", "CAPTCHA"], ["qwant", "timeout"]],
    }

    outcome = outcome_of(FACT, "round-1", 200, 0.4321, payload)

    assert outcome.results == 3 and outcome.dated == 1
    assert outcome.engines == ["brave", "duckduckgo", "google cse"]
    assert outcome.unresponsive == ["startpage: CAPTCHA", "qwant: timeout"]
    assert outcome.domains == ["a.example", "b.example"]
    assert outcome.seconds == 0.432 and outcome.useful


def test_a_refused_or_thin_answer_is_no_search() -> None:
    refused = outcome_of(FACT, "burst", 429, 0.1, None)
    thin = outcome_of(FACT, "burst", 200, 0.1, {"results": [_result("https://a.example", "x")]})

    assert not refused.useful and refused.results == 0
    assert not thin.useful and thin.results == 1 < USEFUL_RESULTS_MIN


def test_the_tally_counts_useful_searches_per_language_kind_and_phase() -> None:
    useful = {"results": [_result(f"https://{n}.example", "brave") for n in "abc"]}
    rows = [
        outcome_of(FACT, "round-1", 200, 0.5, useful),
        outcome_of(
            NEWS,
            "round-1",
            200,
            1.5,
            {"results": [], "unresponsive_engines": [["bing", "timeout"]]},
        ),
        Outcome(NEWS.key, "burst", 0, 6.0, error="ReadTimeout"),
    ]

    summary = tally(rows)

    assert summary["useful"] == "1/3"
    assert summary["by_phase"] == {"burst": "0/1", "round-1": "1/2"}
    assert summary["by_kind"][FACT.kind] == "1/1" and summary["by_kind"]["news"] == "0/2"
    assert summary["engines_unresponsive"] == {"bing: timeout": 1}
    assert summary["transport_errors"] == {"ReadTimeout": 1}
    assert summary["wait_max"] == 1.5  # a wait is read from an answer, never from a failure
    assert summary["news_dated"] == "0/1"
