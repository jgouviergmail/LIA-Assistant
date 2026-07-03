"""Unit tests for connector error i18n (base connector tools).

Regression coverage for the 2026-07 codebase audit (backlog): the
connector-not-activated and category-not-activated error messages were inline
French in ``tools/base.py`` — a CLAUDE.md violation ("never inline French,
including LLM scaffolding"). These strings are LLM-facing (the response node
reformulates them), so a non-French user's model context must not receive
French. They now route through the central ``APIMessages`` mechanism, keyed by
the user's language read from the runtime config (concurrency-safe: language is
a parameter, never stored on the singleton tool's ``self``).
"""

from types import SimpleNamespace

import pytest

from src.core.i18n_api_messages import APIMessages
from src.domains.agents.tools.base import _extract_runtime_language

ALL_LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


# ============================================================================
# APIMessages i18n content
# ============================================================================


@pytest.mark.unit
def test_connector_not_activated_is_localized():
    """The message differs by language and always names the connector."""
    fr = APIMessages.connector_not_activated("Perplexity AI", "fr")
    en = APIMessages.connector_not_activated("Perplexity AI", "en")

    assert "Perplexity AI" in fr and "Perplexity AI" in en
    assert fr != en
    assert "activé" in fr
    assert "enable" in en.lower()


@pytest.mark.unit
@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_connector_not_activated_all_six_languages(language):
    """Every supported language yields a non-empty, name-carrying message."""
    msg = APIMessages.connector_not_activated("ServiceX", language, needs_api_key=True)
    assert msg
    assert "ServiceX" in msg


@pytest.mark.unit
def test_connector_not_activated_api_key_variant_mentions_key():
    """The API-key variant tells the user to provide their API key."""
    en = APIMessages.connector_not_activated("ServiceX", "en", needs_api_key=True)
    assert "api key" in en.lower()


@pytest.mark.unit
def test_category_not_activated_is_localized():
    """Category message differs by language and carries the category label."""
    fr = APIMessages.category_not_activated("Email", "fr")
    en = APIMessages.category_not_activated("Email", "en")

    assert "Email" in fr and "Email" in en
    assert fr != en


@pytest.mark.unit
@pytest.mark.parametrize("language", ALL_LANGUAGES)
def test_category_not_activated_all_six_languages(language):
    """Every supported language yields a non-empty, label-carrying message."""
    msg = APIMessages.category_not_activated("Calendar", language)
    assert msg
    assert "Calendar" in msg


# ============================================================================
# Language extraction from runtime config (concurrency-safe, sync, no DB)
# ============================================================================


def _runtime(user_language=None):
    configurable = {"user_id": "u", "thread_id": "t"}
    if user_language is not None:
        configurable["user_language"] = user_language
    return SimpleNamespace(config={"configurable": configurable})


@pytest.mark.unit
def test_extract_runtime_language_reads_configurable():
    assert _extract_runtime_language(_runtime("en")) == "en"


@pytest.mark.unit
def test_extract_runtime_language_normalizes_zh_to_zh_cn():
    # User.language is "zh"; APIMessages dicts key on "zh-CN"
    assert _extract_runtime_language(_runtime("zh")) == "zh-CN"


@pytest.mark.unit
def test_extract_runtime_language_defaults_when_missing():
    result = _extract_runtime_language(_runtime(None))
    assert result in ALL_LANGUAGES


@pytest.mark.unit
def test_extract_runtime_language_survives_missing_config():
    # Defensive: never raise on a malformed runtime
    assert _extract_runtime_language(SimpleNamespace(config=None)) in ALL_LANGUAGES
