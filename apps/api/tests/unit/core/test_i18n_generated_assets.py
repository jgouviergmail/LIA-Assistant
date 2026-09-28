"""Parity + accessor tests for the generated-files gallery i18n (ADR-319).

The refusal a person reads when keeping one more file would pass the account's
ceilings: it must exist in the six languages, keyed by the backend-canonical
code (``zh-CN``), and carry BOTH ceilings — a sentence that states one cap and
hides the other sends the person looking for a limit they cannot see.
"""

from __future__ import annotations

from typing import get_args

import pytest

from src.core import i18n_generated_assets as iga
from src.core.config import settings
from src.core.i18n_types import Language

pytestmark = pytest.mark.unit


def test_the_refusal_exists_in_every_canonical_language() -> None:
    # The lookup indexes the table directly: a language missing here would be
    # a KeyError on the refusal path, so the keys ARE the canonical codes.
    assert set(iga.KEEP_LIMIT_REACHED) == set(get_args(Language))


def test_every_translation_carries_both_ceilings() -> None:
    for lang, template in iga.KEEP_LIMIT_REACHED.items():
        assert "{max_files}" in template, lang
        assert "{max_mb}" in template, lang


def test_the_accessor_fills_the_ceilings_and_normalises_the_locale() -> None:
    sentence = iga.keep_limit_reached("zh", max_files=100, max_mb=500)
    assert sentence == iga.KEEP_LIMIT_REACHED["zh-CN"].format(max_files=100, max_mb=500)
    assert "100" in iga.keep_limit_reached("fr-FR", max_files=100, max_mb=500)


def test_an_unsupported_locale_reads_the_instance_default_language() -> None:
    assert iga.keep_limit_reached("pt-BR", max_files=1, max_mb=2) == iga.KEEP_LIMIT_REACHED[
        settings.default_language
    ].format(max_files=1, max_mb=2)
