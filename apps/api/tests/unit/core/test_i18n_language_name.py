"""``get_language_name`` names a language for a model, from ANY spelling of its code.

Prompt audit 2026-09-12 (lot 3): ten assemblers handed the model a raw code
(``fr``, ``zh-CN`` — or a frontend ``zh``) where the others named the language, and
the naming helper did not normalise: ``get_language_name("zh")`` returned ``"zh"``.
One chokepoint now: normalise, then name.
"""

from __future__ import annotations

import pytest

from src.core.i18n import DEFAULT_LANGUAGE, get_language_name
from src.core.i18n_types import LANGUAGE_NAMES


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("fr", "French"),
        ("en", "English"),
        ("zh-CN", "Simplified Chinese"),
        ("zh", "Simplified Chinese"),
        ("zh_CN", "Simplified Chinese"),
        ("fr-FR", "French"),
        ("EN_us", "English"),
    ],
)
def test_names_every_spelling(code: str, expected: str) -> None:
    assert get_language_name(code) == expected


def test_unsupported_code_names_the_configured_default() -> None:
    """A code the platform does not speak falls back like every other consumer."""
    assert get_language_name("xx") == LANGUAGE_NAMES[DEFAULT_LANGUAGE]


def test_every_supported_language_has_a_name() -> None:
    for code in ("fr", "en", "es", "de", "it", "zh-CN"):
        assert get_language_name(code) == LANGUAGE_NAMES[code]


def test_the_types_module_no_longer_names_languages() -> None:
    """The raw lookup left ``i18n_types`` so no caller can bypass normalisation."""
    import src.core.i18n_types as types_module

    assert not hasattr(types_module, "get_language_name")
