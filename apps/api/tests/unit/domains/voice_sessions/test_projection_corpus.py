"""The voice projection agrees with the browser's, case by case (ADR-301).

``flattenForVoice`` and ``boundToTokens`` exist in TypeScript for the browser
bridge and here for the server bridge. One corpus pins them to each other:
this test checks the Python side, ``apps/web/src/lib/live/__tests__/
projection-corpus.test.ts`` the TypeScript side, both reading the SAME file.
A rule changed on one side fails the other's build.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domains.agents.display.plain_text import strip_html_if_markup
from src.domains.voice_sessions.projection import (
    bound_to_tokens,
    estimate_tokens,
    flatten_for_voice,
)

pytestmark = pytest.mark.unit

CORPUS = Path(__file__).with_name("voice_projection_corpus.json")


def _corpus() -> dict[str, list[dict[str, str | int]]]:
    loaded = json.loads(CORPUS.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


@pytest.mark.parametrize("case", _corpus()["flatten"], ids=lambda c: c["id"])
def test_flatten_agrees_with_the_corpus(case: dict) -> None:
    assert flatten_for_voice(case["input"], strip_html=strip_html_if_markup) == case["expected"]


@pytest.mark.parametrize("case", _corpus()["bound"], ids=lambda c: c["id"])
def test_bound_agrees_with_the_corpus(case: dict) -> None:
    assert bound_to_tokens(case["input"], case["max_tokens"], case["cut_line"]) == case["expected"]


@pytest.mark.parametrize("case", _corpus()["tokens"], ids=lambda c: c["id"])
def test_token_estimate_agrees_with_the_corpus(case: dict) -> None:
    assert estimate_tokens(case["input"]) == case["expected"]


def test_the_corpus_is_not_trivial() -> None:
    corpus = _corpus()
    assert len(corpus["flatten"]) >= 8 and len(corpus["bound"]) >= 4
