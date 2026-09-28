"""The resolver's hints name words the resolver accepts, in the reader's language (ADR-323).

``ReferenceResolver`` answered « '…' non trouvé dans la liste. Utilisez un numéro
(1-N), un nom, ou 'premier'/'dernier' » to every reader, whatever their
language, although its keywords were already multilingual (``KEYWORD_MAPS``).
The hint now names the keywords of the language it is written in — and a hint
naming a word the resolver refuses would send the person round in circles, so
each named word is checked against the resolver's own table.
"""

from __future__ import annotations

import pytest

from src.core.i18n_api_messages import APIMessages
from src.core.i18n_patterns import KEYWORD_MAPS
from src.core.i18n_types import Language

pytestmark = pytest.mark.unit

#: The first/last keywords each language's hint names.
NAMED_KEYWORDS: dict[Language, tuple[str, str]] = {
    "fr": ("premier", "dernier"),
    "en": ("first", "last"),
    "es": ("primero", "último"),
    "de": ("erster", "letzter"),
    "it": ("primo", "ultimo"),
    "zh-CN": ("第一", "最后"),
}


@pytest.mark.parametrize("language", sorted(NAMED_KEYWORDS))
def test_not_in_list_names_keywords_the_resolver_accepts(language: Language) -> None:
    first, last = NAMED_KEYWORDS[language]
    message = APIMessages.reference_not_in_list("Zoé", 4, language)
    assert "Zoé" in message and "1-4" in message
    assert first in message and last in message
    assert KEYWORD_MAPS[language][first] == 1
    assert KEYWORD_MAPS[language][last] == -1


def test_every_language_has_a_hint() -> None:
    assert set(NAMED_KEYWORDS) == set(KEYWORD_MAPS)


@pytest.mark.parametrize(
    ("language", "listed", "quoted"),
    [
        ("fr", "Jean Dupond, Jean Martin", "«\u00a0Jean\u00a0»"),
        ("de", "Jean Dupond, Jean Martin", "„Jean“"),
        ("es", "Jean Dupond, Jean Martin", "«Jean»"),
        ("zh-CN", "Jean Dupond、Jean Martin", "“Jean”"),
    ],
)
def test_ambiguous_lists_the_candidates_in_the_languages_enumeration(
    language: str, listed: str, quoted: str
) -> None:
    """Each language enumerates and quotes with its own marks (Chinese: 、 and “”)."""
    message = APIMessages.reference_ambiguous("Jean", ["Jean Dupond", "Jean Martin"], language)
    assert message.endswith(listed)
    assert quoted in message
