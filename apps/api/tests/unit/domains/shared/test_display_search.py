"""The API search vocabulary must match the browser, without folding identities."""

import json
from pathlib import Path

import pytest

from src.domains.shared import text_normalization

CORPUS = json.loads(
    (
        Path(__file__).parents[6] / "apps/web/src/lib/__tests__/fixtures/display-search.json"
    ).read_text(encoding="utf-8")
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(("source", "expected"), CORPUS)
def test_display_search_parity(source: str, expected: str) -> None:
    """Typography folds, while compatibility forms and sharp s stay distinct."""
    assert text_normalization.normalize_search_text(source) == expected


def test_search_does_not_change_identity_rules() -> None:
    """A search match never changes the existing person identity equivalence."""
    assert text_normalization.fold_name("Straße") == "strasse"
    assert text_normalization.fold_name("d’Ana") == "d’ana"
