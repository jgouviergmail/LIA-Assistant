"""Every reason a run records has its sentence in the six languages, and no sentence is orphan.

The activity panel reads ``discussions.activity.reason.<code>`` for the last rebuild.
A code without a sentence would show its key; a sentence without a code is a reason
nobody produces (ADR-303: a vocabulary is a contract on both sides).
"""

import json
from pathlib import Path
from typing import get_args

import pytest

from src.domains.proactive_discussions.run_types import RunReason

pytestmark = pytest.mark.unit

LOCALES = Path(__file__).resolve().parents[6] / "apps" / "web" / "locales"
LANGUAGES = ("en", "fr", "de", "es", "it", "zh")


def _codes(annotation: object) -> set[str]:
    values = get_args(annotation)
    if not values:
        return set()
    if all(isinstance(value, str) for value in values):
        return set(values)
    return set().union(*(_codes(value) for value in values))


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_run_reason_has_exactly_one_sentence(language):
    sentences = json.loads((LOCALES / language / "translation.json").read_text(encoding="utf-8"))[
        "discussions"
    ]["activity"]["reason"]
    assert set(sentences) == _codes(RunReason)
    assert all(isinstance(text, str) and text.strip() for text in sentences.values())
