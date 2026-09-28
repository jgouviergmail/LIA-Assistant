"""Every provider client speaks its own code for a language (ADR-323).

An absent language now reaches the clients as the DECLARED canonical code, and
three providers spell Chinese differently from the backend's ``zh-CN``: the
Wikipedia edition is ``zh`` (``zh-CN.wikipedia.org`` does not resolve), Brave's
``search_lang`` names the script (``zh-hans``; ``zh-CN`` is a 422, the key
verification included) and OpenWeatherMap writes ``zh_cn``. An explicit code is
the caller's choice of the provider's vocabulary and passes verbatim, except the
canonical codes a provider spells differently; a Wikipedia edition is lower-cased,
and one that is not a single subdomain label is refused (a model writes it, and it
names the host).
"""

from __future__ import annotations

import pytest

from src.core.config import settings
from src.core.i18n import language_scope
from src.domains.connectors.clients.brave_search_client import BraveSearchClient, _search_lang
from src.domains.connectors.clients.openweathermap_client import _owm_lang
from src.domains.connectors.clients.wikipedia_client import WikipediaClient, wikipedia_edition

pytestmark = pytest.mark.unit

#: A language that is not the instance default: declaring the default would
#: pass by falling back, and prove nothing about the declaration.
_NOT_DEFAULT = next(code for code in ("de", "it") if code != settings.default_language)


class TestWikipediaEdition:
    @pytest.mark.parametrize(
        ("language", "edition"),
        [
            ("zh-CN", "zh"),
            ("zh-cn", "zh"),
            ("fr", "fr"),
            ("EN", "en"),
            ("zh-yue", "zh-yue"),
            ("zh-min-nan", "zh-min-nan"),
            ("simple", "simple"),
        ],
    )
    def test_a_given_code_names_its_edition(self, language: str, edition: str) -> None:
        assert wikipedia_edition(language) == edition

    @pytest.mark.parametrize(
        "written", ["attacker.example#", "evil.com/", "user@host", "fr.evil", "a b", "x", ""]
    )
    def test_a_code_that_is_not_one_label_never_names_the_host(self, written: str) -> None:
        """A model writes the edition, and it is interpolated into the host (ADR-323)."""
        with language_scope(_NOT_DEFAULT):
            client = WikipediaClient(language=written or None)

        assert client.api_base_url == f"https://{_NOT_DEFAULT}.wikipedia.org/w/api.php"

    @pytest.mark.parametrize(
        ("declared", "edition"), [("zh-CN", "zh"), (_NOT_DEFAULT, _NOT_DEFAULT)]
    )
    def test_an_absent_code_reads_the_declared_language_s_edition(
        self, declared: str, edition: str
    ) -> None:
        with language_scope(declared):
            assert wikipedia_edition(None) == edition
            client = WikipediaClient()

        assert client.api_base_url == f"https://{edition}.wikipedia.org/w/api.php"


class TestBraveSearchLang:
    @pytest.mark.parametrize(
        ("language", "search_lang"), [("zh-CN", "zh-hans"), ("fr", "fr"), ("zh-hant", "zh-hant")]
    )
    def test_a_given_code_names_brave_s_search_lang(self, language: str, search_lang: str) -> None:
        assert _search_lang(language) == search_lang

    def test_a_client_built_with_no_language_searches_in_the_declared_one(self) -> None:
        with language_scope("zh-CN"):
            client = BraveSearchClient(api_key="k")

        assert client.language == "zh-hans"


class TestOpenWeatherMapLang:
    @pytest.mark.parametrize(
        ("lang", "owm"), [("zh-CN", "zh_cn"), ("it", "it"), ("zh_tw", "zh_tw")]
    )
    def test_a_given_code_names_owm_s_lang(self, lang: str, owm: str) -> None:
        assert _owm_lang(lang) == owm

    def test_an_absent_lang_is_the_declared_language_in_owm_s_spelling(self) -> None:
        with language_scope("zh"):
            assert _owm_lang(None) == "zh_cn"
