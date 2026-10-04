"""Frontend/browser proof must exercise the exact backend card contract."""

import json
from pathlib import Path

import pytest

from tests.helpers.card_composition_reference import composition_references
from tests.helpers.card_reference_cases import card_references

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
