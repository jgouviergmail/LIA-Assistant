"""Parity + accessor tests for a condition routine's clock sentence (ADR-322).

The sentence replaces a schedule on the card, in the hub and in the chat's
listing: it must exist in the six languages, keyed by the backend-canonical
code (``zh-CN``), and carry the interval as a figure — a number written in the
text could not follow the setting that decides it (ADR-184).
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.core import i18n_routine_triggers as irt
from src.core.config import settings
from src.core.i18n_types import Language

pytestmark = pytest.mark.unit


def test_the_sentence_exists_in_every_canonical_language() -> None:
    # The lookup indexes the table directly: the keys ARE the canonical codes.
    assert set(irt.CONDITION_CADENCE) == set(get_args(Language))


def test_every_translation_carries_the_interval_and_no_other_number() -> None:
    for lang, template in irt.CONDITION_CADENCE.items():
        assert "{minutes}" in template, lang
        assert not any(char.isdigit() for char in template), lang


def test_the_accessor_normalises_the_locale() -> None:
    assert irt.condition_cadence("zh", minutes=10) == "约每 10 分钟检查一次"
    assert irt.condition_cadence("fr-FR", minutes=10) == "Vérifiée environ toutes les 10 min"


def test_an_unsupported_locale_reads_the_instance_default_language() -> None:
    assert irt.condition_cadence("pt-BR", minutes=7) == irt.CONDITION_CADENCE[
        settings.default_language
    ].format(minutes=7)
