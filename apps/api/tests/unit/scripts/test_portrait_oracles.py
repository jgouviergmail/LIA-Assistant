"""The measurement's three oracles tell an analysis from an inventory, deterministically."""

from __future__ import annotations

import pytest

from scripts.journals.measure_portrait import _content_words, _oracles

pytestmark = pytest.mark.unit

# Stored supports carry the canonical quote (label, text, trailing date), never an item id.
ITEM_A = "- [personal] Il garde une heure sans interruption le matin pour les dossiers difficiles. (2026-10-01)"
ITEM_B = (
    "- [personal] Il court les premières heures de certains matins avant le travail. (2026-10-02)"
)
ITEM_C = "- Rotation des astreintes de novembre [open, priority high] équitable, deux options"


def _claim(text: str, *supports: tuple[str, str]) -> dict:
    return {
        "text": text,
        "supports": [{"source": source, "quote": quote} for source, quote in supports],
    }


def test_a_paraphrase_of_one_item_reads_as_a_restatement() -> None:
    claims = [
        _claim(
            "Il garde une heure sans interruption le matin pour les dossiers difficiles.",
            ("memories", ITEM_A),
        )
    ]
    assert _oracles(claims)["restatement_ratio"] == 1.0


def test_a_reading_across_items_is_not_a_restatement_and_crosses_sources() -> None:
    reading = (
        "Cette personne défend son temps de réflexion contre les sollicitations de la journée "
        "et attend qu'une organisation collective soit juste avant d'être rapide."
    )
    result = _oracles(
        [_claim(reading, ("memories", ITEM_A), ("habits", ITEM_B), ("workboard", ITEM_C))]
    )
    assert result["restatement_ratio"] == 0.0
    assert result["multi_source_share"] == 1.0 and result["mean_source_kinds"] == 3.0
    assert result["enumerations"] == 0


def test_a_sentence_listing_items_counts_as_an_enumeration() -> None:
    listing = _claim(
        "Son rythme : une heure le matin, la course certains matins, la lecture du soir, "
        "la natation hebdomadaire, le dimanche sans écran.",
        ("routines", ITEM_A),
    )
    assert _oracles([listing])["enumerations"] == 1


def test_content_words_ignore_short_tokens_digits_case_and_function_words() -> None:
    assert _content_words("Il a 2 options, Équitable et rapide, avec cette personne.") == {
        "options",
        "équitable",
        "rapide",
        "personne",
    }


ITEM_D = "- Résumé des tickets du vendredi — weekly at 16:30: résume les tickets ouverts"


def test_a_pattern_followed_by_its_cited_items_counts_as_listed_grounds() -> None:
    # The reading names a pattern, then lists three of the items it cites: an inventory
    # the comma count alone cannot tell from dense analytical prose.
    listed = _claim(
        "Son temps est fait de fenêtres défendues : une heure sans interruption le matin "
        "pour les dossiers difficiles, la course certains matins avant le travail, et le "
        "résumé des tickets du vendredi.",
        ("memories", ITEM_A),
        ("habits", ITEM_B),
        ("routines", ITEM_D),
    )
    assert _oracles([listed])["listed_grounds"] == 1.0


def test_a_reading_that_crosses_its_items_does_not_list_them() -> None:
    reading = _claim(
        "Cette personne défend son temps de réflexion contre les sollicitations de la "
        "journée, et une demande qui tombe dans ces heures sera refusée plutôt que casée.",
        ("memories", ITEM_A),
        ("habits", ITEM_B),
        ("routines", ITEM_D),
    )
    assert _oracles([reading])["listed_grounds"] == 0.0
