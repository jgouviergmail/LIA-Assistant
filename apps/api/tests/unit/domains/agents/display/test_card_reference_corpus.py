"""Frontend/browser proof must exercise the exact backend card contract."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.domains.agents.tools import routes_formatting
from tests.helpers.card_composition_reference import composition_references
from tests.helpers.card_reference_cases import card_references, route_detail_domain

pytestmark = pytest.mark.unit


def test_browser_reference_corpus_matches_real_backend_rendering() -> None:
    corpus = json.loads(
        Path(__file__).with_name("card_reference_corpus.json").read_text(encoding="utf-8")
    )
    assert corpus == card_references()


def test_browser_composition_corpus_matches_native_rendering_and_projection() -> None:
    corpus = json.loads(
        Path(__file__).with_name("card_composition_corpus.json").read_text(encoding="utf-8")
    )
    assert corpus == composition_references()


@pytest.mark.parametrize("day", [3, 5, 10])
def test_route_reference_is_independent_of_run_date(
    monkeypatch: pytest.MonkeyPatch, day: int
) -> None:
    class RunDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            value = datetime(2026, 10, day, 12, tzinfo=UTC)
            return value.astimezone(tz) if tz else value.replace(tzinfo=None)

    monkeypatch.setattr(routes_formatting, "datetime", RunDateTime)
    corpus = json.loads(
        Path(__file__).with_name("card_reference_corpus.json").read_text(encoding="utf-8")
    )
    for reference in corpus:
        if reference["id"] == "route_details":
            assert route_detail_domain(reference["language"]) == reference["domains"]
    assert routes_formatting.datetime is RunDateTime
