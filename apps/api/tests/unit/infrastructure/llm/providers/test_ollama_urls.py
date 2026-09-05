"""One reading of the Ollama server URL, for every reader.

Measured in production (2026-09-05): the admin had stored ``http://<host>:11434``
while the documentation and the admin placeholder said ``.../v1``, and the two
readers of that one setting tolerated different shapes. Since ADR-267 both the
chat adapter (native client) and the discovery talk to the server ROOT; the
``/v1`` suffix operators typed for the former OpenAI-compatible shim is tolerated
and stripped here, once, and the derivation is idempotent.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.core.constants import OLLAMA_BASE_URL_ENV
from src.infrastructure.llm.providers.ollama_urls import ollama_native_root, resolve_ollama_url

pytestmark = pytest.mark.unit

_ROOT = "http://ollama.local:11434"

#: Every shape an operator has typed or could type, and the root it means.
_SHAPES: list[tuple[str, str]] = [
    (_ROOT, _ROOT),
    (_ROOT + "/", _ROOT),
    (_ROOT + "//", _ROOT),
    (_ROOT + "/v1", _ROOT),
    (_ROOT + "/v1/", _ROOT),
    ("  " + _ROOT + "/v1  ", _ROOT),
    ("https://gateway.example.com/ollama", "https://gateway.example.com/ollama"),
    ("https://gateway.example.com/ollama/v1", "https://gateway.example.com/ollama"),
    ("HTTP://H:11434/v1", "HTTP://H:11434"),
]


class TestNativeRoot:
    @pytest.mark.parametrize(("raw", "root"), _SHAPES)
    def test_every_shape_resolves_to_the_same_root(self, raw: str, root: str) -> None:
        assert ollama_native_root(raw) == root

    def test_idempotent(self) -> None:
        for raw, _ in _SHAPES:
            once = ollama_native_root(raw)
            assert ollama_native_root(once) == once

    def test_a_path_that_merely_contains_v1_is_not_a_suffix(self) -> None:
        """Only a trailing ``/v1`` segment is the former OpenAI-compat suffix."""
        assert ollama_native_root("http://h:11434/v1beta") == "http://h:11434/v1beta"
        assert ollama_native_root("http://h:11434/api/v1") == "http://h:11434/api"

    @pytest.mark.parametrize("placeholder", ["NOT_CONFIGURED", "", "   ", "CHANGE_ME"])
    def test_a_value_that_is_not_a_url_passes_through_unchanged(self, placeholder: str) -> None:
        """The credential placeholder must stay recognisable in the failure it causes.

        ``_require_api_key`` returns ``NOT_CONFIGURED`` when nothing is set so
        the app can boot; rewriting it would bury the one word an operator can
        search for.
        """
        assert ollama_native_root(placeholder) == placeholder


class TestResolveOllamaUrl:
    """DB first, then the environment -- the same order as every provider key."""

    def test_database_value_wins(self) -> None:
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
                return_value="http://from-db:11434",
            ),
            patch.dict(os.environ, {OLLAMA_BASE_URL_ENV: "http://from-env:11434/v1"}),
        ):
            assert resolve_ollama_url() == "http://from-db:11434"

    def test_environment_is_the_fallback(self) -> None:
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
                return_value=None,
            ),
            patch.dict(os.environ, {OLLAMA_BASE_URL_ENV: "http://from-env:11434/v1"}),
        ):
            assert resolve_ollama_url() == "http://from-env:11434/v1"

    def test_none_when_nothing_is_configured(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != OLLAMA_BASE_URL_ENV}
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
                return_value=None,
            ),
            patch.dict(os.environ, env, clear=True),
        ):
            assert resolve_ollama_url() is None

    def test_blank_values_count_as_unset(self) -> None:
        """An empty env var is not an address (`reference_empty_env_var_is_not_absent`)."""
        with (
            patch(
                "src.domains.llm_config.cache.LLMConfigOverrideCache.get_api_key",
                return_value="",
            ),
            patch.dict(os.environ, {OLLAMA_BASE_URL_ENV: "   "}),
        ):
            assert resolve_ollama_url() is None

    def test_the_adapter_and_the_discovery_read_the_same_variable(self) -> None:
        from src.infrastructure.llm.providers.adapter import _ENV_FALLBACK

        assert _ENV_FALLBACK["ollama"] == OLLAMA_BASE_URL_ENV
